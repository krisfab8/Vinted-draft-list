"""
Vinted UI inspector — runs headless=False so you can watch.
Opens the sell form, clicks through category/brand/size/condition/colour/material/package
and saves screenshots + a JSON of every data-testid found at each stage.

Run:
    .venv/bin/python inspect_vinted.py

Output:  inspection/  (created in project root)
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
COOKIES_FILE = ROOT / "vinted_cookies.json"
OUT = ROOT / "inspection"
OUT.mkdir(exist_ok=True)

# One real photo to satisfy the upload requirement
PHOTO = next(ROOT.glob("items/*/front.jpg"), None)

_STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
window.chrome = {runtime: {}};
"""


def _load_cookies():
    raw = json.loads(COOKIES_FILE.read_text())
    sam_map = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "unspecified": "None"}
    pw_valid = {"None", "Lax", "Strict"}
    result = []
    for c in raw:
        rs = c.get("sameSite", "Lax")
        ss = rs if rs in pw_valid else sam_map.get(str(rs).lower(), "Lax")
        pw = {"name": c["name"], "value": c["value"], "domain": c["domain"],
              "path": c.get("path", "/"), "secure": c.get("secure", False),
              "httpOnly": c.get("httpOnly", False), "sameSite": ss}
        if "expirationDate" in c:
            pw["expires"] = int(c["expirationDate"])
        elif "expires" in c and c["expires"] != -1:
            pw["expires"] = int(c["expires"])
        result.append(pw)
    return result


def snap(page, name: str, data: dict):
    """Save screenshot + append to JSON report."""
    png = OUT / f"{name}.png"
    page.screenshot(path=str(png), full_page=False)
    print(f"  📸 {png.name}")
    report_path = OUT / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    report[name] = data
    report_path.write_text(json.dumps(report, indent=2))


def all_testids(page) -> list[str]:
    return page.evaluate("""() =>
        [...document.querySelectorAll('[data-testid]')]
        .map(el => el.dataset.testid)
        .filter((v, i, a) => a.indexOf(v) === i)
    """)


def all_roles_texts(page, role: str) -> list[str]:
    return page.evaluate(f"""() =>
        [...document.querySelectorAll('[role="{role}"]')]
        .filter(el => {{
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }})
        .map(el => el.innerText.trim())
        .filter(Boolean)
    """)


def click_testid(page, testid: str, timeout=8000) -> bool:
    try:
        loc = page.locator(f'[data-testid="{testid}"]').first
        loc.wait_for(state="visible", timeout=timeout)
        loc.scroll_into_view_if_needed()
        loc.click()
        page.wait_for_timeout(800)
        return True
    except Exception as e:
        print(f"    ⚠ click_testid({testid}): {e}")
        return False


def click_button_text(page, text: str, timeout=6000) -> bool:
    pat = f"text={text}"
    try:
        loc = page.get_by_role("button", name=text, exact=True).first
        loc.wait_for(state="visible", timeout=timeout)
        loc.click()
        page.wait_for_timeout(600)
        return True
    except Exception:
        pass
    # Fallback: any role with exact text
    for role in ("radio", "option", "listitem", "menuitem"):
        try:
            loc = page.get_by_role(role, name=text, exact=True).first
            loc.wait_for(state="visible", timeout=1000)
            loc.click()
            page.wait_for_timeout(600)
            return True
        except Exception:
            pass
    return False


def main():
    if not COOKIES_FILE.exists():
        sys.exit("vinted_cookies.json not found — run save_cookies.py first")
    if not PHOTO:
        sys.exit("No photos found in items/ — upload an item first")

    print(f"Using photo: {PHOTO}")
    cookies = _load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        ctx.add_init_script(_STEALTH)
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        # ── 1. Land on sell page ───────────────────────────────────────────
        print("\n[1] Opening /items/new ...")
        page.goto("https://www.vinted.co.uk/items/new", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        if "/items/new" not in page.url:
            snap(page, "00_redirect", {"url": page.url})
            sys.exit(f"Redirected to {page.url} — cookies expired")

        snap(page, "01_initial", {"testids": all_testids(page), "url": page.url})

        # ── 2. Upload photo ────────────────────────────────────────────────
        print("\n[2] Uploading photo ...")
        try:
            page.set_input_files('input[data-testid="add-photos-input"]', [str(PHOTO)])
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"  ⚠ upload failed: {e}")
        snap(page, "02_after_photo", {"testids": all_testids(page)})

        # ── 3. Category picker — open + screenshot each level ─────────────
        print("\n[3] Category picker ...")
        # Find the category input testid
        testids_now = all_testids(page)
        cat_ids = [t for t in testids_now if "catalog" in t.lower() or "category" in t.lower()]
        print(f"  Category-related testids: {cat_ids}")
        snap(page, "03a_before_category", {"category_testids": cat_ids, "all_testids": testids_now})

        # Try to open the category dropdown
        opened = False
        for candidate in ["catalog-select-dropdown-input", "category-select-dropdown-input",
                          "category-select--input", "catalog-input"]:
            if click_testid(page, candidate, timeout=3000):
                print(f"  ✓ Opened category with testid: {candidate}")
                opened = True
                snap(page, "03b_cat_open", {
                    "opened_via": candidate,
                    "buttons": all_roles_texts(page, "button"),
                    "options": all_roles_texts(page, "option"),
                    "testids": all_testids(page),
                })
                break

        if opened:
            # Navigate: Men → Clothing → Trousers  (stop before Joggers to see the sub-list)
            for step in ["Men", "Clothing", "Trousers"]:
                print(f"  Clicking '{step}' ...")
                ok = click_button_text(page, step)
                snap(page, f"03c_cat_{step.lower().replace(' ','_')}", {
                    "clicked": step,
                    "success": ok,
                    "buttons": all_roles_texts(page, "button"),
                    "options": all_roles_texts(page, "option"),
                    "radios": all_roles_texts(page, "radio"),
                    "listitems": all_roles_texts(page, "listitem"),
                    "testids": all_testids(page),
                })
                if not ok:
                    print(f"  ⚠ Could not click '{step}'")
                    break

            # After Trousers: snapshot what's visible (Joggers sub-list?)
            page.wait_for_timeout(1000)
            snap(page, "03d_after_trousers", {
                "buttons": all_roles_texts(page, "button"),
                "options": all_roles_texts(page, "option"),
                "radios": all_roles_texts(page, "radio"),
                "listitems": all_roles_texts(page, "listitem"),
                "testids": all_testids(page),
            })

            # Try clicking Joggers/Joggers & sweatpants
            for joggers_label in ["Joggers & sweatpants", "Joggers"]:
                print(f"  Trying to click '{joggers_label}' ...")
                if click_button_text(page, joggers_label):
                    print(f"  ✓ Clicked '{joggers_label}'")
                    snap(page, "03e_joggers_selected", {
                        "clicked": joggers_label,
                        "testids": all_testids(page),
                    })
                    break
            else:
                print("  ⚠ Could not click Joggers — check 03d screenshot")

        # ── 4. Wait for form fields to appear ─────────────────────────────
        print("\n[4] Waiting for form fields ...")
        page.wait_for_timeout(3000)
        form_testids = all_testids(page)
        snap(page, "04_form_fields", {
            "testids": form_testids,
            "brand_related": [t for t in form_testids if "brand" in t.lower()],
            "size_related": [t for t in form_testids if "size" in t.lower()],
            "condition_related": [t for t in form_testids if "condition" in t.lower()],
            "package_related": [t for t in form_testids if "package" in t.lower() or "parcel" in t.lower() or "postage" in t.lower() or "shipment" in t.lower()],
        })

        # ── 5. Brand picker ───────────────────────────────────────────────
        print("\n[5] Brand picker ...")
        brand_ids = [t for t in form_testids if "brand" in t.lower()]
        print(f"  Brand testids: {brand_ids}")
        for bid in brand_ids:
            if "input" in bid.lower():
                if click_testid(page, bid, timeout=3000):
                    snap(page, "05_brand_open", {
                        "opened_via": bid,
                        "testids": all_testids(page),
                        "buttons": all_roles_texts(page, "button")[:20],
                    })
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    break

        # ── 6. Size picker ────────────────────────────────────────────────
        print("\n[6] Size picker ...")
        size_ids = [t for t in form_testids if "size" in t.lower()]
        print(f"  Size testids: {size_ids}")
        for sid in size_ids:
            if "input" in sid.lower():
                if click_testid(page, sid, timeout=3000):
                    snap(page, "06_size_open", {
                        "opened_via": sid,
                        "testids": all_testids(page),
                        "buttons": all_roles_texts(page, "button")[:30],
                        "options": all_roles_texts(page, "option")[:30],
                    })
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    break

        # ── 7. Condition picker ───────────────────────────────────────────
        print("\n[7] Condition picker ...")
        cond_ids = [t for t in form_testids if "condition" in t.lower()]
        print(f"  Condition testids: {cond_ids}")
        for cid in cond_ids:
            if "input" in cid.lower():
                if click_testid(page, cid, timeout=3000):
                    snap(page, "07_condition_open", {
                        "opened_via": cid,
                        "testids": all_testids(page),
                        "buttons": all_roles_texts(page, "button")[:20],
                        "radios": all_roles_texts(page, "radio"),
                        "condition_testids": [t for t in all_testids(page) if "condition" in t.lower()],
                    })
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    break

        # ── 8. Package / postage picker ───────────────────────────────────
        print("\n[8] Package/postage picker ...")
        pkg_ids = [t for t in form_testids if any(k in t.lower() for k in
                   ["package", "parcel", "postage", "shipment", "delivery"])]
        print(f"  Package testids: {pkg_ids}")
        snap(page, "08_package", {
            "package_testids": pkg_ids,
            "all_testids": form_testids,
        })

        # ── 9. Final full-page screenshot ──────────────────────────────────
        print("\n[9] Final screenshot ...")
        page.wait_for_timeout(500)
        snap(page, "09_full_form", {"testids": all_testids(page)})
        # Full-height version
        page.screenshot(path=str(OUT / "09_full_form_tall.png"), full_page=True)

        print(f"\n✅ Done. Output in: {OUT}/")
        print(f"   Open inspection/report.json to see all testids")
        print(f"   Open inspection/*.png to see screenshots")
        input("\nPress Enter to close the browser...")
        browser.close()


if __name__ == "__main__":
    main()
