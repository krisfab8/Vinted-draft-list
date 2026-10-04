import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from PIL import Image
from app.services import fabric_mill, pricing, review_evidence


@pytest.mark.parametrize('maker,line', [('Pey Lino Panavot','Zelander Dream'),('Zelanderream','Zelanderream'),('Loro Plana','Zealander Dream')])
def test_recorded_cloth_line_resolves_noisy_maker_without_changing_brand(maker,line):
    item={'brand':'Boggi','fabric_mill':maker,'fabric_line':line,'tag_keywords':[maker,'Full Canvas'],'low_confidence_fields':[]}
    result=fabric_mill.verify_mill(item)
    assert result['brand']=='Boggi'
    assert result['fabric_mill']=='Loro Piana' and result['fabric_line']=='Zelander Dream'
    assert result['fabric_mill_raw']==maker
    assert result['fabric_resolution']=='cloth_line_registry'
    assert maker not in result['tag_keywords'] or maker=='Loro Piana'


def test_unknown_and_conflicting_maker_not_published_as_high_confidence():
    for maker,line in [('Pey Lino Panavot',None),('Scabal','Zelander Dream')]:
        result=fabric_mill.verify_mill({'fabric_mill':maker,'fabric_line':line,'tag_keywords':[maker], 'material_confidence':'high'})
        assert result['fabric_mill'] is None
        assert result['fabric_mill_confidence']=='low' and 'fabric_mill' in result['low_confidence_fields']
        assert maker not in result['tag_keywords']
    assert fabric_mill.normalise_mill('Loro made-up name') != 'Loro Piana'


def test_premium_tailoring_does_not_use_generic_band_but_regular_blazer_does():
    base={'brand':'Boggi','item_type':'Blazer','materials':['100% Wool'],'price_gbp':110,'condition_summary':'Good condition'}
    premium=pricing.apply_pricing(dict(base,fabric_mill='Loro Piana'))
    assert premium['price_gbp']==110 and premium['price_evidence']['source']=='model_suggestion'
    assert 'premium_price_review' in premium['warnings']
    regular=pricing.apply_pricing(dict(base))
    assert regular['price_gbp']==50
    full_canvas=pricing.apply_pricing(dict(base,tag_keywords=['Full Canvas']))
    assert full_canvas['price_gbp']==110


def test_saved_evidence_check_corrects_copy_keeps_history_and_manual_price(tmp_path):
    listing={'brand':'Boggi','item_type':'Blazer','title':'Boggi blazer','description':'Boggi.\n- Fabric mill: Pey Lino Panavot\n- Fabric line: Zelander Dream\nKeywords: Pey Lino Panavot.',
             'fabric_mill':'Pey Lino Panavot','fabric_line':'Zelander Dream','tag_keywords':['Pey Lino Panavot','Full Canvas'],
             'materials':['100% Wool'],'condition_summary':'Good condition','tagged_size':'54','normalized_size':'44R','category':'Men > Suits > Blazers','price_gbp':50,'ai_price_gbp':110}
    (tmp_path/'listing.json').write_text(json.dumps(listing))
    result=review_evidence.recheck(tmp_path)
    assert result['price_gbp']==110 and 'Loro Piana' in result['description'] and 'Pey Lino' not in result['description']
    assert json.loads((tmp_path/'analysis.json').read_text())['listing']['price_gbp']==50
    result['price_gbp']=125
    (tmp_path/'listing.json').write_text(json.dumps(result))
    assert review_evidence.recheck(tmp_path)['price_gbp']==125


def test_rereads_see_every_core_photo_even_when_material_slot_is_garment(tmp_path,monkeypatch):
    from app import extractor
    for role in ['front','brand','model_size','material']:
        Image.new('RGB',(40,60)).save(tmp_path/(role+'.jpg'))
    response=NS(content=[NS(text='{"fabric_mill":"Loro Piana","fabric_line":"Zelander Dream","brand":"Boggi"}')],usage=NS(input_tokens=100,output_tokens=30),stop_reason='end_turn')
    create=Mock(return_value=response)
    monkeypatch.setattr(extractor.anthropic,'Anthropic',lambda **kwargs:NS(messages=NS(create=create)))
    assert extractor._reread_material_photo(tmp_path,'model')['fabric_mill']=='Loro Piana'
    assert extractor._reread_brand_photo(tmp_path,'model')['brand']=='Boggi'
    assert create.call_count==2
    for call in create.call_args_list:
        assert sum(block['type']=='image' for block in call.kwargs['messages'][0]['content'])==4


def test_overconfident_unknown_mill_triggers_one_bounded_reread(tmp_path,monkeypatch):
    from app import extractor
    Image.new('RGB',(40,60)).save(tmp_path/'front.jpg')
    initial={'brand':'Boggi','brand_confidence':'high','item_type':'Blazer','materials':['100% Wool'], 'material_confidence':'high','fabric_mill':'Pey Lino Panavot','fabric_line':None,'confidence':.95,'low_confidence_fields':[]}
    create=Mock(side_effect=[NS(content=[NS(text=json.dumps(initial))],usage=NS(input_tokens=100,output_tokens=30),stop_reason='end_turn'),NS(content=[NS(text='{"fabric_mill":"Loro Piana","fabric_line":"Zelander Dream"}')],usage=NS(input_tokens=100,output_tokens=30),stop_reason='end_turn')])
    monkeypatch.setattr(extractor.anthropic,'Anthropic',lambda **kwargs:NS(messages=NS(create=create)))
    monkeypatch.setattr(extractor,'VISION_PROVIDER','claude-haiku')
    item,usage=extractor.extract(tmp_path)
    assert create.call_count==2 and item['fabric_mill']=='Loro Piana'
    assert item['_extract_log']['rereads_count']==1
    assert usage['input_tokens']==200 and len(usage['calls'])==2
