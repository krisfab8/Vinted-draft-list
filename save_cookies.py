"""
Run this once to save your Vinted login session.
A browser window will open — log in, then come back to this terminal and press Enter.
"""
import json
from playwright.sync_api import sync_playwright

_STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
window.chrome = {runtime: {}};
"""

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    context.add_init_script(_STEALTH)
    page = context.new_page()
    page.goto('https://www.vinted.co.uk')

    print("\n" + "="*50)
    print("A browser window has opened.")
    print("1. Log into Vinted in that window")
    print("2. Once you're logged in and can see your account, come back here")
    print("3. Press Enter to save your session")
    print("="*50 + "\n")
    input("Press Enter when logged in > ")

    cookies = context.cookies()
    with open('vinted_cookies.json', 'w') as f:
        json.dump(cookies, f, indent=2)

    print(f"Saved {len(cookies)} cookies to vinted_cookies.json")
    browser.close()
