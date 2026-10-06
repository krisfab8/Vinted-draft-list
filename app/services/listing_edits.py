"""Validate manual facts and protect them independently of model prompts."""
import json
import math
from copy import deepcopy
import jsonschema
from app.config import SCHEMA_PATH

SCHEMA = json.loads(SCHEMA_PATH.read_text())
FIELDS = {
    'brand', 'item_type', 'title', 'description', 'tagged_size', 'normalized_size',
    'materials', 'colour', 'colour_secondary', 'gender', 'price_gbp', 'buy_price_gbp',
    'category', 'condition_summary', 'flaws_note', 'made_in', 'fabric_mill',
    'fabric_line', 'material_hint', 'style', 'cut', 'pattern', 'tag_keywords',
    'trouser_waist', 'trouser_length', 'model_name', 'sub_brand',
}


def validate_updates(updates):
    if not isinstance(updates, dict) or any(key not in FIELDS for key in updates):
        raise ValueError('Only editable listing details can be changed.')
    for key, value in updates.items():
        spec = SCHEMA['properties'].get(key, {'type': ['string', 'null']})
        # Blank optional fields are removed when assembling the final listing.
        if value is None and key not in SCHEMA['required']:
            continue
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Enter a finite GBP amount.')
        try:
            jsonschema.validate(value, spec)
        except jsonschema.ValidationError:
            raise ValueError(f'Invalid value for {key.replace("_", " ")}.') from None
        if isinstance(value, str) and len(value) > (20000 if key == 'description' else 2000):
            raise ValueError('Listing detail is too long.')
        if isinstance(value, list) and (len(value) > 100 or any(len(v) > 1000 for v in value)):
            raise ValueError('Too many listing details.')
    return updates


def apply(existing, updates):
    validate_updates(updates)
    listing = deepcopy(existing)
    manual = set(existing.get('manual_fields') or [])
    for key, value in updates.items():
        if existing.get(key) != value:
            manual.add(key)
        listing[key] = value
    if {'tagged_size', 'normalized_size'} & set(updates):
        from app.services.label_safety import sync_edited_size
        if 'normalized_size' in updates and 'tagged_size' not in updates and 'tagged_size' in (existing.get('low_confidence_fields') or []):
            listing['size_reading_candidate'] = existing.get('tagged_size')
            listing['tagged_size'] = None
        sync_edited_size(listing)
    listing['manual_fields'] = sorted(manual)
    if 'brand' in updates:
        listing['brand_confirmed'] = True
    if 'category' in updates:
        listing['category_locked'] = True
    if 'price_gbp' in updates:
        listing.pop('price_proposal', None)
        listing['price_evidence'] = {'source': 'seller_selected', 'note': 'Price chosen by you.'}
        if existing.get('price_gbp') != updates['price_gbp']:
            from datetime import datetime, timezone
            listing.setdefault('initial_asking_price_gbp', existing.get('price_gbp'))
            listing.setdefault('price_history', []).append({
                'from_gbp': existing.get('price_gbp'), 'to_gbp': updates['price_gbp'],
                'changed_at': datetime.now(timezone.utc).isoformat(), 'source': 'manual_review',
            })
    from app.validate_listing import normalize_generated_listing
    normalize_generated_listing(listing)
    return listing
