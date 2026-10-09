"""Seller accounts: invite-only sign-up, and each person's listings, sales, profile and cloud copies kept apart."""
import os
import subprocess
import sys

import pytest

from app.services import accounts

PASSWORD = "012345678901234567890123456789"


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "ACCOUNTS_DIR", tmp_path / "accounts")
    monkeypatch.setattr(accounts, "_cloud", None)
    return tmp_path


def test_invites_work_once_and_expire(registry):
    code = accounts.create_invite()
    assert accounts.invite_ok(code)
    seller = accounts.sign_up(code, "Anna", "Anna@Example.com", "longenough", owner_username="kristian")
    assert seller["email"] == "anna@example.com" and "longenough" not in str(seller)
    assert not accounts.invite_ok(code)
    with pytest.raises(ValueError, match="expired or been used"):
        accounts.sign_up(code, "Bob", "bob@example.com", "longenough")
    old = accounts.create_invite(now=1)          # made long ago: 7 days are up
    assert not accounts.invite_ok(old)
    assert accounts.check("anna@example.com", "longenough")["id"] == seller["id"]
    assert accounts.check("anna@example.com", "wrong-password") is None


@pytest.mark.parametrize("name,email,password,message", [
    ("", "a@example.com", "longenough", "name"),
    ("Anna", "not-an-email", "longenough", "email"),
    ("Anna", "a@example.com", "short", "8 characters"),
    ("Anna", "kristian", "longenough", "email"),
])
def test_sign_up_checks_the_form(registry, name, email, password, message):
    with pytest.raises(ValueError, match=message):
        accounts.sign_up(accounts.create_invite(), name, email, password, owner_username="kristian")


def test_one_account_per_email(registry):
    accounts.sign_up(accounts.create_invite(), "Anna", "a@example.com", "longenough")
    with pytest.raises(ValueError, match="already an account"):
        accounts.sign_up(accounts.create_invite(), "Anna 2", "A@example.com", "longenough")


def test_scoped_paths_follow_the_active_account(registry):
    owner = registry / "somewhere" / "items"
    path = accounts.ScopedPath(owner, "items")
    assert path.path() == owner and str(path / "x") == str(owner / "x")
    with accounts.scope("a0123456789"):
        assert path.path() == accounts.ACCOUNTS_DIR / "a0123456789" / "items"
        assert path.resolve() == (accounts.ACCOUNTS_DIR / "a0123456789" / "items").resolve()
    assert path.path() == owner
    with pytest.raises(ValueError):
        accounts.root_for("../owner")


def test_hosted_sellers_never_see_each_others_data():
    """End to end on the hosted app (owner + invited seller), including separate cloud copies."""
    script = r'''
import base64, json, re, tempfile
from pathlib import Path
import boto3, moto
from PIL import Image
from app import config, extractor, run_logger, web
from app.services import accounts, item_store, model_usage, removed_items, sales_history, user_profile

def make_item(items, folder, title):
    (items/folder).mkdir(parents=True)
    (items/folder/'listing.json').write_text(json.dumps(dict(title=title, description='Notes.', brand='Barbour',
        item_type='jacket', gender="men's", colour='Green', tagged_size='M', normalized_size='M',
        materials=['100% Cotton'], category='Men > Jackets', price_gbp=60)))
    Image.new('RGB',(40,50),'white').save(items/folder/'front.jpg')

with tempfile.TemporaryDirectory() as tmp, moto.mock_aws():
    root=Path(tmp); items=root/'items'; items.mkdir(); data=root/'data'; data.mkdir()
    config.ITEMS_DIR=web.ITEMS_DIR=extractor.ITEMS_DIR=items
    web.COST_LOG=root/'cost_log.csv'
    item_store._DATA_DIR=data; item_store.DB_PATH=data/'items.db'
    sales_history.DB_PATH=data/'sales.db'; user_profile._PATH=data/'user_profile.json'
    removed_items.PATH=data/'removed_items.json'; model_usage.LEDGER_PATH=data/'model_calls.jsonl'
    run_logger._DATA_DIR=data; run_logger.LOG_PATH=data/'run_logs.jsonl'; run_logger.CORRECTIONS_PATH=data/'corrections.jsonl'
    accounts.ACCOUNTS_DIR=root/'accounts'
    s3=boto3.client('s3',region_name='us-east-1'); s3.create_bucket(Bucket='drafts')
    make_item(items, 'upload_00000001', 'Owner Barbour Jacket')

    from app.hosted import create_app
    app=create_app()
    owner=app.test_client(); seller=app.test_client(); stranger=app.test_client()
    auth={'Authorization':'Basic '+base64.b64encode(b'kristian:''' + PASSWORD + r'''').decode()}

    # Owner makes a one-time invite; the seller signs up with it.
    link=owner.post('/api/accounts/invite',headers=auth).json['link']
    code=link.split('invite=')[1]
    assert stranger.get('/signup?invite=nope').status_code == 404
    assert stranger.post('/signup?invite='+code,headers={'Origin':'https://evil.example'},
                         data={'name':'X','email':'x@example.com','password':'xxxxxxxxxx'}).status_code == 403
    page=seller.get('/signup?invite='+code); assert page.status_code == 200 and b'Create my account' in page.data
    bad=seller.post('/signup?invite='+code,data={'name':'Anna','email':'anna@example.com','password':'short'})
    assert bad.status_code == 400 and b'8 characters' in bad.data
    r=seller.post('/signup?invite='+code,data={'name':'Anna','email':'anna@example.com','password':'anna-password'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/welcome'), r.status_code
    assert stranger.post('/signup?invite='+code,data={'name':'X','email':'x@example.com','password':'xxxxxxxxxx'}).status_code == 404
    seller_id=accounts.check('anna@example.com','anna-password')['id']
    seller_items=accounts.root_for(seller_id)/'items'

    # Separate listings.
    make_item(seller_items, 'upload_00000002', 'Seller Levi Jeans')
    seen_owner=[i['folder'] for i in owner.get('/api/listings',headers=auth).json]
    seen_seller=[i['folder'] for i in seller.get('/api/listings').json]
    assert seen_owner == ['upload_00000001'] and seen_seller == ['upload_00000002'], (seen_owner, seen_seller)
    assert seller.get('/listing/upload_00000001').status_code == 404
    assert b'Owner Barbour' not in seller.get('/drafts').data

    # Separate profiles; only the owner can invite.
    assert seller.post('/api/profile/identity',json={'name':'Anna','email':'anna@example.com'}).status_code == 200
    assert not user_profile._PATH.path().exists() or 'Anna' not in user_profile._PATH.path().read_text()
    assert seller.post('/api/accounts/invite').status_code == 403
    assert seller.get('/api/accounts').status_code == 403
    assert [s['email'] for s in owner.get('/api/accounts',headers=auth).json['sellers']] == ['anna@example.com']
    assert b'Invite a seller' in owner.get('/settings',headers=auth).data
    settings=seller.get('/settings').data
    assert b'Invite a seller' not in settings and b'anna@example.com' in settings
    # Each account keeps its own device backup on the phone (shared phones never mix items).
    assert ('data-account="'+seller_id+'"').encode() in settings
    assert b'data-account=' not in owner.get('/settings',headers=auth).data

    # Sign in with email + password; a wrong password gets nothing.
    assert stranger.post('/signin',data={'username':'anna@example.com','password':'nope'}).status_code == 401
    assert stranger.post('/signin',data={'username':'Anna@Example.com','password':'anna-password'}).status_code == 302
    assert [i['folder'] for i in stranger.get('/api/listings').json] == ['upload_00000002']

    # Cloud copies: the seller's live under their own prefix, the owner's stay where they were.
    for store in (app.extensions['cloud_store'], app.extensions['current_cloud']()):
        store.sync()
    with accounts.scope(seller_id):
        app.extensions['current_cloud']().sync()
    keys=sorted(o['Key'] for o in s3.list_objects_v2(Bucket='drafts').get('Contents',[]))
    assert 'items/upload_00000001.zip' in keys and 'items/upload_00000002.zip' not in keys, keys
    assert f'users/{seller_id}/items/upload_00000002.zip' in keys, keys
    assert 'accounts/registry.json' in keys

    # Delete my data (seller) removes only the seller's items.
    assert seller.post('/api/account/delete-data',json={'confirm':'DELETE'}).status_code == 200
    assert not (seller_items/'upload_00000002').exists() and (items/'upload_00000001').exists()
    print('ok')
'''
    env = {**os.environ, "APP_PASSWORD": PASSWORD, "SESSION_COOKIE_SECURE": "0",
           "B2_KEY_ID": "testing", "B2_APP_KEY": "testing", "B2_BUCKET": "drafts",
           "B2_ENDPOINT": "s3.us-east-1.amazonaws.com", "AWS_DEFAULT_REGION": "us-east-1"}
    pytest.importorskip("moto")
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=180)
    assert result.returncode == 0 and "ok" in result.stdout, (result.stdout[-2000:], result.stderr[-4000:])
