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
    return evidence


def apply(listing, item):
    uncertain = set(item.get('low_confidence_fields') or [])
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
    additions = []
    size = listing.get('normalized_size') or listing.get('tagged_size')
    if size and not re.search(r'\bsize\s*:?[ \t]*'+re.escape(str(size))+r'(?![a-z0-9])',desc,re.I):
        additions.append('- Size: '+str(size))
    materials = listing.get('materials') or []
    if item.get('material_confidence') == 'high' and materials and not all(str(value).lower() in desc.lower() for value in materials):
        additions.append('- Material: '+', '.join(materials))
    if additions:
        listing['description'] = desc.rstrip()+'\n\n'+'\n'.join(additions)
    return listing
