"""Exercise real Flask routes in isolation so hosted guards cannot alter local tests."""
import os
import subprocess
import sys


def test_hosted_access_storage_and_generation_guards():
    script = r'''
import base64, io, json, tempfile
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
    assert c.get('/api/provider-status').status_code == 401
    assert c.get('/',headers=auth).status_code == 200
    assert c.get('/listing/..',headers=auth).status_code == 400
    assert c.post('/create-listing',headers=auth,json={'folder':'/tmp'}).status_code == 400
    assert c.post('/create-listing',headers=auth,json={'folder':'item'}).status_code == 503
    assert c.post('/login/start',headers=auth).json['code'] == 'LOCAL_BROWSER_REQUIRED'
    assert c.post('/create-listing',headers={**auth,'Origin':'https://elsewhere.example'},json={'folder':'item'}).status_code == 403
    assert c.get('/missing',headers=auth).status_code == 404
    assert c.get('/',headers=auth).headers['Cache-Control'] == 'no-store'
    config.ANTHROPIC_API_KEY='test-private-key'
    config.VISION_PROVIDER=config.LISTING_PROVIDER='claude-haiku'
    status=c.get('/api/provider-status',headers=auth)
    assert status.json['vision']['ready'] is True
    assert status.json['vision']['key_variable'] == 'ANTHROPIC_API_KEY'
    assert 'test-private-key' not in status.get_data(as_text=True)
    config.VISION_PROVIDER='accidental-secret-value'
    status=c.get('/api/provider-status',headers=auth)
    assert status.json['vision']['issue'] == 'unsupported_provider'
    assert 'accidental-secret-value' not in status.get_data(as_text=True)
    failure=c.post('/upload',headers=auth)
    assert failure.json['code'] == 'UNSUPPORTED_PROVIDER'
    assert 'VISION_PROVIDER' in failure.json['error']
    config.VISION_PROVIDER='claude-haiku'
    item=items/'failure'; item.mkdir()
    with patch('app.web.pipeline_svc.run_pipeline', side_effect=RuntimeError('test-private-key')):
        failure=c.post('/create-listing',headers=auth,json={'folder':'failure'})
        assert failure.status_code == 500
        assert failure.json['code'] == 'OPERATION_FAILED'
        assert 'test-private-key' not in failure.get_data(as_text=True)
        assert 'Traceback' not in failure.get_data(as_text=True)
        from PIL import Image
        photo=io.BytesIO(); Image.new('RGB',(32,32),'white').save(photo,format='JPEG'); photo.seek(0)
        failure=c.post('/upload',headers=auth,data={'photos':(photo,'front.jpg')})
        assert failure.status_code == 500
        assert failure.json['code'] == 'OPERATION_FAILED'
        assert 'test-private-key' not in failure.get_data(as_text=True)
        assert 'Traceback' not in failure.get_data(as_text=True)
    with patch('app.web.pipeline_svc.run_pipeline', side_effect=ValueError('test-private-key')):
        failure=c.post('/create-listing',headers=auth,json={'folder':'failure'})
        assert failure.status_code == 422
        assert 'test-private-key' not in failure.get_data(as_text=True)
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


def test_copied_api_keys_trim_outer_whitespace():
    env = {**os.environ, 'ANTHROPIC_API_KEY': '  dummy-anthropic\n',
           'OPENAI_API_KEY': '\tdummy-openai\r\n', 'GOOGLE_AI_API_KEY': 'dummy-google\n'}
    script = '''from app import config
assert config.ANTHROPIC_API_KEY == "dummy-anthropic"
assert config.OPENAI_API_KEY == "dummy-openai"
assert config.GOOGLE_AI_API_KEY == "dummy-google"
'''
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hosted_six_character_password_and_rejection():
    script = r'''
import base64, os
from app.hosted import create_app
for password in ('', 'short'):
    os.environ['APP_PASSWORD'] = password
    try:
        create_app()
    except RuntimeError:
        pass
    else:
        raise AssertionError('Missing or undersized password accepted')
os.environ['APP_PASSWORD'] = 'sample'
c = create_app().test_client()
def auth(password):
    return {'Authorization': 'Basic '+base64.b64encode(('kristian:'+password).encode()).decode()}
assert c.get('/').status_code == 401
assert c.get('/', headers=auth('wrong!')).status_code == 401
assert c.get('/', headers=auth('sample')).status_code == 200
'''
    env = {**os.environ, 'APP_USERNAME': 'kristian'}
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
