"""Keep uncertain tag guesses out of generated buyer-facing facts."""
import re


def size_uncertain(item):
    fields = set(item.get('low_confidence_fields') or [])
    return bool(item.get('tagged_size') or item.get('normalized_size')) and (
        bool(fields & {'tagged_size', 'normalized_size', 'size'}) or item.get('size_confidence') in {'low', 'medium'})


def size_supported(size, quote):
    if not isinstance(size, str) or not isinstance(quote, str) or not size.strip():
        return False
    return bool(re.search(r'(?<![a-z0-9])'+re.escape(size.strip())+r'(?![a-z0-9])', quote, re.I))


def composition_supported(materials, quote):
    if not materials or not isinstance(quote, str) or not quote.strip():
        return False
    # Associate each percentage with its following fibre text, not just any number on the tag.
    parts = list(re.finditer(r'(\d+(?:\.\d+)?)\s*%\s*([^%]*?)(?=\d+(?:\.\d+)?\s*%|$)', quote, re.I))
    aliases = {'wool': ('wool','laine','lana','wolle'), 'cotton': ('cotton','coton','cotone','baumwolle'),
               'silk': ('silk','soie','seide'), 'elastane': ('elastane','elastan','elasthanne','spandex'),
               'polyamide': ('polyamide','nylon'), 'nylon': ('nylon','polyamide')}
    for entry in materials:
        pairs = list(re.finditer(r'(\d+(?:\.\d+)?)\s*%\s*([a-z][a-z ]*)', str(entry), re.I))
        if not pairs:
            return False
        for pair in pairs:
            fibre = pair[2].strip().lower()
            names = aliases.get(fibre, (fibre,))
            if not any(float(part[1]) == float(pair[1]) and any(re.search(r'\b'+re.escape(name)+r'\b', part[2], re.I) for name in names) for part in parts):
                return False
    return True


def suppress_uncertain(item):
    fields = set(item.get('low_confidence_fields') or [])
    if size_uncertain(item):
        item['size_reading_candidate'] = item.get('tagged_size') or item.get('normalized_size')
        item['tagged_size'] = item['normalized_size'] = None
        fields.add('tagged_size')
    if item.get('material_confidence') in {'low', 'medium'} and item.get('materials'):
        item['material_reading_candidate'] = item['materials']
        item['materials'] = []
        # An inferred fibre in the garment name must not survive an unknown composition.
        kind = item.get('item_type') or ''
        item['item_type'] = re.sub(r'\b(?:wool|cashmere|cotton|polyester|polyamide|silk|linen|nylon|elastane)\b\s*', '', kind, flags=re.I).strip() or kind
        fields.add('materials')
    item['low_confidence_fields'] = sorted(fields)
    return item


def sync_edited_size(listing):
    """Update only the explicit Size detail; retain the rest of the seller's prose."""
    from app.services.description_layout import size_text
    line = '- Size: '+size_text(listing)
    desc = listing.get('description') or ''
    if re.search(r'(?mi)^[ \t]*[-•]?[ \t]*Size[ \t]*:', desc):
        listing['description'] = re.sub(r'(?mi)^[ \t]*[-•]?[ \t]*Size[ \t]*:[^\n]*', lambda _: line, desc)
    elif size_text(listing):
        listing['description'] = desc.rstrip()+'\n\n'+line
