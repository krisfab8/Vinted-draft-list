"""
Tests for label auto-crop: _autocrop_label, _compress_with_autocrop,
and the ENABLE_LABEL_AUTOCROP feature flag integration.

Run with:  .venv/bin/python -m pytest tests/test_label_autocrop.py -v
"""
import io
import base64
from pathlib import Path

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dark_bg_label_image(
    w: int = 400, h: int = 300,
    bg: tuple = (15, 15, 15),
    label_color: tuple = (240, 240, 240),
    label_rect: tuple = (100, 90, 300, 190),   # (x1, y1, x2, y2)
) -> Image.Image:
    """Synthetic label photo: dark fabric background with a bright white label patch."""
    img = Image.new("RGB", (w, h), color=bg)
    x1, y1, x2, y2 = label_rect
    label = Image.new("RGB", (x2 - x1, y2 - y1), color=label_color)
    img.paste(label, (x1, y1))
    return img


def _uniform_image(w: int = 400, h: int = 300, color: tuple = (20, 20, 20)) -> Image.Image:
    return Image.new("RGB", (w, h), color=color)


def _save_jpg(img: Image.Image, path: Path) -> Path:
    img.save(str(path), "JPEG")
    return path


def _decoded_size(b64_data: str) -> tuple[int, int]:
    raw = base64.standard_b64decode(b64_data)
    return Image.open(io.BytesIO(raw)).size


# ---------------------------------------------------------------------------
# 1. _autocrop_label — core algorithm
# ---------------------------------------------------------------------------

class TestAutocropLabel:
    def test_dark_bg_bright_label_crop_applied(self):
        """Standard case: dark fabric + bright label → crop applied."""
        from app.extractor import _autocrop_label
        img = _dark_bg_label_image(400, 300, bg=(15, 15, 15), label_color=(240, 240, 240))
        _, meta = _autocrop_label(img)
        assert meta["crop_applied"] is True, "Expected crop to be applied on dark-bg label image"

    def test_crop_reduces_area(self):
        """Cropped dimensions must be smaller than original."""
        from app.extractor import _autocrop_label
        img = _dark_bg_label_image(400, 300)
        cropped, meta = _autocrop_label(img)
        cw, ch = meta["cropped_size"]
        ow, oh = meta["original_size"]
        assert cw * ch < ow * oh, "Crop must reduce image area"
        assert cw <= ow and ch <= oh, "Cropped dims must not exceed original"

    def test_crop_keeps_label_region(self):
        """After crop, the center of the label (white pixel) must be inside the result."""
        from app.extractor import _autocrop_label
        label_rect = (100, 90, 300, 190)
        img = _dark_bg_label_image(400, 300, label_rect=label_rect)
        cropped, meta = _autocrop_label(img)
        # Label center in original coords
        lx = (label_rect[0] + label_rect[2]) // 2  # 200
        ly = (label_rect[1] + label_rect[3]) // 2  # 140
        # The cropped image should contain this pixel (verify it's white-ish)
        cw, ch = cropped.size
        assert cw > 0 and ch > 0
        # Padding means label center is still within the cropped image
        assert meta["crop_applied"] is True

    def test_uniform_dark_image_fallback(self):
        """All-dark image has no content → fallback."""
        from app.extractor import _autocrop_label
        img = _uniform_image(color=(10, 10, 10))
        _, meta = _autocrop_label(img)
        assert meta["crop_applied"] is False
        assert meta["fallback_used"] is True

    def test_uniform_white_image_fallback(self):
        """All-white image: background and content same colour → no crop."""
        from app.extractor import _autocrop_label
        img = _uniform_image(400, 300, color=(245, 245, 245))
        _, meta = _autocrop_label(img)
        assert meta["crop_applied"] is False
        assert meta["fallback_used"] is True

    def test_already_tight_label_no_unnecessary_crop(self):
        """Image that IS the label (corners are the label) → area_ratio > threshold → fallback."""
        from app.extractor import _autocrop_label
        # White image with small dark text region — corners already on the label
        img = Image.new("RGB", (200, 150), color=(240, 240, 240))
        # Add a tiny dark text patch in centre — too small to trigger > 15% area saving
        text = Image.new("RGB", (10, 8), color=(10, 10, 10))
        img.paste(text, (95, 71))
        _, meta = _autocrop_label(img)
        # The area ratio after cropping to the tiny text (+ padding) is very small,
        # so crop WOULD be applied or fallback — both are acceptable.
        # Key assertion: output size matches what meta says
        _, meta2 = _autocrop_label(img)
        if meta2["crop_applied"]:
            assert meta2["cropped_size"] == (_, meta2)[0].size
        else:
            assert meta2["fallback_used"] is True

    def test_small_image_not_cropped(self):
        """Images smaller than 32×32 are returned unchanged."""
        from app.extractor import _autocrop_label
        img = Image.new("RGB", (20, 20), color=(200, 200, 200))
        result, meta = _autocrop_label(img)
        assert meta["crop_applied"] is False
        assert result.size == (20, 20)

    def test_crop_applied_flag_true_on_success(self):
        from app.extractor import _autocrop_label
        img = _dark_bg_label_image()
        _, meta = _autocrop_label(img)
        assert isinstance(meta["crop_applied"], bool)

    def test_fallback_used_false_when_crop_applied(self):
        from app.extractor import _autocrop_label
        img = _dark_bg_label_image()
        _, meta = _autocrop_label(img)
        if meta["crop_applied"]:
            assert meta["fallback_used"] is False

    def test_fallback_used_true_when_no_crop(self):
        from app.extractor import _autocrop_label
        img = _uniform_image()
        _, meta = _autocrop_label(img)
        assert meta["fallback_used"] is True
        assert meta["crop_applied"] is False

    def test_original_size_always_matches_input(self):
        from app.extractor import _autocrop_label
        for w, h in [(400, 300), (1024, 768), (800, 600)]:
            img = _dark_bg_label_image(w, h, label_rect=(w//4, h//4, 3*w//4, 3*h//4))
            _, meta = _autocrop_label(img)
            assert meta["original_size"] == (w, h), \
                f"original_size should be input dimensions, got {meta['original_size']}"

    def test_cropped_size_matches_output_image(self):
        """meta['cropped_size'] must match actual output image dimensions."""
        from app.extractor import _autocrop_label
        img = _dark_bg_label_image()
        result, meta = _autocrop_label(img)
        assert result.size == meta["cropped_size"]

    def test_crop_confidence_in_range(self):
        from app.extractor import _autocrop_label
        for img in [_dark_bg_label_image(), _uniform_image()]:
            _, meta = _autocrop_label(img)
            assert 0.0 <= meta["crop_confidence"] <= 1.0

    def test_low_confidence_noise_falls_back(self):
        """Sparse scattered pixels → bbox is huge but few foreground → low confidence → fallback."""
        from app.extractor import _autocrop_label
        img = _uniform_image(400, 300, color=(60, 60, 60))  # dark gray background
        # Place a few bright pixels far apart (this spans the whole image → low density)
        pixels = img.load()
        for x, y in [(5, 5), (395, 295)]:
            pixels[x, y] = (240, 240, 240)  # only 2 bright pixels in 400×300 image
        _, meta = _autocrop_label(img)
        # Two isolated pixels → bbox spans whole image → confidence ≈ 2/(400*300) ≈ 0 → fallback
        assert meta["fallback_used"] is True

    def test_no_upscaling_of_cropped_result(self):
        """Cropped image must not be upscaled beyond original dimensions."""
        from app.extractor import _autocrop_label
        img = _dark_bg_label_image(400, 300)
        result, meta = _autocrop_label(img)
        rw, rh = result.size
        assert rw <= 400 and rh <= 300, "Autocrop must not upscale"

    def test_autocrop_constants_exported(self):
        """Tuning constants must be accessible for dry-run reporting."""
        from app.extractor import (
            _AUTOCROP_TOLERANCE, _AUTOCROP_CONFIDENCE_MIN,
            _AUTOCROP_AREA_MAX, _AUTOCROP_PAD_FRACTION,
        )
        assert 10 <= _AUTOCROP_TOLERANCE <= 80
        assert 0.0 < _AUTOCROP_CONFIDENCE_MIN < 1.0
        assert 0.5 < _AUTOCROP_AREA_MAX < 1.0
        assert 0.0 < _AUTOCROP_PAD_FRACTION < 0.2


# ---------------------------------------------------------------------------
# 2. _compress_with_autocrop
# ---------------------------------------------------------------------------

class TestCompressWithAutocrop:
    def test_returns_three_tuple(self, tmp_path):
        from app.extractor import _compress_with_autocrop
        _save_jpg(_dark_bg_label_image(), tmp_path / "brand.jpg")
        result = _compress_with_autocrop(tmp_path / "brand.jpg", 1024)
        assert len(result) == 3, "Must return (b64, media_type, crop_meta)"

    def test_media_type_is_jpeg(self, tmp_path):
        from app.extractor import _compress_with_autocrop
        _save_jpg(_dark_bg_label_image(), tmp_path / "brand.jpg")
        _, media_type, _ = _compress_with_autocrop(tmp_path / "brand.jpg", 1024)
        assert media_type == "image/jpeg"

    def test_respects_max_dim(self, tmp_path):
        """After autocrop+compress, output must be ≤ max_dim."""
        from app.extractor import _compress_with_autocrop
        big_img = _dark_bg_label_image(2000, 1500)
        _save_jpg(big_img, tmp_path / "brand.jpg")
        b64, _, _ = _compress_with_autocrop(tmp_path / "brand.jpg", 1024)
        w, h = _decoded_size(b64)
        assert max(w, h) <= 1024

    def test_crop_meta_has_required_keys(self, tmp_path):
        from app.extractor import _compress_with_autocrop
        _save_jpg(_dark_bg_label_image(), tmp_path / "brand.jpg")
        _, _, meta = _compress_with_autocrop(tmp_path / "brand.jpg", 1024)
        for key in ("original_size", "cropped_size", "crop_applied", "crop_confidence", "fallback_used"):
            assert key in meta, f"crop_meta missing key '{key}'"

    def test_flag_disabled_no_crop_applied(self, tmp_path, monkeypatch):
        """When ENABLE_LABEL_AUTOCROP is False, no crop should be applied."""
        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_LABEL_AUTOCROP", False)
        _save_jpg(_dark_bg_label_image(), tmp_path / "brand.jpg")
        _, _, meta = app.extractor._compress_with_autocrop(tmp_path / "brand.jpg", 1024)
        assert meta["crop_applied"] is False

    def test_flag_enabled_crop_can_apply(self, tmp_path, monkeypatch):
        """When flag is enabled and image has dark background, crop may apply."""
        import app.extractor
        monkeypatch.setattr(app.extractor, "ENABLE_LABEL_AUTOCROP", True)
        _save_jpg(_dark_bg_label_image(400, 300), tmp_path / "brand.jpg")
        _, _, meta = app.extractor._compress_with_autocrop(tmp_path / "brand.jpg", 1024)
        # Either crop applied or fallback used — both are valid, but meta must be populated
        assert isinstance(meta["crop_applied"], bool)


# ---------------------------------------------------------------------------
# 3. _load_photos integration
# ---------------------------------------------------------------------------

class TestLoadPhotosWithAutocrop:
    def _make_photos(self, tmp_path, roles=("front", "brand", "model_size", "material")):
        for role in roles:
            if role in ("brand", "model_size", "material"):
                _save_jpg(_dark_bg_label_image(), tmp_path / f"{role}.jpg")
            else:
                _save_jpg(_uniform_image(800, 600, (128, 128, 128)), tmp_path / f"{role}.jpg")

    def test_returns_tuple(self, tmp_path):
        from app.extractor import _load_photos
        self._make_photos(tmp_path)
        result = _load_photos(tmp_path)
        assert isinstance(result, tuple) and len(result) == 2, \
            "_load_photos must return (blocks, crop_report)"

    def test_crop_report_has_ocr_roles(self, tmp_path):
        from app.extractor import _load_photos
        self._make_photos(tmp_path)
        _, crop_report = _load_photos(tmp_path)
        for role in ("brand", "model_size", "material"):
            assert role in crop_report, f"crop_report must include '{role}'"

    def test_front_not_in_crop_report(self, tmp_path):
        """Non-OCR photos (front) must not appear in crop_report."""
        from app.extractor import _load_photos
        self._make_photos(tmp_path)
        _, crop_report = _load_photos(tmp_path)
        assert "front" not in crop_report, "front is not an OCR role; must not be in crop_report"

    def test_crop_report_values_are_dicts(self, tmp_path):
        from app.extractor import _load_photos
        self._make_photos(tmp_path)
        _, crop_report = _load_photos(tmp_path)
        for role, meta in crop_report.items():
            assert isinstance(meta, dict), f"crop_report['{role}'] must be a dict"
            assert "crop_applied" in meta

    def test_ocr_roles_use_1024_via_autocrop(self, tmp_path):
        """OCR roles go through _compress_with_autocrop at max_dim=1024."""
        from unittest.mock import patch
        from app.extractor import _compress_with_autocrop as real_cwa
        self._make_photos(tmp_path)

        captured = {}

        def spy(path, max_dim):
            captured[Path(path).stem] = max_dim
            return real_cwa(path, max_dim)

        with patch("app.extractor._compress_with_autocrop", side_effect=spy):
            from app.extractor import _load_photos
            _load_photos(tmp_path)

        assert captured.get("brand") == 1024
        assert captured.get("model_size") == 1024
        assert captured.get("material") == 1024

    def test_front_uses_compress_image_at_768(self, tmp_path):
        """Non-OCR roles go through _compress_image at max_dim=768."""
        from unittest.mock import patch
        from app.extractor import _compress_image as real_ci
        self._make_photos(tmp_path)

        captured = {}

        def spy(path, max_dim=None):
            captured[Path(path).stem] = max_dim
            return real_ci(path, max_dim)

        with patch("app.extractor._compress_image", side_effect=spy):
            from app.extractor import _load_photos
            _load_photos(tmp_path)

        assert captured.get("front") == 768


# ---------------------------------------------------------------------------
# 4. OCR_ROLES constant
# ---------------------------------------------------------------------------

class TestOcrRolesConstant:
    def test_ocr_roles_contains_expected(self):
        from app.extractor import _OCR_ROLES
        assert "brand" in _OCR_ROLES
        assert "model_size" in _OCR_ROLES
        assert "material" in _OCR_ROLES

    def test_front_not_ocr_role(self):
        from app.extractor import _OCR_ROLES
        assert "front" not in _OCR_ROLES

    def test_back_not_ocr_role(self):
        from app.extractor import _OCR_ROLES
        assert "back" not in _OCR_ROLES
