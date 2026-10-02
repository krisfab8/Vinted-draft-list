"""Exercise real Flask routes in isolation so hosted guards cannot alter local tests."""
import os
import subprocess
import sys


def test_hosted_access_storage_and_generation_guards():
    script = r'''
import base64, json, tempfile
from pathlib import Path
from unittest.mock import patch
from app import config, web
from app.hosted import create_app
from scripts.hosted_start import prepare_storage
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); items=root/'items'; items.mkdir()
    config.ITEMS_DIR=items; web.ITEMS_DIR=items
    config.OPENAI_API_KEY=''; config.ANTHROPIC_API_KEY=''
    c=create_app().test_client()
    auth={'Authorization':'Basic '+base64.b64encode(b'kristian:012345678901234567890123456789').decode()}
    assert c.get('/health').status_code == 200
    assert c.get('/').status_code == 401
    assert c.get('/',headers=auth).status_code == 200
    assert c.get('/listing/..',headers=auth).status_code == 400
    assert c.post('/create-listing',headers=auth,json={'folder':'/tmp'}).status_code == 400
    assert c.post('/create-listing',headers=auth,json={'folder':'item'}).status_code == 503
    assert c.post('/login/start',headers=auth).json['code'] == 'LOCAL_BROWSER_REQUIRED'
    assert c.post('/create-listing',headers={**auth,'Origin':'https://elsewhere.example'},json={'folder':'item'}).status_code == 403
    assert c.get('/missing',headers=auth).status_code == 404
    assert c.get('/',headers=auth).headers['Cache-Control'] == 'no-store'
    storage=root/'persist'; prepare_storage(root,storage)
    assert (root/'items').is_symlink()
    (root/'items'/'saved.txt').write_text('survives')
    prepare_storage(root,storage)
    assert (storage/'items'/'saved.txt').read_text() == 'survives'
    (root/'cost_log.csv').write_text('cost')
    assert (storage/'cost_log.csv').read_text() == 'cost'
'''
    env = {**os.environ, "APP_PASSWORD": "012345678901234567890123456789", "APP_USERNAME": "kristian"}
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
