"""Seller-confirmed lifecycle/outcome records. No model calls or buyer data."""
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo
from app.config import ROOT

DB_PATH = ROOT / 'data' / 'sales.db'
PLATFORMS = {'Vinted', 'eBay', 'Depop', 'Other'}
STATUSES = {'listed', 'sold', 'withdrawn', 'returned'}
FACTS = ('title', 'brand', 'brand_confidence', 'item_type', 'category', 'gender', 'materials', 'material_confidence',
         'fabric_mill', 'fabric_line', 'tag_keywords', 'tag_keywords_confidence', 'cut', 'pattern',
         'tagged_size', 'normalized_size', 'colour', 'condition_summary', 'flaws_note',
         'low_confidence_fields', 'model_name', 'sub_brand', 'made_in')


def today():
    return datetime.now(ZoneInfo('Europe/London')).date()


def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS outcomes (folder TEXT PRIMARY KEY, payload TEXT NOT NULL, '
               'match_key TEXT, status TEXT, platform TEXT, sold_date TEXT)')
    columns = {row[1] for row in db.execute('PRAGMA table_info(outcomes)')}
    for column in ('match_key','status','platform','sold_date'):
        if column not in columns: db.execute(f'ALTER TABLE outcomes ADD COLUMN {column} TEXT')
    for folder, payload in db.execute('SELECT folder,payload FROM outcomes WHERE match_key IS NULL').fetchall():
        row = json.loads(payload)
        db.execute('UPDATE outcomes SET match_key=?,status=?,platform=?,sold_date=? WHERE folder=?',
                   (match_key(row['item']),row['status'],row['platform'],row.get('sold_date'),folder))
    db.execute('CREATE INDEX IF NOT EXISTS sale_matches ON outcomes(match_key,platform,status,sold_date)')
    db.commit()
    return db


def read_all():
    with connection() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM outcomes ORDER BY folder')]


def get(folder):
    with connection() as db:
        row = db.execute('SELECT payload FROM outcomes WHERE folder=?', (folder,)).fetchone()
    return json.loads(row[0]) if row else None


def money(value, name, required=False):
    if value in (None, '') and not required: return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100000:
        raise ValueError(f'{name} must be a valid GBP amount.')
    if required and value <= 0: raise ValueError('Sold price must be greater than zero.')
    return round(value, 2)


def day(value, name, required=False):
    if not value and not required: return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'Enter {name} as a date.')
    try: result = date.fromisoformat(value)
    except ValueError: raise ValueError(f'Invalid {name}.') from None
    if result > today(): raise ValueError(f'{name} cannot be in the future.')
    return result.isoformat()


def record(folder, listing, body):
    if not isinstance(body, dict): raise ValueError('Enter listing or sale details.')
    if not re.fullmatch(r'upload_[a-f0-9]{8}', folder): raise ValueError('Invalid item ID.')
    status, platform = body.get('status'), body.get('platform')
    if status not in STATUSES or platform not in PLATFORMS: raise ValueError('Choose a status and platform.')
    existing = get(folder) or {}
    published = day(body.get('published_date'), 'published date', status == 'listed')
    sold = day(body.get('sold_date'), 'sale date', status == 'sold') if status == 'sold' else None
    if sold and published and sold < published: raise ValueError('Sale date cannot be before publication.')
    price = money(body.get('sold_price_gbp'), 'Sold price', True) if status == 'sold' else None
    buy = money(body.get('buy_price_gbp'), 'Purchase cost')
    costs = money(body.get('selling_cost_gbp'), 'Selling costs')
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {key: listing[key] for key in FACTS if listing.get(key) is not None}
    row = {'folder': folder, 'seller_scope': 'private_operator', 'source': 'seller_confirmed',
           'currency': 'GBP', 'status': status, 'platform': platform, 'published_date': published,
           'sold_date': sold, 'sold_price_gbp': price, 'buy_price_gbp': buy, 'selling_cost_gbp': costs,
           'asking_price_gbp': money(listing.get('price_gbp'), 'Asking price'), 'item': snapshot,
           'profit_gbp': round(price - buy - costs, 2) if price is not None and buy is not None and costs is not None else None,
           'days_to_sell': (date.fromisoformat(sold) - date.fromisoformat(published)).days if sold and published else None,
           'created_at': existing.get('created_at', now), 'updated_at': now}
    # A returned/withdrawn item is excluded from learning, while its previous
    # accepted transaction remains inspectable rather than becoming invented zeroes.
    if existing.get('status') == 'sold' and status != 'sold':
        row['previous_sale'] = {k:existing.get(k) for k in ('sold_date','sold_price_gbp','platform','days_to_sell','profit_gbp')}
    elif existing.get('previous_sale'):
        row['previous_sale'] = existing['previous_sale']
    with connection() as db:
        db.execute('INSERT INTO outcomes (folder,payload,match_key,status,platform,sold_date) VALUES (?,?,?,?,?,?) '
                   'ON CONFLICT(folder) DO UPDATE SET payload=excluded.payload,match_key=excluded.match_key,'
                   'status=excluded.status,platform=excluded.platform,sold_date=excluded.sold_date',
                   (folder,json.dumps(row),match_key(snapshot),status,platform,sold))
    return row


def restore(rows):
    """Restore missing records only; an older backup cannot overwrite a correction."""
    if not isinstance(rows, list) or len(rows) > 50000: raise ValueError('Invalid sales backup.')
    checked, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(r'upload_[a-f0-9]{8}', str(row.get('folder', ''))):
            raise ValueError('Invalid sales record.')
        if row['folder'] in seen: raise ValueError('Duplicate sale record.')
        seen.add(row['folder'])
        previous = row.get('previous_sale')
        if row.get('status') not in STATUSES or row.get('platform') not in PLATFORMS or row.get('currency') != 'GBP':
            raise ValueError('Invalid sales record status or currency.')
        if row.get('source') != 'seller_confirmed' or row.get('seller_scope') != 'private_operator':
            raise ValueError('Invalid sales source.')
        item = row.get('item')
        if not isinstance(item, dict) or len(json.dumps(item)) > 30000: raise ValueError('Invalid item facts.')
        for key, value in item.items():
            if key in ('materials','tag_keywords','low_confidence_fields'):
                if not isinstance(value, list) or len(value)>100 or any(not isinstance(v,str) or len(v)>1000 for v in value): raise ValueError('Invalid item facts.')
            elif key in FACTS and (not isinstance(value,str) or len(value)>2000): raise ValueError('Invalid item facts.')
        published = day(row.get('published_date'), 'published date', row['status'] == 'listed')
        sold = day(row.get('sold_date'), 'sale date', row['status'] == 'sold')
        if published and sold and sold < published: raise ValueError('Invalid lifecycle dates.')
        price = money(row.get('sold_price_gbp'), 'Sold price', row['status'] == 'sold')
        buy = money(row.get('buy_price_gbp'), 'Purchase cost')
        costs = money(row.get('selling_cost_gbp'), 'Selling costs')
        for field in ('created_at', 'updated_at'):
            if not isinstance(row.get(field), str): raise ValueError('Missing record timestamp.')
            try: datetime.fromisoformat(row[field])
            except ValueError: raise ValueError('Invalid record timestamp.') from None
        row = {**row, 'item': {key: item[key] for key in FACTS if key in item},
               'asking_price_gbp': money(row.get('asking_price_gbp'), 'Asking price'),
               'days_to_sell': (date.fromisoformat(sold) - date.fromisoformat(published)).days if sold and published else None,
               'profit_gbp': round(price-buy-costs, 2) if row['status'] == 'sold' and all(v is not None for v in (price,buy,costs)) else None}
        row = {key:row[key] for key in ('folder','seller_scope','source','currency','status','platform',
               'published_date','sold_date','sold_price_gbp','buy_price_gbp','selling_cost_gbp',
               'asking_price_gbp','item','profit_gbp','days_to_sell','created_at','updated_at')}
        # Previous transaction is kept for returned items, never treated as a current sale.
        if previous is not None:
            if not isinstance(previous,dict) or previous.get('platform') not in PLATFORMS: raise ValueError('Invalid previous sale.')
            row['previous_sale'] = {'platform':previous['platform'],
                'sold_date':day(previous.get('sold_date'),'previous sale date',True),
                'sold_price_gbp':money(previous.get('sold_price_gbp'),'Previous sold price',True)}
        checked.append(row)
    with connection() as db:
        before = db.total_changes
        for row in checked: db.execute('INSERT OR IGNORE INTO outcomes (folder,payload,match_key,status,platform,sold_date) VALUES (?,?,?,?,?,?)',
            (row['folder'],json.dumps(row),match_key(row['item']),row['status'],row['platform'],row.get('sold_date')))
        return db.total_changes - before


def signature(item):
    from app.services.premium_features import confirmed_terms, tokens
    from app.services.condition import canonical_level
    def norm(value): return ' '.join(sorted(tokens(value)))
    kind = norm(item.get('item_type'))
    groups = [('blazer', ('blazer', 'suit jacket', 'sports jacket')),
              ('trousers', ('trousers', 'trouser', 'chinos', 'corduroy trousers'))]
    for group, choices in groups:
        if any(norm(choice) == kind or set(tokens(choice)) <= tokens(item.get('item_type')) for choice in choices):
            kind = group; break
    if kind == 'trousers':
        garment_tokens = tokens(item.get('item_type'))
        if {'corduroy','cords'} & garment_tokens: kind = 'corduroy trousers'
        elif {'chinos','chino'} & garment_tokens: kind = 'chinos'
    shell = [norm(re.sub(r'\d+(?:\.\d+)?\s*%', '', str(m))) for m in item.get('materials') or [] if 'lining' not in str(m).lower()]
    return (norm(item.get('brand')), kind, norm(item.get('gender')), canonical_level(item.get('condition_summary')) if item.get('condition_summary') else 'unknown',
            norm(item.get('fabric_mill')), norm(item.get('fabric_line')), tuple(sorted(shell)),
            tuple(sorted(norm(v) for v in confirmed_terms(item))), norm(item.get('model_name')),
            norm(item.get('sub_brand')), norm(item.get('cut')), norm(item.get('pattern')))


def comparisons(item, platform='Vinted', rows=None):
    target = signature(item)
    matches = []
    if not target[0] or not target[1] or item.get('brand_confidence') == 'low' or 'brand' in (item.get('low_confidence_fields') or []):
        return {'sample_count': 0, 'platform': platform, 'median_gbp': None, 'mean_gbp': None, 'range_gbp': None, 'examples': []}
    cutoff = (today() - timedelta(days=365)).isoformat()
    if rows is None:
        with connection() as db:
            rows = [json.loads(row[0]) for row in db.execute(
                'SELECT payload FROM outcomes WHERE match_key=? AND platform=? AND status=? AND sold_date>=?',
                (match_key(item), platform, 'sold', cutoff))]
    for row in rows:
        if row['folder'] == item.get('folder') or row['status'] != 'sold' or row['platform'] != platform: continue
        if not row.get('sold_date') or row['sold_date'] < cutoff or signature(row['item']) != target: continue
        matches.append(row)
    prices = [r['sold_price_gbp'] for r in matches]
    return {'source': 'your_confirmed_sales', 'sample_count': len(prices), 'platform': platform,
            'median_gbp': round(median(prices), 2) if len(prices) >= 3 else None,
            'mean_gbp': round(mean(prices), 2) if len(prices) >= 3 else None,
            'range_gbp': [min(prices), max(prices)] if len(prices) >= 3 else None,
            'examples': [{'folder':r['folder'], 'title':r['item'].get('title'), 'sold_price_gbp':r['sold_price_gbp'], 'sold_date':r['sold_date']} for r in matches],
            'note': 'Recent confirmed sales on the same platform, matching brand, garment, condition and cloth details; size and colour may vary. At least 3 needed for a price. Accepted prices exclude postage.'}


def match_key(item):
    return hashlib.sha256(json.dumps(signature(item),separators=(',',':')).encode()).hexdigest()


def metrics(rows=None):
    rows = read_all() if rows is None else rows
    sold = [r for r in rows if r['status'] == 'sold']
    days = [r['days_to_sell'] for r in sold if r.get('days_to_sell') is not None]
    current_day = today()
    cohorts = [r for r in rows if r.get('published_date') and 30 <= (current_day-date.fromisoformat(r['published_date'])).days <= 120]
    completed = [r for r in cohorts if r['status'] == 'sold' and r.get('days_to_sell') is not None and r['days_to_sell'] <= 30]
    return {'tracked':len(rows), 'sold':len(sold), 'revenue_gbp':round(sum(r['sold_price_gbp'] for r in sold),2),
            'profit_gbp': round(sum(r['profit_gbp'] for r in sold if r.get('profit_gbp') is not None),2),
            'profit_known_count': sum(r.get('profit_gbp') is not None for r in sold),
            'median_days_to_sell': median(days) if days else None, 'days_known_count':len(days),
            'cohort_count':len(cohorts), 'cohort_sold_count':len(completed),
            'sell_through_30d_percent':round(100*len(completed)/len(cohorts),1) if cohorts else None,
            'cohort_note':'Listings first published 30–120 days ago; percentage sold within their first 30 days. Includes tracked unsold/withdrawn items. Missing publication dates are excluded. This is your recorded inventory, not market-wide demand.'}


def export_csv():
    out = io.StringIO(newline='')
    columns = ['folder','status','platform','published_date','sold_date','days_to_sell','asking_price_gbp',
               'sold_price_gbp','buy_price_gbp','selling_cost_gbp','profit_gbp',*FACTS,'source']
    writer = csv.DictWriter(out, fieldnames=columns); writer.writeheader()
    for row in read_all():
        flat = {**row, **row['item']}
        values = {key:flat.get(key) for key in columns}
        for key, value in values.items():
            if isinstance(value, list): value = ', '.join(map(str,value))
            if isinstance(value, str) and value.lstrip().startswith(('=','+','-','@')): value = "'" + value
            values[key] = value
        writer.writerow(values)
    return '\ufeff'+out.getvalue()
