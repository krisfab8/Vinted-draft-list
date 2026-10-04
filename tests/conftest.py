import pytest

@pytest.fixture(autouse=True)
def isolate_sales_history(tmp_path, monkeypatch):
    from app.services import sales_history
    monkeypatch.setattr(sales_history, 'DB_PATH', tmp_path / 'sales.db')

@pytest.fixture(autouse=True)
def isolate_usage_ledger(tmp_path, monkeypatch):
    from app.services import model_usage
    monkeypatch.setattr(model_usage, 'LEDGER_PATH', tmp_path / 'model_calls.jsonl')

@pytest.fixture(autouse=True)
def isolate_ebay_cache(tmp_path, monkeypatch):
    from app.services import ebay_comps
    monkeypatch.setattr(ebay_comps, '_cache_path', lambda: tmp_path / 'ebay_cache.json')
