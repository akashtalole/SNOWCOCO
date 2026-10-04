import sys, time
from playwright.sync_api import sync_playwright

port, track, steps = sys.argv[1], sys.argv[2], sys.argv[3:]
out = "/home/user/cococlihack/docs/screenshots/streamlit"

def settle(pg):
    time.sleep(1)
    pg.wait_for_function("!document.querySelector('[data-testid=stSpinner]') && !document.querySelector('[data-testid=stStatusWidget]')", timeout=90000)
    time.sleep(4)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1440, "height": 1300})
    pg.goto(f"http://localhost:{port}")
    pg.wait_for_selector("h1", timeout=60000)
    time.sleep(4)
    for s in steps:
        name, tab, *acts = s.split("|")
        pg.get_by_role("tab", name=tab).click()
        time.sleep(1)
        for a in acts:
            kind, _, arg = a.partition(":")
            if kind == "ask":
                box = pg.locator("[data-testid=stTextInput] input:visible").first
                box.fill(arg); box.press("Enter")
            elif kind == "select":
                pg.locator("[role=combobox]:visible").first.click()
                pg.keyboard.type(arg)
                time.sleep(1)
                pg.keyboard.press("Enter")
            elif kind == "button":
                pg.get_by_role("button", name=arg).first.click()
            elif kind == "expand":
                pg.locator("details summary:visible").first.click()
            settle(pg)
        settle(pg)
        pg.screenshot(path=f"{out}/{track}_{name}.png", full_page=True)
        print("saved", f"{track}_{name}.png")
    b.close()
