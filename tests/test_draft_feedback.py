import io
import json
import zipfile
import pytest
from PIL import Image
from app.services import item_backup, review_evidence, model_usage


@pytest.fixture
def item(tmp_path, monkeypatch):
    from app import web
    folder = tmp_path / 'upload_a58f2f04'
    folder.mkdir()
    listing = {'brand':'Boggi','item_type':'Blazer','title':'Boggi blazer',
               'description':'Original result','tagged_size':'54','normalized_size':'44R',
               'price_gbp':50,'category':'Men > Suits > Blazers'}
    (folder/'listing.json').write_text(json.dumps(listing))
    Image.new('RGB',(40,60)).save(folder/'front.jpg')
    monkeypatch.setattr(web, 'ITEMS_DIR', tmp_path)
    monkeypatch.setattr(model_usage,'LEDGER_PATH',tmp_path/'usage.jsonl')
    monkeypatch.setattr(web.pipeline_svc, 'run_pipeline', lambda *a, **k: pytest.fail('Unexpected AI call'))
    monkeypatch.setattr(web.item_store,'sync_from_listing',lambda *a, **k: None)
    monkeypatch.setitem(web.app.config,'HOSTED_TEST',True)
    return web.app.test_client(), folder, listing


def test_feedback_snapshot_corrections_and_device_backup_roundtrip(item, tmp_path):
    client, folder, original = item
    review_evidence.capture(folder, original, pipeline_latency_ms=12199)
    changed = dict(original,price_gbp=100)
    (folder/'listing.json').write_text(json.dumps(changed))
    response = client.post('/listing/'+folder.name+'/feedback',json={'issues':['fabric','price'], 'notes':'Loro Piana Zealander Dream cloth'})
    assert response.status_code == 200
    assert client.get('/listing/'+folder.name+'/feedback').json['issues']==['fabric','price']
    assert json.loads((folder/'listing.json').read_text()) == changed
    evidence=json.loads((folder/'analysis.json').read_text())
    assert evidence['listing']==original and evidence['pipeline_latency_ms']==12199
    archive=client.get('/api/private/backup?folder='+folder.name).data
    target=tmp_path/'restored'
    assert item_backup.restore(archive,target)==[folder.name]
    assert json.loads((target/folder.name/'feedback.json').read_text())['notes'].startswith('Loro Piana')
    assert json.loads((target/folder.name/'analysis.json').read_text())==evidence
    assert (target/folder.name/'front.jpg').read_bytes()==(folder/'front.jpg').read_bytes()
    assert json.loads((target/folder.name/'listing.json').read_text())['price_gbp']==100
    with pytest.raises(ValueError): item_backup.restore(archive,target)


def test_feedback_validation_missing_and_export_scope(item):
    client, folder, listing = item
    for body in [None,{'issues':['unknown']},{'issues':'fabric'},{'notes':'x'*2001}]:
        assert client.post('/listing/'+folder.name+'/feedback',json=body).status_code==422
    assert not (folder/'feedback.json').exists()
    assert client.get('/listing/upload_00000000/feedback').status_code==404
    assert client.get('/api/private/backup?folder=../bad').status_code==422
    sibling=folder.parent/'upload_00000000';sibling.mkdir()
    (sibling/'listing.json').write_text(json.dumps(listing))
    data=client.get('/api/private/backup?folder='+folder.name).data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert all('upload_00000000' not in name for name in archive.namelist())


def test_saved_evidence_route_does_not_generate_again(item):
    client, folder, listing = item
    listing.update(fabric_mill='Pey Lino Panavot', fabric_line='Zelander Dream',
                   ai_price_gbp=110, materials=['100% Wool'], condition_summary='Good condition')
    (folder/'listing.json').write_text(json.dumps(listing))
    response=client.post('/listing/'+folder.name+'/check-evidence')
    assert response.status_code==200
    assert response.json['fabric_mill']=='Loro Piana' and response.json['price_gbp']==110
    assert client.post('/listing/upload_00000000/check-evidence').status_code==404


def test_restore_unknown_optional_colour_preserves_evidence_and_required_errors(item, tmp_path):
    client, folder, listing = item
    listing['colour'] = None
    (folder/'listing.json').write_text(json.dumps(listing))
    review_evidence.capture(folder, listing)
    archive = client.get('/api/private/backup?folder='+folder.name).data
    target = tmp_path/'unknown-colour'
    item_backup.restore(archive, target)
    restored = json.loads((target/folder.name/'listing.json').read_text())
    assert 'colour' not in restored
    assert restored['title'] == listing['title']
    assert json.loads((target/folder.name/'analysis.json').read_text())['listing']['colour'] is None
    listing['price_gbp'] = None
    (folder/'listing.json').write_text(json.dumps(listing))
    invalid = client.get('/api/private/backup?folder='+folder.name).data
    with pytest.raises(ValueError, match='price_gbp'):
        item_backup.restore(invalid, tmp_path/'invalid-required')
    assert not (tmp_path/'invalid-required').exists()
