"""Backblaze B2 draft persistence, exercised against an in-memory S3 (moto)."""
import json

import pytest
from PIL import Image

from app.services import cloud_store, item_backup, model_usage, sales_history

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

BUCKET = "drafts-test"
FOLDER = "upload_0123abcd"


@pytest.fixture
def s3(monkeypatch, tmp_path):
    monkeypatch.setattr(model_usage, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(sales_history, "read_all", lambda: [])
    monkeypatch.setattr(sales_history, "get", lambda folder: None)
    monkeypatch.setattr(sales_history, "restore", lambda rows: 0)
    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def make_item(items, folder=FOLDER, title="Peter Millar Polo Shirt S"):
    item = items / folder
    item.mkdir(parents=True)
    listing = dict(title=title, description="Seller notes.", brand="Peter Millar",
                   item_type="polo shirt", gender="men's", colour="Blue", tagged_size="S",
                   normalized_size="S", materials=["100% Cotton"],
                   category="Men > Polo Shirts", price_gbp=25)
    (item / "listing.json").write_text(json.dumps(listing))
    Image.new("RGB", (40, 50), "white").save(item / "front.jpg")
    return item


def store_for(client, items, **kwargs):
    return cloud_store.CloudStore(client, BUCKET, items, **kwargs)


def test_drafts_survive_a_wiped_server(s3, tmp_path):
    first = tmp_path / "before" / "items"
    make_item(first)
    store_for(s3, first).sync()

    # Restart: a brand-new empty disk.
    second = tmp_path / "after" / "items"
    seen = []
    store = store_for(s3, second, on_restored=seen.append)
    assert store.restore_all() == [FOLDER]
    assert seen == [FOLDER]
    assert json.loads((second / FOLDER / "listing.json").read_text())["title"] == "Peter Millar Polo Shirt S"
    # Wake-up restores only the summary and a preview; photos come down on first open.
    assert (second / FOLDER / "_thumb.jpg").is_file() and not (second / FOLDER / "front.jpg").exists()
    assert item_backup.revision(second / FOLDER) == item_backup.revision(first / FOLDER)
    with pytest.raises(ValueError):
        item_backup.export(second, FOLDER)          # never an incomplete backup
    store.sync()
    assert store.status["uploaded"] == 0            # a summary-only copy is never uploaded
    assert store.hydrate(FOLDER)
    assert (second / FOLDER / "front.jpg").read_bytes() == (first / FOLDER / "front.jpg").read_bytes()
    assert not item_backup.is_stub(second / FOLDER)
    assert item_backup.revision(second / FOLDER) == item_backup.revision(first / FOLDER)

    # Nothing changed, so the restored item is not uploaded again.
    store.sync()
    assert store.status["uploaded"] == 0


def test_edits_are_uploaded_and_restore_never_overwrites_local(s3, tmp_path):
    items = tmp_path / "items"
    item = make_item(items)
    store = store_for(s3, items)
    store.sync()
    listing = json.loads((item / "listing.json").read_text())
    listing["price_gbp"] = 40
    (item / "listing.json").write_text(json.dumps(listing))
    store.sync()
    assert store.status["uploaded"] == 2

    # The local copy wins over the stored one on startup.
    listing["price_gbp"] = 55
    (item / "listing.json").write_text(json.dumps(listing))
    assert store_for(s3, items).restore_all() == []
    assert json.loads((item / "listing.json").read_text())["price_gbp"] == 55

    restored = tmp_path / "fresh"
    store_for(s3, restored).restore_all()
    assert json.loads((restored / FOLDER / "listing.json").read_text())["price_gbp"] == 40


def test_delete_only_removes_items_seen_locally(s3, tmp_path):
    items = tmp_path / "items"
    make_item(items)
    store_for(s3, items).sync()

    # An empty server must never wipe the bucket.
    empty = store_for(s3, tmp_path / "empty")
    empty.sync()
    assert s3.list_objects_v2(Bucket=BUCKET, Prefix="items/")["KeyCount"] == 1

    # Deleting an item the server holds removes the stored copy.
    store = store_for(s3, items)
    store.sync()
    for f in (items / FOLDER).iterdir():
        f.unlink()
    (items / FOLDER).rmdir()
    store.sync()
    assert s3.list_objects_v2(Bucket=BUCKET)["KeyCount"] == 0


def test_bad_stored_item_is_skipped_not_fatal(s3, tmp_path):
    s3.put_object(Bucket=BUCKET, Key="items/upload_deadbeef.zip", Body=b"not a zip")
    s3.put_object(Bucket=BUCKET, Key="items/../escape.zip", Body=b"x")
    source = tmp_path / "source"
    make_item(source)
    store_for(s3, source).sync()
    store = store_for(s3, tmp_path / "items")
    assert store.restore_all() == [FOLDER]
    assert "upload_deadbeef" in store.status["last_error"]


def test_unreachable_bucket_keeps_app_running(tmp_path):
    class Down:
        def __getattr__(self, name):
            def fail(**kwargs):
                raise ConnectionError("no route")
            return fail
    items = tmp_path / "items"
    make_item(items)
    store = store_for(Down(), items)
    assert store.restore_all() == []
    store.sync()
    assert store.status["uploaded"] == 0 and "ConnectionError" in store.status["last_error"]


def test_not_configured_or_partly_configured_is_disabled(monkeypatch, tmp_path):
    for name in cloud_store.REQUIRED:
        monkeypatch.delenv(name, raising=False)
    assert cloud_store.from_environment(tmp_path) is None
    monkeypatch.setenv("B2_BUCKET", "x")
    assert cloud_store.missing_settings() == ["B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT"]
    assert cloud_store.from_environment(tmp_path) is None


def test_endpoint_region_is_derived(monkeypatch):
    monkeypatch.setenv("B2_KEY_ID", "id")
    monkeypatch.setenv("B2_APP_KEY", "secret")
    monkeypatch.setenv("B2_ENDPOINT", "s3.eu-central-003.backblazeb2.com/")
    client = cloud_store.make_client()
    assert client.meta.region_name == "eu-central-003"
    assert client.meta.endpoint_url == "https://s3.eu-central-003.backblazeb2.com"


def test_export_format_matches_phone_backup(s3, tmp_path):
    items = tmp_path / "items"
    make_item(items)
    store_for(s3, items).sync()
    body = s3.get_object(Bucket=BUCKET, Key=f"items/{FOLDER}.zip")["Body"].read()
    assert item_backup.restore(body, tmp_path / "phone") == [FOLDER]


def test_hosted_app_restores_drafts_on_startup():
    """A fresh hosted server shows drafts stored in the bucket before the first request."""
    import os
    import subprocess
    import sys
    script = r'''
import base64, io, json, tempfile
from pathlib import Path
import boto3, moto
from PIL import Image
from app import config, web
from app.services import item_backup, model_usage, sales_history
with tempfile.TemporaryDirectory() as tmp, moto.mock_aws():
    root=Path(tmp); items=root/'items'; items.mkdir(); source=root/'source'
    config.ITEMS_DIR=items; web.ITEMS_DIR=items
    model_usage.LEDGER_PATH=root/'ledger.jsonl'; sales_history.DB_PATH=root/'sales.db'
    folder='upload_0123abcd'; (source/folder).mkdir(parents=True)
    listing=dict(title='Peter Millar Polo Shirt S',description='Seller notes.',brand='Peter Millar',
        item_type='polo shirt',gender="men's",colour='Blue',tagged_size='S',normalized_size='S',
        materials=['100% Cotton'],category='Men > Polo Shirts',price_gbp=25)
    (source/folder/'listing.json').write_text(json.dumps(listing))
    Image.new('RGB',(40,50),'white').save(source/folder/'front.jpg')
    s3=boto3.client('s3',region_name='us-east-1'); s3.create_bucket(Bucket='drafts')
    s3.put_object(Bucket='drafts',Key='items/'+folder+'.zip',Body=item_backup.export(source,folder))
    from app.hosted import create_app
    c=create_app().test_client()
    auth={'Authorization':'Basic '+base64.b64encode(b'kristian:012345678901234567890123456789').decode()}
    assert (items/folder/'listing.json').is_file()
    assert folder in [i['folder'] for i in c.get('/api/listings',headers=auth).json]
    status=c.get('/api/provider-status',headers=auth).json['cloud_storage']
    assert status['enabled'] and status['restored']==1 and status['last_error'] is None, status
    print('ok')
'''
    env = {**os.environ, "APP_PASSWORD": "012345678901234567890123456789",
           "B2_KEY_ID": "testing", "B2_APP_KEY": "testing", "B2_BUCKET": "drafts",
           "B2_ENDPOINT": "s3.us-east-1.amazonaws.com", "AWS_DEFAULT_REGION": "us-east-1"}
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=120)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr[-3000:]


def test_onboarding_profile_survives_a_wiped_server(s3, tmp_path):
    first = tmp_path / "before"
    (first / "items").mkdir(parents=True)
    profile = first / "user_profile.json"
    profile.write_text(json.dumps({"name": "Kris", "email": "k@example.com"}))
    store_for(s3, first / "items", profile_path=profile).sync()

    second = tmp_path / "after"
    restored = second / "data" / "user_profile.json"
    store = store_for(s3, second / "items", profile_path=restored)
    store.restore_all()
    assert json.loads(restored.read_text())["name"] == "Kris"
    assert store.status["last_error"] is None

    # A profile already saved on this server is never overwritten by the stored copy.
    restored.write_text(json.dumps({"name": "Newer"}))
    store_for(s3, second / "items", profile_path=restored).restore_all()
    assert json.loads(restored.read_text())["name"] == "Newer"


def test_no_stored_profile_is_not_an_error(s3, tmp_path):
    store = store_for(s3, tmp_path / "items", profile_path=tmp_path / "user_profile.json")
    store.restore_all()
    assert store.status["last_error"] is None and not (tmp_path / "user_profile.json").exists()


def test_older_items_get_a_summary_and_failed_fetch_keeps_the_stub(s3, tmp_path):
    # A bucket written before summaries existed: full restore, then a summary is added once.
    old = tmp_path / "old" / "items"
    make_item(old)
    s3.put_object(Bucket=BUCKET, Key=f"items/{FOLDER}.zip", Body=item_backup.export(old, FOLDER))
    fresh = tmp_path / "fresh" / "items"
    store = store_for(s3, fresh)
    assert store.restore_all() == [FOLDER] and (fresh / FOLDER / "front.jpg").is_file()
    store.sync()
    assert s3.list_objects_v2(Bucket=BUCKET, Prefix="meta/")["KeyCount"] == 1
    # Next wake uses the summary; if the photo download then fails, the stub stays a stub.
    third = tmp_path / "third" / "items"
    store = store_for(s3, third)
    store.restore_all()
    s3.delete_object(Bucket=BUCKET, Key=f"items/{FOLDER}.zip")
    assert store.hydrate(FOLDER) is False and item_backup.is_stub(third / FOLDER)


def test_usage_record_survives_a_wiped_server(s3, tmp_path):
    """The monthly limits are counted from the usage record, so a restart must not reset them."""
    ledger = tmp_path / "server1" / "model_calls.jsonl"
    ledger.parent.mkdir()
    ledger.write_text('{"id": "e1", "item": "upload_0123abcd"}\n{"id": "e2"}\n')
    first = store_for(s3, tmp_path / "items1", ledger_path=ledger, prefix="users/a0123456789/")
    first.sync()
    assert s3.get_object(Bucket=BUCKET, Key="users/a0123456789/profile/model_calls.jsonl")["Body"].read()
    fresh = tmp_path / "server2" / "model_calls.jsonl"
    fresh.parent.mkdir()
    fresh.write_text('{"id": "e3"}\n{"id": "e1", "item": "upload_0123abcd"}\n')   # written before the restore ran
    store_for(s3, tmp_path / "items2", ledger_path=fresh, prefix="users/a0123456789/").restore_all()
    ids = [json.loads(line)["id"] for line in fresh.read_text().splitlines()]
    assert sorted(ids) == ["e1", "e2", "e3"]
