"""Compact outcome tracking and deterministic history suggestions."""
import json
import re
from flask import Blueprint, jsonify, request, Response
from app.services import sales_history, item_store, crosslist, listing_state

sales = Blueprint('sales', __name__)


def listing_path(folder):
    from app.web import ITEMS_DIR
    if not re.fullmatch(r'upload_[a-f0-9]{8}', folder): raise ValueError('Invalid item ID.')
    return ITEMS_DIR / folder / 'listing.json'


def load(folder):
    return json.loads(listing_path(folder).read_text())


def save(folder, item):
    # The request already holds this item's lock (serialize_item_requests), so write directly.
    listing_state.write(listing_path(folder), item)


@sales.route('/listing/<folder>/outcome', methods=['GET', 'POST'])
def outcome(folder):
    try:
        item = load(folder)
        if request.method == 'GET': return jsonify(outcome=sales_history.get(folder), comparisons=sales_history.comparisons(dict(item, folder=folder)),
                                                   crosslist=crosslist.where_listed(item))
        row = sales_history.record(folder, item, request.get_json(silent=True))
        delist = []
        if row['status'] == 'sold':
            item_store.set_status(folder, 'sold')
            # Sold on one platform: end it (or list what to end) everywhere else, so it can't sell twice.
            delist = crosslist.after_sale(item, row['platform'])
            save(folder, item)
        else:
            status, review = item_store.derive_status(item)
            item_store.set_status(folder, status, review_needed=review)
        return jsonify(outcome=row, delist=delist, crosslist=crosslist.where_listed(item))
    except FileNotFoundError: return jsonify(error='Draft not found.'), 404
    except (ValueError, TypeError): return jsonify(error='Check the platform, dates and actual GBP amounts. Sale date must follow publication; future dates are not allowed.'), 422


@sales.post('/listing/<folder>/crosslist')
def crosslist_update(folder):
    """{"platform", "action": "listed" | "unlisted" | "removed", "url"?} — where the item is listed."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict): return jsonify(error='Choose a platform.'), 422
    try:
        item, platform, action = load(folder), body.get('platform'), body.get('action')
        if action == 'removed': entries = crosslist.mark_removed(item, platform)
        elif action in ('listed', 'unlisted'):
            url = body.get('url') if isinstance(body.get('url'), str) else None
            entries = crosslist.set_listed(item, platform, live=action == 'listed', url=url)
        else: return jsonify(error='Choose listed, unlisted or removed.'), 422
        save(folder, item)
        outcome = sales_history.get(folder) or {}
        sold_on = outcome.get('platform') if outcome.get('status') == 'sold' else None
        return jsonify(crosslist=entries, still_live=crosslist.still_live(item, sold_on) if sold_on else [])
    except FileNotFoundError: return jsonify(error='Draft not found.'), 404
    except ValueError: return jsonify(error='Choose Vinted, eBay, Depop or Other.'), 422


@sales.get('/api/sales')
def history():
    rows = sales_history.read_all()
    return jsonify(records=rows, metrics=sales_history.metrics(rows))


@sales.get('/api/sales/backup')
def backup():
    return jsonify(sales_history.read_all())


@sales.post('/api/sales/restore')
def restore():
    try: return jsonify(restored=sales_history.restore(request.get_json(silent=True)))
    except (ValueError, TypeError): return jsonify(error='Invalid sales-history backup.'), 422


@sales.get('/api/sales/export.csv')
def export():
    return Response(sales_history.export_csv(), mimetype='text/csv', headers={
        'Content-Disposition':'attachment; filename=sales-history.csv', 'Cache-Control':'no-store'})
