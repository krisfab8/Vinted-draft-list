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
    summary = listing.get('condition_summary') or ''
    summary = re.sub(r'\s+(?:from|due to) storage\b', '', summary, flags=re.I)
    summary = re.sub(r';?\s*no (?:holes|tears|stains)[^.;]*(?:[.;]|$)', '', summary, flags=re.I)
    listing['condition_summary'] = summary.strip(' ;')
    return listing
