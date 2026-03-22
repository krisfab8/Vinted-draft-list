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
AUTH_STATE_FILE = ROOT / "auth_state.json"
VINTED_URL = "https://www.vinted.co.uk"


class VintedAuthError(RuntimeError):
    """Raised when the Vinted session is missing or expired."""

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
window.chrome = {runtime: {}};
"""

# Category nav/aliases and resolution live in app/services/category_validator.py
from app.services.category_validator import (
    CATEGORY_NAV,
    CATEGORY_ALIASES,
    resolve_category_key as _resolve_category_key,
)


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


def check_auth_state() -> dict:
    """Fast file-based session indicator — not authoritative, used for UI status only.

    Returns dict with keys:
      logged_in: "likely" | "expired" | "missing"
      expires_at: Unix timestamp or None
      saved_at:   Unix timestamp of when the auth file was last written (for UI display)
      method: "storage_state" | "cookies" | "none"
    """
    import time
    import os

    def _find_token(cookies: list[dict]) -> dict | None:
        for c in cookies:
            if c.get("name") == "access_token_web":
                return c
        return None

    # Prefer auth_state.json (Playwright storage state)
    if AUTH_STATE_FILE.exists():
        saved_at = int(os.path.getmtime(AUTH_STATE_FILE))
        try:
            data = json.loads(AUTH_STATE_FILE.read_text())
            cookies = data.get("cookies", [])
            token = _find_token(cookies)
            if token:
                exp = token.get("expires", -1)
                if exp and exp > 0:
                    status = "likely" if exp > time.time() else "expired"
                    return {"logged_in": status, "expires_at": int(exp), "saved_at": saved_at, "method": "storage_state"}
            return {"logged_in": "likely", "expires_at": None, "saved_at": saved_at, "method": "storage_state"}
        except Exception:
            pass

    # Fallback: vinted_cookies.json
    if COOKIES_FILE.exists():
        saved_at = int(os.path.getmtime(COOKIES_FILE))
        try:
            raw = json.loads(COOKIES_FILE.read_text())
            token = _find_token(raw)
            if token:
                exp = token.get("expires") or token.get("expirationDate", -1)
                if exp and exp > 0:
                    status = "likely" if float(exp) > time.time() else "expired"
                    return {"logged_in": status, "expires_at": int(exp), "saved_at": saved_at, "method": "cookies"}
            return {"logged_in": "likely", "expires_at": None, "saved_at": saved_at, "method": "cookies"}
        except Exception:
            pass

    return {"logged_in": "missing", "expires_at": None, "saved_at": None, "method": "none"}


_CONTEXT_KWARGS = {
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "viewport": {"width": 1280, "height": 900},
}


def _build_context(browser):
    """Create a Playwright browser context loaded with the best available auth.

    Preference order:
    1. auth_state.json  — Playwright storage state (cookies + localStorage)
    2. vinted_cookies.json — legacy cookie-only fallback
    3. VintedAuthError  — no auth found
    """
    if AUTH_STATE_FILE.exists():
        ctx = browser.new_context(storage_state=str(AUTH_STATE_FILE), **_CONTEXT_KWARGS)
        ctx.add_init_script(_STEALTH_SCRIPT)
        return ctx

    if COOKIES_FILE.exists():
        cookies = _load_cookies()
        ctx = browser.new_context(**_CONTEXT_KWARGS)
        ctx.add_init_script(_STEALTH_SCRIPT)
        ctx.add_cookies(cookies)
        return ctx

    raise VintedAuthError("No Vinted session found — reconnect via the app")


def _probe_auth(page) -> None:
    """Navigate to Vinted home and verify the session is active.

    Raises VintedAuthError if Vinted redirects to /login or /signup,
    which is the definitive sign that the session has expired.
    """
    page.goto(VINTED_URL, wait_until="domcontentloaded", timeout=15000)
    if "/login" in page.url or "/signup" in page.url:
        raise VintedAuthError("Vinted session expired — reconnect via the app")


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

def safe_label(s: str) -> str:
    """Make a string safe for use in a filename."""
    return re.sub(r"[^\w\-]", "_", str(s))[:50]


def _screenshot(page: Page, label: str) -> str | None:
    """Save a debug screenshot. Returns the file path, or None on error.

    Files land in <project-root>/debug_screenshots/ with a timestamp prefix
    so each run's failures are easy to find.
    """
    try:
        import datetime
        outdir = ROOT / "debug_screenshots"
        outdir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%H%M%S")
        safe = re.sub(r"[^\w\-]", "_", label)[:60]
        path = outdir / f"{ts}_{safe}.png"
        page.screenshot(path=str(path))
        return str(path)
    except Exception:
        return None


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

    # Vinted rejects files ≥ 9 MB. Shrink any oversized photos to a temp JPEG.
    _VINTED_MAX_BYTES = 8 * 1024 * 1024
    _VINTED_MAX_DIM   = 2048
    upload_paths: list[str] = []
    _tmp_files: list[Path] = []
    for p in photos:
        if p.stat().st_size <= _VINTED_MAX_BYTES:
            upload_paths.append(str(p))
            continue
        try:
            from PIL import Image as _PIL
            import tempfile
            orig_mb = p.stat().st_size // 1024 // 1024
            img = _PIL.open(p).convert("RGB")
            w, h = img.size
            scale = min(1.0, _VINTED_MAX_DIM / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), _PIL.LANCZOS)
            tmp = Path(tempfile.mktemp(suffix=".jpg"))
            img.save(tmp, "JPEG", quality=85, optimize=True, progressive=True, exif=b"")
            upload_paths.append(str(tmp))
            _tmp_files.append(tmp)
            print(f"[vinted_guard] photo exceeded 8MB, compressed before upload ({orig_mb}MB -> {tmp.stat().st_size // 1024 // 1024}MB)")
        except Exception:
            upload_paths.append(str(p))  # upload as-is, let Vinted give the error

    page.set_input_files('input[data-testid="add-photos-input"]', upload_paths)
    page.wait_for_timeout(2000)
    print(f"  Photos uploaded: {[p.name for p in photos]}")
    for tmp in _tmp_files:
        tmp.unlink(missing_ok=True)


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



def _match_option(target: str, options: list[str]) -> tuple[str, str] | None:
    """Match *target* against *options* using exact → normalised → substring.

    Returns (matched_option, method_name) or None.
    """
    def _n(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    t = target.strip()
    t_norm = _n(t)

    # 1. Exact
    if t in options:
        return t, "exact"

    # 2. Normalised (case + whitespace insensitive)
    for opt in options:
        if _n(opt) == t_norm:
            return opt, "normalized"

    # 3. Substring — prefer longer options (more specific)
    for opt in sorted(options, key=len, reverse=True):
        opt_norm = _n(opt)
        if t_norm in opt_norm or opt_norm in t_norm:
            return opt, "contains"

    return None


def _select_category(page: Page, category: str, style: str | None = None) -> None:
    """Navigate the Vinted category picker.

    Resolves raw → canonical → CATEGORY_NAV path using _resolve_category_key.
    """
    canonical = _resolve_category_key(category, style)
    if not canonical:
        print(f"  Warning: no category mapping for '{category}' (style={style!r}), skipping")
        return
    nav_path = CATEGORY_NAV[canonical]
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
        shot = _screenshot(page, f"category_step_{safe_label(step)}")
        print(f"  Warning: category step '{step}' not found. Available: {available}"
              + (f" — screenshot: {shot}" if shot else ""))
        return
    # Dismiss any lingering sub-category modal.
    # Full-screen modals (e.g. jeans style picker) intercept pointer events so
    # _close_dropdown's click on title--input never reaches it. Escape closes them first.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    _close_dropdown(page)
    page.wait_for_timeout(300)
    print(f"  Category: {canonical}")


def _open_brand_dropdown(page: Page) -> bool:
    """Open the brand dropdown panel. Returns True if content is visible after opening.

    Tries five escalating methods and logs which one succeeded.
    """
    loc = page.locator('[data-testid="brand-select-dropdown-input"]').first
    content = page.locator('[data-testid="brand-select-dropdown-content"]')

    # Attempt 1: scroll into view → wait visible → standard click
    try:
        loc.wait_for(state="visible", timeout=8000)
        loc.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        loc.click()
        page.wait_for_timeout(600)
        if content.is_visible():
            print("  [brand_dropdown] opened via attempt 1 (scroll+click)")
            return True
    except Exception:
        pass

    # Attempt 2: dispatch_event — bypasses overlay hit-testing
    try:
        loc.dispatch_event("click")
        page.wait_for_timeout(600)
        if content.is_visible():
            print("  [brand_dropdown] opened via attempt 2 (dispatch_event)")
            return True
    except Exception:
        pass

    # Attempt 3: JS .click() — different React event path
    try:
        page.evaluate("document.querySelector('[data-testid=\"brand-select-dropdown-input\"]').click()")
        page.wait_for_timeout(600)
        if content.is_visible():
            print("  [brand_dropdown] opened via attempt 3 (js click)")
            return True
    except Exception:
        pass

    # Attempt 4: centre scroll → dismiss overlay → force click → longer wait
    try:
        page.evaluate("""
            const el = document.querySelector('[data-testid="brand-select-dropdown-input"]');
            if (el) el.scrollIntoView({block: 'center'});
        """)
        page.wait_for_timeout(500)
        _dismiss_cookie_banner(page)
        page.wait_for_timeout(300)
        loc.click(force=True)
        page.wait_for_timeout(1000)
        if content.is_visible():
            print("  [brand_dropdown] opened via attempt 4 (force click)")
            return True
    except Exception:
        pass

    # Attempt 5: focus element then press Enter via keyboard
    try:
        loc.focus()
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        if content.is_visible():
            print("  [brand_dropdown] opened via attempt 5 (keyboard Enter)")
            return True
    except Exception:
        pass

    print("  [brand_dropdown] all 5 attempts failed")
    return False


def _select_brand(page: Page, brand: str | None) -> None:
    if not brand:
        return

    # Dismiss any banner/overlay that might intercept clicks on the brand field
    _dismiss_cookie_banner(page)
    page.wait_for_timeout(300)

    if not _open_brand_dropdown(page):
        shot = _screenshot(page, "brand_dropdown_failed")
        print("  Warning: brand dropdown would not open, skipping brand"
              + (f" — screenshot: {shot}" if shot else ""))
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
    """Generate W/L format variants for jeans sizes.

    "W34 L32" → ["W34 L32", "W34/L32", "W34 / L32", "W 34 / L 32",
                  "34/32", "34 / 32", "34 32", "W34", "34"]
    """
    # Require either a W prefix ("W34 L32") or an explicit slash separator ("34/32")
    # to avoid false matches on suit sizes like "44R" (two digits, no separator).
    m = re.match(r"[Ww]\s*(\d+)\s*(?:[/\s]+|[Ll]\s*)(\d+)", size.strip()) or \
        re.match(r"(\d+)\s*/\s*(\d+)", size.strip())
    if not m:
        return []
    w, l = m.group(1), m.group(2)
    return [
        f"W{w} L{l}",       # "W34 L32"  — most common UK resale format
        f"W{w}/L{l}",       # "W34/L32"
        f"W{w} / L{l}",     # "W34 / L32"
        f"W {w} / L {l}",   # "W 34 / L 32"
        f"{w}/{l}",          # "34/32"
        f"{w} / {l}",        # "34 / 32"   — Vinted sometimes uses this
        f"{w} {l}",          # "34 32"
        f"W{w}",             # "W34"       — waist-only fallback
        f"{w}",              # "34"        — bare number
    ]


def _select_size(page: Page, tagged_size: str | None) -> None:
    if not tagged_size:
        return
    _pw_click(page, "size-select-dropdown-input")
    page.wait_for_timeout(600)  # wait for size options to render
    options: list[str] = page.evaluate("""() => {
        const content = document.querySelector('[data-testid="size-select-dropdown-content"]');
        if (!content) return [];
        return Array.from(content.querySelectorAll('[role="button"]')).map(el => el.innerText.trim());
    }""")
    size = tagged_size.strip()
    # Build candidate list: W/L variants (jeans) + standard suit/letter suffixes
    is_wl = bool(re.search(r"[Ww]\d", size) or re.search(r"\d\s*/\s*\d", size))
    candidates = _wl_candidates(size) if is_wl else []
    candidates += [size, size + "R", size + "S", size + "L"]

    # 1. Try explicit candidates (exact match)
    for candidate in candidates:
        if candidate in options:
            _dropdown_click_option(page, "size-select-dropdown-content", candidate)
            print(f"  Size: {candidate} (tagged: {tagged_size})")
            return

    # 2. Try _match_option (normalised + contains) for each candidate
    for candidate in candidates:
        result = _match_option(candidate, options)
        if result:
            matched, method = result
            _dropdown_click_option(page, "size-select-dropdown-content", matched)
            print(f"  Size: {matched} (tagged: {tagged_size}, matched via {method})")
            return

    _close_dropdown(page)
    shot = _screenshot(page, f"size_{safe_label(tagged_size)}")
    print(f"  Warning: size '{tagged_size}' not found in options. Available: {options}"
          + (f" — screenshot: {shot}" if shot else ""))


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

    clicked = None
    try:
        # Attempt 1: data-testid by condition ID
        clicked = page.evaluate(f"""() => {{
            let el = document.querySelector('[data-testid="condition-{condition_id}"]');
            if (el) {{ el.click(); return 'id'; }}
            el = document.querySelector('[data-testid="condition-radio-{condition_id}--input"]');
            if (el) {{ el.click(); return 'radio-id'; }}
            return null;
        }}""")
    except Exception:
        pass

    if not clicked:
        # Attempt 2: read live options and use _match_option (normalised + contains)
        try:
            live_options: list[str] = page.evaluate("""() => {
                const c = document.querySelector(
                    '[data-testid="category-condition-single-list-content"]'
                );
                if (!c) return [];
                return Array.from(
                    c.querySelectorAll('[role="button"], label, li')
                ).map(el => el.innerText.trim()).filter(Boolean);
            }""")
            result = _match_option(vinted, live_options)
            if result:
                matched, method = result
                clicked = page.evaluate(f"""() => {{
                    const text = {json.dumps(matched)};
                    const c = document.querySelector(
                        '[data-testid="category-condition-single-list-content"]'
                    );
                    if (!c) return null;
                    for (const el of c.querySelectorAll('[role="button"], label, li')) {{
                        if (el.innerText && el.innerText.trim() === text) {{
                            el.click(); return 'text-' + {json.dumps(method)};
                        }}
                    }}
                    return null;
                }}""")
            if not clicked:
                shot = _screenshot(page, f"condition_{safe_label(vinted)}")
                print(f"  Warning: condition '{vinted}' not found. "
                      f"Available: {live_options}"
                      + (f" — screenshot: {shot}" if shot else ""))
        except Exception as e:
            print(f"  Warning: condition fallback error: {e}")

    page.wait_for_timeout(400)
    if clicked:
        print(f"  Condition: {vinted} (via {clicked})")
    else:
        print(f"  Condition: {vinted} (click may have failed)")


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
    # Read live options to allow normalised/contains fallback
    colour_options: list[str] = page.evaluate("""() => {
        const c = document.querySelector('[data-testid="color-select-dropdown-content"]');
        if (!c) return [];
        return Array.from(c.querySelectorAll('[role="button"]')).map(el => el.innerText.trim());
    }""")

    def _click_colour(label: str) -> bool:
        """Try exact dropdown click, then _match_option fallback."""
        if _dropdown_click_option(page, "color-select-dropdown-content", label):
            return True
        result = _match_option(label, colour_options)
        if result:
            matched, method = result
            if _dropdown_click_option(page, "color-select-dropdown-content", matched):
                print(f"  [colour] matched '{label}' → '{matched}' via {method}")
                return True
        return False

    if _click_colour(primary):
        print(f"  Colour 1: {primary} (from '{colour}')")
    else:
        shot = _screenshot(page, f"colour_{safe_label(primary)}")
        print(f"  Warning: colour '{primary}' not found in dropdown. "
              f"Available: {colour_options}"
              + (f" — screenshot: {shot}" if shot else ""))

    if colour_secondary:
        secondary = _lookup(colour_secondary)
        if secondary and secondary != primary:
            if _click_colour(secondary):
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
    label_text = {1: "Small", 2: "Medium", 3: "Large"}[pkg]
    clicked = None
    try:
        # Attempt 1: data-testid by package index
        clicked = page.evaluate(f"""() => {{
            const el = document.querySelector('[data-testid="package_type_selector_{pkg}--input"]');
            if (el) {{ el.scrollIntoView({{block: 'nearest'}}); el.click(); return 'testid'; }}
            return null;
        }}""")
    except Exception:
        pass

    if not clicked:
        # Attempt 2: read live package options and use _match_option
        try:
            live_opts: list[str] = page.evaluate("""() => {
                return Array.from(
                    document.querySelectorAll('label, [role="radio"], [role="button"]')
                ).map(el => el.innerText.trim()).filter(Boolean);
            }""")
            result = _match_option(label_text, live_opts)
            if result:
                matched, method = result
                clicked = page.evaluate(f"""() => {{
                    const text = {json.dumps(matched)};
                    for (const el of document.querySelectorAll(
                        'label, [role="radio"], [role="button"]'
                    )) {{
                        if (el.innerText && el.innerText.trim() === text) {{
                            el.scrollIntoView({{block: 'nearest'}}); el.click();
                            return 'text-' + {json.dumps(method)};
                        }}
                    }}
                    return null;
                }}""")
            if not clicked:
                # Attempt 3: input with matching value
                clicked = page.evaluate(f"""() => {{
                    const inp = document.querySelector(
                        'input[name*="package"][value="{pkg}"]'
                    );
                    if (inp) {{ inp.click(); return 'input-value'; }}
                    return null;
                }}""")
            if not clicked:
                shot = _screenshot(page, f"package_{safe_label(label_text)}")
                print(f"  Warning: package size '{label_text}' not found. "
                      f"Tried options: {live_opts[:10]}"
                      + (f" — screenshot: {shot}" if shot else ""))
        except Exception as e:
            print(f"  Warning: package size fallback error: {e}")

    page.wait_for_timeout(200)
    if clicked:
        print(f"  Package size: {label_text} (via {clicked})")
    else:
        print(f"  Package size: {label_text} (click may have failed)")


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

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = _build_context(browser)
        page = context.new_page()

        _probe_auth(page)

        print("Opening Vinted sell page...")
        page.goto(f"{VINTED_URL}/items/new", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Check we're actually on the sell page (belt-and-braces after probe)
        if "/items/new" not in page.url:
            browser.close()
            raise VintedAuthError(
                f"Redirected to {page.url} — session expired. Reconnect via the app."
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

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = _build_context(browser)
        page = context.new_page()

        _probe_auth(page)

        print(f"Opening Vinted edit page: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Belt-and-braces check after probe
        if "/items/new" not in page.url and f"/items/{item_id}" not in page.url:
            browser.close()
            raise VintedAuthError(
                f"Redirected to {page.url} — session expired. Reconnect via the app."
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
