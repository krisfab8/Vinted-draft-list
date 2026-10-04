"""Confirmed selling points shared by titles and comparison searches; no model calls."""
import re
from app.services.fabric_mill import normalise_mill, _CANONICAL_MILLS


def tokens(text):
    # Super 100's / Super100 / Super 100s share one comparison form.
    text = re.sub(r"\bsuper\s*(\d{2,3})\s*['’]?s?\b", r'super \1', str(text or ''), flags=re.I)
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def confirmed_terms(item):
    uncertain = set(item.get('low_confidence_fields') or [])
    terms = []
    mill = normalise_mill(item.get('fabric_mill'))
    if mill in set(_CANONICAL_MILLS.values()) and 'fabric_mill' not in uncertain and item.get('fabric_mill_confidence') != 'low':
        terms.append(mill)
    materials = item.get('materials') or []
    if item.get('material_confidence') == 'high' and not {'material', 'materials'} & uncertain:
        shell = ' '.join(str(m) for m in materials if 'lining' not in str(m).lower())
        for fibre in ('cashmere', 'vicuna', 'angora', 'alpaca', 'mohair', 'merino wool', 'lambswool', 'silk', 'linen', 'wool', 'leather', 'down', 'tweed'):
            if tokens(fibre) <= tokens(shell):
                term = fibre.title()
                if fibre == 'cashmere' and any(re.search(r'\b(?:[1-9]\d?(?:\.\d+)?)%\s*cashmere\b', str(m), re.I) for m in materials):
                    term = 'Cashmere Blend'
                terms.append(term)
                break
    evidence = []
    if item.get('tag_keywords_confidence') == 'high' and 'tag_keywords' not in uncertain:
        evidence.extend(item.get('tag_keywords') or [])
    if item.get('fabric_line') and 'fabric_line' not in uncertain:
        evidence.append(item['fabric_line'])
    for value in evidence:
        for grade in re.findall(r"\bsuper\s*(\d{2,3})\s*['’]?s?\b", str(value), re.I):
            term = f'Super {grade}s'
            if term not in terms: terms.append(term)
    if item.get('tag_keywords_confidence') == 'high' and any('full canvas' in str(v).lower() for v in evidence):
        terms.append('Full Canvas')
    return terms


def ensure_title(listing, evidence=None):
    """Only call for generated copy; caller protects seller-edited titles."""
    terms = confirmed_terms(evidence or listing)
    title = listing.get('title') or ''
    missing = [term for term in terms if not tokens(term) <= tokens(title)]
    if not missing: return listing
    # Cloth-maker context distinguishes a Boggi garment from a Loro Piana garment.
    mill = normalise_mill((evidence or listing).get('fabric_mill'))
    additions = [term + ' cloth' if term == mill and tokens(mill) != tokens(listing.get('brand')) else term for term in missing]
    candidate = ' '.join([title, *additions]).strip()
    if len(candidate) > 120:
        required = [listing.get('brand'), listing.get('item_type'), *[term + ' cloth' if term == mill and tokens(mill) != tokens(listing.get('brand')) else term for term in terms], listing.get('normalized_size') or listing.get('tagged_size')]
        candidate = ' '.join(str(v) for v in required if v)
        for optional in (listing.get('colour'), listing.get('gender')):
            if optional and len(candidate) + len(str(optional)) + 1 <= 120: candidate += ' ' + str(optional)
    if len(candidate) <= 120:
        listing['title'] = candidate
    else:
        listing.setdefault('warnings', []).append('premium_title_needs_review')
    return listing
