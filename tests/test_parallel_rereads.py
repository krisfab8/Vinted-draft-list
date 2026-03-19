"""
Tests for parallel brand + material rereads (Step 3: ENABLE_PARALLEL_REREADS).

Run with:  .venv/bin/python -m pytest tests/test_parallel_rereads.py -v
"""
import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpg(path: Path, w: int = 200, h: int = 200) -> Path:
    Image.new("RGB", (w, h), color=(128, 128, 128)).save(str(path), "JPEG")
    return path


def _make_folder(tmp_path: Path, photos=("brand", "material")) -> Path:
    """Create a minimal item folder with the requested photos."""
    _make_jpg(tmp_path / "front.jpg")
    for name in photos:
        _make_jpg(tmp_path / f"{name}.jpg")
    return tmp_path


def _base_extraction(overrides: dict | None = None) -> dict:
    """Minimal extraction result that triggers both rereads."""
    base = {
        "brand": "Barbur",            # OCR typo → triggers brand reread
        "brand_confidence": "low",
        "brand_reason": "unclear",
        "brand_candidates": [],
        "item_type": "blazer",
        "tagged_size": "M",
        "normalized_size": "M",
        "materials": [],              # empty → triggers material full reread
        "material_confidence": "low",
        "material_reason": "unclear",
        "material_candidates": [],
        "pricing_sensitive_material": False,
        "fabric_mill": None,
        "colour": "Navy",
        "gender": "men's",
        "confidence": 0.6,
        "low_confidence_fields": ["brand", "materials"],
        "condition_summary": "Very good used condition — minimal wear.",
        "flaws_note": None,
    }
    if overrides:
        base.update(overrides)
    return base


def _mock_anthropic_create(brand_response: str, material_response: str):
    """
    Return a factory that produces mock anthropic clients.
    Call order within a test is not guaranteed (parallel), so match by content.
    """
    def _factory():
        mock_client = MagicMock()
        call_count = [0]

        def _create(**kwargs):
            call_count[0] += 1
            # Identify call by max_tokens (brand=80, material=150 for full)
            max_tok = kwargs.get("max_tokens", 0)
            if max_tok <= 80:
                text = brand_response
            else:
                text = material_response
            resp = MagicMock()
            resp.content = [MagicMock(text=text)]
            return resp

        mock_client.messages.create.side_effect = _create
        return mock_client

    return _factory


# ---------------------------------------------------------------------------
# 1. Feature flag
# ---------------------------------------------------------------------------

class TestParallelRereadsFlag:
    def test_flag_exists_and_defaults_true(self):
        from app.config import ENABLE_PARALLEL_REREADS
        assert ENABLE_PARALLEL_REREADS is True

    def test_flag_importable_in_extractor(self):
        from app.extractor import ENABLE_PARALLEL_REREADS  # noqa: F401


# ---------------------------------------------------------------------------
# 2. _should_reread_brand / _should_reread_material gate logic (unchanged)
# ---------------------------------------------------------------------------

class TestRereadsGates:
    def test_both_triggered(self):
        from app.extractor import _should_reread_brand, _should_reread_material
        item = _base_extraction()
        assert _should_reread_brand(item)
        assert _should_reread_material(item)

    def test_only_brand_triggered(self):
        from app.extractor import _should_reread_brand, _should_reread_material
        item = _base_extraction({
            "brand_confidence": "low",
            "materials": ["100% Cotton"],
            "material_confidence": "high",
            "fabric_mill": "None",
        })
        item["fabric_mill"] = "some mill"  # skip mill-only too
        assert _should_reread_brand(item)
        assert not _should_reread_material(item)

    def test_only_material_triggered(self):
        from app.extractor import _should_reread_brand, _should_reread_material
        item = _base_extraction({
            "brand": "Barbour",
            "brand_confidence": "high",
            "materials": [],
            "material_confidence": "low",
        })
        assert not _should_reread_brand(item)
        assert _should_reread_material(item)

    def test_neither_triggered(self):
        from app.extractor import _should_reread_brand, _should_reread_material
        item = _base_extraction({
            "brand": "Barbour",
            "brand_confidence": "high",
            "materials": ["100% Cotton"],
            "material_confidence": "high",
            "fabric_mill": "some mill",
        })
        assert not _should_reread_brand(item)
        assert not _should_reread_material(item)


# ---------------------------------------------------------------------------
# 3. Parallel path: both rereads run concurrently
# ---------------------------------------------------------------------------

class TestParallelExecution:
    def _make_timing_mock(self, folder: Path):
        """Returns (mock_factory, call_log) where call_log records (role, thread_id, t_start)."""
        call_log = []
        lock = threading.Lock()

        def _compress_with_autocrop_spy(path, max_dim):
            return "fake_b64", "image/jpeg", {"crop_applied": False, "fallback_used": True,
                                               "original_size": (200, 200), "cropped_size": (200, 200),
                                               "crop_confidence": 1.0}

        real_brand_fn = None
        real_mat_fn = None

        def brand_photo_spy(f, model):
            t = time.perf_counter()
            tid = threading.get_ident()
            with lock:
                call_log.append(("brand", tid, t))
            time.sleep(0.05)  # simulate network latency
            return {"brand": "Barbour", "collection_keywords": []}

        def mat_photo_spy(f, model, full_reread=False):
            t = time.perf_counter()
            tid = threading.get_ident()
            with lock:
                call_log.append(("material", tid, t))
            time.sleep(0.05)
            return {"materials": ["100% Wool"], "fabric_mill": None}

        return brand_photo_spy, mat_photo_spy, call_log

    def test_parallel_uses_different_threads(self, tmp_path, monkeypatch):
        """When both rereads trigger, they run in separate threads."""
        _make_folder(tmp_path)
        brand_spy, mat_spy, call_log = self._make_timing_mock(tmp_path)

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)

        # Patch API calls and image loading
        with patch("app.extractor._reread_brand_photo", side_effect=brand_spy), \
             patch("app.extractor._reread_material_photo", side_effect=mat_spy), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(_base_extraction(), {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            app.extractor.extract(tmp_path)

        assert len(call_log) == 2, "Both rereads must run"
        thread_ids = {entry[1] for entry in call_log}
        assert len(thread_ids) == 2, "Each reread must run in a different thread"

    def test_parallel_faster_than_sequential(self, tmp_path, monkeypatch):
        """Parallel path should complete in ~1× latency not ~2× sequential."""
        _make_folder(tmp_path)
        DELAY = 0.08  # 80ms per call

        call_times: list[float] = []

        def slow_brand(f, model):
            call_times.append(time.perf_counter())
            time.sleep(DELAY)
            return {"brand": "Barbour", "collection_keywords": []}

        def slow_mat(f, model, full_reread=False):
            call_times.append(time.perf_counter())
            time.sleep(DELAY)
            return {"materials": ["100% Wool"], "fabric_mill": None}

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)

        t0 = time.perf_counter()
        with patch("app.extractor._reread_brand_photo", side_effect=slow_brand), \
             patch("app.extractor._reread_material_photo", side_effect=slow_mat), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(_base_extraction(), {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            app.extractor.extract(tmp_path)
        elapsed = time.perf_counter() - t0

        # Sequential would take ≥ 2×DELAY; parallel should finish in < 1.8×DELAY
        assert elapsed < 1.8 * DELAY, (
            f"Parallel rereads took {elapsed:.3f}s — expected < {1.8 * DELAY:.3f}s"
        )


# ---------------------------------------------------------------------------
# 4. Brand reread only
# ---------------------------------------------------------------------------

class TestOnlyBrandReread:
    def test_brand_result_applied(self, tmp_path, monkeypatch):
        _make_folder(tmp_path, photos=["brand"])
        item = _base_extraction({
            "materials": ["100% Cotton"],
            "material_confidence": "high",
        })

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)

        with patch("app.extractor._reread_brand_photo",
                   return_value={"brand": "Barbour", "collection_keywords": []}), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            result, _ = app.extractor.extract(tmp_path)

        assert result["brand"] == "Barbour"
        assert result["brand_confidence"] == "high"

    def test_material_not_called_when_not_triggered(self, tmp_path, monkeypatch):
        _make_folder(tmp_path, photos=["brand"])
        item = _base_extraction({
            "materials": ["100% Cotton"],
            "material_confidence": "high",
            "fabric_mill": "SomeMill",
        })

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)
        mat_call_count = [0]

        def count_mat(f, m, **kw):
            mat_call_count[0] += 1
            return None

        with patch("app.extractor._reread_brand_photo",
                   return_value={"brand": "Barbour", "collection_keywords": []}), \
             patch("app.extractor._reread_material_photo", side_effect=count_mat), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            app.extractor.extract(tmp_path)

        assert mat_call_count[0] == 0


# ---------------------------------------------------------------------------
# 5. Material reread only
# ---------------------------------------------------------------------------

class TestOnlyMaterialReread:
    def test_material_result_applied(self, tmp_path, monkeypatch):
        _make_folder(tmp_path, photos=["material"])
        item = _base_extraction({
            "brand": "Barbour",
            "brand_confidence": "high",
        })

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)

        with patch("app.extractor._reread_material_photo",
                   return_value={"materials": ["100% Wool"], "fabric_mill": None}), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            result, _ = app.extractor.extract(tmp_path)

        assert "100% Wool" in result["materials"]

    def test_brand_not_called_when_not_triggered(self, tmp_path, monkeypatch):
        _make_folder(tmp_path, photos=["material"])
        item = _base_extraction({
            "brand": "Barbour",
            "brand_confidence": "high",
        })

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)
        brand_call_count = [0]

        def count_brand(f, m):
            brand_call_count[0] += 1
            return {"brand": "Barbour", "collection_keywords": []}

        with patch("app.extractor._reread_brand_photo", side_effect=count_brand), \
             patch("app.extractor._reread_material_photo",
                   return_value={"materials": ["100% Wool"], "fabric_mill": None}), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            app.extractor.extract(tmp_path)

        assert brand_call_count[0] == 0


# ---------------------------------------------------------------------------
# 6. Graceful failure: one reread fails, other succeeds
# ---------------------------------------------------------------------------

class TestRereadFailureGraceful:
    def test_brand_fails_material_still_applied(self, tmp_path, monkeypatch):
        """Brand reread raising an exception must not prevent material reread."""
        _make_folder(tmp_path)
        item = _base_extraction()

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)

        def fail_brand(f, model):
            raise RuntimeError("Network timeout")

        with patch("app.extractor._reread_brand_photo", side_effect=fail_brand), \
             patch("app.extractor._reread_material_photo",
                   return_value={"materials": ["80% Wool", "20% Polyester"], "fabric_mill": None}), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            result, _ = app.extractor.extract(tmp_path)

        # Material reread applied despite brand failure
        assert "80% Wool" in result["materials"]
        # Brand stays as-is (corrected by deterministic fallback)
        assert result.get("brand") is not None  # fallback ran

    def test_material_fails_brand_still_applied(self, tmp_path, monkeypatch):
        """Material reread raising an exception must not prevent brand reread."""
        _make_folder(tmp_path)
        item = _base_extraction()

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)

        def fail_mat(f, model, full_reread=False):
            raise RuntimeError("Connection refused")

        with patch("app.extractor._reread_brand_photo",
                   return_value={"brand": "Barbour", "collection_keywords": []}), \
             patch("app.extractor._reread_material_photo", side_effect=fail_mat), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            result, _ = app.extractor.extract(tmp_path)

        # Brand reread applied despite material failure
        assert result["brand"] == "Barbour"
        assert result["brand_confidence"] == "high"

    def test_both_fail_no_exception_raised(self, tmp_path, monkeypatch):
        """Both rereads failing must not raise — extract() returns gracefully."""
        _make_folder(tmp_path)
        item = _base_extraction()

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)

        with patch("app.extractor._reread_brand_photo",
                   side_effect=RuntimeError("timeout")), \
             patch("app.extractor._reread_material_photo",
                   side_effect=RuntimeError("timeout")), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            result, _ = app.extractor.extract(tmp_path)  # must not raise

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 7. Both rereads skipped
# ---------------------------------------------------------------------------

class TestBothSkipped:
    def test_no_reread_functions_called(self, tmp_path, monkeypatch):
        _make_folder(tmp_path, photos=["brand", "material"])
        item = _base_extraction({
            "brand": "Barbour",
            "brand_confidence": "high",
            "materials": ["100% Cotton"],
            "material_confidence": "high",
            "fabric_mill": "SomeMill",
        })

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", True)
        calls = []

        with patch("app.extractor._reread_brand_photo",
                   side_effect=lambda *a, **k: calls.append("brand") or None), \
             patch("app.extractor._reread_material_photo",
                   side_effect=lambda *a, **k: calls.append("material") or None), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            app.extractor.extract(tmp_path)

        assert calls == [], f"Expected no reread calls, got: {calls}"


# ---------------------------------------------------------------------------
# 8. Flag disabled falls back to sequential
# ---------------------------------------------------------------------------

class TestFlagDisabledSequential:
    def test_flag_off_still_produces_correct_result(self, tmp_path, monkeypatch):
        """With flag disabled, rereads still run (sequentially) and results applied."""
        _make_folder(tmp_path)
        item = _base_extraction()

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", False)

        with patch("app.extractor._reread_brand_photo",
                   return_value={"brand": "Barbour", "collection_keywords": []}), \
             patch("app.extractor._reread_material_photo",
                   return_value={"materials": ["100% Wool"], "fabric_mill": None}), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            result, _ = app.extractor.extract(tmp_path)

        assert result["brand"] == "Barbour"
        assert "100% Wool" in result["materials"]

    def test_flag_off_uses_single_thread(self, tmp_path, monkeypatch):
        """With flag disabled, both calls happen on the main thread."""
        _make_folder(tmp_path)
        item = _base_extraction()
        thread_ids = []

        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_PARALLEL_REREADS", False)

        def brand_thread(f, m):
            thread_ids.append(("brand", threading.get_ident()))
            return {"brand": "Barbour", "collection_keywords": []}

        def mat_thread(f, m, full_reread=False):
            thread_ids.append(("material", threading.get_ident()))
            return {"materials": ["100% Wool"], "fabric_mill": None}

        main_tid = threading.get_ident()
        with patch("app.extractor._reread_brand_photo", side_effect=brand_thread), \
             patch("app.extractor._reread_material_photo", side_effect=mat_thread), \
             patch("app.extractor._load_photos", return_value=([], {})), \
             patch("app.extractor._extract_claude", return_value=(item, {})), \
             patch("app.extractor.VISION_PROVIDER", "claude-haiku"):
            app.extractor.extract(tmp_path)

        for role, tid in thread_ids:
            assert tid == main_tid, f"{role} reread ran in unexpected thread {tid}"
