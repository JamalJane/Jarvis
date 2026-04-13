import time
from playwright.sync_api import sync_playwright

path = r"C:\Users\bashe\AppData\Local\Google\Chrome\User Data"

with sync_playwright() as p:
    try:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=path,
            channel="chrome",
            headless=False,
            args=["--profile-directory=Profile 9"]
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://google.com")
        print("SUCCESS! Page title:", page.title())
        time.sleep(3)
        browser.close()
    except Exception as e:
        print("FAILED:", e)
