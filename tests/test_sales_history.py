import json
from copy import deepcopy
from datetime import date, timedelta
import pytest
from app.services import sales_history as h, pricing, item_backup, description_layout

ITEM = dict(brand='Boggi',item_type='wool blazer',title='Boggi Loro Piana blazer',price_gbp=85,
            materials=['100% Merino Wool'],material_confidence='high',fabric_mill='Loro Piana',
            fabric_line='Zelander Dream',tag_keywords=['Full Canvas'],tag_keywords_confidence='high',
            condition_summary='Good condition',gender="men's",tagged_size='54',normalized_size='44R')


def payload(price=70, **changes):
    result=dict(status='sold',platform='Vinted',sold_price_gbp=price,
                sold_date=(date.today()-timedelta(days=20)).isoformat(),
                published_date=(date.today()-timedelta(days=40)).isoformat(),
                buy_price_gbp=10,selling_cost_gbp=0)
    result.update(changes);return result


def test_record_corrects_one_unit_without_double_count_and_keeps_actuals():
    first=h.record('upload_11111111',ITEM,payload())
    assert first['profit_gbp']==60 and first['days_to_sell']==20 and first['asking_price_gbp']==85
    h.record('upload_11111111',ITEM,payload(75))
    assert len(h.read_all())==1 and h.metrics()['revenue_gbp']==75
    assert h.restore([first])==0 and h.get('upload_11111111')['sold_price_gbp']==75
    returned=h.record('upload_11111111',ITEM,payload(status='returned'))
    assert h.metrics()['sold']==0 and returned['previous_sale']['sold_price_gbp']==75
    assert h.comparisons(ITEM)['sample_count']==0


def test_matching_keeps_platform_cloth_condition_and_model_separate():
    for i, price in enumerate([60,70,200]):
        h.record(f'upload_{i+1:08x}',dict(ITEM,colour=['Blue','Brown','Black'][i],tagged_size=str(50+i)),payload(price))
    h.record('upload_11111111',ITEM,payload(999,platform='eBay'))
    h.record('upload_22222222',dict(ITEM,fabric_mill=None,fabric_line=None,tag_keywords=[]),payload(20))
    h.record('upload_33333333',dict(ITEM,condition_summary='Satisfactory condition'),payload(10))
    h.record('upload_44444444',ITEM,payload(30,sold_date=(date.today()-timedelta(days=370)).isoformat(),published_date=None))
    result=h.comparisons(ITEM)
    assert result['sample_count']==3 and result['median_gbp']==70 and result['mean_gbp']==110
    listing=deepcopy(ITEM)
    pricing.apply_pricing(listing)
    assert listing['price_gbp']==70 and listing['ai_price_gbp']==85
    assert listing['price_evidence']['source']=='your_confirmed_sales'
    assert h.comparisons(dict(ITEM,model_name='Other model'))['sample_count']==0
    assert h.signature(dict(ITEM,item_type='corduroy trousers')) != h.signature(dict(ITEM,item_type='chinos'))


def test_sell_through_uses_mature_inventory_and_unknown_stays_unknown():
    h.record('upload_11111111',ITEM,payload())
    h.record('upload_22222222',ITEM,payload(status='listed'))
    h.record('upload_33333333',ITEM,payload(published_date=None,buy_price_gbp=None,selling_cost_gbp=None))
    result=h.metrics()
    assert result['cohort_count']==2 and result['cohort_sold_count']==1 and result['sell_through_30d_percent']==50
    assert result['sold']==2 and result['days_known_count']==1 and result['profit_known_count']==1
    assert h.get('upload_33333333')['days_to_sell'] is None
    assert h.get('upload_33333333')['profit_gbp'] is None


@pytest.mark.parametrize('changes', [dict(sold_price_gbp=True),dict(sold_price_gbp=-1),dict(sold_price_gbp=float('nan')),
    dict(sold_date='garbage'),dict(sold_date=(h.today()+timedelta(days=1)).isoformat()),
    dict(published_date=date.today().isoformat()),dict(platform='Untrusted')])
def test_invalid_records_do_not_enter_learning(changes):
    with pytest.raises(ValueError):h.record('upload_11111111',ITEM,payload(**changes))
    assert h.read_all()==[]


def test_restore_backup_survives_deleted_photos_and_preserves_server_corrections(tmp_path,monkeypatch):
    h.record('upload_11111111',dict(ITEM,title='=DANGER'),payload())
    assert "'=DANGER" in h.export_csv()
    items=tmp_path/'items';items.mkdir()
    data=item_backup.export(items)
    monkeypatch.setattr(h,'DB_PATH',tmp_path/'restored.db')
    assert item_backup.restore(data,tmp_path/'restored_items')==[]
    assert h.metrics()['sold']==1 and h.get('upload_11111111')['sold_price_gbp']==70


def test_outcome_route_does_not_reanalyse_or_reprice(tmp_path,monkeypatch):
    from app import web
    folder=tmp_path/'upload_11111111';folder.mkdir()
    (folder/'listing.json').write_text(json.dumps(ITEM))
    monkeypatch.setattr(web,'ITEMS_DIR',tmp_path)
    monkeypatch.setattr(web.pipeline_svc,'run_pipeline',lambda *a,**k:pytest.fail('Paid analysis called'))
    client=web.app.test_client()
    assert client.post('/listing/'+folder.name+'/outcome',json=payload()).status_code==200
    assert json.loads((folder/'listing.json').read_text())==ITEM
    assert client.get('/listing/'+folder.name).json['outcome']['sold_price_gbp']==70
    assert client.get('/api/sales/export.csv').status_code==200
    assert client.post('/listing/'+folder.name+'/outcome',json=payload(-1)).status_code==422


def test_legacy_backup_recovers_printed_tag_and_layout(tmp_path):
    import io,zipfile
    listing=dict(ITEM,tagged_size='44R',normalized_size='44R',tag_keywords=['Size 54'],
                 category='Men > Suits > Blazers',description='Boggi blazer.\n- Size: 44R\nKeywords: Size 54.')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:z.writestr('items/upload_11111111/listing.json',json.dumps(listing))
    item_backup.restore(out.getvalue(),tmp_path/'items')
    restored=json.loads((tmp_path/'items/upload_11111111/listing.json').read_text())
    assert restored['tagged_size']=='54' and '- Size: UK 44R / EU 54' in restored['description']


def test_quick_sale_defaults_today_preserves_publication_and_edit_date():
    published=(h.today()-timedelta(days=15)).isoformat()
    h.record('upload_11111111',ITEM,dict(status='listed',platform='Vinted',published_date=published,buy_price_gbp=9))
    sale=h.record('upload_11111111',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=50))
    assert sale['sold_date']==h.today().isoformat()
    assert sale['published_date']==published and sale['days_to_sell']==15
    assert sale['buy_price_gbp']==9 and sale['selling_cost_gbp'] is None
    earlier=(h.today()-timedelta(days=2)).isoformat()
    h.record('upload_11111111',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=50,sold_date=earlier))
    assert h.record('upload_11111111',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=55))['sold_date']==earlier


def test_quick_sale_does_not_invent_publication_from_draft_creation():
    row=h.record('upload_11111111',dict(ITEM,listed_date='2026-09-01'),dict(status='sold',platform='Vinted',sold_price_gbp=50))
    assert row['published_date'] is None and row['days_to_sell'] is None


def test_sold_page_uses_actual_prices_and_moves_items_from_drafts(tmp_path,monkeypatch):
    from app import web
    monkeypatch.setattr(web,'ITEMS_DIR',tmp_path)
    folder=tmp_path/'upload_11111111';folder.mkdir()
    (folder/'listing.json').write_text(json.dumps(dict(ITEM,listed_date='2026-09-02')))
    h.record(folder.name,ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=47.5,buy_price_gbp=8))
    client=web.app.test_client()
    page=client.get('/sold')
    assert page.status_code==200 and page.headers['Cache-Control']=='no-store'
    html=page.get_data(as_text=True)
    assert 'class="sold-tag">SOLD' in html and '£47.5' in html and 'Bought for £8' in html
    assert 'href="/sold"' in html and 'btn-delete-draft" onclick' not in html
    assert 'card-upload_11111111' not in client.get('/drafts').get_data(as_text=True)
    assert web._draft_count()==0
    assert client.get('/stats').status_code==200


def test_monthly_summary_profit_and_return_ignore_unknown_costs():
    month=h.today().strftime('%Y-%m')
    h.record('upload_11111111',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=50,buy_price_gbp=5))
    h.record('upload_22222222',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=20,buy_price_gbp=None))
    summary=h.monthly_summary(month=month)
    assert summary['revenue_gbp']==70 and summary['sold_count']==2
    assert summary['gross_profit_gbp']==45 and summary['average_profit_gbp']==45
    assert summary['return_on_cost_percent']==900 and summary['known_cost_count']==1
    h.record('upload_33333333',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=10,buy_price_gbp=0))
    assert h.monthly_summary()['average_profit_gbp']==27.5
    assert h.monthly_summary(month='2000-01')['sold_count']==0
    with pytest.raises(ValueError):h.monthly_summary(month='2026-99')


def test_monthly_summary_unknown_zero_and_loss_are_distinct():
    h.record('upload_11111111',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=10,buy_price_gbp=None))
    assert h.monthly_summary()['gross_profit_gbp'] is None
    assert h.monthly_summary()['return_on_cost_percent'] is None
    h.record('upload_11111111',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=10,buy_price_gbp=0))
    assert h.monthly_summary()['gross_profit_gbp']==10
    assert h.monthly_summary()['return_on_cost_percent'] is None
    h.record('upload_11111111',ITEM,dict(status='sold',platform='Vinted',sold_price_gbp=10,buy_price_gbp=20))
    assert h.monthly_summary()['gross_profit_gbp']==-10
    assert h.monthly_summary()['return_on_cost_percent']==-50
