"""Memory-light backups, duplicate tidy-up / removal tombstones, sign-in and delete-my-data."""
import json
import os
import subprocess
import sys
import zipfile

import pytest

from app import web
from app.services import account_data, item_backup, item_store, removed_items, sales_history, user_profile


@pytest.fixture
def items(tmp_path, monkeypatch):
    root = tmp_path / "items"; root.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", root)
    monkeypatch.setattr(removed_items, "PATH", tmp_path / "removed.json")
    monkeypatch.setattr(item_store, "DB_PATH", tmp_path / "items.db")
    monkeypatch.setattr(sales_history, "DB_PATH", tmp_path / "sales.db")
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    item_store.init_db()
    return root


def make(root, folder, **listing):
    path = root / folder; path.mkdir()
    base = dict(brand="Barbour", item_type="jacket", title="Barbour jacket", description="Wax.",
                tagged_size="L", normalized_size="L", price_gbp=40)
    (path / "listing.json").write_text(json.dumps({**base, **listing}))
    (path / "front.jpg").write_bytes(b"\xff\xd8 photo")
    return path


def test_backup_zip_streams_and_stores_photos_uncompressed(items):
    make(items, "upload_aaaaaaaa")
    with item_backup.export_file(items, "upload_aaaaaaaa") as spool:
        names = {i.filename: i.compress_type for i in zipfile.ZipFile(spool).infolist()}
    assert names["items/upload_aaaaaaaa/front.jpg"] == zipfile.ZIP_STORED
    assert names["items/upload_aaaaaaaa/listing.json"] == zipfile.ZIP_DEFLATED
    assert item_backup.folders_in(item_backup.export(items, "upload_aaaaaaaa")) == {"upload_aaaaaaaa"}


def test_listings_carry_a_backup_revision_that_changes_with_files(items):
    path = make(items, "upload_aaaaaaaa")
    client = web.app.test_client()
    first = client.get("/api/listings").json[0]["backup_revision"]
    assert first and client.get("/api/listings").json[0]["backup_revision"] == first
    (path / "back.jpg").write_bytes(b"new photo")
    assert client.get("/api/listings").json[0]["backup_revision"] != first


def test_deleted_listing_cannot_be_restored_from_a_phone_backup(items):
    make(items, "upload_aaaaaaaa")
    backup = item_backup.export(items, "upload_aaaaaaaa")
    client = web.app.test_client()
    web.app.config["HOSTED_TEST"] = True
    try:
        assert client.delete("/listing/upload_aaaaaaaa").status_code == 200
        assert removed_items.contains("upload_aaaaaaaa")
        response = client.post("/api/private/restore-backup", data=backup, content_type="application/zip")
        assert response.status_code == 410 and not (items / "upload_aaaaaaaa").exists()
    finally:
        web.app.config.pop("HOSTED_TEST", None)


def retest(root, source, token, **listing):
    path = make(root, "upload_retest_" + token, **listing)
    (path / "reanalysis.json").write_text(json.dumps({"source": source}))
    return path


def test_old_retest_copies_merge_into_one_listing(items):
    # Untouched original: the fresh read replaces it, keeping the original folder.
    make(items, "upload_aaaaaaaa", title="Old AI title")
    retest(items, "upload_aaaaaaaa", "a" * 32, title="Fresh AI title")
    # Seller already edited the original: the original stays, the copy goes.
    make(items, "upload_bbbbbbbb", title="Seller title", manual_fields=["title"])
    retest(items, "upload_bbbbbbbb", "b" * 32, title="Fresh AI title")
    # Original deleted: the copy is the only listing, so it stays.
    retest(items, "upload_cccccccc", "c" * 32)
    result = removed_items.merge_retests(items)
    assert result["merged"] == ["upload_aaaaaaaa"]
    assert json.loads((items / "upload_aaaaaaaa" / "listing.json").read_text())["title"] == "Fresh AI title"
    assert json.loads((items / "upload_bbbbbbbb" / "listing.json").read_text())["title"] == "Seller title"
    assert sorted(p.name for p in items.iterdir()) == ["upload_aaaaaaaa", "upload_bbbbbbbb", "upload_retest_" + "c" * 32]
    assert removed_items.contains("upload_retest_" + "a" * 32) and removed_items.contains("upload_retest_" + "b" * 32)


def test_delete_my_data_needs_the_word_and_removes_everything(items, tmp_path, monkeypatch):
    from app import run_logger
    from app.services import model_usage
    for module, name in ((run_logger, "LOG_PATH"), (run_logger, "CORRECTIONS_PATH"),
                         (model_usage, "LEDGER_PATH"), (web, "COST_LOG")):
        monkeypatch.setattr(module, name, tmp_path / (name.lower() + ".log"))
    make(items, "upload_aaaaaaaa")
    user_profile.save(dict(user_profile.load(), name="Kris"))
    client = web.app.test_client()
    assert client.post("/api/account/delete-data", json={"confirm": "yes"}).status_code == 422
    assert (items / "upload_aaaaaaaa").exists()
    response = client.post("/api/account/delete-data", json={"confirm": "delete"})
    assert response.status_code == 200 and response.json["listings"] == 1
    assert list(items.iterdir()) == [] and not user_profile._PATH.exists()
    assert removed_items.contains("upload_aaaaaaaa")


def test_privacy_page_is_plain_and_reachable():
    page = web.app.test_client().get("/privacy").get_data(as_text=True)
    assert "Delete my data" in page and "Backblaze" in page


def test_sign_in_page_session_and_sign_out():
    script = r'''
import os, tempfile
from pathlib import Path
from app import config, web
with tempfile.TemporaryDirectory() as tmp:
    items = Path(tmp) / "items"; items.mkdir()
    config.ITEMS_DIR = web.ITEMS_DIR = items
    from app.hosted import create_app
    c = create_app().test_client()
    html = {"Accept": "text/html"}
    r = c.get("/drafts", headers=html)
    assert r.status_code == 302 and r.headers["Location"].startswith("/signin?next=/drafts")
    assert c.get("/api/listings").status_code == 401                  # app requests: plain 401
    assert "WWW-Authenticate" not in c.get("/api/listings").headers   # no browser pop-up
    assert c.get("/signin").status_code == 200 and c.get("/privacy").status_code == 200
    bad = c.post("/signin", data={"username": "kristian", "password": "nope"})
    assert bad.status_code == 401 and "isn" in bad.get_data(as_text=True)
    ok = c.post("/signin?next=/drafts", data={"username": "kristian", "password": "sample-password"})
    assert ok.status_code == 302 and ok.headers["Location"] == "/drafts"
    assert c.get("/", headers=html).status_code == 200
    evil = c.post("/signin?next=//evil.example", data={"username": "kristian", "password": "sample-password"})
    assert evil.headers["Location"] == "/"
    c.post("/signout")
    assert c.get("/api/listings").status_code == 401
'''
    env = {**os.environ, "APP_USERNAME": "kristian", "APP_PASSWORD": "sample-password", "SESSION_COOKIE_SECURE": "0"}
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
