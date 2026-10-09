"""Bandwidth: cached static files, revalidated photos, gzip pages and small card thumbnails."""
import gzip
import json

from PIL import Image

from app import web
from app.services import item_store, sales_history, user_profile


def test_cache_policy():
    assert web.cache_policy("/static/studio.css", True) == "public, max-age=31536000, immutable"
    assert web.cache_policy("/static/icon-192.png", False) == "public, max-age=86400"
    assert web.cache_policy("/items/upload_1/front.jpg", False) == "private, no-cache"
    assert web.cache_policy("/drafts", False) is None


def test_drafts_use_small_thumbnails_and_pages_are_gzipped(tmp_path, monkeypatch):
    items = tmp_path / "items"; items.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", items)
    monkeypatch.setattr(item_store, "DB_PATH", tmp_path / "items.db")
    monkeypatch.setattr(sales_history, "DB_PATH", tmp_path / "sales.db")
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    item_store.init_db()
    folder = items / "upload_0000abcd"; folder.mkdir()
    (folder / "listing.json").write_text(json.dumps({"title": "Barbour jacket " * 40, "brand": "Barbour", "price_gbp": 40}))
    Image.effect_noise((2048, 1536), 60).convert("RGB").save(folder / "front.jpg", quality=90)
    client = web.app.test_client()
    page = client.get("/drafts", headers={"Accept-Encoding": "gzip"})
    assert page.headers["Content-Encoding"] == "gzip"
    html = gzip.decompress(page.data).decode()
    assert "/items/upload_0000abcd/_grid.jpg?v=" in html
    thumb = folder / "_grid.jpg"
    assert thumb.stat().st_size < (folder / "front.jpg").stat().st_size / 5
    with Image.open(thumb) as image:
        assert max(image.size) == 480
    photo = client.get("/items/upload_0000abcd/_grid.jpg")
    assert photo.headers["Cache-Control"] == "private, no-cache"
    static = client.get("/static/studio.css?v=1")
    assert "immutable" in static.headers["Cache-Control"]
