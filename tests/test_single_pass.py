import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from app.services import pipeline, single_pass


def evidence():
    return dict(brand='Barbour', item_type='wax jacket', tagged_size='M',
                normalized_size='M', materials=['100% Cotton'], colour='Navy',
                gender="men's", condition_summary='Good used condition',
                flaws_note=None, price_gbp=40, category='Men > Coats > Overcoat',
                brand_confidence='high', material_confidence='high',
                tag_keywords_confidence='low', tag_keywords=['Rare'], confidence=.95,
                low_confidence_fields=['pattern'], pattern='Pinstripe')


def test_real_pipeline_one_response_no_writer_and_all_costs(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'ENABLE_SINGLE_PASS', True)
    monkeypatch.setattr(config, 'VISION_PROVIDER', 'claude-haiku')
    monkeypatch.setattr(config, 'LISTING_PROVIDER', 'claude-haiku')
    Image.new('RGB', (600, 800), 'navy').save(tmp_path / 'front.jpg')
    response = SimpleNamespace(content=[SimpleNamespace(text=json.dumps(evidence()))],
                               usage=SimpleNamespace(input_tokens=3000, output_tokens=400),
                               stop_reason='end_turn')
    with patch('app.extractor.anthropic.Anthropic') as client, \
         patch('app.listing_writer.write', side_effect=AssertionError('paid writer invoked')):
        client.return_value.messages.create.return_value = response
        listing, extracted, written, log, _ = pipeline.run_pipeline(
            tmp_path, {'brand': 'Confirmed Brand', 'size': 'L'}, buy_price_gbp=10)
    assert client.return_value.messages.create.call_count == 1
    assert listing['brand'] == 'Confirmed Brand' and listing['normalized_size'] == 'L'
    assert 'Confirmed Brand' in listing['title']
    assert 'Pinstripe' not in listing['description'] and 'Rare' not in listing['description']
    assert '100% Cotton' in listing['description']
    assert listing['buy_price_gbp'] == 10
    assert len(extracted['calls']) == 1 and written['calls'] == []
    assert extracted['input_tokens'] == 3000 and written['input_tokens'] == 0
    assert extracted['calls'][0]['cost_usd'] == .005
    assert log['pipeline_version'] == 'single-pass-v1'


def test_corrected_evidence_and_hints_used_for_copy():
    item = evidence()
    item.update(brand='Reread Brand', model_name='Uncertain model', model_confidence='low')
    result, _ = single_pass.assemble(item, {'made_in': 'Portugal', 'damages': 'Small hole'})
    assert 'Reread Brand' in result['title']
    assert 'Uncertain model' not in result['title']
    assert 'Portugal' in result['description'] and result['flaws_note'] == 'Small hole'


@pytest.mark.parametrize('kind,size,expected', [('blazer', '54', '44R'), ('trainers', '43', '9')])
def test_size_conversion_before_copy(kind, size, expected):
    item = evidence()
    item.update(item_type=kind, tagged_size=size, normalized_size=size)
    result, _ = single_pass.assemble(item, {})
    assert result['normalized_size'] == expected
    assert expected in result['title'] and f'Size: UK {expected} / EU {size}' in result['description']
    assert result['tagged_size']==size


def test_missing_price_fails_without_paid_fallback():
    item = evidence()
    item.pop('price_gbp')
    with pytest.raises(ValueError, match='price_gbp'):
        single_pass.assemble(item, {})


def test_shorter_prompt_and_no_paid_copy_stage():
    from app.extractor import _EXTRACT_PROMPT
    assert len(single_pass.build_prompt({})) < len(_EXTRACT_PROMPT)
