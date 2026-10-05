"""Keep first-run evidence and operator feedback beside the authoritative listing."""
import json
from datetime import datetime, timezone

ISSUES = {'brand', 'fabric', 'size', 'material', 'price', 'copy', 'other'}


def capture(path, listing, **metrics):
    target = path / 'analysis.json'
    # Exclusive creation: later edits never replace the original result.
    try:
        with target.open('x') as out:
            json.dump({'captured_at': datetime.now(timezone.utc).isoformat(),
                       'listing': listing, **metrics}, out, indent=2)
    except FileExistsError:
        pass


def read(path):
    target = path / 'feedback.json'
    return json.loads(target.read_text()) if target.exists() else {'issues': [], 'notes': ''}


def save(path, body):
    if not isinstance(body, dict):
        raise ValueError('Choose an issue and enter any corrections.')
    issues, notes = body.get('issues', []), body.get('notes', '')
    if (not isinstance(issues, list) or len(issues) > len(ISSUES)
            or any(not isinstance(i, str) or i not in ISSUES for i in issues)
            or not isinstance(notes, str) or len(notes) > 2000):
        raise ValueError('Invalid feedback; notes must be under 2,000 characters.')
    capture(path, json.loads((path / 'listing.json').read_text()))
    result = {'issues': list(dict.fromkeys(issues)), 'notes': notes.strip(),
              'updated_at': datetime.now(timezone.utc).isoformat()}
    temporary = path / 'feedback.json.tmp'
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(path / 'feedback.json')
    return result



def recheck(path):
    """Recheck recorded evidence and pricing without AI, preserving manual prices."""
    from app.services import fabric_mill, pricing
    from app.validate_listing import validate_or_raise
    listing = json.loads((path / 'listing.json').read_text())
    capture(path, listing)
    analysis = json.loads((path / 'analysis.json').read_text())
    original = analysis['listing']
    generated_copy = listing.get('description') == original.get('description') and any(key in analysis for key in ('extract_log', 'recorded_run_log'))
    before_mill, before_line = listing.get('fabric_mill'), listing.get('fabric_line')
    fabric_mill.verify_mill(listing)
    description = listing.get('description') or ''
    for label, before, after in [('Fabric mill', before_mill, listing.get('fabric_mill')),
                                  ('Fabric line', before_line, listing.get('fabric_line'))]:
        if before and before != after:
            text = f'- {label}: {before}'
            description = description.replace(text, f'- {label}: {after}' if after else '')
    # Rebuild just the generated keywords line, not the seller's other copy.
    import re
    description = re.sub(r'^Keywords:.*$', 'Keywords: '+', '.join(listing.get('tag_keywords') or [])+'.', description, flags=re.M)
    listing['description'] = description
    if generated_copy:
        from app.services import copy_quality, condition
        copy_quality.apply(listing, listing)
        condition.apply_condition(listing)
        condition.inject_condition_line(listing)
    if listing.get('title') == original.get('title'):
        from app.services.premium_features import ensure_title
        ensure_title(listing)
    from app.services.ebay_comps import search_links, EbayQueryError
    try:
        listing['ebay_links'] = search_links(listing)
    except EbayQueryError:
        pass
    current_price = listing.get('price_gbp')
    manual_price = current_price != original.get('price_gbp')
    if not manual_price and listing.get('ai_price_gbp') is not None:
        listing['price_gbp'] = listing['ai_price_gbp']
        pricing.apply_pricing(listing)
    listing['evidence_check_version'] = 'fabric-price-v1'
    validate_or_raise(listing)
    from app.services import listing_state
    listing_state.write(path / 'listing.json', listing)
    return listing
