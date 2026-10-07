import json
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from app import listing_writer, config
from app.services import description_layout, garment_text, compact_writer, copy_quality

# Illustrative transcription, not verified ground truth for the user's photo.
WORDING = 'Dunbarney Golf Club'
ITEM = dict(brand='Galvin Green', item_type='polo shirt', tagged_size='L', normalized_size='L',
            materials=['97% Polyester', '3% Elastane'], material_confidence='high',
            brand_confidence='high', colour='Blue', gender="men's", condition_summary='Good condition',
            garment_text=[dict(text=WORDING, location='chest embroidery', confidence='high')])


@pytest.mark.parametrize('compact', [True, False])
def test_real_writer_retains_unfamiliar_markings_when_model_omits_them(monkeypatch, compact):
    monkeypatch.setattr(config, 'ENABLE_COMPACT_WRITER', compact)
    proposed=dict(ITEM, title='Galvin Green Blue Polo L', description='Blue polo shirt.',
                  price_gbp=25, category='Men > Tops > Polo shirts')
    proposed.pop('garment_text')
    client=NS(messages=NS(create=lambda **kw:NS(content=[NS(text=json.dumps(proposed))],
              usage=NS(input_tokens=100,output_tokens=50), stop_reason='end_turn')))
    monkeypatch.setattr(listing_writer.anthropic, 'Anthropic', lambda **kw:client)
    listing, _ = listing_writer.write(deepcopy(ITEM))
    assert listing['brand']=='Galvin Green' and listing['garment_text']==ITEM['garment_text']
    assert '- Logo / print: '+WORDING+', chest embroidery' in listing['description']
    assert WORDING not in listing['title']
    first=listing['description']
    description_layout.apply(listing)
    assert listing['description']==first


def test_each_readable_marking_survives_unknown_name_unicode_and_duplicates():
    listing=dict(description='A shirt.', garment_text=[
        dict(text=' ZŁOTY  KLUB ', location='back print', confidence='high'),
        dict(text='ZŁOTY KLUB', location='back print', confidence='high'),
        dict(text='Acme Works', location='sleeve print', confidence='high')])
    description_layout.apply(listing)
    assert listing['description'].count('ZŁOTY KLUB')==1
    assert 'Acme Works' in listing['description']
    assert 'affiliated' not in listing['description']


def test_uncertain_wording_retained_as_evidence_but_not_published():
    item=deepcopy(ITEM)
    item['garment_text'][0]['confidence']='low'
    listing=dict(description='Polo shirt.')
    garment_text.carry(listing,item)
    description_layout.apply(listing)
    assert WORDING not in listing['description']
    assert 'garment_text' in listing['low_confidence_fields']
    assert listing['garment_text'][0]['text']==WORDING
    assert copy_quality.writer_evidence(item)['garment_text']==[]
    generated=dict(title='Polo '+WORDING, description='Polo with '+WORDING)
    copy_quality.apply(generated,item)
    assert WORDING not in generated['title'] and WORDING not in generated['description']


def test_compact_prompt_carries_readable_exterior_words_separate_from_brand():
    prompt=compact_writer.build_prompt(ITEM,{},'Men > Tops > Polo shirts')
    assert WORDING in prompt and 'garment_text' in prompt
    assert 'unfamiliar' in prompt and 'affiliation' in prompt


def test_legacy_listing_without_markings_gets_no_invented_detail():
    listing={'description':'Plain shirt.'}
    description_layout.apply(listing)
    assert listing['description']=='Plain shirt.'
    assert garment_text.normalize([None,'Logo',dict(text=None)])==[]
