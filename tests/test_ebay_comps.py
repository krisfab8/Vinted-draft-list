"""
Tests for app/services/ebay_comps.py

All tests are mocked — no live network calls.
Follows the same pattern as test_pricing_service.py.
"""
import json
import time
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_token_response(token="test_token", expires_in=7200, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = {"access_token": token, "expires_in": expires_in}
    return mock


def _make_search_response(items, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = {"itemSummaries": items}
    return mock


def _ebay_item(title="Barbour Wax Jacket", price=85.0, currency="GBP", condition="Used"):
    return {
        "title": title,
        "price": {"value": str(price), "currency": currency},
        "condition": condition,
        "itemWebUrl": "https://www.ebay.co.uk/itm/123",
    }


def _reset_token_cache():
    from app.services import ebay_comps
    ebay_comps._token_cache.clear()


def _mock_config(app_id="app123", cert_id="cert456", discount=0.70, enabled=True):
    """Return a mock config object with the given eBay settings."""
    cfg = MagicMock()
    cfg.EBAY_APP_ID = app_id
    cfg.EBAY_CERT_ID = cert_id
    cfg.EBAY_ACTIVE_TO_SOLD_DISCOUNT = discount
    cfg.ENABLE_EBAY_COMPS = enabled
    return cfg


# ── OAuth / token management ──────────────────────────────────────────────

class TestGetToken:

    def setup_method(self):
        _reset_token_cache()

    def test_returns_access_token(self):
        from app.services.ebay_comps import _get_token
        with patch("app.services.ebay_comps._cfg", return_value=_mock_config()):
            with patch("requests.post", return_value=_make_token_response("tok_abc")):
                token = _get_token()
        assert token == "tok_abc"

    def test_caches_result(self):
        from app.services.ebay_comps import _get_token
        with patch("app.services.ebay_comps._cfg", return_value=_mock_config()):
            with patch("requests.post", return_value=_make_token_response()) as mock_post:
                _get_token()
                _get_token()
        assert mock_post.call_count == 1

    def test_refreshes_near_expiry(self):
        from app.services import ebay_comps
        # Pre-populate cache with token expiring in 30 s (< refresh buffer of 60 s)
        ebay_comps._token_cache["token"] = "old_token"
        ebay_comps._token_cache["expires_at"] = time.time() + 30
        with patch("app.services.ebay_comps._cfg", return_value=_mock_config()):
            with patch("requests.post", return_value=_make_token_response("new_token")) as mock_post:
                token = ebay_comps._get_token()
        assert mock_post.call_count == 1
        assert token == "new_token"

    def test_raises_on_bad_credentials(self):
        from app.services.ebay_comps import _get_token, EbayAuthError
        with patch("app.services.ebay_comps._cfg", return_value=_mock_config()):
            with patch("requests.post", return_value=_make_token_response(status=401)):
                with pytest.raises(EbayAuthError):
                    _get_token()

    def test_raises_config_error_when_no_credentials(self):
        from app.services.ebay_comps import _get_token, EbayConfigError
        with patch("app.services.ebay_comps._cfg", return_value=_mock_config(app_id="", cert_id="")):
            with pytest.raises(EbayConfigError):
                _get_token()


# ── Search / normalisation ────────────────────────────────────────────────

class TestSearch:

    def test_returns_normalised_comps(self):
        from app.services.ebay_comps import _search
        items = [_ebay_item("Jacket A", 80.0), _ebay_item("Jacket B", 90.0)]
        with patch("requests.get", return_value=_make_search_response(items)):
            result = _search("barbour wax jacket", "tok")
        assert len(result) == 2
        assert result[0]["price_gbp"] == 80.0
        assert result[0]["title"] == "Jacket A"
        assert "url" in result[0]

    def test_filters_non_gbp_results(self):
        from app.services.ebay_comps import _search
        items = [
            _ebay_item("GBP item", 80.0, currency="GBP"),
            _ebay_item("USD item", 90.0, currency="USD"),
            _ebay_item("EUR item", 70.0, currency="EUR"),
        ]
        with patch("requests.get", return_value=_make_search_response(items)):
            result = _search("query", "tok")
        assert len(result) == 1
        assert result[0]["price_gbp"] == 80.0

    def test_returns_empty_list_on_zero_results(self):
        from app.services.ebay_comps import _search
        with patch("requests.get", return_value=_make_search_response([])):
            result = _search("query", "tok")
        assert result == []

    def test_query_includes_used_condition_filter(self):
        from app.services.ebay_comps import _search
        with patch("requests.get", return_value=_make_search_response([])) as mock_get:
            _search("barbour jacket", "tok")
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
        # params passed as keyword arg
        params = mock_get.call_args.kwargs.get("params", {})
        assert "USED" in params.get("filter", "")

    def test_marketplace_header_is_ebay_gb(self):
        from app.services.ebay_comps import _search
        with patch("requests.get", return_value=_make_search_response([])) as mock_get:
            _search("query", "tok")
        headers = mock_get.call_args.kwargs.get("headers", {})
        assert headers.get("X-EBAY-C-MARKETPLACE-ID") == "EBAY_GB"

    def test_raises_rate_limit_error_on_429(self):
        from app.services.ebay_comps import _search, EbayRateLimitError
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(EbayRateLimitError):
                _search("query", "tok")

    def test_raises_api_error_on_500(self):
        from app.services.ebay_comps import _search, EbayApiError
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(EbayApiError):
                _search("query", "tok")


# ── Query building ────────────────────────────────────────────────────────

class TestBuildQuery:

    def test_basic_brand_and_item_type(self):
        from app.services.ebay_comps import _build_query
        listing = {"brand": "Barbour", "item_type": "wax jacket"}
        assert _build_query(listing) == "Barbour wax jacket"

    def test_appends_material_when_brand_confidence_high(self):
        from app.services.ebay_comps import _build_query
        listing = {
            "brand": "Brora", "item_type": "jumper",
            "brand_confidence": "high", "materials": ["cashmere"],
        }
        q = _build_query(listing)
        assert "cashmere" in q

    def test_skips_material_when_brand_confidence_not_high(self):
        from app.services.ebay_comps import _build_query
        listing = {
            "brand": "Unknown", "item_type": "blazer",
            "brand_confidence": "low", "materials": ["wool"],
        }
        q = _build_query(listing)
        assert "wool" not in q

    def test_skips_common_material_not_in_useful_set(self):
        from app.services.ebay_comps import _build_query
        listing = {
            "brand": "Zara", "item_type": "shirt",
            "brand_confidence": "high", "materials": ["cotton"],
        }
        q = _build_query(listing)
        assert "cotton" not in q

    def test_raises_when_brand_and_item_type_missing(self):
        from app.services.ebay_comps import _build_query, EbayQueryError
        with pytest.raises(EbayQueryError):
            _build_query({})


# ── Outlier removal + range ───────────────────────────────────────────────

class TestOutlierRemoval:

    def test_removes_high_outliers(self):
        from app.services.ebay_comps import _remove_outliers
        prices = [50, 55, 60, 55, 52, 58, 200]   # 200 is an outlier
        clean = _remove_outliers(prices)
        assert 200 not in clean

    def test_removes_low_outliers(self):
        from app.services.ebay_comps import _remove_outliers
        prices = [1, 55, 60, 55, 52, 58, 54]   # 1 is an outlier
        clean = _remove_outliers(prices)
        assert 1 not in clean

    def test_keeps_tight_distribution(self):
        from app.services.ebay_comps import _remove_outliers
        prices = [50, 55, 60, 65, 70]
        clean = _remove_outliers(prices)
        assert clean == sorted(prices)

    def test_returns_unchanged_when_fewer_than_4(self):
        from app.services.ebay_comps import _remove_outliers
        prices = [10, 100]
        assert _remove_outliers(prices) == prices


class TestComputeRange:

    def test_range_has_low_mid_high(self):
        from app.services.ebay_comps import _compute_range
        r = _compute_range([40, 50, 60, 70, 80])
        assert r["low"] == 40
        assert r["mid"] == 60
        assert r["high"] == 80
        assert r["currency"] == "GBP"

    def test_median_correct_for_even_count(self):
        from app.services.ebay_comps import _compute_range
        r = _compute_range([40, 50, 60, 70])
        assert r["mid"] == 55  # (50+60)/2


class TestApplyDiscount:

    def test_discount_applied(self):
        from app.services.ebay_comps import _apply_discount
        r = _apply_discount({"low": 50, "high": 100, "mid": 75, "currency": "GBP"}, 0.70)
        assert r == {"low": 35, "high": 70}


# ── enrich() public function ──────────────────────────────────────────────

class TestEnrich:

    def setup_method(self):
        _reset_token_cache()

    def _run_enrich(self, listing, items, discount=0.70):
        """Helper: run enrich() with mocked token + search returning given items."""
        cfg = _mock_config(discount=discount)
        with patch("app.services.ebay_comps._cfg", return_value=cfg):
            with patch("requests.post", return_value=_make_token_response()):
                with patch("requests.get", return_value=_make_search_response(items)):
                    from app.services.ebay_comps import enrich
                    return enrich(listing)

    def test_writes_comps_to_listing(self):
        items = [_ebay_item(f"Jacket {i}", 80 + i) for i in range(5)]
        listing = {"brand": "Barbour", "item_type": "wax jacket", "price_gbp": 70}
        self._run_enrich(listing, items)
        assert "ebay_suggested_range" in listing
        assert "ebay_vinted_range" in listing
        assert "ebay_comps_fetched_at" in listing
        assert "ebay_comps_note" in listing
        assert "ebay_comps_skipped" not in listing

    def test_does_not_modify_price_gbp(self):
        items = [_ebay_item(f"Jacket {i}", 120 + i) for i in range(5)]
        listing = {"brand": "Barbour", "item_type": "wax jacket", "price_gbp": 70}
        self._run_enrich(listing, items)
        assert listing["price_gbp"] == 70

    def test_skips_when_credentials_missing(self):
        from app.services.ebay_comps import enrich
        cfg = _mock_config(app_id="", cert_id="")
        with patch("app.services.ebay_comps._cfg", return_value=cfg):
            listing = {"brand": "Barbour", "item_type": "wax jacket"}
            enrich(listing)
        assert listing.get("ebay_comps_skipped") == "no credentials"
        assert "ebay_suggested_range" not in listing

    def test_skips_when_feature_flag_off(self):
        from app.services.ebay_comps import enrich
        cfg = _mock_config(enabled=False)
        with patch("app.services.ebay_comps._cfg", return_value=cfg):
            with patch("requests.post") as mock_post:
                with patch("requests.get") as mock_get:
                    listing = {"brand": "Barbour", "item_type": "wax jacket"}
                    enrich(listing)
        mock_post.assert_not_called()
        mock_get.assert_not_called()

    def test_sets_skipped_on_auth_failure(self):
        from app.services.ebay_comps import enrich
        cfg = _mock_config()
        with patch("app.services.ebay_comps._cfg", return_value=cfg):
            with patch("requests.post", return_value=_make_token_response(status=401)):
                listing = {"brand": "Barbour", "item_type": "wax jacket"}
                enrich(listing)
        assert listing.get("ebay_comps_skipped") == "auth failed"

    def test_sets_skipped_on_zero_results(self):
        from app.services.ebay_comps import enrich
        cfg = _mock_config()
        with patch("app.services.ebay_comps._cfg", return_value=cfg):
            with patch("requests.post", return_value=_make_token_response()):
                with patch("requests.get", return_value=_make_search_response([])):
                    listing = {"brand": "Barbour", "item_type": "wax jacket"}
                    enrich(listing)
        assert listing.get("ebay_comps_skipped") == "no results"

    def test_sets_skipped_on_insufficient_results_after_filtering(self):
        """Fewer than MIN_RESULTS GBP items → insufficient results."""
        items = [_ebay_item("Item A", 80.0, "GBP"), _ebay_item("Item B", 90.0, "GBP")]
        listing = {"brand": "Barbour", "item_type": "wax jacket"}
        self._run_enrich(listing, items)
        assert listing.get("ebay_comps_skipped") == "insufficient results"

    def test_never_raises_on_connection_error(self):
        """ConnectionError on token request → outer except → 'error' skip, no raise."""
        from app.services.ebay_comps import enrich
        cfg = _mock_config()
        with patch("app.services.ebay_comps._cfg", return_value=cfg):
            with patch("requests.post", side_effect=ConnectionError("timeout")):
                listing = {"brand": "Barbour", "item_type": "wax jacket"}
                result = enrich(listing)   # must not raise
        assert result is listing
        assert listing.get("ebay_comps_skipped") == "error"

    def test_never_raises_on_unhandled_exception(self):
        from app.services.ebay_comps import enrich
        with patch("app.services.ebay_comps._cfg", side_effect=RuntimeError("boom")):
            listing = {"brand": "Barbour", "item_type": "wax jacket"}
            result = enrich(listing)   # must not raise
        assert result is listing
        assert listing.get("ebay_comps_skipped") == "error"

    def test_vinted_range_applies_discount(self):
        # 5 items at £100 each → eBay range mid=100, Vinted = 100*0.70=70
        items = [_ebay_item(f"J{i}", 100.0) for i in range(5)]
        listing = {"brand": "X", "item_type": "jacket"}
        self._run_enrich(listing, items, discount=0.70)
        v = listing.get("ebay_vinted_range", {})
        # All prices same → low=high=100 → vinted low=high=70
        assert v.get("low") == 70
        assert v.get("high") == 70

    def test_comps_count_reflects_cleaned_set(self):
        # 10 items with 1 outlier — after IQR removal should be 9
        prices = [80, 82, 85, 83, 81, 84, 86, 82, 83, 500]  # 500 is outlier
        items = [_ebay_item(f"J{i}", p) for i, p in enumerate(prices)]
        listing = {"brand": "X", "item_type": "jacket"}
        self._run_enrich(listing, items)
        assert listing.get("ebay_comps_count", 0) < 10

    def test_clears_prior_skipped_on_success(self):
        items = [_ebay_item(f"J{i}", 80.0) for i in range(5)]
        listing = {
            "brand": "Barbour", "item_type": "wax jacket",
            "ebay_comps_skipped": "no results",  # stale from previous attempt
        }
        self._run_enrich(listing, items)
        assert "ebay_comps_skipped" not in listing


# ── Route test ────────────────────────────────────────────────────────────

class TestFetchEbayCompsRoute:

    def test_returns_200_and_comp_summary(self, tmp_path, monkeypatch):
        """Route loads listing, calls enrich, saves, returns summary fields."""
        import json as _json
        from app.web import app as flask_app

        # Redirect ITEMS_DIR to tmp_path
        folder = "test_item"
        item_dir = tmp_path / folder
        item_dir.mkdir()
        (item_dir / "listing.json").write_text(_json.dumps({
            "brand": "Barbour", "item_type": "wax jacket", "price_gbp": 85,
        }))
        monkeypatch.setattr("app.web.ITEMS_DIR", tmp_path)

        # Mock enrich to write comps fields directly
        def _fake_enrich(listing):
            listing["ebay_suggested_range"] = {"low": 60, "mid": 80, "high": 100, "currency": "GBP"}
            listing["ebay_vinted_range"] = {"low": 42, "high": 70}
            listing["ebay_comps_count"] = 7
            listing["ebay_comps_titles"] = ["Jacket A"]
            listing["ebay_comps_query"] = "Barbour wax jacket"
            listing["ebay_comps_note"] = "7 listings"
            listing["ebay_comps_fetched_at"] = "2026-03-19T12:00:00"
            return listing

        monkeypatch.setattr("app.services.ebay_comps.enrich", _fake_enrich)

        with flask_app.test_client() as client:
            resp = client.post(f"/api/listing/{folder}/fetch-ebay-comps")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ebay_suggested_range"]["low"] == 60
        assert data["ebay_vinted_range"]["low"] == 42
        assert "price_gbp" not in data   # only summary fields returned

    def test_returns_404_for_missing_listing(self, tmp_path, monkeypatch):
        from app.web import app as flask_app
        monkeypatch.setattr("app.web.ITEMS_DIR", tmp_path)
        with flask_app.test_client() as client:
            resp = client.post("/api/listing/nonexistent_folder/fetch-ebay-comps")
        assert resp.status_code == 404

    def test_saves_comps_to_listing_json(self, tmp_path, monkeypatch):
        """Verify enrich result is actually persisted to disk."""
        import json as _json
        from app.web import app as flask_app

        folder = "test_save"
        item_dir = tmp_path / folder
        item_dir.mkdir()
        listing_path = item_dir / "listing.json"
        listing_path.write_text(_json.dumps({"brand": "Barbour", "item_type": "wax jacket"}))
        monkeypatch.setattr("app.web.ITEMS_DIR", tmp_path)

        def _fake_enrich(listing):
            listing["ebay_comps_count"] = 5
            listing["ebay_suggested_range"] = {"low": 50, "mid": 70, "high": 90, "currency": "GBP"}
            listing["ebay_vinted_range"] = {"low": 35, "high": 63}
            listing["ebay_comps_titles"] = []
            listing["ebay_comps_query"] = "Barbour wax jacket"
            listing["ebay_comps_note"] = "5 listings"
            listing["ebay_comps_fetched_at"] = "2026-03-19T12:00:00"
            return listing

        monkeypatch.setattr("app.services.ebay_comps.enrich", _fake_enrich)

        with flask_app.test_client() as client:
            client.post(f"/api/listing/{folder}/fetch-ebay-comps")

        saved = _json.loads(listing_path.read_text())
        assert saved["ebay_comps_count"] == 5
        assert saved["ebay_suggested_range"]["low"] == 50
        assert saved["brand"] == "Barbour"   # original fields preserved
