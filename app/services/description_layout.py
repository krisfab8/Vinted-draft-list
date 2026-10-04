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


def apply(listing):
    """Normalize generated descriptions; editing a saved draft does not call this."""
    desc = listing.get('description') or ''
    # Keep opening prose, other useful bullets, keywords and confirmed measurements.
    # Rebuild only these labelled details, so contradictory/duplicate size lines disappear.
    managed = r'(?:Size|Made in|Fabric mill|Fabric line|Cloth|Fit|Model|Material|Materials)'
    desc = re.sub(r'[^\S\n]+([-•]\s*'+managed+r'\s*:)', r'\n\1', desc, flags=re.I)
    remaining = re.sub(r'(?mi)^\s*[-•]?\s*'+managed+r'\s*:[^\n]*', '', desc)
    remaining = re.sub(r'\n{3,}', '\n\n', remaining).strip()
    fields = [('Size', size_text(listing)), ('Made in', listing.get('made_in')),
              ('Fabric mill', listing.get('fabric_mill')), ('Fabric line', listing.get('fabric_line')),
              ('Fit', listing.get('cut')), ('Model', listing.get('model_name')),
              ('Material', ', '.join(listing.get('materials') or []))]
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
