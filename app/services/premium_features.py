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


# Care/handling wording on a tag is not a selling point for the title.
_NOT_TITLE_WORDS = re.compile(r'wash|dry clean|iron|bleach|tumble|^size\b|made in', re.I)


def ensure_tag_terms(listing, item, limit=2, max_length=120):
    """Put clearly read tag names ("Summer Comfort") in the title after the brand.

    Only for generated copy; caller protects seller-edited titles. Skips
    uncertain readings and anything that would push the title past max_length.
    """
    if item.get('tag_keywords_confidence') != 'high' or 'tag_keywords' in (item.get('low_confidence_fields') or []):
        return listing
    title = listing.get('title') or ''
    brand = str(listing.get('brand') or '')
    added = 0
    for term in item.get('tag_keywords') or []:
        term = re.sub(r'\s+', ' ', str(term)).strip()
        if term.isupper() and len(term) > 3:
            term = term.title()  # "SUMMER COMFORT" on the tag reads as "Summer Comfort"
        if added >= limit or not term or _NOT_TITLE_WORDS.search(term) or tokens(term) <= tokens(title):
            continue
        if brand and title.lower().startswith(brand.lower()):
            candidate = f'{title[:len(brand)]} {term}{title[len(brand):]}'
        else:
            candidate = f'{title} {term}'.strip()
        if len(candidate) <= max_length:
            title = candidate
            added += 1
    listing['title'] = title
    return listing


def _title_size_pattern(size):
    from app.services.description_layout import _LETTER_SIZES
    alternatives = [re.escape(size)]
    word = _LETTER_SIZES.get(size.upper())
    if word and word.upper() != size.upper():
        alternatives.insert(0, '(?i:' + re.escape(word) + ')')
    return re.compile(r"(?<![\w'’])(?i:size\s+)?(?:" + '|'.join(alternatives) + r")(?![\w'’])")


def _title_size_phrase(size):
    from app.services.description_layout import _LETTER_SIZES
    word = _LETTER_SIZES.get(size.upper())
    return f'Size {word}' if word else size


def _replace_last(title, pattern, phrase):
    matches = list(pattern.finditer(title))
    if not matches:
        return None
    last = matches[-1]
    return title[:last.start()] + phrase + title[last.end():]


def ensure_title_size(listing, max_length=120):
    """Letter sizes read as words in the title: "... Mens Navy L" -> "... Mens Navy Size Large".

    Only for generated copy; caller protects seller-edited titles. Other sizes
    (W32 L30, UK 10, 40R) are left exactly as written.
    """
    size = str(listing.get('normalized_size') or listing.get('tagged_size') or '').strip()
    phrase = _title_size_phrase(size) if size else ''
    if not phrase.startswith('Size '):
        return listing
    title = listing.get('title') or ''
    candidate = _replace_last(title, _title_size_pattern(size), phrase)
    if candidate is None:
        candidate = f'{title} {phrase}'.strip()
    if len(candidate) <= max_length:
        listing['title'] = candidate
    return listing


def retitle_size(listing, old_size):
    """After a size edit, swap the old size in the title (either written form) for the new one."""
    old_size = str(old_size or '').strip()
    new_size = str(listing.get('normalized_size') or '').strip()
    title = listing.get('title') or ''
    if not old_size or not new_size:
        return listing
    candidate = _replace_last(title, _title_size_pattern(old_size), _title_size_phrase(new_size))
    if candidate is not None:
        listing['title'] = candidate
    return listing
