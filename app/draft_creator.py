"""
Playwright-based Vinted draft creator.

Loads session cookies from vinted_cookies.json, fills the /items/new form
deterministically from a listing dict, then saves as draft.

Usage:
    from app.draft_creator import create_draft
    url = create_draft(listing, item_folder)
"""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

from app.config import ROOT

COOKIES_FILE = ROOT / "vinted_cookies.json"
VINTED_URL = "https://www.vinted.co.uk"

# Listing category string -> Vinted navigation path (list of [role="button"] labels to click)
CATEGORY_NAV: dict[str, list[str]] = {
    "Men > Suits > Blazers":           ["Men", "Clothing", "Suits & blazers", "Suit jackets & blazers"],
    "Men > Coats & Jackets":           ["Men", "Clothing", "Outerwear"],
    "Men > Jackets":                   ["Men", "Clothing", "Outerwear"],
    "Men > Knitwear":                  ["Men", "Clothing", "Jumpers & sweaters"],
    "Men > Sweatshirts & Hoodies":     ["Men", "Clothing", "Tops & t-shirts"],
    "Men > Shirts":                    ["Men", "Clothing", "Tops & t-shirts"],
    "Men > T-shirts":                  ["Men", "Clothing", "Tops & t-shirts"],
    "Men > Shoes > Boots":             ["Men", "Shoes", "Boots"],
    "Men > Shoes > Casual shoes":      ["Men", "Shoes", "Trainers & sneakers"],
    "Men > Trousers":                  ["Men", "Clothing", "Trousers"],
    "Men > Jeans":                     ["Men", "Clothing", "Jeans"],
    "Women > Suits > Blazers":         ["Women", "Clothing", "Suits & blazers"],
    "Women > Coats & Jackets":         ["Women", "Clothing", "Coats & jackets"],
    "Women > Jackets":                 ["Women", "Clothing", "Jackets & coats"],
    "Women > Knitwear":                ["Women", "Clothing", "Knitwear"],
    "Women > Sweatshirts & Hoodies":   ["Women", "Clothing", "Sweatshirts & hoodies"],
    "Women > Tops":                    ["Women", "Clothing", "Tops"],
    "Women > Dresses":                 ["Women", "Clothing", "Dresses"],
    "Women > Shoes > Boots":           ["Women", "Shoes", "Boots"],
    "Women > Shoes > Flat shoes":      ["Women", "Shoes", "Flat shoes"],
    "Women > Trousers & Leggings":     ["Women", "Clothing", "Trousers & leggings"],
    "Women > Jeans":                   ["Women", "Clothing", "Jeans"],
    "Women > Skirts":                  ["Women", "Clothing", "Skirts"],
}

# Keyword -> Vinted colour label (longest-first matching)
COLOUR_MAP: dict[str, str] = {
    "light blue": "Light blue",
    "dark green": "Dark green",
    "charcoal": "Grey",
    "black": "Black",
    "white": "White",
    "grey": "Grey",
    "gray": "Grey",
    "brown": "Brown",
    "tan": "Brown",
    "beige": "Beige",
    "cream": "Cream",
    "navy": "Navy",
    "blue": "Blue",
    "green": "Green",
    "olive": "Khaki",
    "khaki": "Khaki",
    "red": "Red",
    "burgundy": "Burgundy",
    "wine": "Burgundy",
    "pink": "Pink",
    "rose": "Rose",
    "purple": "Purple",
    "lilac": "Lilac",
    "orange": "Orange",
    "yellow": "Yellow",
    "gold": "Gold",
    "silver": "Silver",
    "turquoise": "Turquoise",
    "multi": "Multi",
    "mustard": "Mustard",
    "mint": "Mint",
    "coral": "Coral",
    "apricot": "Apricot",
}


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def _load_cookies() -> list[dict]:
    if not COOKIES_FILE.exists():
        raise FileNotFoundError(
            f"Cookies file not found: {COOKIES_FILE}\n"
            "Export your Vinted session cookies using the Cookie-Editor browser extension "
            "and save the JSON to vinted_cookies.json in the project root."
        )
    raw = json.loads(COOKIES_FILE.read_text())
    sam_map = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "unspecified": "None"}
    result = []
    for c in raw:
        pw = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": sam_map.get(c.get("sameSite", "lax"), "Lax"),
        }
        if "expirationDate" in c:
            pw["expires"] = int(c["expirationDate"])
        result.append(pw)
    return result


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

def _dismiss_cookie_banner(page: Page) -> None:
    page.evaluate("""() => {
        ['#onetrust-consent-sdk', '.onetrust-pc-dark-filter', '#onetrust-pc-sdk'].forEach(sel => {
            const el = document.querySelector(sel);
            if (el) el.remove();
        });
        document.body.style.overflow = 'auto';
    }""")
    page.wait_for_timeout(200)


def _js_click(page: Page, testid: str) -> None:
    page.evaluate(f'document.querySelector(\'[data-testid="{testid}"]\').click()')
    page.wait_for_timeout(600)


def _dropdown_click_option(page: Page, content_testid: str, option_text: str) -> bool:
    """Click a [role=button] element by exact text within a dropdown container."""
    found = page.evaluate(f"""() => {{
        const content = document.querySelector('[data-testid="{content_testid}"]');
        if (!content) return false;
        for (const el of content.querySelectorAll('[role="button"]')) {{
            if (el.innerText.trim() === {json.dumps(option_text)}) {{
                el.click();
                return true;
            }}
        }}
        return false;
    }}""")
    page.wait_for_timeout(500)
    return bool(found)


def _close_dropdown(page: Page) -> None:
    """Click the title field to close any open dropdown."""
    page.evaluate('document.querySelector(\'[data-testid="title--input"]\').click()')
    page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Field fillers
# ---------------------------------------------------------------------------

def _upload_photos(page: Page, folder: Path) -> None:
    patterns = ["*.jpg", "*.jpeg", "*.png", "*.webp"]
    photos: list[Path] = []
    for pat in patterns:
        photos.extend(folder.glob(pat))
    # Sort by leading number in filename (01_front.jpg, 02_tag.jpg …), then alpha
    def _sort_key(p: Path) -> tuple:
        m = re.match(r"^(\d+)", p.stem)
        return (int(m.group(1)) if m else 9999, p.name.lower())
    photos = sorted(set(photos), key=_sort_key)
    if not photos:
        raise FileNotFoundError(f"No photos found in {folder}")
    page.set_input_files('input[data-testid="add-photos-input"]', [str(p) for p in photos])
    page.wait_for_timeout(2000)
    print(f"  Photos uploaded: {[p.name for p in photos]}")


def _select_category(page: Page, category: str) -> None:
    nav_path = CATEGORY_NAV.get(category)
    if not nav_path:
        print(f"  Warning: no category mapping for '{category}', skipping")
        return
    _js_click(page, "catalog-select-dropdown-input")
    for step in nav_path:
        if not _dropdown_click_option(page, "catalog-select-dropdown-content", step):
            print(f"  Warning: category step '{step}' not found")
            return
    print(f"  Category: {category}")


def _select_brand(page: Page, brand: str | None) -> None:
    if not brand:
        return
    _js_click(page, "brand-select-dropdown-input")
    try:
        page.locator('[data-testid="brand-search--input"]').fill(brand, timeout=5000)
    except Exception:
        _close_dropdown(page)
        print(f"  Warning: brand search input not found, skipping brand")
        return
    page.wait_for_timeout(1000)
    if not _dropdown_click_option(page, "brand-select-dropdown-content", brand):
        # Fallback: "Use X as brand"
        _dropdown_click_option(page, "brand-select-dropdown-content", f'Use "{brand}" as brand')
    print(f"  Brand: {brand}")


def _select_size(page: Page, tagged_size: str | None) -> None:
    if not tagged_size:
        return
    _js_click(page, "size-select-dropdown-input")
    options: list[str] = page.evaluate("""() => {
        const content = document.querySelector('[data-testid="size-select-dropdown-content"]');
        if (!content) return [];
        return Array.from(content.querySelectorAll('[role="button"]')).map(el => el.innerText.trim());
    }""")
    size = tagged_size.strip()
    # Try exact, then common suffixes
    for candidate in [size, size + "R", size + "S", size + "L"]:
        if candidate in options:
            _dropdown_click_option(page, "size-select-dropdown-content", candidate)
            print(f"  Size: {candidate} (tagged: {tagged_size})")
            return
    _close_dropdown(page)
    print(f"  Warning: size '{tagged_size}' not found in options, skipping")


_CONDITION_ID: dict[str, int] = {
    "New with tags": 6,
    "New without tags": 1,
    "Very good": 2,
    "Good": 3,
    "Satisfactory": 4,
}


def _select_condition(page: Page, condition_summary: str | None) -> None:
    if not condition_summary:
        return
    lower = condition_summary.lower()
    if "new with tag" in lower or ("brand new" in lower and "tag" in lower):
        vinted = "New with tags"
    elif "new without" in lower:
        vinted = "New without tags"
    elif "very good" in lower or "excellent" in lower or "barely worn" in lower or "hardly worn" in lower:
        vinted = "Very good"
    elif "satisfactory" in lower or "fair" in lower or "worn" in lower:
        vinted = "Satisfactory"
    else:
        vinted = "Very good"
    condition_id = _CONDITION_ID[vinted]
    _js_click(page, "category-condition-single-list-input")
    page.evaluate(f'document.querySelector(\'[data-testid="condition-radio-{condition_id}--input"]\').click()')
    page.wait_for_timeout(400)
    print(f"  Condition: {vinted}")


def _select_colour(page: Page, colour: str | None) -> None:
    if not colour:
        return
    lower = colour.lower()
    vinted_colour = None
    for keyword in sorted(COLOUR_MAP, key=len, reverse=True):
        if keyword in lower:
            vinted_colour = COLOUR_MAP[keyword]
            break
    if not vinted_colour:
        print(f"  Warning: no colour mapping for '{colour}', skipping")
        return
    _js_click(page, "color-select-dropdown-input")
    _dropdown_click_option(page, "color-select-dropdown-content", vinted_colour)
    print(f"  Colour: {vinted_colour} (from '{colour}')")


def _select_material(page: Page, materials: list[str] | None) -> None:
    if not materials:
        return
    # Extract base names: "80% wool" -> "wool", "cashmere blend" -> "cashmere"
    names = []
    for m in materials:
        name = re.sub(r"^\d+%\s*", "", m).strip().lower()
        name = name.split()[0] if name else ""
        if name:
            names.append(name)
    if not names:
        return

    _js_click(page, "category-material-multi-list-input")
    options: list[str] = page.evaluate("""() => {
        const content = document.querySelector('[data-testid="category-material-multi-list-content"]');
        if (!content) return [];
        return Array.from(content.querySelectorAll('[role="button"]')).map(el => el.innerText.trim());
    }""")
    options_lower = [o.lower() for o in options]

    for name in names:
        for i, opt_lower in enumerate(options_lower):
            if name in opt_lower:
                page.evaluate(f"""() => {{
                    const content = document.querySelector('[data-testid="category-material-multi-list-content"]');
                    const els = content.querySelectorAll('[role="button"]');
                    if (els[{i}]) els[{i}].click();
                }}""")
                page.wait_for_timeout(300)
                print(f"  Material: {options[i]}")
                break

    _close_dropdown(page)


def _select_package_size(page: Page, item_type: str | None) -> None:
    """1=Small envelope, 2=Medium shoebox (default), 3=Large moving box."""
    bulky_keywords = {"coat", "jacket", "blazer", "suit", "wax", "trench", "parka"}
    lower = (item_type or "").lower()
    pkg = 2 if any(k in lower for k in bulky_keywords) else 1
    page.evaluate(f'document.querySelector(\'[data-testid="package_type_selector_{pkg}--input"]\').click()')
    page.wait_for_timeout(200)
    print(f"  Package size: {'Medium' if pkg == 2 else 'Small'}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def create_draft(listing: dict, item_folder: Path | str) -> str | None:
    """
    Fill Vinted sell form from a validated listing dict and save as draft.

    Args:
        listing: validated listing JSON (output of listing_writer.write)
        item_folder: path to the item folder containing photos

    Returns:
        URL of the saved draft, or None if save failed.
    """
    folder = Path(item_folder)
    cookies = _load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        context.add_cookies(cookies)
        page = context.new_page()

        print("Opening Vinted sell page...")
        page.goto(f"{VINTED_URL}/items/new", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Check we're actually on the sell page (cookies may have expired)
        if "/items/new" not in page.url:
            browser.close()
            raise RuntimeError(
                f"Redirected to {page.url} — session cookies may have expired. "
                "Re-export cookies from your browser using Cookie-Editor."
            )

        _dismiss_cookie_banner(page)

        print("Filling form...")
        _upload_photos(page, folder)
        _select_category(page, listing.get("category", ""))

        # These fields only appear after category is selected
        page.wait_for_timeout(500)

        page.locator('[data-testid="title--input"]').fill(listing.get("title", ""))
        page.locator('[data-testid="description--input"]').fill(listing.get("description", ""))
        _select_brand(page, listing.get("brand"))
        # Prefer normalized_size (UK) over raw tagged_size (may be EU for tailoring)
        _select_size(page, listing.get("normalized_size") or listing.get("tagged_size"))
        _select_condition(page, listing.get("condition_summary"))
        _select_colour(page, listing.get("colour"))
        _select_material(page, listing.get("materials"))
        page.locator('[data-testid="price-input--input"]').fill(str(listing.get("price_gbp", "")))
        _select_package_size(page, listing.get("item_type"))

        page.wait_for_timeout(500)

        print("Saving draft...")
        _dismiss_cookie_banner(page)  # re-dismiss in case it reappeared
        # Scroll to button and use a proper Playwright click
        save_btn = page.locator('[data-testid="upload-form-save-draft-button"]')
        save_btn.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        save_btn.click()

        try:
            # Vinted redirects to member profile or item page after saving draft
            page.wait_for_function(
                "() => !window.location.pathname.includes('/items/new')",
                timeout=20000,
            )
            draft_url = page.url
        except Exception:
            draft_url = page.url

        if "/items/new" in draft_url:
            print(f"  Warning: still on /items/new — draft may not have saved")
        else:
            print(f"  Draft saved (redirected to): {draft_url}")

        browser.close()
        return draft_url
