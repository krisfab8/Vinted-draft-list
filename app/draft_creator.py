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

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
window.chrome = {runtime: {}};
"""

# Listing category string -> Vinted navigation path (list of [role="button"] labels to click)
# All paths verified against vinted_categories.json scraped 2026-03-14
CATEGORY_NAV: dict[str, list[str]] = {
    # ── Men: Suits & Blazers ──────────────────────────────────────────────
    "Men > Suits > Blazers":                    ["Men", "Clothing", "Suits & blazers", "Suit jackets & blazers"],
    "Men > Suits > Waistcoats":                 ["Men", "Clothing", "Suits & blazers", "Waistcoats"],
    "Men > Suits > Trousers":                   ["Men", "Clothing", "Suits & blazers", "Suit trousers"],
    # ── Men: Outerwear — Coats ────────────────────────────────────────────
    "Men > Coats > Overcoat":                   ["Men", "Clothing", "Outerwear", "Coats", "Overcoats & long coats"],
    "Men > Coats > Trench":                     ["Men", "Clothing", "Outerwear", "Coats", "Trench coats"],
    "Men > Coats > Parka":                      ["Men", "Clothing", "Outerwear", "Coats", "Parkas"],
    "Men > Coats > Peacoat":                    ["Men", "Clothing", "Outerwear", "Coats", "Peacoats"],
    "Men > Coats > Raincoat":                   ["Men", "Clothing", "Outerwear", "Coats", "Raincoats"],
    "Men > Coats > Duffle":                     ["Men", "Clothing", "Outerwear", "Coats", "Duffle coats"],
    "Men > Coats & Jackets":                    ["Men", "Clothing", "Outerwear", "Coats", "Overcoats & long coats"],
    "Men > Coats":                              ["Men", "Clothing", "Outerwear", "Coats", "Overcoats & long coats"],
    # ── Men: Outerwear — Jackets ──────────────────────────────────────────
    "Men > Jackets > Denim":                    ["Men", "Clothing", "Outerwear", "Jackets", "Denim jackets"],
    "Men > Jackets > Bomber":                   ["Men", "Clothing", "Outerwear", "Jackets", "Bomber jackets"],
    "Men > Jackets > Biker":                    ["Men", "Clothing", "Outerwear", "Jackets", "Biker & racer jackets"],
    "Men > Jackets > Field":                    ["Men", "Clothing", "Outerwear", "Jackets", "Field & utility jackets"],
    "Men > Jackets > Fleece":                   ["Men", "Clothing", "Outerwear", "Jackets", "Fleece jackets"],
    "Men > Jackets > Harrington":               ["Men", "Clothing", "Outerwear", "Jackets", "Harrington jackets"],
    "Men > Jackets > Puffer":                   ["Men", "Clothing", "Outerwear", "Jackets", "Puffer jackets"],
    "Men > Jackets > Quilted":                  ["Men", "Clothing", "Outerwear", "Jackets", "Quilted jackets"],
    "Men > Jackets > Shacket":                  ["Men", "Clothing", "Outerwear", "Jackets", "Shackets"],
    "Men > Jackets > Varsity":                  ["Men", "Clothing", "Outerwear", "Jackets", "Varsity jackets"],
    "Men > Jackets > Windbreaker":              ["Men", "Clothing", "Outerwear", "Jackets", "Windbreakers"],
    "Men > Jackets":                            ["Men", "Clothing", "Outerwear", "Jackets", "Field & utility jackets"],
    "Men > Gilets":                             ["Men", "Clothing", "Outerwear", "Gilets & body warmers"],
    # ── Men: Jumpers & Sweaters ───────────────────────────────────────────
    "Men > Knitwear":                           ["Men", "Clothing", "Jumpers & sweaters", "Jumpers"],
    "Men > Knitwear > Crew neck":               ["Men", "Clothing", "Jumpers & sweaters", "Crew neck jumpers"],
    "Men > Knitwear > V-neck":                  ["Men", "Clothing", "Jumpers & sweaters", "V-neck jumpers"],
    "Men > Knitwear > Turtleneck":              ["Men", "Clothing", "Jumpers & sweaters", "Turtleneck jumpers"],
    "Men > Knitwear > Cardigan":                ["Men", "Clothing", "Jumpers & sweaters", "Cardigans"],
    "Men > Sweatshirts & Hoodies":              ["Men", "Clothing", "Jumpers & sweaters", "Hoodies & sweaters"],
    "Men > Sweatshirts & Hoodies > Zip":        ["Men", "Clothing", "Jumpers & sweaters", "Zip-through hoodies & sweaters"],
    # ── Men: Tops ─────────────────────────────────────────────────────────
    "Men > Shirts":                             ["Men", "Clothing", "Tops & t-shirts", "Shirts", "Other shirts"],
    "Men > Shirts > Checked":                   ["Men", "Clothing", "Tops & t-shirts", "Shirts", "Checked shirts"],
    "Men > Shirts > Denim":                     ["Men", "Clothing", "Tops & t-shirts", "Shirts", "Denim shirts"],
    "Men > Shirts > Plain":                     ["Men", "Clothing", "Tops & t-shirts", "Shirts", "Plain shirts"],
    "Men > Shirts > Striped":                   ["Men", "Clothing", "Tops & t-shirts", "Shirts", "Striped shirts"],
    "Men > T-shirts":                           ["Men", "Clothing", "Tops & t-shirts", "T-shirts", "Other t-shirts"],
    "Men > T-shirts > Plain":                   ["Men", "Clothing", "Tops & t-shirts", "T-shirts", "Plain t-shirts"],
    "Men > T-shirts > Long-sleeve":             ["Men", "Clothing", "Tops & t-shirts", "T-shirts", "Long-sleeved t-shirts"],
    "Men > Polo Shirts":                        ["Men", "Clothing", "Tops & t-shirts", "T-shirts", "Polo shirts"],
    # ── Men: Bottoms ──────────────────────────────────────────────────────
    "Men > Trousers > Joggers":                 ["Men", "Clothing", "Trousers", "Joggers"],
    "Men > Trousers > Chinos":                  ["Men", "Clothing", "Trousers", "Chinos"],
    "Men > Trousers > Skinny":                  ["Men", "Clothing", "Trousers", "Skinny trousers"],
    "Men > Trousers > Cropped":                 ["Men", "Clothing", "Trousers", "Cropped trousers"],
    "Men > Trousers > Tailored":                ["Men", "Clothing", "Trousers", "Tailored trousers"],
    "Men > Trousers > Wide-leg":                ["Men", "Clothing", "Trousers", "Wide-legged trousers"],
    "Men > Trousers > Formal":                  ["Men", "Clothing", "Trousers", "Tailored trousers"],
    "Men > Trousers > Cargo":                   ["Men", "Clothing", "Trousers", "Other trousers"],
    "Men > Trousers > Other":                   ["Men", "Clothing", "Trousers", "Other trousers"],
    "Men > Trousers":                           ["Men", "Clothing", "Trousers", "Other trousers"],
    "Men > Shorts":                             ["Men", "Clothing", "Shorts", "Other shorts"],
    "Men > Shorts > Cargo":                     ["Men", "Clothing", "Shorts", "Cargo shorts"],
    "Men > Shorts > Chino":                     ["Men", "Clothing", "Shorts", "Chino shorts"],
    "Men > Shorts > Denim":                     ["Men", "Clothing", "Shorts", "Denim shorts"],
    # Men's jeans — only 4 sub-types on Vinted UK: Ripped, Skinny, Slim fit, Straight fit
    "Men > Jeans > Slim":                       ["Men", "Clothing", "Jeans", "Slim fit jeans"],
    "Men > Jeans > Straight":                   ["Men", "Clothing", "Jeans", "Straight fit jeans"],
    "Men > Jeans > Skinny":                     ["Men", "Clothing", "Jeans", "Skinny jeans"],
    "Men > Jeans > Ripped":                     ["Men", "Clothing", "Jeans", "Ripped jeans"],
    "Men > Jeans":                              ["Men", "Clothing", "Jeans", "Straight fit jeans"],
    # ── Men: Shoes ────────────────────────────────────────────────────────
    "Men > Shoes > Boots > Chelsea":            ["Men", "Shoes", "Boots", "Chelsea & slip-on boots"],
    "Men > Shoes > Boots > Desert":             ["Men", "Shoes", "Boots", "Desert & lace-up boots"],
    "Men > Shoes > Boots > Wellington":         ["Men", "Shoes", "Boots", "Wellington boots"],
    "Men > Shoes > Boots > Work":               ["Men", "Shoes", "Boots", "Work boots"],
    "Men > Shoes > Boots":                      ["Men", "Shoes", "Boots", "Desert & lace-up boots"],
    "Men > Shoes > Formal":                     ["Men", "Shoes", "Formal shoes"],
    "Men > Shoes > Loafers":                    ["Men", "Shoes", "Boat shoes, loafers & moccasins"],
    "Men > Shoes > Casual shoes":               ["Men", "Shoes", "Boat shoes, loafers & moccasins"],
    "Men > Shoes > Trainers":                   ["Men", "Shoes", "Sports shoes", "Running shoes"],
    "Men > Shoes > Sandals":                    ["Men", "Shoes", "Sandals"],
    # ── Women: Suits & Blazers ────────────────────────────────────────────
    "Women > Suits > Blazers":                  ["Women", "Clothing", "Suits & blazers", "Blazers"],
    "Women > Suits > Trousers":                 ["Women", "Clothing", "Suits & blazers", "Trouser suits"],
    # ── Women: Outerwear — Coats ──────────────────────────────────────────
    "Women > Coats > Overcoat":                 ["Women", "Clothing", "Outerwear", "Coats", "Overcoats & long coats"],
    "Women > Coats > Trench":                   ["Women", "Clothing", "Outerwear", "Coats", "Trench coats"],
    "Women > Coats > Parka":                    ["Women", "Clothing", "Outerwear", "Coats", "Parkas"],
    "Women > Coats > Peacoat":                  ["Women", "Clothing", "Outerwear", "Coats", "Peacoats"],
    "Women > Coats > Raincoat":                 ["Women", "Clothing", "Outerwear", "Coats", "Raincoats"],
    "Women > Coats > Duffle":                   ["Women", "Clothing", "Outerwear", "Coats", "Duffle coats"],
    "Women > Coats > Faux fur":                 ["Women", "Clothing", "Outerwear", "Coats", "Faux fur coats"],
    "Women > Coats & Jackets":                  ["Women", "Clothing", "Outerwear", "Coats", "Overcoats & long coats"],
    "Women > Coats":                            ["Women", "Clothing", "Outerwear", "Coats", "Overcoats & long coats"],
    # ── Women: Outerwear — Jackets ────────────────────────────────────────
    "Women > Jackets > Denim":                  ["Women", "Clothing", "Outerwear", "Jackets", "Denim jackets"],
    "Women > Jackets > Bomber":                 ["Women", "Clothing", "Outerwear", "Jackets", "Bomber jackets"],
    "Women > Jackets > Biker":                  ["Women", "Clothing", "Outerwear", "Jackets", "Biker & racer jackets"],
    "Women > Jackets > Field":                  ["Women", "Clothing", "Outerwear", "Jackets", "Field & utility jackets"],
    "Women > Jackets > Fleece":                 ["Women", "Clothing", "Outerwear", "Jackets", "Fleece jackets"],
    "Women > Jackets > Puffer":                 ["Women", "Clothing", "Outerwear", "Jackets", "Puffer jackets"],
    "Women > Jackets > Quilted":                ["Women", "Clothing", "Outerwear", "Jackets", "Quilted jackets"],
    "Women > Jackets > Shacket":                ["Women", "Clothing", "Outerwear", "Jackets", "Shackets"],
    "Women > Jackets > Varsity":                ["Women", "Clothing", "Outerwear", "Jackets", "Varsity jackets"],
    "Women > Jackets":                          ["Women", "Clothing", "Outerwear", "Jackets", "Denim jackets"],
    "Women > Gilets":                           ["Women", "Clothing", "Outerwear", "Gilets & body warmers"],
    # ── Women: Jumpers & Sweaters ─────────────────────────────────────────
    "Women > Knitwear":                         ["Women", "Clothing", "Jumpers & sweaters", "Jumpers", "Knitted jumpers"],
    "Women > Knitwear > Turtleneck":            ["Women", "Clothing", "Jumpers & sweaters", "Jumpers", "Turtleneck jumpers"],
    "Women > Knitwear > V-neck":                ["Women", "Clothing", "Jumpers & sweaters", "Jumpers", "V-neck jumpers"],
    "Women > Knitwear > Cardigan":              ["Women", "Clothing", "Jumpers & sweaters", "Cardigans"],
    "Women > Sweatshirts & Hoodies":            ["Women", "Clothing", "Jumpers & sweaters", "Hoodies & sweatshirts"],
    # ── Women: Tops ───────────────────────────────────────────────────────
    "Women > Tops":                             ["Women", "Clothing", "Tops & t-shirts", "Other tops & t-shirts"],
    "Women > Tops > T-shirt":                   ["Women", "Clothing", "Tops & t-shirts", "T-shirts"],
    "Women > Tops > Blouse":                    ["Women", "Clothing", "Tops & t-shirts", "Blouses"],
    "Women > Tops > Shirt":                     ["Women", "Clothing", "Tops & t-shirts", "Shirts"],
    "Women > Blouses & Shirts":                 ["Women", "Clothing", "Tops & t-shirts", "Blouses"],
    # ── Women: Dresses ────────────────────────────────────────────────────
    "Women > Dresses":                          ["Women", "Clothing", "Dresses", "Other dresses"],
    "Women > Dresses > Midi":                   ["Women", "Clothing", "Dresses", "Midi-dresses"],
    "Women > Dresses > Maxi":                   ["Women", "Clothing", "Dresses", "Long dresses"],
    "Women > Dresses > Mini":                   ["Women", "Clothing", "Dresses", "Mini-dresses"],
    "Women > Dresses > Casual":                 ["Women", "Clothing", "Dresses", "Casual dresses"],
    "Women > Dresses > Summer":                 ["Women", "Clothing", "Dresses", "Summer dresses"],
    # ── Women: Bottoms ────────────────────────────────────────────────────
    "Women > Trousers > Joggers":               ["Women", "Clothing", "Activewear", "Trousers"],
    "Women > Trousers > Leggings":              ["Women", "Clothing", "Trousers & leggings", "Leggings"],
    "Women > Trousers > Cropped":               ["Women", "Clothing", "Trousers & leggings", "Cropped trousers & chinos"],
    "Women > Trousers > Wide-leg":              ["Women", "Clothing", "Trousers & leggings", "Wide-leg trousers"],
    "Women > Trousers > Skinny":                ["Women", "Clothing", "Trousers & leggings", "Skinny trousers"],
    "Women > Trousers > Tailored":              ["Women", "Clothing", "Trousers & leggings", "Tailored trousers"],
    "Women > Trousers > Straight-leg":          ["Women", "Clothing", "Trousers & leggings", "Straight-leg trousers"],
    "Women > Trousers > Leather":               ["Women", "Clothing", "Trousers & leggings", "Leather trousers"],
    "Women > Trousers > Other":                 ["Women", "Clothing", "Trousers & leggings", "Other trousers"],
    "Women > Trousers & Leggings":              ["Women", "Clothing", "Trousers & leggings", "Other trousers"],
    "Women > Shorts":                           ["Women", "Clothing", "Shorts & cropped trousers", "Other shorts & cropped trousers"],
    "Women > Shorts > Denim":                   ["Women", "Clothing", "Shorts & cropped trousers", "Denim shorts"],
    "Women > Shorts > High-waisted":            ["Women", "Clothing", "Shorts & cropped trousers", "High-waisted shorts"],
    # Women's jeans — sub-types: Boyfriend, Cropped, Flared, High waisted, Other, Ripped, Skinny, Straight
    # Note: no "Slim fit" exists for Women on Vinted UK — map to Straight
    "Women > Jeans > Straight":                 ["Women", "Clothing", "Jeans", "Straight jeans"],
    "Women > Jeans > Skinny":                   ["Women", "Clothing", "Jeans", "Skinny jeans"],
    "Women > Jeans > Slim":                     ["Women", "Clothing", "Jeans", "Straight jeans"],
    "Women > Jeans > Boyfriend":                ["Women", "Clothing", "Jeans", "Boyfriend jeans"],
    "Women > Jeans > Cropped":                  ["Women", "Clothing", "Jeans", "Cropped jeans"],
    "Women > Jeans > Flared":                   ["Women", "Clothing", "Jeans", "Flared jeans"],
    "Women > Jeans > High waisted":             ["Women", "Clothing", "Jeans", "High waisted jeans"],
    "Women > Jeans > Ripped":                   ["Women", "Clothing", "Jeans", "Ripped jeans"],
    "Women > Jeans":                            ["Women", "Clothing", "Jeans", "Straight jeans"],
    # ── Women: Skirts ─────────────────────────────────────────────────────
    "Women > Skirts":                           ["Women", "Clothing", "Skirts", "Knee-length skirts"],
    "Women > Skirts > Mini":                    ["Women", "Clothing", "Skirts", "Mini skirts"],
    "Women > Skirts > Midi":                    ["Women", "Clothing", "Skirts", "Midi skirts"],
    "Women > Skirts > Maxi":                    ["Women", "Clothing", "Skirts", "Maxi skirts"],
    # ── Women: Shoes ──────────────────────────────────────────────────────
    "Women > Shoes > Boots > Ankle":            ["Women", "Shoes", "Boots", "Ankle boots"],
    "Women > Shoes > Boots > Knee":             ["Women", "Shoes", "Boots", "Knee-high boots"],
    "Women > Shoes > Boots > Wellington":       ["Women", "Shoes", "Boots", "Wellington boots"],
    "Women > Shoes > Boots":                    ["Women", "Shoes", "Boots", "Ankle boots"],
    "Women > Shoes > Heels":                    ["Women", "Shoes", "Heels"],
    "Women > Shoes > Loafers":                  ["Women", "Shoes", "Boat shoes, loafers & moccasins"],
    "Women > Shoes > Flat shoes":               ["Women", "Shoes", "Ballerinas"],
    "Women > Shoes > Trainers":                 ["Women", "Shoes", "Trainers"],
    "Women > Shoes > Sandals":                  ["Women", "Shoes", "Sandals"],
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
    # Handle both Cookie-Editor format (lowercase sameSite, expirationDate)
    # and Playwright-native format (capitalised sameSite, expires)
    sam_map = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "unspecified": "None"}
    pw_valid = {"None", "Lax", "Strict"}
    result = []
    for c in raw:
        raw_same_site = c.get("sameSite", "Lax")
        if raw_same_site in pw_valid:
            same_site = raw_same_site  # already Playwright format
        else:
            same_site = sam_map.get(str(raw_same_site).lower(), "Lax")
        pw = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": same_site,
        }
        # Cookie-Editor uses expirationDate; Playwright-native uses expires
        if "expirationDate" in c:
            pw["expires"] = int(c["expirationDate"])
        elif "expires" in c and c["expires"] != -1:
            pw["expires"] = int(c["expires"])
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


def _pw_click(page: Page, testid: str, timeout: int = 8000) -> bool:
    """Click a data-testid element using Playwright's native click (triggers React events)."""
    try:
        loc = page.locator(f'[data-testid="{testid}"]').first
        loc.wait_for(state="visible", timeout=timeout)
        loc.scroll_into_view_if_needed()
        loc.click()
        page.wait_for_timeout(600)
        return True
    except Exception:
        return False


def _dropdown_click_option(page: Page, content_testid: str, option_text: str) -> bool:
    """Click a [role=button] element by EXACT text within a dropdown container."""
    try:
        loc = (
            page.locator(f'[data-testid="{content_testid}"]')
            .locator('[role="button"]')
            .filter(has_text=re.compile(r"^\s*" + re.escape(option_text) + r"\s*$"))
            .first
        )
        loc.wait_for(state="visible", timeout=5000)
        loc.click()
        page.wait_for_timeout(500)
        return True
    except Exception:
        return False


def _close_dropdown(page: Page) -> None:
    """Click the title field to close any open dropdown."""
    try:
        page.locator('[data-testid="title--input"]').first.click()
    except Exception:
        pass
    page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Field fillers
# ---------------------------------------------------------------------------

_PHOTO_KEYWORD_ORDER: dict[str, int] = {
    "front": 1, "main": 1,
    "back": 2,
    "side": 3,
    "detail": 4, "close": 4,
    "flat": 5,
    "model": 6, "worn": 6,
    "tag": 7, "label": 7,
    "brand": 8,
    "material": 9, "fabric": 9,
}


def _photo_sort_key(p: Path) -> tuple:
    # Files with a leading number (01_front.jpg) sort first by that number
    m = re.match(r"^(\d+)", p.stem)
    if m:
        return (int(m.group(1)), p.name.lower())
    # Otherwise rank by keyword in stem, then alpha
    stem = p.stem.lower()
    for keyword, rank in _PHOTO_KEYWORD_ORDER.items():
        if keyword in stem:
            return (100 + rank, p.name.lower())
    return (200, p.name.lower())


def _upload_photos(page: Page, folder: Path) -> None:
    patterns = ["*.jpg", "*.jpeg", "*.png", "*.webp"]
    photos: list[Path] = []
    for pat in patterns:
        photos.extend(folder.glob(pat))
    photos = sorted(set(photos), key=_photo_sort_key)
    if not photos:
        raise FileNotFoundError(f"No photos found in {folder}")
    page.set_input_files('input[data-testid="add-photos-input"]', [str(p) for p in photos])
    page.wait_for_timeout(2000)
    print(f"  Photos uploaded: {[p.name for p in photos]}")


def _get_dropdown_options(page: Page) -> list[str]:
    """Return all visible [role=button] labels in the category dropdown content."""
    try:
        return page.locator('[data-testid="catalog-select-dropdown-content"] [role="button"]').all_inner_texts()
    except Exception:
        return []


def _click_page_option(page: Page, option_text: str, timeout: int = 5000) -> bool:
    """Click any visible interactive element (button, radio, listitem) whose
    label matches option_text.  Used for sub-category selectors that Vinted
    renders as a radio-button list rather than a dropdown menu."""
    pat = re.compile(r"^\s*" + re.escape(option_text) + r"\s*$")
    selectors = [
        '[role="radio"]',
        '[role="option"]',
        '[role="listitem"]',
        '[role="button"]',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).filter(has_text=pat).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.scroll_into_view_if_needed()
            loc.click()
            page.wait_for_timeout(500)
            return True
        except Exception:
            pass
    return False


def _select_category(page: Page, category: str, style: str | None = None) -> None:
    """Navigate the Vinted category picker.

    If *style* is provided, look up the more specific key ``category > style``
    first (e.g. "Men > Jeans" + "Slim" → "Men > Jeans > Slim").  Falls back
    to the base category if no specific key exists.
    """
    if style:
        specific = f"{category} > {style}"
        if specific in CATEGORY_NAV:
            category = specific
    nav_path = CATEGORY_NAV.get(category)
    if not nav_path:
        print(f"  Warning: no category mapping for '{category}', skipping")
        return
    _pw_click(page, "catalog-select-dropdown-input")
    for step in nav_path:
        if _dropdown_click_option(page, "catalog-select-dropdown-content", step):
            continue
        # Step not found in the open dropdown.
        # After selecting a mid-level category (e.g. "Trousers") Vinted closes the
        # main picker and shows the remaining sub-categories as a radio-button list
        # directly on the form.  Try matching the step text across all interactive
        # elements on the page before giving up.
        _close_dropdown(page)
        page.wait_for_timeout(600)
        if _click_page_option(page, step):
            continue
        available = _get_dropdown_options(page)
        print(f"  Warning: category step '{step}' not found. Available: {available}")
        return
    # Dismiss any lingering sub-category modal.
    # Full-screen modals (e.g. jeans style picker) intercept pointer events so
    # _close_dropdown's click on title--input never reaches it. Escape closes them first.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    _close_dropdown(page)
    page.wait_for_timeout(300)
    print(f"  Category: {category}")


def _open_brand_dropdown(page: Page) -> bool:
    """Open the brand dropdown panel. Returns True if content is visible after opening."""
    loc = page.locator('[data-testid="brand-select-dropdown-input"]').first
    content = page.locator('[data-testid="brand-select-dropdown-content"]')

    # Attempt 1: standard Playwright click (scroll + click)
    try:
        loc.wait_for(state="visible", timeout=8000)
        loc.scroll_into_view_if_needed()
        page.wait_for_timeout(300)  # let scroll settle before clicking
        loc.click()
        page.wait_for_timeout(600)
        if content.is_visible():
            return True
    except Exception:
        pass

    # Attempt 2: dispatch_event bypasses hit-testing (fires directly on element,
    # ignores any sticky header / overlay covering it)
    try:
        loc.dispatch_event("click")
        page.wait_for_timeout(600)
        if content.is_visible():
            return True
    except Exception:
        pass

    # Attempt 3: JS click — different event path through the browser
    try:
        page.evaluate("document.querySelector('[data-testid=\"brand-select-dropdown-input\"]').click()")
        page.wait_for_timeout(600)
        if content.is_visible():
            return True
    except Exception:
        pass

    return False


def _select_brand(page: Page, brand: str | None) -> None:
    if not brand:
        return

    # Dismiss any banner/overlay that might intercept clicks on the brand field
    _dismiss_cookie_banner(page)
    page.wait_for_timeout(300)

    if not _open_brand_dropdown(page):
        print("  Warning: brand dropdown would not open, skipping brand")
        return

    content = page.locator('[data-testid="brand-select-dropdown-content"]')

    # Type brand into the search box character-by-character (fires React onChange on each key)
    search = content.locator('[data-testid="brand-search--input"]')
    try:
        search.wait_for(state="visible", timeout=3000)
        search.click()
        search.press_sequentially(brand, delay=80)
    except Exception as e:
        _close_dropdown(page)
        print(f"  Warning: brand search input not ready ({e}), skipping brand")
        return

    page.wait_for_timeout(1200)  # wait for search results to load

    # Find the result row with EXACTLY this brand name (not collabs or partial matches).
    # Use bounding_box + page.mouse to do a real pointer move+click — the only reliable
    # way to trigger the React onClick on Vinted's custom-styled brand rows.
    brand_row = content.get_by_text(brand, exact=True).first
    try:
        brand_row.wait_for(state="visible", timeout=3000)
        box = brand_row.bounding_box()
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            page.mouse.move(cx, cy)
            page.wait_for_timeout(100)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(600)
            if not content.is_visible():
                print(f"  Brand: {brand}")
                return
    except Exception:
        pass

    _close_dropdown(page)
    print(f"  Warning: could not select brand '{brand}', left blank")


def _wl_candidates(size: str) -> list[str]:
    """Generate W/L format variants to try against Vinted's size list.
    Input 'W33 L34' → ['W33 L34', 'W33/L34', 'W 33 / L 34', '33/34', 'W33']
    """
    m = re.match(r"[Ww]?\s*(\d+)\s*[/\s]?\s*[Ll]?\s*(\d+)", size)
    if not m:
        return []
    w, l = m.group(1), m.group(2)
    return [
        f"W{w} L{l}",
        f"W{w}/L{l}",
        f"W {w} / L {l}",
        f"{w}/{l}",
        f"W{w}",
    ]


def _select_size(page: Page, tagged_size: str | None) -> None:
    if not tagged_size:
        return
    _pw_click(page, "size-select-dropdown-input")
    options: list[str] = page.evaluate("""() => {
        const content = document.querySelector('[data-testid="size-select-dropdown-content"]');
        if (!content) return [];
        return Array.from(content.querySelectorAll('[role="button"]')).map(el => el.innerText.trim());
    }""")
    size = tagged_size.strip()
    # Build candidate list: standard suffixes + W/L variants for jeans
    candidates = [size, size + "R", size + "S", size + "L"]
    if re.search(r"[Ww]\d", size) or re.search(r"\d\s*/\s*\d", size):
        candidates = _wl_candidates(size) + candidates
    for candidate in candidates:
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
    _pw_click(page, "category-condition-single-list-input")
    page.wait_for_timeout(600)
    try:
        # The radio inputs are visually hidden — using scroll_into_view on them
        # causes Playwright to scroll the whole page in a loop.
        # Use JS direct click on the parent cell (the visible label/wrapper).
        clicked = page.evaluate(f"""() => {{
            // Try parent condition cell first (visible)
            let el = document.querySelector('[data-testid="condition-{condition_id}"]');
            if (el) {{ el.click(); return 'cell'; }}
            // Fallback: direct JS click on the hidden radio input (no scroll)
            el = document.querySelector('[data-testid="condition-radio-{condition_id}--input"]');
            if (el) {{ el.click(); return 'radio'; }}
            return null;
        }}""")
        if not clicked:
            print(f"  Warning: condition {condition_id} not found")
    except Exception as e:
        print(f"  Warning: condition radio {condition_id} error: {e}")
    page.wait_for_timeout(400)
    print(f"  Condition: {vinted}")


def _select_colour(page: Page, colour: str | None, colour_secondary: str | None = None) -> None:
    if not colour:
        return

    def _lookup(c: str) -> str | None:
        lower = c.lower()
        for keyword in sorted(COLOUR_MAP, key=len, reverse=True):
            if keyword in lower:
                return COLOUR_MAP[keyword]
        return None

    primary = _lookup(colour)
    if not primary:
        print(f"  Warning: no colour mapping for '{colour}', skipping")
        return

    _pw_click(page, "color-select-dropdown-input")
    _dropdown_click_option(page, "color-select-dropdown-content", primary)
    print(f"  Colour 1: {primary} (from '{colour}')")

    if colour_secondary:
        secondary = _lookup(colour_secondary)
        if secondary and secondary != primary:
            _dropdown_click_option(page, "color-select-dropdown-content", secondary)
            print(f"  Colour 2: {secondary} (from '{colour_secondary}')")

    page.keyboard.press("Escape")


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

    _pw_click(page, "category-material-multi-list-input")
    options: list[str] = page.evaluate("""() => {
        const content = document.querySelector('[data-testid="category-material-multi-list-content"]');
        if (!content) return [];
        return Array.from(content.querySelectorAll('[role="button"]')).map(el => el.innerText.trim());
    }""")
    options_lower = [o.lower() for o in options]

    for name in names:
        for i, opt_lower in enumerate(options_lower):
            if name in opt_lower:
                try:
                    page.locator('[data-testid="category-material-multi-list-content"] [role="button"]').nth(i).click()
                    page.wait_for_timeout(300)
                    print(f"  Material: {options[i]}")
                except Exception:
                    pass
                break

    _close_dropdown(page)


def _select_package_size(page: Page, item_type: str | None) -> None:
    """1=Small envelope, 2=Medium shoebox, 3=Large box."""
    lower = (item_type or "").lower()
    # Large: bulky outerwear — coats, heavy jackets
    # Check "raincoat" before "coat" so it falls to medium instead
    is_large = (
        ("coat" in lower and "raincoat" not in lower) or
        any(k in lower for k in ("parka", "trench", "wax", "overcoat", "anorak", "ski jacket"))
    )
    is_medium = any(k in lower for k in (
        "trouser", "jean", "jogger", "sweatpant", "track pant",
        "short", "chino", "cargo",
        "jumper", "sweater", "sweatshirt", "hoodie", "knitwear", "cardigan",
        "shoe", "boot", "trainer", "sneaker", "loafer",
        "blazer", "jacket", "suit", "waistcoat", "gilet", "raincoat",
    ))
    if is_large:
        pkg = 3
    elif is_medium:
        pkg = 2
    else:
        pkg = 1  # t-shirts, shirts, polos, accessories, hats, belts, ties, socks
    # Close any open dropdown (condition picker may still be active)
    _close_dropdown(page)
    page.wait_for_timeout(500)
    try:
        # Package size inputs are also hidden radios — use JS click to avoid page scroll
        clicked = page.evaluate(f"""() => {{
            const el = document.querySelector('[data-testid="package_type_selector_{pkg}--input"]');
            if (el) {{ el.scrollIntoView({{block: 'nearest'}}); el.click(); return true; }}
            return false;
        }}""")
        if not clicked:
            print(f"  Warning: package size selector {pkg} not found")
    except Exception as e:
        print(f"  Warning: package size selector {pkg} error: {e}")
    page.wait_for_timeout(200)
    label = {1: "Small", 2: "Medium", 3: "Large"}[pkg]
    print(f"  Package size: {label}")


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
            viewport={"width": 1280, "height": 900},
        )
        context.add_init_script(_STEALTH_SCRIPT)
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
        _select_category(page, listing.get("category", ""), listing.get("style"))

        # Wait for dependent fields to appear after category is selected
        try:
            page.wait_for_selector('[data-testid="brand-select-dropdown-input"]', timeout=10000)
        except Exception:
            page.wait_for_timeout(3000)

        page.locator('[data-testid="title--input"]').fill(listing.get("title", ""))
        page.locator('[data-testid="description--input"]').fill(listing.get("description", ""))
        _select_brand(page, listing.get("brand"))
        # Prefer normalized_size (UK) over raw tagged_size (may be EU for tailoring)
        _select_size(page, listing.get("normalized_size") or listing.get("tagged_size"))
        _select_condition(page, listing.get("condition_summary"))
        _select_colour(page, listing.get("colour"), listing.get("colour_secondary"))
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


def edit_draft(listing: dict, item_folder: Path | str, draft_url: str) -> str | None:
    """
    Edit an existing Vinted draft by navigating to its /edit page.
    Skips photo upload (photos are already attached to the draft).
    Falls back to create_draft() if the draft URL doesn't contain an item ID.

    Args:
        listing: validated listing JSON
        item_folder: path to the item folder (used only for fallback)
        draft_url: URL of the existing Vinted draft (e.g. https://www.vinted.co.uk/items/12345678)

    Returns:
        URL after saving, or None if save failed.
    """
    m = re.search(r"/items/(\d+)", draft_url)
    if not m:
        print("  edit_draft: can't extract item ID from draft_url, falling back to create_draft")
        return create_draft(listing, item_folder)

    item_id = m.group(1)
    edit_url = f"{VINTED_URL}/items/{item_id}/edit"
    cookies = _load_cookies()

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
            viewport={"width": 1280, "height": 900},
        )
        context.add_init_script(_STEALTH_SCRIPT)
        context.add_cookies(cookies)
        page = context.new_page()

        print(f"Opening Vinted edit page: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # If redirected away from edit page, session may have expired
        if "/items/new" not in page.url and f"/items/{item_id}" not in page.url:
            browser.close()
            raise RuntimeError(
                f"Redirected to {page.url} — session cookies may have expired. "
                "Re-export cookies from your browser using Cookie-Editor."
            )

        _dismiss_cookie_banner(page)

        print("Updating fields (photos kept as-is)...")
        # No photo upload — photos are already attached to the draft
        _select_category(page, listing.get("category", ""), listing.get("style"))

        try:
            page.wait_for_selector('[data-testid="brand-select-dropdown-input"]', timeout=10000)
        except Exception:
            page.wait_for_timeout(3000)

        page.locator('[data-testid="title--input"]').fill(listing.get("title", ""))
        page.locator('[data-testid="description--input"]').fill(listing.get("description", ""))
        _select_brand(page, listing.get("brand"))
        _select_size(page, listing.get("normalized_size") or listing.get("tagged_size"))
        _select_condition(page, listing.get("condition_summary"))
        _select_colour(page, listing.get("colour"), listing.get("colour_secondary"))
        _select_material(page, listing.get("materials"))
        page.locator('[data-testid="price-input--input"]').fill(str(listing.get("price_gbp", "")))
        _select_package_size(page, listing.get("item_type"))

        page.wait_for_timeout(500)

        print("Saving updated draft...")
        _dismiss_cookie_banner(page)
        save_btn = page.locator('[data-testid="upload-form-save-draft-button"]')
        save_btn.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        save_btn.click()

        try:
            page.wait_for_function(
                "() => !window.location.pathname.includes('/edit')",
                timeout=20000,
            )
            result_url = page.url
        except Exception:
            result_url = page.url

        print(f"  Draft updated (url): {result_url}")
        browser.close()
        return result_url
