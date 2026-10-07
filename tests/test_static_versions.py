"""Static CSS/JS URLs carry the file's modified time so phones never keep stale code after a deploy."""
import re

from app import web


def test_upload_page_scripts_and_styles_are_versioned(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "ITEMS_DIR", tmp_path / "items")
    html = web.app.test_client().get("/").get_data(as_text=True)
    for name in ("camera_capture.js", "photo_quality.js", "studio.css"):
        assert re.search(rf"/static/{re.escape(name)}\?v=\d+\"", html), name
