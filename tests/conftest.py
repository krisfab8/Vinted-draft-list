import pytest

@pytest.fixture(autouse=True)
def isolate_usage_ledger(tmp_path, monkeypatch):
    from app.services import model_usage
    monkeypatch.setattr(model_usage, 'LEDGER_PATH', tmp_path / 'model_calls.jsonl')
