import io,json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from PIL import Image
from app.services import measurements as m, model_usage


def reading(**kwargs):
    return dict(start=2,end=66,unit='cm',start_visible=True,end_visible=True,aligned=True,confidence='high',**kwargs)


def test_units_nonzero_start_and_hidden_references():
    raw=reading()
    assert m.proposal(raw,'measure_length','photo.jpg')['value_cm']==64
    assert m.proposal(dict(raw,start=0,end=25,unit='in'),'measure_length','photo.jpg')['value_cm']==63.5
    for field,value in [('start_visible',False),('end_visible',False),('aligned',False),('confidence','low'),('unit','mm'),('start',None),('end',float('nan')),('end',True),('start',-1),('end',1)]:
        result=m.proposal(dict(raw,**{field:value}),'measure_length','photo.jpg')
        assert result['status']=='unknown' and result['value_cm'] is None


def test_roles_do_not_shift_missing_slots():
    roles=m.parse_roles(json.dumps(['front','material','measure_length']),3)
    paths=[Path('one.jpg'),Path('two.jpg'),Path('three.jpg')]
    mapped=m.role_map(paths,roles)
    assert mapped['material']==paths[1] and 'brand' not in mapped
    for raw,count in [('[]',1),('["front","front"]',2),('["../bad"]',1),('null',1)]:
        with pytest.raises(ValueError):m.parse_roles(raw,count)


def test_optional_ruler_call_records_usage_and_requires_confirmation(tmp_path,monkeypatch):
    from app import extractor
    Image.new('RGB',(100,100),'white').save(tmp_path/'measure_length.jpg')
    created=[]
    def create(**kwargs):
        created.append(kwargs)
        return NS(content=[NS(text=json.dumps({'readings':[dict(reading(),source_photo='measure_length.jpg')]}))],
                  usage=NS(input_tokens=200,output_tokens=100),stop_reason='end_turn')
    monkeypatch.setattr(extractor.anthropic,'Anthropic',lambda **kwargs:NS(messages=NS(create=create)))
    with model_usage.run(tmp_path) as context:
        proposals=m.analyze(tmp_path,'claude-haiku')
    assert len(created)==1 and created[0]['max_tokens']==600
    assert proposals[0]['status']=='needs_confirmation'
    assert context['calls'][0]['stage']=='measurements'
    assert m.analyze(tmp_path/'missing','claude-haiku')==[]
    assert len(created)==1


def test_confirmation_is_validated_and_does_not_change_tagged_size():
    listing={'description':'A jacket.\n\nKeywords: jacket','tagged_size':'2XL','normalized_size':'2XL'}
    listing['measurements']=m.confirmed([{'role':'measure_pit_to_pit','value_cm':64}])
    m.apply_description(listing); first=listing['description'];m.apply_description(listing)
    assert listing['description']==first and first.count('seller confirmed')==1
    assert 'flat width' in first and 'circumference' not in first
    assert listing['tagged_size']==listing['normalized_size']=='2XL'
    listing['measurements']=[];m.apply_description(listing)
    assert 'seller confirmed' not in listing['description'] and 'Keywords:' in listing['description']
    for cm in [True,0,-1,float('inf'),float('nan'),'64',251]:
        with pytest.raises(ValueError):m.confirmed([{'role':'measure_length','value_cm':cm}])


def test_phone_orientation_applied_before_resize(tmp_path):
    from app.web import _resize_photo
    from app.extractor import _compress_image
    import base64
    path=tmp_path/'rotated.jpg'; img=Image.new('RGB',(80,40),'red');exif=img.getexif();exif[274]=6;img.save(path,exif=exif)
    encoded,_=_compress_image(path,1024)
    assert Image.open(io.BytesIO(base64.b64decode(encoded))).size==(40,80)
    _resize_photo(path)
    result=Image.open(path)
    assert result.size==(40,80) and result.getexif().get(274) is None


def test_real_upload_manifest_and_confirmation_route(tmp_path,monkeypatch):
    from app import web
    from app.services import pipeline
    monkeypatch.setattr(web,'ITEMS_DIR',tmp_path)
    monkeypatch.setattr(web,'_log_cost',lambda *a:None)
    monkeypatch.setattr(web,'_write_run_log',lambda *a:None)
    monkeypatch.setattr(web,'_sync_item_status',lambda *a:None)
    def run(folder,hints,**kwargs):
        manifest=json.loads((folder/'photo_roles.json').read_text())
        assert manifest['roles']['material']=='material.jpg'
        assert (folder/'measure_length.jpg').exists() and not (folder/'brand.jpg').exists()
        listing={'brand':'Avia Trix','item_type':'leather jacket','title':'Leather jacket 2XL',
                 'description':'A jacket.','tagged_size':'2XL','normalized_size':'2XL','price_gbp':68,'category':'Men > Jackets'}
        usage={'model':'claude-haiku-4-5-20251001','input_tokens':100,'output_tokens':20}
        return listing,usage,dict(usage),{},{}
    monkeypatch.setattr(pipeline,'run_pipeline',run)
    def photo():
        stream=io.BytesIO();Image.new('RGB',(32,32),'white').save(stream,format='JPEG');stream.seek(0);return stream
    c=web.app.test_client()
    result=c.post('/upload',data={'photos':[(photo(),'a.jpg'),(photo(),'b.jpg'),(photo(),'c.jpg')],
        'photo_roles':json.dumps(['front','material','measure_length'])})
    assert result.status_code==200
    folder=result.json['folder']
    assert c.post('/listing/'+folder+'/measurements',json={'measurements':[{'role':'measure_length','value_cm':64}]}).status_code==200
    saved=c.get('/listing/'+folder).json
    assert saved['normalized_size']=='2XL' and '64 cm' in saved['description']
    old=(tmp_path/folder/'listing.json').read_text()
    assert c.post('/listing/'+folder+'/measurements',json={'measurements':[{'role':'measure_length','value_cm':-1}]}).status_code==422
    assert (tmp_path/folder/'listing.json').read_text()==old
    assert c.patch('/listing/'+folder,json={'measurements':[]}).status_code==422
    assert c.post('/upload',data={'photos':[(photo(),'a.jpg'),(photo(),'b.jpg')],
        'photo_roles':'["front","front"]'}).status_code==422


def test_confirmed_measurements_survive_regeneration_without_model_override():
    from app.services.pipeline import preserve_user_fields
    existing={'measurements':[{'role':'measure_length','value_cm':64,'confirmed':True}]}
    generated={'description':'New approved copy.','tagged_size':'2XL','normalized_size':'2XL',
               'measurements':[{'role':'measure_length','value_cm':200,'confirmed':True}]}
    result=preserve_user_fields(existing,generated)
    assert result['measurements'][0]['value_cm']==64
    assert '64 cm' in result['description'] and '200 cm' not in result['description']


def test_measurement_failure_leaves_unknown_and_preserves_ledger(tmp_path,monkeypatch):
    from app import extractor
    Image.new('RGB',(50,50)).save(tmp_path/'measure_sleeve.jpg')
    def create(**kwargs):raise RuntimeError('secret should not be stored')
    monkeypatch.setattr(extractor.anthropic,'Anthropic',lambda **kw:NS(messages=NS(create=create)))
    result=m.analyze(tmp_path,'claude-haiku')
    assert result[0]['status']=='unknown'
    ledger=model_usage.LEDGER_PATH.read_text()
    assert 'secret' not in ledger
    assert json.loads(ledger)['cost_gbp'] is None


def test_full_upload_pipeline_including_three_recorded_model_stages(tmp_path,monkeypatch):
    from app import web, extractor
    monkeypatch.setattr(web,'ITEMS_DIR',tmp_path)
    monkeypatch.setattr(web,'COST_LOG',tmp_path/'cost.csv')
    monkeypatch.setattr(web,'_write_run_log',lambda *a:None)
    monkeypatch.setattr(web,'_sync_item_status',lambda *a:None)
    extracted={'brand':'Avia Trix','item_type':'leather jacket','tagged_size':'2XL','normalized_size':'2XL',
               'materials':['100% Leather'],'colour':'Tan','gender':"men's",'brand_confidence':'high',
               'material_confidence':'high','confidence':.92,'low_confidence_fields':[],
               'condition_summary':'Good used condition','flaws_note':None,
               'measurements':[{'role':'measure_length','value_cm':200,'confirmed':True}]}
    stage_calls=[]
    def create(**kwargs):
        max_tokens=kwargs['max_tokens'];stage_calls.append(max_tokens)
        if max_tokens==1024:
            payload=extracted; usage=NS(input_tokens=1000,output_tokens=100)
        elif max_tokens==600:
            payload={'readings':[dict(reading(),source_photo='measure_length.jpg')]}
            usage=NS(input_tokens=400,output_tokens=80)
        elif max_tokens==2500:
            payload=dict(extracted,title='Avia Trix Leather Jacket Mens 2XL Tan',description='A jacket.',price_gbp=68,category='Men > Jackets')
            usage=NS(input_tokens=300,output_tokens=60)
        else:raise AssertionError('Unnecessary reread')
        return NS(content=[NS(text=json.dumps(payload))],usage=usage,stop_reason='end_turn')
    monkeypatch.setattr(extractor.anthropic,'Anthropic',lambda **kwargs:NS(messages=NS(create=create)))
    def photo():
        stream=io.BytesIO();Image.new('RGB',(40,60),'white').save(stream,format='JPEG');stream.seek(0);return stream
    client=web.app.test_client()
    result=client.post('/upload',data={'photos':[(photo(),'front.jpg'),(photo(),'material.jpg'),(photo(),'ruler.jpg')],
        'photo_roles':'["front","material","measure_length"]'})
    assert result.status_code==200, result.json
    timing=result.headers['Server-Timing']
    assert all(stage+';dur=' in timing for stage in ['receive','prepare','pipeline','total'])
    data=result.json
    snapshot_path=web.ITEMS_DIR/data['folder']/'analysis.json'
    snapshot=json.loads(snapshot_path.read_text())
    assert snapshot['listing']['cost_gbp']==data['cost_gbp']
    assert snapshot['listing']['measurements']==[]
    assert snapshot['extract_log']['photos_found']==['front','material']
    assert stage_calls==[1024,600,2500]
    assert [c['stage'] for c in data['model_calls']]==['extract','measurements','write']
    assert len({c['run_id'] for c in data['model_calls']})==1
    assert data['cost_gbp']==pytest.approx(.00229)
    assert data['cost_tokens']=={'input':1700,'output':240}
    assert data['cost_complete'] is True and data['measurements']==[]
    assert data['measurement_proposals'][0]['value_cm']==64
    assert data['normalized_size']=='2XL' and '200' not in data['description']
    confirmed=client.post('/listing/'+data['folder']+'/measurements',json={'measurements':[{'role':'measure_length','value_cm':64}]})
    assert confirmed.status_code==200 and '64 cm' in confirmed.json['description']
    assert json.loads(snapshot_path.read_text())==snapshot
    assert stage_calls==[1024,600,2500]  # Seller confirmation is free.
