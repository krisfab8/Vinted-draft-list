"""Credential-free per-call ledger; records responses before JSON parsing."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import json
import threading
import time
import uuid
from datetime import datetime, timezone

from app.config import ROOT

LEDGER_PATH = ROOT / 'data' / 'model_calls.jsonl'
RATES = {'claude-haiku-4-5-20251001': (1, 5), 'claude-sonnet-4-6': (3, 15),
         'gpt-6-luna': (.1, .5), 'gpt-6.1-sol': (2, 10)}
USD_TO_GBP = .79
_context = ContextVar('model_usage', default=None)
_lock = threading.Lock()

@contextmanager
def run(folder):
    token = _context.set({'run_id': uuid.uuid4().hex, 'item': Path(folder).name, 'calls': []})
    try:
        yield _context.get()
    finally:
        _context.reset(token)


def cost_usd(event):
    rate = RATES.get(event.get('model'))
    if rate is None or event.get('input_tokens') is None or event.get('output_tokens') is None:
        return None
    # Cache writes and hits have separate rates on Anthropic.
    return (event['input_tokens'] * rate[0] + event['output_tokens'] * rate[1]
            + event.get('cache_creation_input_tokens', 0) * rate[0] * 1.25
            + event.get('cache_read_input_tokens', 0) * rate[0] * .1) / 1_000_000


def record(model, stage, *, usage=None, stop_reason=None, error=None, latency_ms=0):
    def integer(name):
        value = getattr(usage, name, None)
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    ctx = _context.get()
    event = {'id': uuid.uuid4().hex, 'run_id': ctx['run_id'] if ctx else None,
             'item': ctx['item'] if ctx else None,
             'timestamp': datetime.now(timezone.utc).isoformat(), 'stage': stage,
             'model': model, 'input_tokens': integer('input_tokens'),
             'output_tokens': integer('output_tokens'),
             'cache_creation_input_tokens': integer('cache_creation_input_tokens') or 0,
             'cache_read_input_tokens': integer('cache_read_input_tokens') or 0,
             'stop_reason': stop_reason if isinstance(stop_reason, str) else None,
             'error_type': type(error).__name__ if error else None,
             'latency_ms': latency_ms, 'rate_version': '2026-10-02', 'usd_to_gbp': USD_TO_GBP}
    cost = cost_usd(event)
    event.update(cost_usd=cost, cost_gbp=cost * USD_TO_GBP if cost is not None else None,
                 billing_status='estimated' if cost is not None else 'unknown')
    # No response text, prompts, request headers or exception messages belong here.
    with _lock:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open('a') as f:
            f.write(json.dumps(event) + '\n')
        if ctx is not None:
            ctx['calls'].append(event)
    return event


def call(create, *, stage, **kwargs):
    started = time.perf_counter()
    try:
        response = create(**kwargs)
    except Exception as exc:
        record(kwargs['model'], stage, error=exc, latency_ms=round((time.perf_counter()-started)*1000))
        raise
    record(kwargs['model'], stage, usage=response.usage, stop_reason=response.stop_reason,
           latency_ms=round((time.perf_counter()-started)*1000))
    return response


def tracked(stage):
    """Aggregate each extraction/writer's real calls, including parallel rereads."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if _context.get() is None:
                folder = args[0] if stage == 'extract' else 'standalone'
                with run(folder):
                    return wrapped(*args, **kwargs)
            ctx = _context.get()
            before = len(ctx['calls'])
            result, usage = fn(*args, **kwargs)
            calls = ctx['calls'][before:]
            if calls:
                usage['calls'] = calls
                usage['input_tokens'] = sum(c['input_tokens'] or 0 for c in calls)
                usage['output_tokens'] = sum(c['output_tokens'] or 0 for c in calls)
                usage['cost_complete'] = all(c['cost_usd'] is not None for c in calls)
            return result, usage
        return wrapped
    return decorate


def pipeline(fn):
    @wraps(fn)
    def wrapped(item_path, *args, **kwargs):
        with run(item_path):
            return fn(item_path, *args, **kwargs)
    return wrapped
