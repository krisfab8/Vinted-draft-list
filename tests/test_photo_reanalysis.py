import json
import uuid
from pathlib import Path
from unittest.mock import Mock
import pytest
from app import web
from app.services import listing_state, item_store


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(web,'ITEMS_DIR',tmp_path)
    monkeypatch.setattr(item_store,'DB_PATH',tmp_path/'items.db')
    item_store.init_db()
    source=tmp_path/'upload_source';source.mkdir()
    old=dict(brand='M&S',item_type='blazer',title='Seller corrected title',description='Seller copy.',
             tagged_size='L',normalized_size='18',materials=['Seller-confirmed composition'],
             category='Women > Blazers',price_gbp=30,buy_price_gbp=5,manual_fields=['description','normalized_size'])
    listing_state.write(source/'listing.json',old)
    for role in ('front','brand','model_size','material','back'):
        (source/(role+'.jpg')).write_bytes(('original-'+role).encode())
    (source/'photo_roles.json').write_text(json.dumps({'roles':{'front':'front.jpg'}}))
    (source/'contact.jpg').write_bytes(b'not an original slot')
    monkeypatch.setattr(web,'_log_cost',lambda *a,**k:None)
    monkeypatch.setattr(web,'_write_run_log',lambda *a,**k:None)
    new=dict(old,title='Fresh photo result',description='Fresh description.',normalized_size='L',
             materials=['Fresh composition'],manual_fields=[])
    usage=dict(input_tokens=100,output_tokens=30,calls=[],cost_complete=True)
    pipeline=Mock(return_value=(new,usage,usage,{},{}))
    monkeypatch.setattr(web.pipeline_svc,'run_pipeline',pipeline)
    return tmp_path,source,old,pipeline,web.app.test_client()


def test_fresh_analysis_replaces_the_listing_in_place(saved):
    root,source,old,pipeline,client=saved
    listing=json.loads((source/'listing.json').read_text())
    listing_state.write(source/'listing.json',dict(listing,draft_url='https://www.vinted.co.uk/items/1/edit'))
    photos={role:(source/(role+'.jpg')).read_bytes() for role in ('front','brand','model_size','material','back')}
    nonce=str(uuid.uuid4())
    response=client.post('/reanalyze/'+source.name,json={'request_id':nonce})
    assert response.status_code==200
    result=response.json
    # Same listing, new AI read; no second listing is left behind.
    assert result['folder']==source.name and [p.name for p in root.iterdir() if p.name.startswith('upload_')]==[source.name]
    saved_listing=json.loads((source/'listing.json').read_text())
    assert saved_listing['title']=='Fresh photo result' and saved_listing['normalized_size']=='L'
    assert result['reanalysis_baseline']['Size']=='18 / L'
    # The draft link and buy price belong to the item, not the AI read.
    assert saved_listing['draft_url']=='https://www.vinted.co.uk/items/1/edit' and saved_listing['buy_price_gbp']==5
    for role,data in photos.items():
        assert (source/(role+'.jpg')).read_bytes()==data
    # The AI read the exact saved photo slots, without old corrections as hints.
    analysed=pipeline.call_args.args[0]
    assert analysed!=source and pipeline.call_args.args[1]=={} and not analysed.exists()
    assert pipeline.call_args.kwargs['buy_price_gbp']==5
    assert result['cost_tokens']=={'input':200,'output':60}
    repeated=client.post('/reanalyze/'+source.name,json={'request_id':nonce})
    assert repeated.status_code==200 and repeated.json['folder']==source.name and pipeline.call_count==1
    page=client.get('/review/'+source.name)
    assert page.status_code==200 and b'Fresh photo analysis' in page.data and b'Previous listing' in page.data


def test_failed_paid_attempt_leaves_listing_unchanged_and_can_be_retried(saved):
    root,source,old,pipeline,client=saved
    original=(source/'listing.json').read_bytes()
    pipeline.side_effect=RuntimeError('private provider details')
    nonce=str(uuid.uuid4())
    response=client.post('/reanalyze/'+source.name,json={'request_id':nonce})
    assert response.status_code==500 and 'private' not in response.json['error']
    assert (source/'listing.json').read_bytes()==original
    assert [p.name for p in root.iterdir() if p.name.startswith('upload_')]==[source.name]
    pipeline.side_effect=None
    assert client.post('/reanalyze/'+source.name,json={'request_id':nonce}).status_code==200
    assert pipeline.call_count==2


def test_missing_photos_invalid_nonce_and_symlinks_never_start_ai(saved):
    root,source,old,pipeline,client=saved
    assert client.post('/reanalyze/'+source.name,json={'request_id':'../../bad'}).status_code==422
    for photo in source.glob('*.jpg'): photo.unlink()
    outside=root/'outside.jpg';outside.write_bytes(b'outside')
    (source/'front.jpg').symlink_to(outside)
    response=client.post('/reanalyze/'+source.name,json={'request_id':str(uuid.uuid4())})
    assert response.status_code==422 and 'No saved' in response.json['error']
    assert not pipeline.called


def test_reanalysis_button_is_visible_in_draft_sheet(saved):
    _,source,_,_,client=saved
    page=client.get('/drafts')
    assert page.status_code==200 and b'Analyse photos again' in page.data
