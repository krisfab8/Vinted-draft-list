"""
Category validation service — pure functions, no Playwright.

Owns CATEGORY_NAV, CATEGORY_ALIASES, and the resolution logic that maps
AI-extracted category strings to real Vinted navigation paths.

Importing this module does NOT load Playwright. Use this for pre-flight
validation (e.g. in web.py) without triggering browser dependencies.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Listing category string -> Vinted navigation path
# (list of [role="button"] labels to click in sequence)
# All paths verified against vinted_categories.json scraped 2026-03-14
# ---------------------------------------------------------------------------
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
    "Men > T-shirts > Graphic":                 ["Men", "Clothing", "Tops & t-shirts", "T-shirts", "Print"],
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

# ---------------------------------------------------------------------------
# Category aliases — map raw AI-extracted strings to CATEGORY_NAV keys.
# ---------------------------------------------------------------------------
CATEGORY_ALIASES: dict[str, str] = {
    # ── Men: Jeans — full Vinted-label variants the AI echoes back ────────
    "Men > Jeans > Straight fit jeans":         "Men > Jeans > Straight",
    "Men > Jeans > Straight-fit jeans":         "Men > Jeans > Straight",
    "Men > Jeans > Straight jeans":             "Men > Jeans > Straight",
    "Men > Jeans > Slim fit jeans":             "Men > Jeans > Slim",
    "Men > Jeans > Slim-fit jeans":             "Men > Jeans > Slim",
    "Men > Jeans > Slim jeans":                 "Men > Jeans > Slim",
    "Men > Jeans > Skinny jeans":               "Men > Jeans > Skinny",
    "Men > Jeans > Ripped jeans":               "Men > Jeans > Ripped",
    # ── Men: Jeans — tapered/relaxed/regular AI variants → closest Vinted type
    "Men > Jeans > Tapered jeans":              "Men > Jeans > Slim",
    "Men > Jeans > Tapered":                    "Men > Jeans > Slim",
    "Men > Jeans > Tapered fit jeans":          "Men > Jeans > Slim",
    "Men > Jeans > Relaxed jeans":              "Men > Jeans > Straight",
    "Men > Jeans > Relaxed fit jeans":          "Men > Jeans > Straight",
    "Men > Jeans > Regular jeans":              "Men > Jeans > Straight",
    "Men > Jeans > Regular fit jeans":          "Men > Jeans > Straight",
    "Men > Jeans > Bootcut jeans":              "Men > Jeans > Straight",
    "Men > Jeans > Bootcut":                    "Men > Jeans > Straight",
    "Men > Jeans > Wide leg jeans":             "Men > Jeans > Straight",
    "Men > Jeans > Wide-leg jeans":             "Men > Jeans > Straight",
    # ── Men: Jeans — top-level shortcuts (no sub-path) ───────────────────
    "Men > Straight jeans":                     "Men > Jeans > Straight",
    "Men > Straight-leg jeans":                 "Men > Jeans > Straight",
    "Men > Slim jeans":                         "Men > Jeans > Slim",
    "Men > Slim-fit jeans":                     "Men > Jeans > Slim",
    "Men > Tapered jeans":                      "Men > Jeans > Slim",
    "Men > Skinny jeans":                       "Men > Jeans > Skinny",
    "Men > Ripped jeans":                       "Men > Jeans > Ripped",
    # ── Women: Jeans — full Vinted-label variants ─────────────────────────
    "Women > Jeans > Straight fit jeans":       "Women > Jeans > Straight",
    "Women > Jeans > Straight-fit jeans":       "Women > Jeans > Straight",
    "Women > Jeans > Straight jeans":           "Women > Jeans > Straight",
    "Women > Jeans > Slim fit jeans":           "Women > Jeans > Slim",
    "Women > Jeans > Slim-fit jeans":           "Women > Jeans > Slim",
    "Women > Jeans > Slim jeans":               "Women > Jeans > Slim",
    "Women > Jeans > Boyfriend jeans":          "Women > Jeans > Boyfriend",
    "Women > Jeans > Cropped jeans":            "Women > Jeans > Cropped",
    "Women > Jeans > Flared jeans":             "Women > Jeans > Flared",
    "Women > Jeans > High waisted jeans":       "Women > Jeans > High waisted",
    "Women > Jeans > High-waisted jeans":       "Women > Jeans > High waisted",
    "Women > Jeans > Skinny jeans":             "Women > Jeans > Skinny",
    "Women > Jeans > Ripped jeans":             "Women > Jeans > Ripped",
    "Women > Jeans > Tapered jeans":            "Women > Jeans > Straight",
    "Women > Jeans > Relaxed jeans":            "Women > Jeans > Straight",
    "Women > Jeans > Regular fit jeans":        "Women > Jeans > Straight",
    "Women > Jeans > Bootcut jeans":            "Women > Jeans > Straight",
    # ── Men: Trousers — alternate labels ─────────────────────────────────
    "Men > Trousers > Tracksuit Bottoms":       "Men > Trousers > Joggers",
    "Men > Trousers > Track Pants":             "Men > Trousers > Joggers",
    "Men > Trousers > Sweatpants":              "Men > Trousers > Joggers",
    "Men > Trousers > Running Pants":           "Men > Trousers > Joggers",
    # ── Women: Trousers — alternate labels ───────────────────────────────
    "Women > Trousers > Track Pants":           "Women > Trousers > Joggers",
    "Women > Trousers > Tracksuit Bottoms":     "Women > Trousers > Joggers",
    "Women > Trousers > Sweatpants":            "Women > Trousers > Joggers",
    "Women > Trousers > Running Pants":         "Women > Trousers > Joggers",
    "Men > Trousers > Cargos":                  "Men > Trousers > Cargo",
    "Men > Trousers > Tailored trousers":       "Men > Trousers > Tailored",
    "Men > Trousers > Chino trousers":          "Men > Trousers > Chinos",
    # ── Men: Tops ─────────────────────────────────────────────────────────
    "Men > T-shirts & Tops":                    "Men > T-shirts",
    "Men > Tops":                               "Men > T-shirts",
    "Men > Tops > T-shirt":                     "Men > T-shirts",
    "Men > T-shirts > Print":                   "Men > T-shirts > Graphic",
    "Men > T-shirts > Printed":                 "Men > T-shirts > Graphic",
    "Men > T-shirts > Graphic tee":             "Men > T-shirts > Graphic",
    "Men > T-shirts > Graphic print":           "Men > T-shirts > Graphic",
    "Men > T-shirts > Band tee":                "Men > T-shirts > Graphic",
    "Men > T-shirts > Slogan":                  "Men > T-shirts > Graphic",
    "Men > Tops > Polo":                        "Men > Polo Shirts",
    # ── Men: Knitwear ─────────────────────────────────────────────────────
    "Men > Jumpers & Sweaters":                 "Men > Knitwear",
    "Men > Jumpers":                            "Men > Knitwear",
    "Men > Sweaters":                           "Men > Knitwear",
    "Men > Knitwear > Jumper":                  "Men > Knitwear",
    # ── Men: Outerwear — path variants ───────────────────────────────────
    "Men > Outerwear > Coats":                  "Men > Coats",
    "Men > Outerwear > Coats > Overcoat":       "Men > Coats > Overcoat",
    "Men > Outerwear > Coats > Trench":         "Men > Coats > Trench",
    "Men > Outerwear > Coats > Parka":          "Men > Coats > Parka",
    "Men > Outerwear > Jackets":                "Men > Jackets",
    "Men > Outerwear > Jackets > Bomber":       "Men > Jackets > Bomber",
    "Men > Outerwear > Jackets > Puffer":       "Men > Jackets > Puffer",
    "Men > Outerwear > Jackets > Denim":        "Men > Jackets > Denim",
    "Men > Outerwear":                          "Men > Jackets",
    # ── Women: Outerwear — path variants ─────────────────────────────────
    "Women > Outerwear > Coats":                "Women > Coats",
    "Women > Outerwear > Coats > Overcoat":     "Women > Coats > Overcoat",
    "Women > Outerwear > Coats > Trench":       "Women > Coats > Trench",
    "Women > Outerwear > Jackets":              "Women > Jackets",
    "Women > Outerwear":                        "Women > Jackets",
    # ── Men: Suits ────────────────────────────────────────────────────────
    "Men > Suits & Blazers > Blazers":          "Men > Suits > Blazers",
    "Men > Suits & Blazers > Waistcoats":       "Men > Suits > Waistcoats",
    "Men > Suits & Blazers > Trousers":         "Men > Suits > Trousers",
    "Men > Suits & Blazers":                    "Men > Suits > Blazers",
    # ── Women: Suits ──────────────────────────────────────────────────────
    "Women > Suits & Blazers > Blazers":        "Women > Suits > Blazers",
    "Women > Suits & Blazers":                  "Women > Suits > Blazers",
}


def _normalise_category(category: str) -> str:
    """Strip AI-hallucinated middle segments the model sometimes inserts.

    e.g. "Men > Clothing > Trousers > Joggers" → "Men > Trousers > Joggers"
         "Women > Activewear > Trousers"        → "Women > Trousers"
    """
    parts = [p.strip() for p in category.split(">")]
    stripped = [p for p in parts if p not in ("Clothing", "Activewear")]
    return " > ".join(stripped)


def resolve_category_key(raw: str, style: str | None = None) -> str | None:
    """Resolve a raw extracted category string to a CATEGORY_NAV key.

    Resolution order:
    1. Style-qualified lookup  ("Men > Jeans" + style "Slim" → "Men > Jeans > Slim")
    2. CATEGORY_ALIASES exact lookup (raw or normalised)
    3. CATEGORY_NAV direct lookup   (raw or normalised)
    4. Fuzzy: last-segment containment match against same-gender nav keys

    Returns the canonical CATEGORY_NAV key, or None if unresolvable.
    """
    norm = _normalise_category(raw)

    def _try(key: str) -> str | None:
        if style:
            for styled in (f"{key} > {style}", f"{key} > {style.title()}"):
                if styled in CATEGORY_ALIASES:
                    return CATEGORY_ALIASES[styled]
                if styled in CATEGORY_NAV:
                    return styled
        if key in CATEGORY_ALIASES:
            return CATEGORY_ALIASES[key]
        if key in CATEGORY_NAV:
            return key
        return None

    canonical = _try(norm) or _try(raw)
    if canonical:
        _STYLE_TERMINALS = {"plain", "graphic"}
        if style:
            canon_parts = [p.strip() for p in canonical.split(">")]
            if (len(canon_parts) >= 2
                    and canon_parts[-1].lower() in _STYLE_TERMINALS
                    and canon_parts[-1].lower() != style.lower()):
                base_key = " > ".join(canon_parts[:-1])
                for styled in (f"{base_key} > {style}", f"{base_key} > {style.title()}"):
                    if styled in CATEGORY_ALIASES:
                        canonical = CATEGORY_ALIASES[styled]
                        break
                    if styled in CATEGORY_NAV:
                        canonical = styled
                        break

        if style and canonical not in (norm, raw):
            for styled in (f"{canonical} > {style}", f"{canonical} > {style.title()}"):
                if styled in CATEGORY_ALIASES:
                    canonical = CATEGORY_ALIASES[styled]
                    break
                if styled in CATEGORY_NAV:
                    canonical = styled
                    break
        return canonical

    # Fuzzy: last-segment containment match against same-gender nav keys
    parts = [p.strip() for p in norm.split(">")]
    if len(parts) >= 2:
        gender = parts[0].lower()
        last_raw = parts[-1].lower()
        for key in CATEGORY_NAV:
            kparts = [p.strip() for p in key.split(">")]
            if kparts[0].lower() != gender:
                continue
            klast = kparts[-1].lower()
            if klast not in last_raw and not last_raw.startswith(klast):
                continue
            if len(parts) >= 3 and len(kparts) >= 3:
                mid = parts[-2].lower()
                kmid = kparts[-2].lower()
                if kmid not in mid and mid not in kmid:
                    continue
            return key

    return None
