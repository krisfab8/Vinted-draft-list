"""Stable buyer-facing details from saved facts, without another model call."""
import re


def size_text(listing):
    tagged = str(listing.get('tagged_size') or '').strip()
    normalized = str(listing.get('normalized_size') or '').strip()
    if tagged and normalized and tagged != normalized:
        from app.listing_writer import _TAILORING_KEYWORDS, _EU_TO_UK, _EU_TO_UK_SHOE, _is_shoe_item
        kind = (listing.get('item_type') or '').lower()
        eu = re.fullmatch(r'(?:EU\s*)?(\d{2})', tagged, re.I)
        if eu:
            number = int(eu.group(1))
            uk = re.sub(r'^UK\s*', '', normalized, flags=re.I)
            tailoring = any(word in kind for word in _TAILORING_KEYWORDS)
            if ((tailoring and number in _EU_TO_UK and uk == f'{_EU_TO_UK[number]}R')
                    or (_is_shoe_item(kind) and number in _EU_TO_UK_SHOE
                        and uk == str(_EU_TO_UK_SHOE[number]))):
                return f'UK {uk} / EU {number} (label)'
        return f'{normalized} (equivalent); {tagged} (label)'
    return normalized or tagged


def recover_tag(listing):
    """Recover a legacy tailoring tag only from an explicit saved Size keyword."""
    from app.listing_writer import _TAILORING_KEYWORDS, _EU_TO_UK
    kind = (listing.get('item_type') or '').lower()
    normalized = listing.get('normalized_size')
    if listing.get('tagged_size') != normalized or not any(word in kind for word in _TAILORING_KEYWORDS): return
    for value in listing.get('tag_keywords') or []:
        match = re.fullmatch(r'Size\s+(?:EU\s*)?(\d{2})', str(value), re.I)
        if match and f'{_EU_TO_UK.get(int(match[1]))}R' == normalized:
            listing['tagged_size'] = match[1]
            return


def apply(listing):
    """Normalize generated descriptions; editing a saved draft does not call this."""
    from app.services.garment_text import detail
    desc = listing.get('description') or ''
    listing['description_layout_version'] = 'dash-details-v1'
    # Keep opening prose, other useful bullets, keywords and confirmed measurements.
    # Rebuild only these labelled details, so contradictory/duplicate size lines disappear.
    managed = r'(?:Size|Made in|Fabric mill|Fabric line|Cloth|Fit|Model|Material|Materials|Logo / print)'
    desc = re.sub(r'[^\S\n]+([-•]\s*'+managed+r'\s*:)', r'\n\1', desc, flags=re.I)
    remaining = re.sub(r'(?mi)^\s*[-•]?\s*'+managed+r'\s*:[^\n]*', '', desc)
    remaining = re.sub(r'\n{3,}', '\n\n', remaining).strip()
    fields = [('Size', size_text(listing)), ('Made in', listing.get('made_in')),
              ('Fabric mill', listing.get('fabric_mill')), ('Fabric line', listing.get('fabric_line')),
              ('Fit', listing.get('cut')), ('Model', listing.get('model_name')),
              ('Material', ', '.join(listing.get('materials') or [])),
              ('Logo / print', detail(listing))]
    details = '\n'.join(f'- {label}: {value}' for label, value in fields if value)
    if not details:
        listing['description'] = remaining
        return listing
    lines = remaining.splitlines()
    index = next((i for i, line in enumerate(lines)
                  if re.match(r'^\s*(?:[-•]|Keywords:|Measurements\b)', line, re.I)), len(lines))
    opening = '\n'.join(lines[:index]).strip()
    tail = '\n'.join(lines[index:]).strip()
    listing['description'] = '\n\n'.join(part for part in (opening, details, tail) if part)
    return listing
