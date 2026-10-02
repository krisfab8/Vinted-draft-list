import json
from types import SimpleNamespace as NS
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.services import model_usage as m


def response(in_tokens=100, out_tokens=20):
    return NS(usage=NS(input_tokens=in_tokens, output_tokens=out_tokens), stop_reason='end_turn')


def test_parallel_rereads_and_escalation_accounted():
    @m.tracked('extract')
    def extract():
        m.call(lambda **kw: response(), stage='extract', model='claude-haiku-4-5-20251001')
        m.call(lambda **kw: response(200, 30), stage='extract', model='claude-sonnet-4-6')
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(copy_context().run, m.call, lambda **kw: response(),
                                   stage=stage, model='claude-haiku-4-5-20251001')
                       for stage in ('brand_reread', 'material_reread')]
            for future in futures: future.result()
        return {}, {'model': 'claude-sonnet-4-6'}
    with m.run('item'):
        _, usage = extract()
    assert len(usage['calls']) == 4
    assert usage['input_tokens'] == 500
    assert usage['output_tokens'] == 90
    assert usage['cost_complete']
    assert {c['item'] for c in usage['calls']} == {'item'}
    assert len({c['run_id'] for c in usage['calls']}) == 1
    assert sum(c['cost_usd'] for c in usage['calls']) == pytest.approx(.00165)


def test_usage_survives_parse_failure_and_error_does_not_leak():
    with m.run('item'):
        m.call(lambda **kw: response(), stage='extract', model='claude-haiku-4-5-20251001')
        def broken(**kw): raise ValueError('secret-key-do-not-save')
        with pytest.raises(ValueError):
            m.call(broken, stage='write', model='claude-haiku-4-5-20251001')
    raw = m.LEDGER_PATH.read_text()
    events = [json.loads(line) for line in raw.splitlines()]
    assert len(events) == 2
    assert events[0]['cost_usd'] > 0
    assert events[1]['cost_gbp'] is None
    assert events[1]['billing_status'] == 'unknown'
    assert 'secret-key' not in raw


def test_cache_rates_and_unknown_model():
    event = {'model':'claude-haiku-4-5-20251001', 'input_tokens':100,
             'output_tokens':20, 'cache_creation_input_tokens':1000, 'cache_read_input_tokens':2000}
    assert m.cost_usd(event) == pytest.approx(.00165)
    assert m.cost_usd(dict(event, model='unknown')) is None


def test_mill_relevance_retains_tailoring_and_skips_leather():
    from app.extractor import _mill_check_relevant
    assert not _mill_check_relevant({'item_type':'leather jacket','materials':['100% leather']})
    assert not _mill_check_relevant({'item_type':'t-shirt','materials':['cotton']})
    assert _mill_check_relevant({'item_type':'blazer','materials':['wool']})
    assert _mill_check_relevant({'item_type':'jacket','fabric_line':'Trofeo'})


def test_incomplete_openai_response_still_records_paid_usage(monkeypatch):
    from app.services import openai_provider
    monkeypatch.setattr(openai_provider.config, 'OPENAI_API_KEY', 'test')
    monkeypatch.setattr(openai_provider.requests, 'post', lambda *a,**kw:NS(
        status_code=200,json=lambda:{'status':'incomplete','usage':{'input_tokens':50,'output_tokens':10}}))
    with pytest.raises(ValueError, match='incomplete'):
        openai_provider.generate('JSON','gpt-6-luna',100)
    event=json.loads(m.LEDGER_PATH.read_text())
    assert event['input_tokens']==50 and event['cost_gbp']>0
