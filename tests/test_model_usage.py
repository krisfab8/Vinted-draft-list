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


def test_stats_count_failed_paid_responses_and_repeated_runs_without_duplication():
    from app.web import _compute_stats
    with m.run('item') as context:
        event=m.record('claude-haiku-4-5-20251001','extract',usage=NS(input_tokens=1000,output_tokens=100))
    with m.run('item'):
        m.record('claude-haiku-4-5-20251001','write',error=RuntimeError())
    rows=[{'folder':'item','run_id':context['run_id'],'cost_gbp':event['cost_gbp']},
          {'folder':'item','cost_gbp':.01},{'folder':'item','cost_gbp':.02}]
    stats=_compute_stats([],rows)
    assert stats['total_spend_gbp']==pytest.approx(round(.03+event['cost_gbp'],5))
    assert stats['unpriced_calls']==1


def test_old_cost_csv_migrates_without_losing_history(tmp_path,monkeypatch):
    from app import web
    path=tmp_path/'cost.csv';path.write_text('timestamp,folder,cost_gbp\nold,item,0.02\n')
    monkeypatch.setattr(web,'COST_LOG',path)
    with m.run('item'):
        event=m.record('claude-haiku-4-5-20251001','extract',usage=NS(input_tokens=100,output_tokens=20))
    usage={'model':event['model'],'input_tokens':100,'output_tokens':20,'calls':[event]}
    web._log_cost('item',usage,{'model':event['model'],'input_tokens':0,'output_tokens':0}, {})
    rows=web._get_cost_history()
    assert rows[0]['run_id']==event['run_id']
    assert rows[1]['timestamp']=='old' and rows[1]['cost_gbp']=='0.02'


def test_seller_profit_matches_item_proceeds():
    from app.web import _compute_stats
    from app.services.pricing import _apply_profitability
    listing={'price_gbp':50,'buy_price_gbp':10}
    _apply_profitability(listing,50)
    assert listing['estimated_profit_gbp']==40
    assert _compute_stats([listing],[])['potential_profit_gbp']==40
