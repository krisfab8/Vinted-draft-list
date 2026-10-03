import json
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from app.services import copy_quality, condition, ebay_comps as e


def test_uncertain_copy_and_duplicate_condition_are_removed_without_losing_product_details():
    item={'pattern':'Graphic','low_confidence_fields':['pattern'],'model_name':'Power','model_confidence':'low','tag_keywords':['design']}
    assert copy_quality.writer_evidence(item)['pattern'] is None
    assert copy_quality.writer_evidence(item)['model_name'] is None
    listing={'title':'Sweaty Betty Graphic Leggings S',
             'description':'Sweaty Betty leggings with graphic detailing.\n\nGood condition with minor creasing from storage. No holes, tears or stains. British design activewear.',
             'condition_summary':'Good condition; minor creasing from storage; no holes, tears, or stains detected.'}
    copy_quality.apply(listing,item)
    condition.apply_condition(listing);condition.inject_condition_line(listing)
    assert 'graphic' not in listing['description'].lower() and 'Graphic' not in listing['title']
    assert 'storage' not in listing['condition_summary']
    assert 'British design activewear.' in listing['description']
    assert listing['description'].lower().count('condition')==1
    assert 'No holes' not in listing['description']
    original=listing['description'];condition.inject_condition_line(listing)
    assert listing['description']==original


def test_cache_prefix_preserves_every_instruction_and_keeps_hints_images_outside_cache(monkeypatch):
    from app import extractor as x,config
    calls=[]
    def create(**kw):
        calls.append(kw)
        return NS(content=[NS(text='{}')],usage=NS(input_tokens=10,output_tokens=2),stop_reason='end_turn')
    monkeypatch.setattr(x.anthropic,'Anthropic',lambda **kw:NS(messages=NS(create=create)))
    monkeypatch.setattr(config,'ENABLE_PROMPT_CACHE',True)
    photo={'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':'fixture'}}
    for brand in ['Seller brand A','Seller brand B']:
        x._extract_claude([photo],x.HAIKU_MODEL,x._build_prompt_with_hints({'brand':brand}))
    a,b=[v['messages'][0]['content'] for v in calls]
    assert a[0]==b[0] and a[0]['text']==x._EXTRACT_PROMPT
    assert a[0]['cache_control']=={'type':'ephemeral'}
    assert 'Seller brand A' in a[1]['text'] and 'Seller brand B' in b[1]['text']
    assert a[-1]==photo and 'cache_control' not in a[-1]


def test_relevance_and_query_use_visible_model_size_material():
    listing={'brand':'Sweaty Betty','item_type':'cropped leggings','normalized_size':'S','model_name':'Power','model_confidence':'high'}
    assert e._build_query(listing)=='Sweaty Betty cropped leggings Power S'
    assert e._relevant({'title':'Sweaty Betty Power Capri Leggings S'},listing)
    assert not e._relevant({'title':'Sweaty Betty Power Capri Leggings XL'},listing)
    assert not e._relevant({'title':'Nike Power Capri Leggings S'},listing)
    listing['model_confidence']='low'
    assert 'Power' not in e._build_query(listing)
    assert 'cashmere' in e._build_query({'brand':'X','brand_confidence':'high','item_type':'jumper','materials':['100% Cashmere']})


def test_cached_asking_summary_filters_noise_and_never_invents_sold_data(tmp_path,monkeypatch):
    monkeypatch.setattr(e,'_cache_path',lambda:tmp_path/'cache.json')
    monkeypatch.setattr(e,'_cfg',lambda:NS(ENABLE_EBAY_COMPS=True,EBAY_APP_ID='id',EBAY_CERT_ID='secret',EBAY_ACTIVE_TO_SOLD_DISCOUNT=.7))
    monkeypatch.setattr(e,'_get_token',Mock(return_value='token'))
    search=Mock(return_value=[{'title':'Sweaty Betty cropped leggings S','price_gbp':p,'url':'https://www.ebay.co.uk/itm/1','shipping_gbp':None} for p in [10,12,14]]+
                [{'title':'Nike cropped leggings S','price_gbp':1000}])
    monkeypatch.setattr(e,'_search',search)
    listing={'brand':'Sweaty Betty','item_type':'cropped leggings','normalized_size':'S','price_gbp':18}
    e.enrich(listing)
    market=listing['ebay_market']
    assert market['mean_asking_gbp']==12 and market['median_asking_gbp']==12 and market['sample_count']==3
    assert market['sold_mean_gbp'] is None and market['sell_through_percent'] is None and market['mean_delivered_gbp'] is None
    assert listing['price_gbp']==18
    e.enrich(dict(listing));assert search.call_count==1
    assert 'token' not in (tmp_path/'cache.json').read_text() and 'secret' not in (tmp_path/'cache.json').read_text()
    monkeypatch.setattr(e,'CACHE_TTL',-1)
    e.enrich(dict(listing));assert search.call_count==2


def test_research_ratios_have_explicit_period_and_unknown_zero_denominators():
    result=e.research_metrics(100,200,90)
    assert result['sales_to_active_percent']==200 and result['active_to_sold_ratio']==.5
    assert result['sold_share_percent']==66.67 and result['source']=='seller_entered_research'
    assert e.research_metrics(0,0,90)['sales_to_active_percent'] is None
    assert e.research_metrics(10,0,90)['active_to_sold_ratio'] is None
    assert e.research_metrics(10,20,90,12.5)['mean_sold_gbp']==12.5
    for price in [True,-1,float('nan'),float('inf'),'12']:
        with pytest.raises(ValueError):e.research_metrics(10,20,90,price)
    for counts in [(True,2,90),(-1,2,90),(1,2,91),(1,2,0),(1.2,2,90)]:
        with pytest.raises(ValueError):e.research_metrics(*counts)


def test_research_route_preserves_price_and_rejects_invalid_data(tmp_path,monkeypatch):
    from app import web
    monkeypatch.setattr(web,'ITEMS_DIR',tmp_path)
    path=tmp_path/'item';path.mkdir();file=path/'listing.json'
    file.write_text(json.dumps({'price_gbp':18,'title':'Seller title','brand':'Sweaty Betty','item_type':'cropped leggings'}))
    client=web.app.test_client()
    response=client.post('/api/listing/item/ebay-research',json={'active_count':100,'sold_count':200,'period_days':90})
    assert response.status_code==200 and response.json['sales_to_active_percent']==200
    assert json.loads(file.read_text())['price_gbp']==18
    before=file.read_text()
    assert client.post('/api/listing/item/ebay-research',json={'active_count':-1,'sold_count':2,'period_days':90}).status_code==422
    assert file.read_text()==before


def test_backup_roundtrip_and_invalid_paths_never_import_auth(tmp_path,monkeypatch):
    import io,zipfile
    from app.services import item_backup,model_usage
    source=tmp_path/'source';folder=source/'upload_a58f2f04';folder.mkdir(parents=True)
    listing={'brand':'Sweaty Betty','item_type':'cropped leggings','title':'Seller approved title',
             'description':'Approved copy.','tagged_size':'S','normalized_size':'S','price_gbp':18,'category':'Women > Trousers > Leggings'}
    (folder/'listing.json').write_text(json.dumps(listing))
    (folder/'auth_state.json').write_text('must not be exported')
    from PIL import Image
    Image.new('RGB',(40,60)).save(folder/'front.jpg')
    archive=item_backup.export(source)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert all('auth' not in name for name in z.namelist())
    target=tmp_path/'target'
    assert item_backup.restore(archive,target)==['upload_a58f2f04']
    saved=json.loads((target/folder.name/'listing.json').read_text())
    assert saved['title']==listing['title'] and saved['price_gbp']==18
    assert (target/folder.name/'front.jpg').read_bytes()==(folder/'front.jpg').read_bytes()
    with pytest.raises(ValueError):item_backup.restore(archive,target)
    for name in ['items/../../auth_state.json','items/upload_a58f2f04/auth_state.json','items/upload_a58f2f04/../listing.json']:
        bad=io.BytesIO()
        with zipfile.ZipFile(bad,'w') as z:z.writestr(name,'{}')
        with pytest.raises(ValueError):item_backup.restore(bad.getvalue(),tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_copy_keeps_known_size_and_exact_composition_without_upgrading_condition():
    item={'condition_summary':'Good condition; minor creasing from storage',
          'material_confidence':'high','pattern':'Graphic','low_confidence_fields':['pattern']}
    listing={'title':'Leggings','description':'Navy leggings.', 'normalized_size':'S',
             'materials':['81% Polyester','19% Elastane'],'condition_summary':'Excellent condition','style':'Graphic'}
    copy_quality.apply(listing,item)
    assert '- Size: S' in listing['description'] and '81% Polyester, 19% Elastane' in listing['description']
    assert listing['condition_summary'].startswith('Good condition') and 'storage' not in listing['condition_summary']
    assert listing['style'] is None
    original=listing['description'];copy_quality.apply(listing,item)
    assert listing['description']==original
