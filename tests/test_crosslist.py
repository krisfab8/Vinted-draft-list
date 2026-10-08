"""Auto-delist when sold: where an item is listed, and what to take down after it sells."""
import json

import pytest

from app import web
from app.services import crosslist, item_store, sales_history, user_profile

FOLDER = "upload_abcdef12"


@pytest.fixture
def items(tmp_path, monkeypatch):
    root = tmp_path / "items"; root.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", root)
    monkeypatch.setattr(item_store, "DB_PATH", tmp_path / "items.db")
    monkeypatch.setattr(sales_history, "DB_PATH", tmp_path / "sales.db")
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    monkeypatch.setattr(crosslist, "DELISTERS", {})
    item_store.init_db()
    (root / FOLDER).mkdir()
    (root / FOLDER / "listing.json").write_text(json.dumps(dict(
        brand="Barbour", item_type="jacket", title="Barbour jacket", price_gbp=60,
        draft_url="https://www.vinted.co.uk/items/123/edit")))
    return root


def listing(root):
    return json.loads((root / FOLDER / "listing.json").read_text())


def test_vinted_draft_counts_as_listed_and_manual_platforms_toggle():
    item = {"draft_url": "https://www.vinted.co.uk/items/1/edit"}
    assert crosslist.where_listed(item) == {"Vinted": {"status": "live", "url": item["draft_url"]}}
    crosslist.set_listed(item, "eBay", url="https://www.ebay.co.uk/itm/9")
    crosslist.set_listed(item, "Depop")
    crosslist.set_listed(item, "Depop", live=False)
    assert set(crosslist.where_listed(item)) == {"Vinted", "eBay"}
    assert crosslist.where_listed(item)["eBay"]["url"] == "https://www.ebay.co.uk/itm/9"
    with pytest.raises(ValueError):
        crosslist.set_listed(item, "Gumtree")
    crosslist.set_listed(item, "Other", url="javascript:alert(1)")   # unsafe links are not stored
    assert "url" not in crosslist.where_listed(item)["Other"]


def test_sale_auto_ends_where_it_can_and_lists_the_rest():
    ended = []
    crosslist.DELISTERS["eBay"] = lambda listing, entry: ended.append(entry) or True
    crosslist.DELISTERS["Depop"] = lambda listing, entry: 1 / 0          # a failing delister never blocks the sale
    item = {"draft_url": "https://www.vinted.co.uk/items/1/edit"}
    for p in ("eBay", "Depop"):
        crosslist.set_listed(item, p)
    try:
        tasks = crosslist.after_sale(item, "Vinted")
    finally:
        crosslist.DELISTERS.clear()
    assert {t["platform"]: (t["done"], t["auto"]) for t in tasks} == {"eBay": (True, True), "Depop": (False, True)}
    assert len(ended) == 1
    where = crosslist.where_listed(item)
    assert where["Vinted"]["status"] == "sold" and where["eBay"]["status"] == "removed"
    assert crosslist.still_live(item, "Vinted") == ["Depop"]


def test_marking_sold_returns_the_take_down_checklist_and_flags_the_card(items):
    client = web.app.test_client()
    r = client.post(f"/listing/{FOLDER}/crosslist", json={"platform": "eBay", "action": "listed",
                                                           "url": "https://www.ebay.co.uk/itm/9"})
    assert r.status_code == 200 and set(r.json["crosslist"]) == {"Vinted", "eBay"}

    r = client.post(f"/listing/{FOLDER}/outcome", json={"status": "sold", "platform": "Vinted", "sold_price_gbp": 55})
    assert r.status_code == 200
    assert r.json["delist"] == [{"platform": "eBay", "url": "https://www.ebay.co.uk/itm/9", "done": False, "auto": False}]
    assert listing(items)["crosslist"]["Vinted"]["status"] == "sold"

    sold_page = client.get("/sold").get_data(as_text=True)
    assert "Still on eBay" in sold_page
    assert client.get(f"/listing/{FOLDER}").json["still_live"] == ["eBay"]

    r = client.post(f"/listing/{FOLDER}/crosslist", json={"platform": "eBay", "action": "removed"})
    assert r.status_code == 200 and r.json["still_live"] == []
    assert "Still on eBay" not in client.get("/sold").get_data(as_text=True)


def test_sold_only_where_listed_needs_nothing(items):
    client = web.app.test_client()
    r = client.post(f"/listing/{FOLDER}/outcome", json={"status": "sold", "platform": "Vinted", "sold_price_gbp": 55})
    assert r.json["delist"] == []


def test_bad_crosslist_requests_are_refused(items):
    client = web.app.test_client()
    assert client.post(f"/listing/{FOLDER}/crosslist", json={"platform": "Gumtree", "action": "listed"}).status_code == 422
    assert client.post(f"/listing/{FOLDER}/crosslist", json={"platform": "eBay", "action": "explode"}).status_code == 422
    assert client.post("/listing/upload_00000000/crosslist", json={"platform": "eBay", "action": "listed"}).status_code == 404
