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
        assert usage['_write_log']['prompt_version']==('compact-v1' if enabled else 'legacy')
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
