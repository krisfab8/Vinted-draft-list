"""Onboarding saves validated answers; the upload page knows whether it is done."""
import json

import pytest

from app import web
from app.services import user_profile


@pytest.fixture
def profile_file(monkeypatch, tmp_path):
    path = tmp_path / "user_profile.json"
    monkeypatch.setattr(user_profile, "_PATH", path)
    return path


ANSWERS = {"name": "  Kris   Fab ", "email": "Kris@Example.com", "intent": "reseller", "volume": "high",
           "vinted_experience": "experienced", "pricing_mode": "price", "photo_mode": "pro",
           "marketing_opt_in": True}


def test_onboarding_saves_clean_answers(profile_file):
    response = web.app.test_client().post("/api/onboarding", json=ANSWERS)
    assert response.status_code == 200
    assert response.json == {"name": "Kris Fab", "photo_mode": "pro", "daily_goal": 6}
    saved = json.loads(profile_file.read_text())
    assert saved["email"] == "kris@example.com" and saved["intent"] == "reseller"
    assert saved["marketing_opt_in"] is True and saved["onboarded_at"]


@pytest.mark.parametrize("change, message", [
    ({"name": " "}, "Add your name."),
    ({"email": "not-an-email"}, "Check your email address."),
    ({"volume": "loads"}, "Choose an option for volume."),
])
def test_onboarding_rejects_bad_answers(profile_file, change, message):
    response = web.app.test_client().post("/api/onboarding", json={**ANSWERS, **change})
    assert response.status_code == 422 and response.json["error"] == message
    assert not profile_file.exists()


def test_profile_patch_cannot_set_identity(profile_file):
    client = web.app.test_client()
    client.post("/api/onboarding", json=ANSWERS)
    client.patch("/api/profile", json={"email": "evil@example.com", "pricing_mode": "speed"})
    saved = json.loads(profile_file.read_text())
    assert saved["email"] == "kris@example.com" and saved["pricing_mode"] == "speed"


def test_upload_page_sends_new_users_to_welcome(profile_file, monkeypatch, tmp_path):
    monkeypatch.setattr(web, "ITEMS_DIR", tmp_path / "items")
    client = web.app.test_client()
    assert '<meta name="onboarded" content="no">' in client.get("/").get_data(as_text=True)
    assert client.get("/welcome").status_code == 200
    client.post("/api/onboarding", json=ANSWERS)
    assert '<meta name="onboarded" content="yes">' in client.get("/").get_data(as_text=True)


def test_profile_patch_validates_choices(profile_file):
    client = web.app.test_client()
    assert client.patch("/api/profile", json={"pricing_mode": "cheap"}).status_code == 422
    assert client.patch("/api/profile", json={"photo_mode": "pro"}).json["photo_mode"] == "pro"


def test_upload_page_carries_onboarding_choices(profile_file, monkeypatch, tmp_path):
    monkeypatch.setattr(web, "ITEMS_DIR", tmp_path / "items")
    client = web.app.test_client()
    client.post("/api/onboarding", json=ANSWERS)
    html = client.get("/").get_data(as_text=True)
    assert '<meta name="photo-mode" content="pro">' in html
    assert '<meta name="pricing-mode" content="price">' in html


def test_reprice_uses_the_onboarding_style(profile_file, monkeypatch, tmp_path):
    from app.services import pricing, sales_history
    monkeypatch.setattr(pricing, "lookup_memory", lambda **kwargs: None)
    monkeypatch.setattr(sales_history, "comparisons", lambda listing: {})
    items = tmp_path / "items"; folder = items / "upload_0000abcd"; folder.mkdir(parents=True)
    listing = {"title": "Peter Millar Polo Shirt Mens S", "brand": "Peter Millar", "item_type": "polo shirt",
               "price_gbp": 30, "ai_price_gbp": 30, "condition_summary": "Very good used condition",
               "ai_price_condition": "Very good", "description": "Polo.", "category": "Men > Polo Shirts"}
    (folder / "listing.json").write_text(json.dumps(listing))
    monkeypatch.setattr(web, "ITEMS_DIR", items)
    client = web.app.test_client()
    client.post("/api/onboarding", json=ANSWERS)  # Best price
    response = client.post("/reprice/upload_0000abcd", json={})
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    body = response.json
    proposal = body.get("price_proposal") or body.get("proposal") or body
    assert proposal.get("price_gbp") == 33
