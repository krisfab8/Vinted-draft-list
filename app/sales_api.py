"""Compact outcome tracking and deterministic history suggestions."""
import json
import re
from flask import Blueprint, jsonify, request, Response
from app.services import sales_history, item_store

sales = Blueprint('sales', __name__)


def load(folder):
    from app.web import ITEMS_DIR
    if not re.fullmatch(r'upload_[a-f0-9]{8}', folder): raise ValueError('Invalid item ID.')
    path = ITEMS_DIR / folder / 'listing.json'
    return json.loads(path.read_text())


@sales.route('/listing/<folder>/outcome', methods=['GET', 'POST'])
def outcome(folder):
    try:
        item = load(folder)
        if request.method == 'GET': return jsonify(outcome=sales_history.get(folder), comparisons=sales_history.comparisons(dict(item, folder=folder)))
        row = sales_history.record(folder, item, request.get_json(silent=True))
        if row['status'] == 'sold': item_store.set_status(folder, 'sold')
        else:
            status, review = item_store.derive_status(item)
            item_store.set_status(folder, status, review_needed=review)
        return jsonify(outcome=row)
    except FileNotFoundError: return jsonify(error='Draft not found.'), 404
    except (ValueError, TypeError): return jsonify(error='Check the platform, dates and actual GBP amounts. Sale date must follow publication; future dates are not allowed.'), 422


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
