"""Phone app Vinted filling: payload built from a listing, and the fill report."""
import json

import pytest

from app import web
from app.services import vinted_payload


@pytest.fixture
def item(tmp_path, monkeypatch):
    items = tmp_path / "items"; items.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", items)
    monkeypatch.setattr(web, "ROOT", tmp_path)
    folder = items / "upload_abcdef12"; folder.mkdir()
    (folder / "listing.json").write_text(json.dumps(dict(
        title="Barbour Bedale Wax Jacket Size Large", description="Lovely.", brand="Barbour", item_type="wax jacket",
        tagged_size="L", normalized_size="L", price_gbp=55, colour="Olive green", materials=["100% Cotton"],
        condition_summary="Very good used condition", category="Men > Jackets > Waxed")))
    for name in ("back.jpg", "front.jpg", "_thumb.jpg"):
        (folder / name).write_bytes(b"\xff\xd8" + name.encode())
    return folder


def test_payload_maps_listing_to_vinted_form(item):
    p = web.app.test_client().get("/api/vinted-fill/" + item.name).json
    assert p["title"].startswith("Barbour") and p["price"] == "55" and p["size"] == "L"
    assert p["condition"] == "Very good" and p["condition_id"] == 2
    assert p["package"] == 3 and p["materials"] == ["cotton"]
    assert [ph["name"] for ph in p["photos"]] == ["front.jpg", "back.jpg"]          # role order, no preview file
    assert p["photos"][0]["data_url"].startswith("data:image/jpeg;base64,")


@pytest.mark.parametrize("summary, label", [("New with tags attached", "New with tags"),
                                            ("Fair, visibly worn", "Satisfactory"), ("", "Very good")])
def test_condition_labels(summary, label):
    assert vinted_payload.condition_label(summary) == label


def test_saved_report_stores_vinted_draft_link_only_for_vinted(item):
    client = web.app.test_client()
    client.post("/api/vinted-fill-report", json={"folder": item.name, "saved": True, "draft_url": "https://evil.example/x"})
    assert "draft_url" not in json.loads((item / "listing.json").read_text())
    r = client.post("/api/vinted-fill-report", json={"folder": item.name, "saved": True, "filled": 11, "total": 11,
                                                    "draft_url": "https://www.vinted.co.uk/items/123/edit"})
    assert r.status_code == 200
    assert json.loads((item / "listing.json").read_text())["draft_url"] == "https://www.vinted.co.uk/items/123/edit"
    lines = (web.ROOT / "data" / "vinted_fill_reports.jsonl").read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["filled"] == 11
