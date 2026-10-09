"""Hardening from the code review: forged usage records, wiped limits, password guessing, giant photos."""
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest
from PIL import Image

from app import web
from app.services import accounts, account_data, item_backup, model_usage


def test_cost_maths_ignores_forged_or_damaged_numbers():
    good = {"model": "gpt-6-luna", "input_tokens": 1000, "output_tokens": 100}
    assert model_usage.cost_usd(good) > 0
    for bad in ({"input_tokens": -10**12}, {"input_tokens": "x"}, {"output_tokens": True},
                {"cache_read_input_tokens": -5}, {"web_search_requests": "lots"}):
        assert model_usage.cost_usd({**good, **bad}) is None


def _backup_with_events(events, tmp_path):
    """A real phone backup of one item, with extra usage events added."""
    items = tmp_path / "source"
    (items / "upload_0123abcd").mkdir(parents=True)
    (items / "upload_0123abcd" / "listing.json").write_text(json.dumps(dict(
        title="Nike Shirt M", description="Notes.", brand="Nike", item_type="shirt", gender="men's", colour="Blue",
        tagged_size="M", normalized_size="M", materials=["100% Cotton"], category="Men > Shirts", price_gbp=20)))
    Image.new("RGB", (20, 20), "white").save(items / "upload_0123abcd" / "front.jpg")
    data = item_backup.export(items, "upload_0123abcd")
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            body = src.read(info)
            if info.filename.endswith("model_calls.json"):
                body = json.dumps(events).encode()
            dst.writestr(info, body)
        if not any(i.filename.endswith("model_calls.json") for i in src.infolist()):
            pytest.skip("backup format has no usage file")
    return out.getvalue()


def test_restore_keeps_only_well_formed_usage_events(tmp_path, monkeypatch):
    from app.services import sales_history
    monkeypatch.setattr(model_usage, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(sales_history, "restore", lambda rows: 0)
    ok = {"id": "a" * 32, "timestamp": "2026-10-01T10:00:00+00:00", "model": "gpt-6-luna",
          "input_tokens": 10, "output_tokens": 2}
    forged = [{**ok, "id": "b" * 32, "input_tokens": -10**12}, {**ok, "id": "c" * 32, "input_tokens": "x"},
              {**ok, "id": "d" * 32, "timestamp": "not a date"}]
    item_backup.restore(_backup_with_events([ok] + forged, tmp_path), tmp_path / "items")
    assert [e["id"] for e in model_usage.read_events()] == ["a" * 32]


def test_delete_my_data_keeps_the_usage_record(tmp_path, monkeypatch):
    from app import run_logger
    from app.services import item_store, sales_history, user_profile
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"id": "x"}\n')
    for module, attr, name in ((model_usage, "LEDGER_PATH", "ledger.jsonl"), (user_profile, "_PATH", "p.json"),
                               (run_logger, "LOG_PATH", "r.jsonl"), (run_logger, "CORRECTIONS_PATH", "c.jsonl"),
                               (item_store, "DB_PATH", "i.db"), (sales_history, "DB_PATH", "s.db"),
                               (web, "COST_LOG", "cost.csv")):
        monkeypatch.setattr(module, attr, tmp_path / name)
    monkeypatch.setattr("app.services.removed_items.PATH", tmp_path / "removed.json")
    (tmp_path / "items").mkdir()
    account_data.wipe(tmp_path / "items")
    assert ledger.exists()


def test_giant_photos_are_refused_before_decoding(tmp_path, monkeypatch):
    from app.services import photo_prepare
    monkeypatch.setattr(photo_prepare, "MAX_PIXELS", 100)
    photo = tmp_path / "big.png"
    Image.new("RGB", (20, 20), "white").save(photo)
    with pytest.raises(web.PhotoTooLarge):
        web._resize_photo(photo)


def test_per_account_files_include_aliases_and_fill_reports():
    scoped = {(m, a) for m, a, _ in accounts.SCOPED}
    assert ("app.services.alias_memory", "_ALIAS_FILE") in scoped and ("app.web", "FILL_REPORTS") in scoped


def test_hosted_password_guessing_is_limited_and_session_key_is_random():
    script = r'''
import base64, hashlib, hmac, tempfile
from pathlib import Path
from app import config, web
from app.services import accounts
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp); (root/'items').mkdir()
    config.ITEMS_DIR = web.ITEMS_DIR = root/'items'
    accounts.ACCOUNTS_DIR = root/'accounts'
    from app.hosted import create_app
    app = create_app()
    password = '012345678901234567890123456789'
    assert app.secret_key != hmac.new(password.encode(), b"vinted-session", hashlib.sha256).hexdigest()
    assert len(app.secret_key) == 64 and app.secret_key == accounts.session_secret()
    hooks = app.before_request_funcs[None]
    assert hooks[0].__name__ == 'protect_test_app', [h.__name__ for h in hooks]   # sign-in before item locks
    c = app.test_client()
    bad = {'Authorization': 'Basic ' + base64.b64encode(b'kristian:wrong').decode()}
    good = {'Authorization': 'Basic ' + base64.b64encode(('kristian:' + password).encode()).decode()}
    assert c.get('/api/listings', headers=good).status_code == 200
    for _ in range(8):
        assert c.get('/api/listings', headers=bad).status_code == 401
    assert c.get('/api/listings', headers=good).status_code == 401       # this address is paused for a while
    assert c.post('/signin', data={'username': 'kristian', 'password': password}).status_code == 401
    other = {**good, 'X-Forwarded-For': '203.0.113.9'}
    assert c.get('/api/listings', headers=other).status_code == 200      # other addresses still fine
    print('ok')
'''
    env = {**os.environ, "APP_PASSWORD": "012345678901234567890123456789", "SESSION_COOKIE_SECURE": "0"}
    env.pop("SECRET_KEY", None)
    for name in ("B2_KEY_ID", "B2_APP_KEY", "B2_BUCKET", "B2_ENDPOINT"):
        env.pop(name, None)
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=120)
    assert result.returncode == 0 and "ok" in result.stdout, (result.stdout[-1500:], result.stderr[-3000:])
