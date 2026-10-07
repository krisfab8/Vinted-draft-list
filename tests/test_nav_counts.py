"""Bottom bar: red counts for drafts and this month's sales, and today's listings."""
import json
from datetime import date

from app import web
from app.services import sales_history


def test_nav_shows_draft_and_sold_counts(monkeypatch, tmp_path):
    for name in ("upload_0000000a", "upload_0000000b", "upload_0000000c"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "listing.json").write_text(json.dumps({"title": name}))
    month = date.today().strftime("%Y-%m")
    rows = [{"folder": "upload_0000000c", "status": "sold", "sold_date": f"{month}-01"},
            {"folder": "upload_old", "status": "sold", "sold_date": "2001-01-01"}]
    monkeypatch.setattr(web, "ITEMS_DIR", tmp_path)
    monkeypatch.setattr(sales_history, "read_all", lambda: rows)
    html = web.app.test_client().get("/").get_data(as_text=True)
    assert 'aria-label="Drafts, 2"' in html
    assert 'aria-label="Sold, 1 this month"' in html
    assert 'id="snStreakCount">3<' in html


def test_nav_hides_zero_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "ITEMS_DIR", tmp_path)
    monkeypatch.setattr(sales_history, "read_all", lambda: [])
    html = web.app.test_client().get("/").get_data(as_text=True)
    assert 'class="nav-badge"' not in html
