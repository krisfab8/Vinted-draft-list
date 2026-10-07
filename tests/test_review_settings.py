"""Restyled review page (editable gender/category) and the settings page."""
import html
import json

import pytest

from app import web
from app.services import item_store, listing_state, user_profile


@pytest.fixture
def profile_file(monkeypatch, tmp_path):
    path = tmp_path / "user_profile.json"
    monkeypatch.setattr(user_profile, "_PATH", path)
    return path


@pytest.fixture
def item(tmp_path, monkeypatch, profile_file):
    items = tmp_path / "items"
    items.mkdir()
    monkeypatch.setattr(web, "ITEMS_DIR", items)
    monkeypatch.setattr(item_store, "DB_PATH", tmp_path / "items.db")
    item_store.init_db()
    folder = items / "upload_review"
    folder.mkdir()
    listing_state.write(folder / "listing.json", dict(
        brand="Barbour", item_type="jacket", title="Barbour jacket Size Large", description="Wax jacket.",
        tagged_size="L", normalized_size="L", gender="men's", category="Men > Coats & Jackets", price_gbp=40,
        materials=["Cotton"], low_confidence_fields=["normalized_size", "material_confidence"],
        warnings=["low_confidence_fields"]))
    for role in ("back", "front"):
        (folder / f"{role}.jpg").write_bytes(b"jpg")
    return folder


def test_review_page_has_editable_gender_and_category(item):
    page = web.app.test_client().get("/review/" + item.name).get_data(as_text=True)
    assert 'id="f-gender"' in page and 'data-field="gender"' in page
    assert 'id="f-category"' in page and 'data-field="category"' in page
    assert '<option value="Men > Coats & Jackets" selected' in html.unescape(page)
    assert "Check normalized size" in page and "material confidence" not in page
    assert page.index("front.jpg") < page.index("back.jpg")


def test_review_gender_and_category_edits_save(item):
    client = web.app.test_client()
    response = client.patch("/listing/" + item.name,
                            json={"gender": "women's", "category": "Women > Coats & Jackets"})
    assert response.status_code == 200, response.json
    saved = json.loads((item / "listing.json").read_text())
    assert saved["gender"] == "women's" and saved["category"] == "Women > Coats & Jackets"


def test_category_groups_keep_unknown_current_category():
    groups = web._category_groups("Women > Something new")
    assert groups["Women"][0] == "Women > Something new"
    assert "Men" in groups


def test_settings_page_renders_profile(profile_file, monkeypatch, tmp_path):
    monkeypatch.setattr(web, "ITEMS_DIR", tmp_path / "items")
    user_profile.save(dict(user_profile.load(), name="Kris", email="kris@example.com", pricing_mode="price"))
    page = web.app.test_client().get("/settings").get_data(as_text=True)
    assert 'value="Kris"' in page and "kris@example.com" in page
    assert 'class="header-avatar on"' in page and ">K<" in page


def test_identity_update_validates_and_keeps_other_fields(profile_file):
    client = web.app.test_client()
    user_profile.save(dict(user_profile.load(), name="Kris", email="kris@example.com"))
    assert client.post("/api/profile/identity", json={"email": "nope"}).status_code == 422
    response = client.post("/api/profile/identity", json={"name": "  Kris  F ", "marketing_opt_in": True})
    assert response.status_code == 200
    assert response.json == {"name": "Kris F", "email": "kris@example.com", "marketing_opt_in": True}
