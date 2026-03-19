"""
Tests for Vinted in-app session management.

Covers:
  1. check_auth_state() — fast file-based status indicator
  2. _build_context()   — context factory; raises VintedAuthError when no auth files
  3. _probe_auth()      — live session check via page URL
  4. Web routes         — /auth/status, /create-draft VINTED_AUTH_EXPIRED, /login/save

Run with:  .venv/bin/python -m pytest tests/test_auth_session.py -v
"""
import json
import time
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage_state(expires: float | None, name: str = "access_token_web") -> dict:
    """Build a minimal Playwright storage_state dict."""
    cookie = {
        "name": name,
        "value": "tok_abc123",
        "domain": ".vinted.co.uk",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "None",
    }
    if expires is not None:
        cookie["expires"] = expires
    return {"cookies": [cookie], "origins": []}


def _make_cookies_file(expires: float | None) -> list:
    """Build a raw vinted_cookies.json style list."""
    c = {
        "name": "access_token_web",
        "value": "tok_xyz",
        "domain": ".vinted.co.uk",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "lax",
    }
    if expires is not None:
        c["expires"] = expires
    return [c]


# ---------------------------------------------------------------------------
# 1. check_auth_state() — file-based status indicator
# ---------------------------------------------------------------------------

class TestCheckAuthState:
    def _check(self, auth_file=None, cookies_file=None, tmp_path=None):
        """Run check_auth_state() with temporary files injected via monkeypatching."""
        import app.draft_creator as dc

        orig_auth  = dc.AUTH_STATE_FILE
        orig_cook  = dc.COOKIES_FILE
        try:
            dc.AUTH_STATE_FILE  = tmp_path / "auth_state.json"
            dc.COOKIES_FILE     = tmp_path / "vinted_cookies.json"

            if auth_file is not None:
                dc.AUTH_STATE_FILE.write_text(json.dumps(auth_file))
            if cookies_file is not None:
                dc.COOKIES_FILE.write_text(json.dumps(cookies_file))

            return dc.check_auth_state()
        finally:
            dc.AUTH_STATE_FILE = orig_auth
            dc.COOKIES_FILE    = orig_cook

    def test_valid_storage_state_likely_logged_in(self, tmp_path):
        future = time.time() + 86400 * 10   # 10 days ahead
        state = _make_storage_state(future)
        result = self._check(auth_file=state, tmp_path=tmp_path)
        assert result["logged_in"] == "likely"
        assert result["method"] == "storage_state"
        assert result["expires_at"] == int(future)

    def test_expired_storage_state_returns_expired(self, tmp_path):
        past = time.time() - 3600   # 1 hour ago
        state = _make_storage_state(past)
        result = self._check(auth_file=state, tmp_path=tmp_path)
        assert result["logged_in"] == "expired"
        assert result["method"] == "storage_state"

    def test_no_auth_files_returns_missing(self, tmp_path):
        result = self._check(tmp_path=tmp_path)
        assert result["logged_in"] == "missing"
        assert result["method"] == "none"
        assert result["expires_at"] is None

    def test_cookie_fallback_likely_logged_in(self, tmp_path):
        """Only vinted_cookies.json exists — non-expired → likely."""
        future = time.time() + 86400 * 5
        cookies = _make_cookies_file(future)
        result = self._check(cookies_file=cookies, tmp_path=tmp_path)
        assert result["logged_in"] == "likely"
        assert result["method"] == "cookies"

    def test_cookie_fallback_expired(self, tmp_path):
        past = time.time() - 7200
        cookies = _make_cookies_file(past)
        result = self._check(cookies_file=cookies, tmp_path=tmp_path)
        assert result["logged_in"] == "expired"
        assert result["method"] == "cookies"

    def test_storage_state_without_token_assumes_likely(self, tmp_path):
        """auth_state.json exists but has no access_token_web — assume likely (may use localStorage)."""
        state = {"cookies": [], "origins": []}
        result = self._check(auth_file=state, tmp_path=tmp_path)
        assert result["logged_in"] == "likely"
        assert result["method"] == "storage_state"

    def test_storage_state_preferred_over_cookies(self, tmp_path):
        """When both files exist, auth_state.json wins."""
        future = time.time() + 86400
        state = _make_storage_state(future)
        cookies = _make_cookies_file(time.time() - 3600)  # expired cookies
        result = self._check(auth_file=state, cookies_file=cookies, tmp_path=tmp_path)
        # Should read auth_state.json (likely) not cookies (expired)
        assert result["logged_in"] == "likely"
        assert result["method"] == "storage_state"


# ---------------------------------------------------------------------------
# 2. _build_context() — raises VintedAuthError when no auth files present
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_raises_vinted_auth_error_without_auth_files(self, tmp_path):
        import app.draft_creator as dc

        orig_auth = dc.AUTH_STATE_FILE
        orig_cook = dc.COOKIES_FILE
        try:
            dc.AUTH_STATE_FILE = tmp_path / "auth_state.json"
            dc.COOKIES_FILE    = tmp_path / "vinted_cookies.json"

            browser = MagicMock()
            with pytest.raises(dc.VintedAuthError, match="No Vinted session found"):
                dc._build_context(browser)
        finally:
            dc.AUTH_STATE_FILE = orig_auth
            dc.COOKIES_FILE    = orig_cook

    def test_uses_storage_state_when_present(self, tmp_path):
        import app.draft_creator as dc

        orig_auth = dc.AUTH_STATE_FILE
        orig_cook = dc.COOKIES_FILE
        try:
            dc.AUTH_STATE_FILE = tmp_path / "auth_state.json"
            dc.COOKIES_FILE    = tmp_path / "vinted_cookies.json"
            dc.AUTH_STATE_FILE.write_text(json.dumps({"cookies": [], "origins": []}))

            browser = MagicMock()
            dc._build_context(browser)
            # storage_state kwarg should have been passed to new_context
            call_kwargs = browser.new_context.call_args.kwargs
            assert "storage_state" in call_kwargs
            assert call_kwargs["storage_state"] == str(dc.AUTH_STATE_FILE)
        finally:
            dc.AUTH_STATE_FILE = orig_auth
            dc.COOKIES_FILE    = orig_cook

    def test_falls_back_to_cookies_when_no_storage_state(self, tmp_path):
        import app.draft_creator as dc

        orig_auth = dc.AUTH_STATE_FILE
        orig_cook = dc.COOKIES_FILE
        try:
            dc.AUTH_STATE_FILE = tmp_path / "auth_state.json"
            dc.COOKIES_FILE    = tmp_path / "vinted_cookies.json"
            # Write a minimal valid cookies file
            dc.COOKIES_FILE.write_text(json.dumps([{
                "name": "access_token_web", "value": "x",
                "domain": ".vinted.co.uk", "path": "/",
                "secure": True, "httpOnly": True, "sameSite": "lax",
            }]))

            browser = MagicMock()
            ctx = dc._build_context(browser)
            # No storage_state kwarg — uses plain new_context + add_cookies
            call_kwargs = browser.new_context.call_args.kwargs
            assert "storage_state" not in call_kwargs
            ctx.add_cookies.assert_called_once()
        finally:
            dc.AUTH_STATE_FILE = orig_auth
            dc.COOKIES_FILE    = orig_cook


# ---------------------------------------------------------------------------
# 3. _probe_auth() — live session check
# ---------------------------------------------------------------------------

class TestProbeAuth:
    def test_raises_on_login_redirect(self):
        from app.draft_creator import _probe_auth, VintedAuthError

        page = MagicMock()
        page.url = "https://www.vinted.co.uk/login"
        with pytest.raises(VintedAuthError, match="session expired"):
            _probe_auth(page)

    def test_raises_on_signup_redirect(self):
        from app.draft_creator import _probe_auth, VintedAuthError

        page = MagicMock()
        page.url = "https://www.vinted.co.uk/signup"
        with pytest.raises(VintedAuthError):
            _probe_auth(page)

    def test_passes_on_vinted_home(self):
        from app.draft_creator import _probe_auth

        page = MagicMock()
        page.url = "https://www.vinted.co.uk"
        _probe_auth(page)   # must not raise

    def test_passes_on_vinted_subpage(self):
        from app.draft_creator import _probe_auth

        page = MagicMock()
        page.url = "https://www.vinted.co.uk/member/12345"
        _probe_auth(page)   # must not raise


# ---------------------------------------------------------------------------
# 4. Web routes
# ---------------------------------------------------------------------------

class TestWebRoutes:
    @pytest.fixture
    def client(self):
        from app.web import app
        app.config["TESTING"] = True
        return app.test_client()

    def test_auth_status_endpoint_returns_json(self, client):
        """GET /auth/status returns a JSON dict with logged_in key."""
        resp = client.get("/auth/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "logged_in" in data
        assert data["logged_in"] in ("likely", "expired", "missing")

    def test_create_draft_returns_auth_expired_code(self, client):
        """VintedAuthError from draft_creator → 401 with VINTED_AUTH_EXPIRED code."""
        from app import draft_creator

        with patch.object(draft_creator, "create_draft",
                          side_effect=draft_creator.VintedAuthError("session gone")):
            # Need a real listing.json to pass the 404 guard
            import tempfile, json as _json
            from app.config import ITEMS_DIR
            folder = "_test_auth_folder"
            item_path = ITEMS_DIR / folder
            item_path.mkdir(parents=True, exist_ok=True)
            listing_path = item_path / "listing.json"
            listing_path.write_text(_json.dumps({"title": "Test", "price_gbp": 10}))
            try:
                resp = client.post("/create-draft",
                                   json={"folder": folder},
                                   content_type="application/json")
                assert resp.status_code == 401
                data = resp.get_json()
                assert data["code"] == "VINTED_AUTH_EXPIRED"
                assert "session gone" in data["error"]
            finally:
                listing_path.unlink(missing_ok=True)
                try: item_path.rmdir()
                except Exception: pass

    def test_login_save_signals_background_thread_and_returns_saved(self, client):
        """POST /login/save sets save_path, signals done, and returns saved once the
        background 'saved' event fires (simulated here with a pre-set event)."""
        import threading
        import app.web as web_mod

        done_event  = threading.Event()
        saved_event = threading.Event()
        saved_event.set()   # simulate background thread completing immediately

        web_mod._vinted_login["done"]       = done_event
        web_mod._vinted_login["saved"]      = saved_event
        web_mod._vinted_login["save_error"] = None   # no error
        try:
            resp = client.post("/login/save")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "saved"
            assert data["method"] == "storage_state"
            # done was set, save_path was recorded
            assert done_event.is_set()
            assert web_mod._vinted_login.get("save_path", "").endswith("auth_state.json")
        finally:
            web_mod._vinted_login.clear()
