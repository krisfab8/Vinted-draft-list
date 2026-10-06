"""Deterministic copy checks; preserve review evidence without confident guesses."""
import re
from copy import deepcopy


def writer_evidence(item):
    evidence = deepcopy(item)
    uncertain = set(item.get('low_confidence_fields') or [])
    for field in ('pattern', 'colour_secondary', 'model_name'):
        if field in uncertain:
            evidence[field] = None
    if item.get('model_confidence') == 'low':
        evidence['model_name'] = None
    if item.get('tag_keywords_confidence') != 'high':
        evidence['tag_keywords'] = []
    from app.services.garment_text import normalize
    if 'garment_text' in item:
        evidence['garment_text'] = [v for v in normalize(item['garment_text']) if v['confidence'] == 'high']
    return evidence


def apply(listing, item):
    uncertain = set(item.get('low_confidence_fields') or [])
    from app.services.garment_text import normalize
    for marking in normalize(item.get('garment_text')):
        if marking['confidence'] != 'high':
            for field in ('title', 'description'):
                listing[field] = re.sub(re.escape(marking['text']), '', listing.get(field) or '', flags=re.I).strip()
    candidate = item.get('size_reading_candidate')
    if candidate and not (item.get('tagged_size') or item.get('normalized_size')):
        for field in ('title', 'description'):
            text = listing.get(field) or ''
            text = re.sub(r'\b(?:UK|EU|size)\s*:?\s*'+re.escape(str(candidate))+r'(?![a-z0-9])', '', text, flags=re.I)
            listing[field] = re.sub(r'[ \t]+', ' ', text).strip()
    if item.get('material_reading_candidate') and not item.get('materials'):
        for field in ('title', 'description'):
            text = listing.get(field) or ''
            text = re.sub(r'\b(?:\d+(?:\.\d+)?%\s*)?(?:wool|cashmere|cotton|polyester|polyamide|silk|linen|nylon|elastane|spandex|acrylic|viscose|modal|lyocell|angora|alpaca|mohair)\b', '', text, flags=re.I)
            listing[field] = re.sub(r'[ \t]+', ' ', text).strip()
    if 'pattern' in uncertain and item.get('pattern'):
        value = re.escape(str(item['pattern']))
        for field in ('title', 'description'):
            text = listing.get(field) or ''
            text = re.sub(r'\b(?:with\s+)?'+value+r'(?:\s+(?:detailing|pattern|print|design))?\b', '', text, flags=re.I)
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r' +([.,])', r'\1', text)
            listing[field] = text.strip()
        listing['pattern'] = None
    if 'pattern' in uncertain and listing.get('style') == item.get('pattern'):
        listing['style'] = None
    summary = item.get('condition_summary') or listing.get('condition_summary') or ''
    summary = re.sub(r'\s+(?:from|due to) storage\b', '', summary, flags=re.I)
    summary = re.sub(r';?\s*no (?:holes|tears|stains)[^.;]*(?:[.;]|$)', '', summary, flags=re.I)
    listing['condition_summary'] = summary.strip(' ;')
    desc = listing.get('description') or ''
    # Strong condition assurances are not established by a few photos.
    desc = re.sub(r'\b(?:Immaculate|Pristine|Mint) condition[.!]?\s*', '', desc, flags=re.I)
    brand = listing.get('brand')
    if brand:
        desc = re.sub(r'^(?:Excellent|Immaculate|Pristine)\s+(?='+re.escape(str(brand))+r'\b)', '', desc, flags=re.I)
    additions = []
    size = listing.get('normalized_size') or listing.get('tagged_size')
    tagged = listing.get('tagged_size')
    if tagged and size and str(tagged) != str(size):
        # Distinguish printed label and conversion in one generated size line.
        variants = re.escape(str(tagged))+'(?:\\s*\\(EU\\))?|'+re.escape(str(size))
        desc = re.sub(r'(?mi)^[ \t]*[-•]?[ \t]*Size:[ \t]*(?:'+variants+r')[.!]?[ \t]*$', '', desc)
        from app.services.description_layout import size_text
        size_line = '- Size: ' + size_text(listing)
        if size_line not in desc:
            additions.append(size_line)
    elif size and not re.search(r'\bsize\s*:?[ \t]*'+re.escape(str(size))+r'(?![a-z0-9])',desc,re.I):
        additions.append('- Size: '+str(size))
    materials = listing.get('materials') or []
    if item.get('material_confidence') == 'high' and materials and not all(str(value).lower() in desc.lower() for value in materials):
        additions.append('- Material: '+', '.join(materials))
    listing['description'] = desc.rstrip() + ('\n\n'+'\n'.join(additions) if additions else '')
    return listing
