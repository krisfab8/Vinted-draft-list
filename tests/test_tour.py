"""How it works tour: shown after the welcome, ends in the camera, rewatchable from Settings."""
from pathlib import Path

from app import web
from app.services import user_profile

ROOT = Path(__file__).resolve().parents[1]


def test_tour_page_has_five_cards_and_starts_the_camera(tmp_path, monkeypatch):
    monkeypatch.setattr(user_profile, "_PATH", tmp_path / "profile.json")
    page = web.app.test_client().get("/tour").get_data(as_text=True)
    assert page.count('class="tr-slide"') == 5
    assert "Nothing goes live" in page                    # drafts, never auto-published
    assert 'leave("/?camera=1")' in page and "coin.js" in page
    settings = web.app.test_client().get("/settings").get_data(as_text=True)
    assert 'href="/tour"' in settings


def test_welcome_finishes_on_the_tour_and_upload_opens_the_camera():
    assert "location.replace('/tour')" in (ROOT / "app/templates/onboarding.html").read_text()
    assert 'get("camera") === "1"' in (ROOT / "app/templates/index.html").read_text()
