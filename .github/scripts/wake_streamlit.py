import os
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

URL = os.environ.get("STREAMLIT_URL", "").strip()
if not URL:
    print("ERROR: STREAMLIT_URL variable is not set.")
    print("Go to: Settings → Secrets and variables → Actions → Variables → New repository variable")
    print("Name: STREAMLIT_URL   Value: https://yourname-appname.streamlit.app")
    sys.exit(1)

WAKE_BUTTON_TEXT  = "Yes, get this app back up!"
PAGE_LOAD_TIMEOUT = 60_000
BUTTON_WAIT       = 10_000

def main():
    print(f"Visiting: {URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(URL, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            print("Page load timed out — app may be starting. Treating as awake.")
            browser.close()
            return

        try:
            wake_btn = page.get_by_text(WAKE_BUTTON_TEXT, exact=False)
            wake_btn.wait_for(timeout=BUTTON_WAIT)
            print("App is sleeping — clicking wake button...")
            wake_btn.click()
            try:
                wake_btn.wait_for(state="hidden", timeout=30_000)
                print("Wake button dismissed — app is starting up.")
            except PlaywrightTimeout:
                print("Button did not disappear within 30 s — may still be waking.")
        except PlaywrightTimeout:
            print("App is already awake. No action needed.")

        page.wait_for_timeout(5_000)
        print("Done.")
        browser.close()

if __name__ == "__main__":
    main()
