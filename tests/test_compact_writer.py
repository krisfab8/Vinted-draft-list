import json
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace as NS
from app import listing_writer as w, config
from app.services import compact_writer, pricing

ITEM={'brand':'Avia Trix','item_type':'leather jacket','normalized_size':'2XL',
      'tagged_size':'2XL','materials':['100% Leather'],'gender':"men's",'colour':'Tan',
      'made_in':'UK','condition_summary':'Good used condition','brand_confidence':'high',
      'material_confidence':'high','confidence':.92}


def test_compact_contract_is_smaller_and_preserves_evidence():
    categories=w._slice_category_rules(ITEM['gender'],ITEM['item_type'])
    compact=compact_writer.build_prompt(ITEM, {'brand':'Confirmed brand'}, categories)
    original=w._build_prompt(ITEM, hints={'brand':'Confirmed brand'})
    assert len(compact)<len(original)*.65
    for text in ['2XL','100% Leather','Confirmed brand','UK',categories]: assert text in compact
    assert 'never invent' in compact and 'ruler' in compact


def test_real_writer_postprocessing_with_compact_and_rollback(monkeypatch):
    calls=[]
    listing=dict(ITEM,title='Avia Trix Leather Jacket Mens 2XL Tan',description='Leather jacket.',
                 price_gbp=68,category='Men > Jackets')
    def create(**kw):
        calls.append(kw)
        return NS(content=[NS(text=json.dumps(listing))],usage=NS(input_tokens=100,output_tokens=50),stop_reason='end_turn')
    client=NS(messages=NS(create=create))
    monkeypatch.setattr(w.anthropic,'Anthropic',lambda **kw:client)
    for enabled in [True,False]:
        monkeypatch.setattr(config,'ENABLE_COMPACT_WRITER',enabled)
        result,usage=w.write(ITEM,hints={'size':'2XL'})
        assert result['normalized_size']=='2XL' and result['price_gbp']==68
        assert usage['_write_log']['prompt_version']==('compact-v2-delta' if enabled else 'legacy')
    assert len(calls[0]['messages'][0]['content'])<len(calls[1]['messages'][0]['content'])


def test_price_evidence_never_invents_market_range(monkeypatch):
    monkeypatch.setattr(pricing,'lookup_memory',lambda **kw:None)
    listing=dict(ITEM,price_gbp=68)
    pricing.apply_pricing(listing)
    assert listing['price_gbp']==68
    assert listing['price_evidence']['range_gbp'] is None
    assert listing['price_evidence']['source']=='model_suggestion'
    monkeypatch.setattr(pricing,'lookup_memory',lambda **kw:{'low':30,'high':60,'confidence':'medium'})
    pricing.apply_pricing(listing)
    assert listing['price_evidence']['range_gbp']==[30,60]
    assert listing['price_evidence']['confidence']=='unverified'


def test_optional_numbers_and_authoritative_purchase_price(monkeypatch):
    listing=dict(ITEM,title='Jacket',description='Leather jacket.',price_gbp=68,
                 category='Men > Jackets',buy_price_gbp=None,confidence=None,
                 tag_keywords_confidence=.9,brand_confidence=.8,material_confidence=None)
    def create(**kw):
        return NS(content=[NS(text=json.dumps(listing))],usage=NS(input_tokens=100,output_tokens=50),stop_reason='end_turn')
    monkeypatch.setattr(w.anthropic,'Anthropic',lambda **kw:NS(messages=NS(create=create)))
    result,_=w.write(ITEM)
    assert 'buy_price_gbp' not in result and result['confidence']==.92
    assert result['brand_confidence']=='high' and result['material_confidence']=='high'
    assert result['tag_keywords_confidence']=='low'
    for price in [0, 7.5]:
        result,_=w.write(dict(ITEM,buy_price_gbp=price))
        assert result['buy_price_gbp']==price
    item=dict(ITEM);item.pop('confidence')
    result,_=w.write(item)
    assert 'confidence' not in result


def test_required_price_is_not_silently_invented():
    from app.validate_listing import validate
    listing=dict(ITEM,title='Jacket',description='Jacket.',price_gbp=None,category='Men > Jackets')
    assert any(error.startswith('price_gbp: ') for error in validate(listing))


def test_delta_writer_preserves_labels_and_rejects_missing_price(monkeypatch):
    import pytest
    monkeypatch.setattr(config, 'ENABLE_COMPACT_WRITER', True)
    item = dict(ITEM, fabric_mill='Loro Piana', fabric_line='Zelander Dream',
                price_gbp=99, tag_keywords=['Full Canvas'], tag_keywords_confidence='high')
    proposed = dict(title='Avia Trix jacket', description='Leather jacket.', price_gbp=45,
                    category='Men > Jackets', style=None, premium=False,
                    brand='Invented', materials=['Polyester'], normalized_size='S')
    monkeypatch.setattr(w.anthropic, 'Anthropic', lambda **kw:NS(messages=NS(create=lambda **kw:
        NS(content=[NS(text=json.dumps(proposed))],usage=NS(input_tokens=100,output_tokens=50),stop_reason='end_turn'))))
    result, _ = w.write(item)
    assert result['brand'] == ITEM['brand'] and result['normalized_size'] == '2XL'
    assert result['materials'] == ['100% Leather'] and result['fabric_line'] == 'Zelander Dream'
    assert 'Loro Piana cloth' in result['title'] and 'Full Canvas' in result['title']
    assert result['price_gbp'] == 45
    proposed.pop('price_gbp')
    with pytest.raises(ValueError):
        w.write(item)


def test_optional_nulls_and_gender_formatting_follow_schema():
    from app.validate_listing import normalize_generated_listing, validate
    listing=dict(ITEM,title='Jacket',description='Jacket.',price_gbp=68,category='Women > Jackets',
                 gender=" Women’s ",premium=None,materials=None,colour=None,confidence=None)
    normalize_generated_listing(listing)
    assert listing['gender']=="women's"
    assert not any(k in listing for k in ['premium','materials','colour','confidence'])
    assert validate(listing)==[]
    listing['price_gbp']=None
    normalize_generated_listing(listing)
    assert 'price_gbp' in listing and validate(listing)
    listing['gender']='unknown'
    normalize_generated_listing(listing)
    assert listing['gender']=='unknown' and any('gender' in e for e in validate(listing))
