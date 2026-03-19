# Title Format

**Structure:** `[Brand] [ItemType] [Mens/Womens] [Size] [Colour] [Material] [KeyStyle] [Fit]`

- Max **70 characters** — be ruthless, cut filler words ("in", "with", "a", "the")
- No punctuation in title
- Write "Mens" / "Womens" (no apostrophe) based on gender:
  - men's → "Mens"
  - women's → "Womens"
  - unisex → omit
- Size: write the UK size directly, no "size" prefix — e.g. "M", "W32 L32", "44R"
- Colour: use standardised colour (see Colour Standards below)
- Material: include ONLY if premium/sellable (cashmere, silk, angora, alpaca, mohair, merino, wool, lambswool, linen, waxed, down, leather, tweed, corduroy)
- KeyStyle: include ONE synonym from the Item Synonyms list below
- Fit: include if visible (Slim Fit, Regular Fit, Tailored Fit) — omit if unknown

**Examples:**
```
Barbour Shirt Mens M Navy Cotton Button Down
Suit Supply Trousers Mens W32 L32 Grey Wool Slim Fit
Ermenegildo Zegna Blazer Mens 44R Charcoal Wool Cashmere
John Smedley Jumper Mens M Navy Merino Rollneck
Brora Jumper Womens 12 Oatmeal Lambswool Rollneck
Barbour Jacket Mens C42 Olive Waxed Cotton
```

**Shoe title format:** `Brand + Model name (if on tag) + Colour + Type + UK Size`
```
Nike Air Force 1 White Trainers UK 9
Loake Chelsea Boots Tan Leather UK 9
Clarks Desert Boots Sand Suede UK 8
Church Oxford Brogues Burgundy UK 10
```
- Always end with `UK [size]` — buyers search by UK size
- Include model name only if clearly printed on the tag (e.g. "Air Force 1", "Desert Boot")
- No W/L format for shoes
- Material (leather, suede, canvas) only if premium or relevant

# Item Type Synonyms

Add the most relevant synonym to the title (one only, pick the most searchable):

| Item type | Synonym to add |
|---|---|
| shirt | Button Down |
| casual shirt | Button Down |
| formal shirt | Dress Shirt |
| jacket | Coat |
| wax jacket | Waxed Jacket |
| fleece | Pullover |
| jumper | Sweater |
| knitwear | Knit |
| trousers | Trousers |
| jeans | Denim |
| shorts | Shorts |
| suit jacket / blazer | Blazer |
| coat | Overcoat |
| gilet | Gilet |
| polo shirt | Polo |
| track pants / joggers / sweatpants | Joggers |
| trainers / sneakers / running shoes | Trainers |
| chelsea boots | Chelsea Boots |
| ankle boots | Ankle Boots |
| brogue shoes / oxford shoes / derby shoes | Brogues |
| loafers | Loafers |
| court shoes / heels / pumps | Heels |
| sandals / espadrilles | Sandals |

# Colour Standards

Normalise all colours to these standard names in title and description:

| Raw colour | Standardised |
|---|---|
| navy blue, dark blue, navy | Navy |
| light blue, sky blue, pale blue | Blue |
| dark green, forest green | Dark Green |
| olive, khaki green | Olive |
| beige, sand, stone, camel | Beige |
| dark grey, charcoal grey | Charcoal |
| light grey, heather grey | Grey |
| mid grey | Grey |
| dark brown | Brown |
| tan, light brown | Tan |
| off white, cream, ivory | Cream |
| white | White |
| black | Black |
| burgundy, wine, deep red | Burgundy |
| red | Red |
| pink | Pink |
| yellow, mustard | Yellow |

# Description Format

Short opening sentence (what it is, brand, colour).
Key features in short bullet lines:
- material
- notable detail (e.g. corduroy collar, patch pockets)
- Made in [Country] if known
- fabric mill name if known (e.g. "Tessuti Sondrio cloth" — buyers search for these)
- Flaw bullet ONLY if there is visible damage: one plain line, e.g. "Small mark on left sleeve." Do NOT add a flaw line if there is no damage.

Do NOT restate the condition (no "Good used condition", "Excellent condition", "No visible damage", or similar phrases) — the condition is shown separately as a structured field.

Measurements in photos.
Fast postage.

**Keyword sentence (always append at end of description):**
`Keywords: [brand] [item type] [colour] [size] mens/womens clothing [material if notable] casual smart designer`

Example: `Keywords: barbour shirt navy mens shirt cotton button down casual designer`

# Description Examples

**Men's:**
```
Barbour Oxford shirt in navy cotton.

- Mens size M
- 100% cotton
- Button down collar

Measurements in photos.
Fast postage.

Keywords: barbour shirt navy mens shirt cotton button down casual designer
```

**Women's:**
```
Brora lambswool rollneck in oatmeal.

- Womens size 12
- 100% lambswool
- Ribbed collar and cuffs

Measurements in photos.
Fast postage.

Keywords: brora jumper oatmeal womens jumper lambswool sweater knit casual designer
```

**Shoes:**
```
Loake 1880 Chelsea boots in tan leather.

- Mens UK size 9
- Full leather upper and sole
- Made in England

Photos show soles and heel condition.
Fast postage.

Keywords: loake chelsea boots tan mens boots leather uk 9 smart casual designer
```

**With damage:**
```
Hugo Boss blazer in charcoal wool.

- Mens size 44R
- 80% wool 20% polyester
- Small mark on left lapel.

Measurements in photos.
Fast postage.

Keywords: hugo boss blazer charcoal mens blazer wool slim fit casual smart designer
```

# Tone
Concise, clean, non-hype.

# Rules
- Title max **70 characters** (shorter than old 80 — be concise).
- Do not use ALL CAPS.
- Do not use "rare", "stunning", "amazing", "perfect" unless objectively accurate.
- Condition is a SEPARATE STRUCTURED FIELD — do NOT repeat it in the description body.
- Never use phrases like "Good used condition", "Excellent condition", "no visible damage", "no holes or stains" in the description text.
- Only mention damage in the description if flaws_note is set — add a single plain bullet (e.g. "Small mark on left sleeve.").
- The condition_summary field must use one of these exact phrases:
  - "New with tags — original labels attached."
  - "New without tags — unworn, no original tags."
  - "Excellent used condition — [brief note]."
  - "Very good used condition — [brief note]."
  - "Good used condition — [brief note]."
- Default condition_summary is "Very good used condition" unless photos show clear damage (then "Good used condition") or item looks nearly new (then "Excellent used condition").
- For trousers/jeans/shorts: ALWAYS show waist + length as "W32 L32". Never use a bare EU number.
- For suits/blazers with bare EU number (e.g. "54"): convert to UK by subtracting 10, add R. EU 54 → UK 44R.
- For shoes: ALWAYS end the title with "UK [size]" (e.g. "UK 9"). Never use W/L for shoes.
