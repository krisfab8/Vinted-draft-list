"""
Offline replay/validation of draft_creator logic against a set of realistic
problem items.  No browser, no Vinted cookies required — tests the pure
Python functions only.

Run with:
    .venv/bin/python tests/validate_draft_logic.py

Output:
    Per-item pass/fail table, field-level failure details, and a summary of
    the most common remaining failure points.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.draft_creator import (
    CATEGORY_NAV,
    CATEGORY_ALIASES,
    _resolve_category_key,
    _wl_candidates,
    _match_option,
    _normalise_category,
    _CONDITION_ID,
)

# ---------------------------------------------------------------------------
# Simulated Vinted size option banks (realistic snapshots per category type)
# ---------------------------------------------------------------------------

VINTED_SIZE_OPTIONS: dict[str, list[str]] = {
    "jeans": [
        "W26 L30", "W26 L32", "W28 L30", "W28 L32", "W28 L34",
        "W30 L30", "W30 L32", "W30 L34", "W32 L30", "W32 L32",
        "W32 L34", "W34 L30", "W34 L32", "W34 L34", "W36 L30",
        "W36 L32", "W38 L32",
    ],
    "letter": ["XS", "S", "M", "L", "XL", "XXL", "XXXL"],
    "suit_number": [
        "36R", "38R", "40R", "42R", "44R", "46R", "48R",
        "36L", "38L", "40L", "42L", "44L", "46L",
        "36S", "38S", "40S",
    ],
    "shirt_collar": [
        "XS", "S", "M", "L", "XL", "XXL",
        "14.5", "15", "15.5", "16", "16.5", "17", "17.5",
    ],
    "shoes": [
        "UK 6", "UK 7", "UK 8", "UK 9", "UK 10", "UK 11", "UK 12",
        "EU 40", "EU 41", "EU 42", "EU 43", "EU 44", "EU 45",
    ],
    "vinted_slash": [
        # Vinted sometimes uses slash notation without W/L prefix
        "28/30", "28/32", "30/30", "30/32", "32/30", "32/32",
        "34/30", "34/32", "34/34", "36/32",
    ],
}

# ---------------------------------------------------------------------------
# Condition mapping (mirrors _select_condition logic)
# ---------------------------------------------------------------------------

def _map_condition(condition_summary: str) -> str:
    lower = condition_summary.lower()
    if "new with tag" in lower or ("brand new" in lower and "tag" in lower):
        return "New with tags"
    elif "new without" in lower:
        return "New without tags"
    elif "very good" in lower or "excellent" in lower or "barely worn" in lower or "hardly worn" in lower:
        return "Very good"
    elif "satisfactory" in lower or "fair" in lower or "worn" in lower:
        return "Satisfactory"
    return "Very good"


# ---------------------------------------------------------------------------
# Package size mapping (mirrors _select_package_size logic)
# ---------------------------------------------------------------------------

def _map_package(item_type: str) -> str:
    lower = item_type.lower()
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
    return "Large" if is_large else ("Medium" if is_medium else "Small")


# ---------------------------------------------------------------------------
# Problem items — real-world category/size combinations that previously failed
# ---------------------------------------------------------------------------

ITEMS: list[dict] = [
    # 1. Straight jeans — exact Vinted label echoed by AI
    {
        "name": "straight_jeans",
        "desc": "Diesel straight jeans W34 L32",
        "category_raw": "Men > Jeans > Straight fit jeans",
        "style": None,
        "size": "W34 L32",
        "size_options": "jeans",
        "condition": "Very good used condition — minor fading on knees",
        "item_type": "jeans",
        "brand": "Diesel",
        "expect_category": "Men > Jeans > Straight",
        "expect_size_matched": True,
    },
    # 2. Slim jeans — full Vinted label
    {
        "name": "slim_jeans",
        "desc": "Levi's 511 slim fit jeans W32 L30",
        "category_raw": "Men > Jeans > Slim fit jeans",
        "style": None,
        "size": "W32 L30",
        "size_options": "jeans",
        "condition": "Good used condition — light fading",
        "item_type": "jeans",
        "brand": "Levi's",
        "expect_category": "Men > Jeans > Slim",
        "expect_size_matched": True,
    },
    # 3. Tapered jeans — not a real Vinted type, should map to Slim
    {
        "name": "tapered_jeans",
        "desc": "G-Star tapered jeans W30 L32",
        "category_raw": "Men > Jeans > Tapered jeans",
        "style": None,
        "size": "W30 L32",
        "size_options": "jeans",
        "condition": "Very good used condition",
        "item_type": "jeans",
        "brand": "G-Star",
        "expect_category": "Men > Jeans > Slim",
        "expect_size_matched": True,
    },
    # 4. Cargo trousers — alias from "Cargos" → "Cargo"
    {
        "name": "cargo_trousers",
        "desc": "Carhartt cargo trousers M",
        "category_raw": "Men > Trousers > Cargos",
        "style": None,
        "size": "M",
        "size_options": "letter",
        "condition": "Very good used condition — washed once",
        "item_type": "cargo trousers",
        "brand": "Carhartt",
        "expect_category": "Men > Trousers > Cargo",
        "expect_size_matched": True,
    },
    # 5. Knitwear — from "Jumpers & Sweaters" alias
    {
        "name": "knitwear",
        "desc": "John Smedley merino crew neck jumper L",
        "category_raw": "Men > Jumpers & Sweaters",
        "style": "Crew neck",
        "size": "L",
        "size_options": "letter",
        "condition": "Excellent used condition — barely worn",
        "item_type": "jumper",
        "brand": "John Smedley",
        "expect_category": "Men > Knitwear > Crew neck",  # alias + style re-qualification
        "expect_size_matched": True,
    },
    # 6. Outerwear coat — via Outerwear path alias
    {
        "name": "outerwear_coat",
        "desc": "Burberry overcoat 44R",
        "category_raw": "Men > Outerwear > Coats > Overcoat",
        "style": None,
        "size": "44R",
        "size_options": "suit_number",
        "condition": "Very good used condition — dry cleaned",
        "item_type": "overcoat",
        "brand": "Burberry",
        "expect_category": "Men > Coats > Overcoat",
        "expect_size_matched": True,
    },
    # 7. Women's jeans — straight jeans alias
    {
        "name": "womens_straight_jeans",
        "desc": "Zara straight leg jeans W28 L30",
        "category_raw": "Women > Jeans > Straight jeans",
        "style": None,
        "size": "W28 L30",
        "size_options": "jeans",
        "condition": "Very good used condition",
        "item_type": "jeans",
        "brand": "Zara",
        "expect_category": "Women > Jeans > Straight",
        "expect_size_matched": True,
    },
    # 8. Awkward size — shirt collar/sleeve format (Vinted uses collar only)
    {
        "name": "shirt_collar_size",
        "desc": "Thomas Pink shirt collar 15.5",
        "category_raw": "Men > Shirts > Plain",
        "style": None,
        "size": "15.5",
        "size_options": "shirt_collar",
        "condition": "Very good used condition",
        "item_type": "shirt",
        "brand": "Thomas Pink",
        "expect_category": "Men > Shirts > Plain",
        "expect_size_matched": True,
    },
    # 9. Unknown/no brand — should not cause a crash
    {
        "name": "no_brand",
        "desc": "Generic t-shirt XL",
        "category_raw": "Men > T-shirts",
        "style": None,
        "size": "XL",
        "size_options": "letter",
        "condition": "Good used condition",
        "item_type": "t-shirt",
        "brand": "",
        "expect_category": "Men > T-shirts",
        "expect_size_matched": True,
    },
    # 10. Slash-notation jeans — Vinted options without W/L prefix
    {
        "name": "jeans_slash_options",
        "desc": "Nudie slim jeans W32 L32 (Vinted uses slash format)",
        "category_raw": "Men > Jeans > Slim fit jeans",
        "style": None,
        "size": "W32 L32",
        "size_options": "vinted_slash",  # simulate Vinted showing "32/32"
        "condition": "Very good used condition",
        "item_type": "jeans",
        "brand": "Nudie Jeans",
        "expect_category": "Men > Jeans > Slim",
        "expect_size_matched": True,  # should match "32/32" via candidates
    },
    # 11. Activewear joggers — previously "no category mapping"
    {
        "name": "joggers",
        "desc": "Nike joggers M",
        "category_raw": "Men > Clothing > Trousers > Joggers",
        "style": None,
        "size": "M",
        "size_options": "letter",
        "condition": "Very good used condition",
        "item_type": "joggers",
        "brand": "Nike",
        "expect_category": "Men > Trousers > Joggers",
        "expect_size_matched": True,
    },
    # 12. Women's high-waisted jeans — specific alias
    {
        "name": "womens_high_waisted_jeans",
        "desc": "ASOS high waisted jeans W26 L32",
        "category_raw": "Women > Jeans > High-waisted jeans",
        "style": None,
        "size": "W26 L32",
        "size_options": "jeans",
        "condition": "Very good used condition",
        "item_type": "jeans",
        "brand": "ASOS",
        "expect_category": "Women > Jeans > High waisted",
        "expect_size_matched": True,
    },
]


# ---------------------------------------------------------------------------
# Field validation helpers
# ---------------------------------------------------------------------------

class FieldResult:
    def __init__(self, field: str, requested: str, passed: bool,
                 matched: str | None = None, method: str | None = None,
                 candidates: list[str] | None = None,
                 options: list[str] | None = None,
                 note: str | None = None):
        self.field = field
        self.requested = requested
        self.passed = passed
        self.matched = matched
        self.method = method
        self.candidates = candidates or []
        self.options = options or []
        self.note = note


def validate_item(item: dict) -> tuple[bool, list[FieldResult]]:
    results: list[FieldResult] = []

    # --- Category ---
    canonical = _resolve_category_key(item["category_raw"], item.get("style"))
    cat_pass = canonical is not None
    if canonical and item.get("expect_category"):
        cat_pass = canonical == item["expect_category"]
    results.append(FieldResult(
        field="category",
        requested=item["category_raw"],
        passed=cat_pass,
        matched=canonical,
        note=(f"expected {item['expect_category']!r}" if not cat_pass else None),
    ))

    # --- Size ---
    size = item.get("size", "")
    options = VINTED_SIZE_OPTIONS.get(item["size_options"], [])
    is_wl = bool(__import__("re").search(r"[Ww]\d", size) or
                 __import__("re").search(r"\d\s*/\s*\d", size))
    candidates = _wl_candidates(size) + [size, size + "R", size + "S", size + "L"] \
        if is_wl else [size, size + "R", size + "S", size + "L"]

    # First: exact candidate match
    size_matched = None
    size_method = None
    for c in candidates:
        if c in options:
            size_matched = c
            size_method = "exact"
            break

    # Second: _match_option fallback
    if size_matched is None:
        for c in candidates:
            result = _match_option(c, options)
            if result:
                size_matched, size_method = result
                break

    size_pass = size_matched is not None
    if not size_pass and item.get("expect_size_matched"):
        pass  # fail as expected_to_match but didn't
    results.append(FieldResult(
        field="size",
        requested=size,
        passed=size_pass,
        matched=size_matched,
        method=size_method,
        candidates=candidates[:5],
        options=options[:8],
        note=(None if size_pass else f"no match in {len(options)} options"),
    ))

    # --- Condition ---
    cond_raw = item.get("condition", "")
    vinted_cond = _map_condition(cond_raw)
    cond_pass = vinted_cond in _CONDITION_ID
    results.append(FieldResult(
        field="condition",
        requested=cond_raw[:50],
        passed=cond_pass,
        matched=vinted_cond,
    ))

    # --- Package size ---
    pkg = _map_package(item.get("item_type", ""))
    pkg_pass = pkg in ("Small", "Medium", "Large")
    results.append(FieldResult(
        field="package",
        requested=item.get("item_type", ""),
        passed=pkg_pass,
        matched=pkg,
    ))

    item_pass = all(r.passed for r in results)
    return item_pass, results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m~\033[0m"


def _format_category_root_cause(r: FieldResult) -> str:
    """Explain why category resolution failed."""
    raw = r.requested
    norm = _normalise_category(raw)
    lines = [f"    raw   : {raw!r}"]
    if norm != raw:
        lines.append(f"    norm  : {norm!r}")
    if raw in CATEGORY_ALIASES:
        lines.append(f"    alias → {CATEGORY_ALIASES[raw]!r}")
    elif norm in CATEGORY_ALIASES:
        lines.append(f"    alias (norm) → {CATEGORY_ALIASES[norm]!r}")
    else:
        lines.append("    not in CATEGORY_ALIASES")
    if raw not in CATEGORY_NAV and norm not in CATEGORY_NAV:
        lines.append("    not in CATEGORY_NAV directly")
    lines.append(f"    resolved: {r.matched!r}")
    if r.note:
        lines.append(f"    note  : {r.note}")
    return "\n".join(lines)


def run():
    print("=" * 70)
    print("  Draft Logic Validation — Offline Replay")
    print("=" * 70)

    all_pass = 0
    all_fail = 0
    failure_categories: dict[str, int] = {}

    item_results: list[tuple[dict, bool, list[FieldResult]]] = []
    for item in ITEMS:
        passed, results = validate_item(item)
        item_results.append((item, passed, results))
        if passed:
            all_pass += 1
        else:
            all_fail += 1

    # --- Per-item table ---
    print(f"\n{'Item':<28} {'Cat':^5} {'Size':^5} {'Cond':^5} {'Pkg':^5}  Result")
    print("-" * 70)
    for item, passed, results in item_results:
        rmap = {r.field: r for r in results}
        def sym(f):
            return PASS if rmap[f].passed else FAIL
        overall = PASS if passed else FAIL
        print(f"  {item['name']:<26} {sym('category'):^5} {sym('size'):^5} "
              f"{sym('condition'):^5} {sym('package'):^5}  {overall}")

    # --- Detailed failures ---
    any_failure = any(not p for _, p, _ in item_results)
    if any_failure:
        print("\n" + "=" * 70)
        print("  FAILURE DETAILS")
        print("=" * 70)
        for item, passed, results in item_results:
            if passed:
                continue
            print(f"\n  [{FAIL}] {item['name']} — {item['desc']}")
            for r in results:
                if r.passed:
                    continue
                failure_categories[r.field] = failure_categories.get(r.field, 0) + 1
                print(f"\n    Field: {r.field.upper()}")
                print(f"    Requested : {r.requested!r}")
                if r.field == "category":
                    print(_format_category_root_cause(r))
                else:
                    print(f"    Matched   : {r.matched!r}  (method: {r.method})")
                    if r.candidates:
                        print(f"    Candidates tried  : {r.candidates}")
                    if r.options:
                        print(f"    Visible options   : {r.options}")
                    if r.note:
                        print(f"    Note: {r.note}")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    total = all_pass + all_fail
    print(f"\n  Items: {total}  |  Pass: {all_pass}  |  Fail: {all_fail}")
    if failure_categories:
        print("\n  Failures by field:")
        for field, count in sorted(failure_categories.items(), key=lambda x: -x[1]):
            root = {
                "category": "category-related (aliases/fuzzy)",
                "size":     "dropdown option-matching",
                "condition": "condition selector",
                "package":  "package size selector",
            }.get(field, field)
            print(f"    {field:12s}: {count}  [{root}]")
    else:
        print("\n  No failures — all fields resolved correctly.")

    # --- Spot-check: normalisation edge cases ---
    print("\n" + "=" * 70)
    print("  SPOT-CHECKS — normalisation edge cases")
    print("=" * 70)
    checks = [
        ("Men > Clothing > Jeans > Straight fit jeans", None, "Men > Jeans > Straight"),
        ("Men > Activewear > Joggers", None, "Men > Trousers > Joggers"),
        ("Men > Suits & Blazers > Blazers", None, "Men > Suits > Blazers"),
        ("Men > Jeans > Tapered jeans", None, "Men > Jeans > Slim"),
        ("Women > Jeans > High-waisted jeans", None, "Women > Jeans > High waisted"),
        ("Men > Jeans > Regular fit jeans", None, "Men > Jeans > Straight"),
        ("Men > Jeans", "Slim", "Men > Jeans > Slim"),
        ("Men > Jeans", "Straight", "Men > Jeans > Straight"),
        # These should NOT resolve (no sensible Vinted mapping)
        ("Men > Pyjamas > Bottoms", None, None),
        # Leggings in Activewear correctly maps to Women > Trousers > Leggings
        ("Women > Activewear > Leggings", None, "Women > Trousers > Leggings"),
    ]
    spot_pass = spot_fail = 0
    for raw, style, expected in checks:
        got = _resolve_category_key(raw, style)
        ok = got == expected
        sym = PASS if ok else FAIL
        if ok:
            spot_pass += 1
        else:
            spot_fail += 1
        style_str = f" style={style!r}" if style else ""
        print(f"  {sym} {raw!r}{style_str}")
        if not ok:
            print(f"       expected {expected!r}, got {got!r}")

    print(f"\n  Spot-checks: {spot_pass} pass, {spot_fail} fail")
    print()
    return all_fail == 0 and spot_fail == 0


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
