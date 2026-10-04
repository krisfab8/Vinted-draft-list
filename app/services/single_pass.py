"""One vision response, then evidence-based copy and the existing finalizer.

Rereads may still be needed for unclear labels; those remain in the usage ledger.
No paid writer fallback or claim of researched prices is made here.
"""
import json
import time
from app.config import PROMPTS_DIR


def build_prompt(hints):
    categories = list(dict.fromkeys(line.split('->', 1)[1].strip()
                     for line in (PROMPTS_DIR / 'category_rules.md').read_text().splitlines()
                     if '->' in line and not line.startswith('#')))
    return '''Read the clothing photos and return one compact JSON object, no markdown.
Seller hints override extraction. Use visible evidence only; unknown text stays null.
Read the brand label letter by letter. Manufacturer = brand; model/fit/collection =
model_name or sub_brand. Merge compound brand lines. Fabric mills (VBC, Reda,
Lanificio, Tessuti Sondrio, Scabal, Dormeuil, cloth-supplier Loro Piana) are NOT
the garment brand: store in fabric_mill; preserve fabric_line and material_hint.
Two leg openings = trousers/jeans/shorts; collar + short placket = polo shirt.
Read EVERY composition line with EXACT percentages including lining/shell.
Translate multilingual fibre names once, preserve minor fibres, do not guess
missing percentages or infer materials from appearance. No care instructions
in materials. Only explicit garment Made in X proves origin; cloth origin does not.
Preserve tagged_size exactly. normalized_size keeps letter sizes, visible W/L,
bare EU tailoring sizes; shoes use printed UK size if present, otherwise EU.
Do not infer chest sizes or ruler measurements; those are handled separately.
Assess body colour/pattern rather than logos; exclude uncertain features from copy.
condition_summary reports visible condition only; no invented storage history
or assurances of no damage. Seller damages/condition are authoritative.
Brand/material confidence is high only for fully readable labels, medium for
partial reads, low for missing/unreadable. Give brief reasons and candidates
only where genuinely ambiguous; mark uncertain field names in low_confidence_fields.
Include fields: brand, brand_confidence, brand_reason, brand_candidates, sub_brand,
model_name, item_type, tagged_size, normalized_size, trouser_waist, trouser_length,
materials (array of strings), material_confidence, material_reason,
material_candidates, pricing_sensitive_material (boolean), fabric_mill,
fabric_line, material_hint, made_in, colour, colour_secondary, pattern, style,
cut, gender (men's/women's/unisex), condition_summary, flaws_note,
tag_keywords (visible label terms only), tag_keywords_confidence (high/low),
confidence (0 to 1), low_confidence_fields (array), category, price_gbp.
Use null for unknown optional text and [] for empty arrays. Missing brand/material
evidence must be low confidence, never default high. Be concise; no repeated prose.
price_gbp is a tentative nonnegative GBP asking price, not a researched sale value.
Choose category from these permitted paths; mark category uncertain if ambiguous:
''' + json.dumps(categories, separators=(',', ':')) + '\nSeller hints: ' + json.dumps(hints)


def assemble(item, hints):
    from app import listing_writer
    from app.services.copy_quality import writer_evidence
    started = time.perf_counter()
    # Work from the corrected evidence AFTER any field reread, so the copy cannot
    # retain an old brand, model or material from the first response.
    evidence = writer_evidence(item)
    listing = {k: v for k, v in evidence.items() if not k.startswith('_')}
    for hint, field in (('brand', 'brand'), ('size', 'normalized_size'),
                        ('gender', 'gender'), ('made_in', 'made_in'), ('item_type', 'item_type')):
        if hints.get(hint):
            listing[field] = hints[hint]
    if hints.get('size'):
        listing['tagged_size'] = hints['size']
    if hints.get('damages'):
        listing['flaws_note'] = hints['damages']
    if hints.get('condition_summary'):
        listing['condition_summary'] = hints['condition_summary']
    # Missing required type/category/price deliberately fails validation, rather
    # than inventing a usable-looking listing or silently paying for another call.
    listing.setdefault('tagged_size', None)
    listing.setdefault('normalized_size', None)
    listing.setdefault('brand', None)
    listing = listing_writer._convert_eu_suit_size(listing)
    listing = listing_writer._convert_eu_shoe_size(listing)
    gender = {'men\'s': 'Mens', 'women\'s': 'Womens', 'unisex': 'Unisex'}.get(listing.get('gender'), '')
    parts = [listing.get('brand'), listing.get('model_name'), listing.get('colour'),
             listing.get('item_type'), gender, listing.get('normalized_size')]
    listing['title'] = ' '.join(str(p) for p in parts if p)[:120].strip()
    lines = [listing['title'] + '.']
    for label, field in (('Size', 'normalized_size'), ('Made in', 'made_in'),
                         ('Fabric mill', 'fabric_mill'), ('Fabric line', 'fabric_line'), ('Fit', 'cut')):
        if listing.get(field):
            lines.append(f'- {label}: {listing[field]}')
    if listing.get('material_confidence') == 'high' and listing.get('materials'):
        lines.append('- Material: ' + ', '.join(listing['materials']))
    keywords = listing.get('tag_keywords') or []
    if keywords:
        lines.append('Keywords: ' + ', '.join(keywords) + '.')
    listing['description'] = '\n'.join(lines)
    # Conversion above is idempotent for already normalized UK values.
    listing = listing_writer.finalize_listing(listing, item, hints)
    listing['pipeline_version'] = 'single-pass-v1'
    return listing, {'input_tokens': 0, 'output_tokens': 0, 'model': 'deterministic-copy',
                     'calls': [], 'cost_complete': True, '_write_log': {
                         'prompt_version': 'single-pass-v1', 'prompt_chars': 0,
                         'write_latency_ms': round((time.perf_counter() - started) * 1000)}}
