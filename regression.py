"""
Opens the Streamlit Cloud app and clicks the wake button if it is asleep.

Requires a GitHub repository VARIABLE (not a secret) named STREAMLIT_URL:
  Settings -> Secrets and variables -> Actions -> Variables -> New
"""
import os
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = os.environ.get("STREAMLIT_URL", "").strip()
if not URL:
    print("ERROR: repository variable STREAMLIT_URL is not set.")
    print("Settings -> Secrets and variables -> Actions -> Variables -> New")
    sys.exit(1)

WAKE_TEXT = "Yes, get this app back up!"


def main():
    print(f"Visiting {URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(URL, timeout=60_000, wait_until="domcontentloaded")
        except PWTimeout:
            print("Page load timed out - app may be starting. Treating as awake.")
            browser.close()
            return

        try:
            btn = page.get_by_text(WAKE_TEXT, exact=False)
            btn.wait_for(timeout=10_000)
            print("App was asleep - clicking wake button.")
            btn.click()
            try:
                btn.wait_for(state="hidden", timeout=30_000)
                print("App is starting up.")
            except PWTimeout:
                print("Still waking after 30 s.")
        except PWTimeout:
            print("App is already awake.")

        page.wait_for_timeout(5_000)
        print("Done.")
        browser.close()


if __name__ == "__main__":
    main()
