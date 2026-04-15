import os
import time
from playwright.sync_api import sync_playwright

path = os.getenv("CHROME_USER_DATA")
if not path:
    raise ValueError("CHROME_USER_DATA environment variable not set")

with sync_playwright() as p:
    try:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=path,
            channel="chrome",
            headless=False,
            args=["--profile-directory=Profile 9"]
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://google.com", timeout=15_000)
        print("SUCCESS! Page title:", page.title())
        time.sleep(3)
        browser.close()
    except Exception as e:
        print("FAILED:", e)
