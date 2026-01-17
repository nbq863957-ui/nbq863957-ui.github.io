import requests
import json
import os
import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


USERNAME = os.environ.get("STU_ID")
PASSWORD = os.environ.get("STU_PWD")
APPID = os.environ.get("WX_APPID")
APPSECRET = os.environ.get("WX_SECRET")
OPENID = os.environ.get("WX_OPENID")
TEMPLATE_ID = os.environ.get("WX_TEMPLATE_ID")
DATA_FILE = "grades.json"


def fetch_grades():
    print("正在尝试登录教务系统...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) # 可以改成 True 让他后台运行
        context = browser.new_context()
        page = context.new_page()
        
        try:
            page.goto("https://sfzt.ycu.edu.cn/auth/#/login?service=https://jwxt.ycu.edu.cn/sso/sxcjlogin")

            # 登录
            page.fill('input[placeholder="请输入学号/职工号"]', USERNAME)
            page.fill('input[placeholder="请输入密码"]', PASSWORD)
            page.click('div.longBtn')

            # 点击“更多”，获取新标签页
            with page.context.expect_page() as new_page_info:
                page.click('#cjgd a')
            new_page = new_page_info.value
            new_page.wait_for_load_state()

            # 等待表格加载
            new_page.wait_for_selector("table#tabGrid tbody tr.jqgrow", timeout=15000)
            
            table_html = new_page.inner_html("table#tabGrid")
            soup = BeautifulSoup(table_html, "html.parser")
            rows = soup.select("tr.jqgrow")

            grades = []
            for row in rows:
                cells = row.find_all("td")
                grade_entry = {}
                for td in cells:
                    col = td.get("aria-describedby", "")
                    if col in ["tabGrid_kcmc", "tabGrid_cj"]:
                        value = td.get("title", td.get_text(strip=True))
                        grade_entry[col] = value
                grades.append(grade_entry)

            browser.close()
            return grades
            
        except Exception as e:
            print(f"爬取失败: {e}")
            browser.close()
            return []

def load_previous():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_current(grades):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(grades, f, ensure_ascii=False, indent=2)

def get_access_token():
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APPID}&secret={APPSECRET}"
    resp = requests.get(url)
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("access_token")
        if token:
            return token
        else:
            print(f"[ERROR] 获取Token失败: {data}")
            return None
    else:
        print("[ERROR] 连接微信服务器失败")
        return None

def send_wechat(grades):
    if not grades:
        return

    # 1. 这里是关键修复：先调用函数获取 token
    access_token = get_access_token()
    if not access_token:
        print("因为无法获取Token，跳过发送")
        return


    content_str = "您有新的成绩更新：\n"

    data = {
        "touser": OPENID,
        "template_id": TEMPLATE_ID,
        "url": "nbq863957-ui.github.io", # 点击卡片跳转的链接，没有可留空
        "data": {
            "content": {
                "title": content_str,
            }
        }
    }

    # 4. 发送请求，这里使用刚才获取到的 access_token 变量
    post_url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
    
    try:
        res = requests.post(post_url, json=data)
        res_json = res.json()
        if res_json.get("errcode") == 0:
            print(f"[SUCCESS] 微信通知发送成功！")
        else:
            print(f"[FAIL] 发送失败: {res_json}")
    except Exception as e:
        print(f"[ERROR] 发送请求异常: {e}")

def main():
    print("开始检查成绩...")
    current_grades = fetch_grades()
    
    if not current_grades:
        print("未获取到成绩记录（可能是登录失败或暂无成绩）。")
        return

    previous_grades = load_previous()
    
    # 简单的比较逻辑：如果列表内容不一样，就视为有新成绩
    # 注意：这比较依赖两次抓取的顺序一致，严格来说应该比对ID
    if current_grades == previous_grades:
        print("成绩没有变化。")
    else:
        print(f"发现成绩更新！当前共 {len(current_grades)} 门课。")
        for g in current_grades:
            print(f"{g.get('tabGrid_kcmc')} : {g.get('tabGrid_cj')}")
        
        save_current(current_grades)
        send_wechat(current_grades)

if __name__ == "__main__":
    main()