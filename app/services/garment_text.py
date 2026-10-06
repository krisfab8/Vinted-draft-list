"""Preserve readable garment markings without treating them as the maker."""
import re
from copy import deepcopy


def normalize(values):
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values[:20]:
        if not isinstance(value, dict):
            continue
        text = value.get('text')
        if not isinstance(text, str) or not text.strip():
            continue
        text = re.sub(r'\s+', ' ', text).strip()[:500]
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        location = value.get('location')
        location = re.sub(r'\s+', ' ', location).strip()[:100] if isinstance(location, str) else ''
        confidence = value.get('confidence')
        result.append(dict(text=text, location=location,
                           confidence=confidence if confidence in {'high', 'medium', 'low'} else 'low'))
    return result


def carry(listing, item):
    """The vision evidence owns these words, even if the writer omits them."""
    values = normalize(item.get('garment_text'))
    if values or 'garment_text' in item:
        listing['garment_text'] = deepcopy(values)
    if any(value['confidence'] != 'high' for value in values):
        fields = set(listing.get('low_confidence_fields') or [])
        fields.add('garment_text')
        listing['low_confidence_fields'] = sorted(fields)
    return listing


def detail(listing):
    values = normalize(listing.get('garment_text'))
    return '; '.join('“'+value['text']+'”'+(' ('+value['location']+')' if value['location'] else '')
                     for value in values if value['confidence'] == 'high')
