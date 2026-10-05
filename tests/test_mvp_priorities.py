import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from app import web
from app.services import listing_state, sales_history, item_store


ITEM = dict(brand='Boggi', item_type='wool blazer', title='My own title',
            description='My own carefully written description.', category='Men > Suits > Blazers',
            tagged_size='54', normalized_size='44R', price_gbp=95, ai_price_gbp=80,
            buy_price_gbp=10, condition_summary='Good condition', materials=['100% Wool'],
            gender="men's", brand_confirmed=True, manual_fields=['title', 'description', 'brand'])


@pytest.fixture
def item(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'ITEMS_DIR', tmp_path)
    monkeypatch.setattr(item_store, 'DB_PATH', tmp_path/'items.db')
    item_store.init_db()
    folder = tmp_path/'upload_12345678'; folder.mkdir()
    listing_state.write(folder/'listing.json', ITEM)
    return folder, web.app.test_client()


def test_price_check_is_free_and_preserves_copy_until_accepted(item, monkeypatch):
    folder, client = item
    monkeypatch.setattr(web.listing_writer, 'write', lambda *a, **k: pytest.fail('Paid writer called'))
    response = client.post('/reprice/'+folder.name)
    assert response.status_code == 200
    result = response.json
    assert result['price_gbp'] == 95 and result['title'] == ITEM['title'] and result['description'] == ITEM['description']
    assert result['price_proposal']['price_gbp'] is not None
    accepted = client.patch('/listing/'+folder.name, json={'price_gbp':70})
    assert accepted.json['price_gbp'] == 70 and accepted.json['estimated_profit_gbp'] == 60
    assert 'price_proposal' not in accepted.json
    assert accepted.json['price_history'][0]['from_gbp'] == 95


def test_two_tabs_cannot_overwrite_newer_edits(item):
    folder, client = item
    revision = client.get('/listing/'+folder.name).headers['X-Item-Revision']
    first = client.patch('/listing/'+folder.name, json={'title':'First edit'}, headers={'If-Match':revision})
    assert first.status_code == 200 and first.headers['X-Item-Revision'] != revision
    second = client.patch('/listing/'+folder.name, json={'title':'Stale edit'}, headers={'If-Match':revision})
    assert second.status_code == 409 and second.json['code'] == 'EDIT_CONFLICT'
    assert json.loads((folder/'listing.json').read_text())['title'] == 'First edit'


def test_concurrent_requests_check_revision_inside_item_lock(item):
    folder, client = item
    revision = client.get('/listing/'+folder.name).headers['X-Item-Revision']
    def edit(title):
        with web.app.test_client() as other:
            return other.patch('/listing/'+folder.name, json={'title':title}, headers={'If-Match':revision}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit, ['First concurrent edit','Second concurrent edit'])) == [200,409]


@pytest.mark.parametrize('updates', [{'price_gbp':-1}, {'price_gbp':True}, {'price_gbp':float('nan')},
                                     {'draft_url':'invented'}, {'cost_gbp':0}, {'title':'x'*121}, ['not an object']])
def test_invalid_edits_leave_saved_listing_unchanged(item, updates):
    folder, client = item
    before = (folder/'listing.json').read_bytes()
    assert client.patch('/listing/'+folder.name, json=updates).status_code == 422
    assert (folder/'listing.json').read_bytes() == before


def test_regeneration_keeps_manual_copy_facts_cost_and_chosen_price(item, monkeypatch):
    folder, client = item
    generated = deepcopy(ITEM)
    generated.update(title='AI replacement', description='AI replacement', brand='Wrong brand', buy_price_gbp=999, price_gbp=20)
    monkeypatch.setattr(web.listing_writer, 'write', lambda *a, **k: (deepcopy(generated), {'input_tokens':100,'output_tokens':10,'model':'haiku'}))
    result = client.post('/regen/'+folder.name, json={'updates':{'colour':'Blue'}})
    assert result.status_code == 200, result.json
    assert result.json['title'] == ITEM['title'] and result.json['description'] == ITEM['description']
    assert result.json['brand'] == 'Boggi' and result.json['buy_price_gbp'] == 10
    assert result.json['price_gbp'] == 95 and result.json['colour'] == 'Blue'


def test_failed_regeneration_does_not_save_partial_updates(item, monkeypatch):
    folder, client = item
    before = (folder/'listing.json').read_bytes()
    def fail(*args, **kwargs): raise RuntimeError('Provider unavailable')
    monkeypatch.setattr(web.listing_writer, 'write', fail)
    assert client.post('/regen/'+folder.name, json={'updates':{'colour':'Blue'}}).status_code == 500
    assert (folder/'listing.json').read_bytes() == before


def test_atomic_replace_failure_keeps_previous_file(item, monkeypatch):
    folder, _ = item
    before = (folder/'listing.json').read_bytes()
    def fail(*args): raise OSError('Disk failure')
    monkeypatch.setattr(listing_state.os, 'replace', fail)
    with pytest.raises(OSError): listing_state.write(folder/'listing.json', {'title':'New data'})
    assert (folder/'listing.json').read_bytes() == before
    assert list(folder.iterdir()) == [folder/'listing.json']


def test_inventory_and_sale_revision_refresh_without_analysis(item):
    folder, client = item
    revision = client.get('/listing/'+folder.name).headers['X-Item-Revision']
    published = (sales_history.today()-timedelta(days=40)).isoformat()
    sale = client.post('/listing/'+folder.name+'/outcome',json=dict(status='sold',platform='Vinted',
        published_date=published,sold_date=(sales_history.today()-timedelta(days=20)).isoformat(),sold_price_gbp=75))
    assert sale.status_code == 200 and sale.headers['X-Item-Revision'] != revision
    assert client.get('/api/listings').json[0]['inventory_status'] == 'sold'
    assert 'Live / unsold' in client.get('/drafts').text
    listing = client.patch('/listing/'+folder.name,json={'colour':'Blue'})
    assert listing.status_code == 200 and item_store.get_status(folder.name) == 'sold'


def test_matching_preserves_composition_flaws_and_migrates_old_index(item):
    folder, _ = item
    sold_date = (sales_history.today()-timedelta(days=10)).isoformat()
    for i in range(3):
        sales_history.record(f'upload_{i+1:08x}', ITEM, dict(status='sold',platform='Vinted',
            published_date=(sales_history.today()-timedelta(days=20)).isoformat(),sold_date=sold_date,sold_price_gbp=70+i))
    with sales_history.connection() as db:
        db.execute("UPDATE outcomes SET match_key='legacy-key'")
        db.execute('PRAGMA user_version=1')
    comparisons = sales_history.comparisons(ITEM)
    assert comparisons['sample_count'] == 3 and comparisons['median_days_to_sell'] == 10
    assert sales_history.comparisons(dict(ITEM,materials=['10% Wool']))['sample_count'] == 0
    assert sales_history.comparisons(dict(ITEM,flaws_note='Hole in sleeve'))['sample_count'] == 0
