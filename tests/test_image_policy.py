"""
Unit tests for the image resize policy and photo selection rules.

Run with:  .venv/bin/python -m pytest tests/test_image_policy.py -v
"""
import io
import struct
import tempfile
from pathlib import Path
from unittest.mock import call, patch

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpg(path: Path, w: int, h: int) -> Path:
    """Write a plain JPEG of the given size to path."""
    img = Image.new("RGB", (w, h), color=(128, 128, 128))
    img.save(str(path), "JPEG")
    return path


def _decoded_size(b64_data: str) -> tuple[int, int]:
    """Decode a base64 JPEG and return its (width, height)."""
    import base64
    raw = base64.standard_b64decode(b64_data)
    img = Image.open(io.BytesIO(raw))
    return img.size


# ---------------------------------------------------------------------------
# 1. Core photo list
# ---------------------------------------------------------------------------

class TestCorePhotoList:
    def test_back_excluded(self):
        from app.config import CORE_PHOTOS
        assert "back" not in CORE_PHOTOS, "back must be excluded from CORE_PHOTOS"

    def test_required_photos_present(self):
        from app.config import CORE_PHOTOS
        for name in ("front", "brand", "model_size", "material"):
            assert name in CORE_PHOTOS, f"'{name}' must be in CORE_PHOTOS"

    def test_order(self):
        from app.config import CORE_PHOTOS
        assert CORE_PHOTOS.index("front") < CORE_PHOTOS.index("brand"), \
            "front should come before brand"


# ---------------------------------------------------------------------------
# 2. Per-role max dimension config
# ---------------------------------------------------------------------------

class TestPhotoMaxDimConfig:
    def test_front_is_768(self):
        from app.extractor import _PHOTO_MAX_DIM
        assert _PHOTO_MAX_DIM["front"] == 768

    def test_brand_is_1024(self):
        from app.extractor import _PHOTO_MAX_DIM
        assert _PHOTO_MAX_DIM["brand"] == 1024

    def test_model_size_is_1024(self):
        from app.extractor import _PHOTO_MAX_DIM
        assert _PHOTO_MAX_DIM["model_size"] == 1024

    def test_material_is_1024(self):
        from app.extractor import _PHOTO_MAX_DIM
        assert _PHOTO_MAX_DIM["material"] == 1024

    def test_default_is_768(self):
        from app.extractor import _DEFAULT_MAX_DIM
        assert _DEFAULT_MAX_DIM == 768


# ---------------------------------------------------------------------------
# 3. _compress_image actual resize behaviour
# ---------------------------------------------------------------------------

class TestCompressImage:
    def test_front_photo_capped_at_768(self, tmp_path):
        from app.extractor import _compress_image
        src = _make_jpg(tmp_path / "front.jpg", 1500, 2000)
        data, _ = _compress_image(src, max_dim=768)
        w, h = _decoded_size(data)
        assert max(w, h) <= 768, f"front should be ≤768px, got {w}×{h}"
        assert max(w, h) >= 760, f"front should use full 768px budget, got {w}×{h}"

    def test_label_photo_capped_at_1024(self, tmp_path):
        from app.extractor import _compress_image
        src = _make_jpg(tmp_path / "brand.jpg", 3024, 3024)
        data, _ = _compress_image(src, max_dim=1024)
        w, h = _decoded_size(data)
        assert max(w, h) <= 1024
        assert max(w, h) >= 1020

    def test_small_image_not_upscaled(self, tmp_path):
        from app.extractor import _compress_image
        src = _make_jpg(tmp_path / "tiny.jpg", 400, 300)
        data, _ = _compress_image(src, max_dim=1024)
        w, h = _decoded_size(data)
        assert w == 400 and h == 300, "small images must not be upscaled"

    def test_default_falls_back_to_768(self, tmp_path):
        from app.extractor import _compress_image
        src = _make_jpg(tmp_path / "unknown.jpg", 2000, 2000)
        data, _ = _compress_image(src)  # no max_dim arg
        w, h = _decoded_size(data)
        assert max(w, h) <= 768

    def test_landscape_aspect_ratio_preserved(self, tmp_path):
        from app.extractor import _compress_image
        src = _make_jpg(tmp_path / "wide.jpg", 2000, 1000)
        data, _ = _compress_image(src, max_dim=768)
        w, h = _decoded_size(data)
        assert w > h, "landscape orientation must be preserved"
        assert abs(w / h - 2.0) < 0.05, "aspect ratio should be ~2:1"


# ---------------------------------------------------------------------------
# 4. _load_photos — correct max_dim passed per role
# ---------------------------------------------------------------------------

class TestLoadPhotos:
    """Verifies _load_photos passes the right max_dim for each photo role.

    OCR roles (brand, model_size, material) now go through _compress_with_autocrop;
    non-OCR roles (front) go through _compress_image.
    """

    def test_front_gets_768(self, tmp_path):
        _make_jpg(tmp_path / "front.jpg", 1500, 2000)
        _make_jpg(tmp_path / "brand.jpg", 3024, 3024)
        _make_jpg(tmp_path / "model_size.jpg", 3024, 3024)
        _make_jpg(tmp_path / "material.jpg", 3024, 3024)

        from app.extractor import (
            _compress_image as real_compress,
            _compress_with_autocrop as real_autocrop,
        )
        calls_compress = []
        calls_autocrop = []

        def spy_compress(path, max_dim=None):
            calls_compress.append((Path(path).stem, max_dim))
            return real_compress(path, max_dim)

        def spy_autocrop(path, max_dim):
            calls_autocrop.append((Path(path).stem, max_dim))
            return real_autocrop(path, max_dim)

        with patch("app.extractor._compress_image", side_effect=spy_compress), \
             patch("app.extractor._compress_with_autocrop", side_effect=spy_autocrop):
            from app.extractor import _load_photos
            with patch("app.config.CORE_PHOTOS", ["front", "brand", "model_size", "material"]):
                _load_photos(tmp_path)

        dim_compress = dict(calls_compress)
        dim_autocrop = dict(calls_autocrop)
        assert dim_compress.get("front") == 768, \
            f"front should use 768 via _compress_image, got {dim_compress.get('front')}"
        assert dim_autocrop.get("brand") == 1024, \
            f"brand should use 1024 via _compress_with_autocrop, got {dim_autocrop.get('brand')}"
        assert dim_autocrop.get("model_size") == 1024
        assert dim_autocrop.get("material") == 1024

    def test_back_not_loaded_when_core_photos_excludes_it(self, tmp_path):
        """Even if a back.jpg file exists, it must not be loaded."""
        _make_jpg(tmp_path / "front.jpg", 1500, 2000)
        _make_jpg(tmp_path / "back.jpg", 1500, 2000)

        loaded_names = []
        from app.extractor import (
            _compress_image as real_compress,
            _compress_with_autocrop as real_autocrop,
        )

        def spy_compress(path, max_dim=None):
            loaded_names.append(Path(path).stem)
            return real_compress(path, max_dim)

        def spy_autocrop(path, max_dim):
            loaded_names.append(Path(path).stem)
            return real_autocrop(path, max_dim)

        with patch("app.extractor._compress_image", side_effect=spy_compress), \
             patch("app.extractor._compress_with_autocrop", side_effect=spy_autocrop):
            from app.extractor import _load_photos
            with patch("app.config.CORE_PHOTOS", ["front", "brand", "model_size", "material"]):
                _load_photos(tmp_path)

        assert "back" not in loaded_names, "back.jpg must not be loaded when excluded from CORE_PHOTOS"


# ---------------------------------------------------------------------------
# 5. Re-read functions always use 1024px
# ---------------------------------------------------------------------------

class TestRereadDimensions:
    """Brand and material re-reads are OCR-critical — must always use 1024px.

    Both now go through _compress_with_autocrop (which also does the autocrop step).
    """

    def test_reread_brand_uses_1024(self, tmp_path):
        _make_jpg(tmp_path / "brand.jpg", 3024, 3024)

        captured = {}
        from app.extractor import _compress_with_autocrop as real_cwa

        def spy(path, max_dim):
            captured["max_dim"] = max_dim
            return real_cwa(path, max_dim)

        with patch("app.extractor._compress_with_autocrop", side_effect=spy), \
             patch("app.extractor.anthropic") as mock_anthropic:
            mock_client = mock_anthropic.Anthropic.return_value
            mock_client.messages.create.return_value.content = [
                type("obj", (), {"text": '{"brand": "Barbour", "collection_keywords": []}'})()
            ]
            from app.extractor import _reread_brand_photo
            _reread_brand_photo(tmp_path, "claude-haiku-4-5-20251001")

        assert captured.get("max_dim") == 1024, \
            f"_reread_brand_photo must use max_dim=1024, got {captured.get('max_dim')}"

    def test_reread_material_uses_1024(self, tmp_path):
        _make_jpg(tmp_path / "material.jpg", 3024, 3024)

        captured = {}
        from app.extractor import _compress_with_autocrop as real_cwa

        def spy(path, max_dim):
            captured["max_dim"] = max_dim
            return real_cwa(path, max_dim)

        with patch("app.extractor._compress_with_autocrop", side_effect=spy), \
             patch("app.extractor.anthropic") as mock_anthropic:
            mock_client = mock_anthropic.Anthropic.return_value
            mock_client.messages.create.return_value.content = [
                type("obj", (), {"text": '{"fabric_mill": null}'})()
            ]
            from app.extractor import _reread_material_photo
            _reread_material_photo(tmp_path, "claude-haiku-4-5-20251001")

        assert captured.get("max_dim") == 1024, \
            f"_reread_material_photo must use max_dim=1024, got {captured.get('max_dim')}"


# ---------------------------------------------------------------------------
# 6. Brand correction pipeline
# ---------------------------------------------------------------------------

class TestBrandCorrections:
    def test_exact_match_suitsupply(self):
        from app.extractor import _apply_brand_corrections
        assert _apply_brand_corrections("buttsupply") == "Suitsupply"
        assert _apply_brand_corrections("Burts Supply") == "Suitsupply"

    def test_exact_match_levis(self):
        from app.extractor import _apply_brand_corrections
        assert _apply_brand_corrections("levis") == "Levi's"
        assert _apply_brand_corrections("levi strauss") == "Levi's"

    def test_fuzzy_catches_ocr_typo_barbour(self):
        from app.extractor import _apply_brand_corrections
        result = _apply_brand_corrections("Barbur")
        assert result == "Barbour", f"Expected 'Barbour', got '{result}'"

    def test_fuzzy_catches_moncler_misread(self):
        from app.extractor import _apply_brand_corrections
        result = _apply_brand_corrections("Monclair")
        assert result == "Moncler", f"Expected 'Moncler', got '{result}'"

    def test_correct_brand_unchanged(self):
        from app.extractor import _apply_brand_corrections
        assert _apply_brand_corrections("Barbour") == "Barbour"
        assert _apply_brand_corrections("Hugo Boss") == "Hugo Boss"
        assert _apply_brand_corrections("Ermenegildo Zegna") == "Ermenegildo Zegna"

    def test_none_passthrough(self):
        from app.extractor import _apply_brand_corrections
        assert _apply_brand_corrections(None) is None

    def test_empty_string_passthrough(self):
        from app.extractor import _apply_brand_corrections
        assert _apply_brand_corrections("") == ""

    def test_unknown_brand_not_corrupted(self):
        """A brand not in the list should pass through unchanged (cutoff guards against false positives)."""
        from app.extractor import _apply_brand_corrections
        result = _apply_brand_corrections("Zzzzyx Unknown Brand Co")
        assert result == "Zzzzyx Unknown Brand Co"


# ---------------------------------------------------------------------------
# 7. Prompt builder
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_no_hints_returns_base_prompt(self):
        from app.extractor import _build_prompt_with_hints, _EXTRACT_PROMPT
        result = _build_prompt_with_hints({})
        assert result == _EXTRACT_PROMPT

    def test_brand_hint_injected(self):
        from app.extractor import _build_prompt_with_hints
        result = _build_prompt_with_hints({"brand": "Barbour"})
        assert "Barbour" in result
        assert "USER-PROVIDED HINTS" in result

    def test_hint_section_precedes_main_prompt(self):
        from app.extractor import _build_prompt_with_hints, _EXTRACT_PROMPT
        result = _build_prompt_with_hints({"brand": "Test"})
        hint_pos = result.index("USER-PROVIDED HINTS")
        prompt_pos = result.index(_EXTRACT_PROMPT[:50])
        assert hint_pos < prompt_pos


# ---------------------------------------------------------------------------
# 8. _resize_photo — upload-time JPEG compression (web.py)
# ---------------------------------------------------------------------------

def _make_jpg_with_exif(path: Path, w: int, h: int) -> Path:
    """Write a JPEG with a minimal EXIF APP1 marker so we can verify stripping."""
    img = Image.new("RGB", (w, h), color=(200, 100, 50))
    buf = io.BytesIO()
    # Write a fake EXIF blob — a minimal APP1 header (0xFFE1) with "Exif\0\0" magic
    exif_payload = b"Exif\x00\x00" + b"\x00" * 20   # minimal TIFF header stub
    app1 = struct.pack(">HH", 0xFFE1, len(exif_payload) + 2) + exif_payload
    # Save baseline JPEG then inject the APP1 segment after the SOI marker
    img.save(buf, "JPEG", quality=95)
    raw = buf.getvalue()
    # SOI = first 2 bytes (FF D8). Insert APP1 right after.
    jpeg_with_exif = raw[:2] + app1 + raw[2:]
    path.write_bytes(jpeg_with_exif)
    return path


def _jpeg_has_exif(path: Path) -> bool:
    """Return True if the JPEG file contains an APP1/EXIF segment."""
    data = path.read_bytes()
    # Scan for FF E1 marker
    i = 2  # skip SOI
    while i < len(data) - 3:
        if data[i] == 0xFF:
            marker = data[i + 1]
            seg_len = struct.unpack(">H", data[i + 2: i + 4])[0]
            if marker == 0xE1:  # APP1
                payload = data[i + 4: i + 2 + seg_len]
                if payload[:6] == b"Exif\x00\x00":
                    return True
            i += 2 + seg_len
        else:
            i += 1
    return False


class TestResizePhoto:
    """Tests for web.py _resize_photo()."""

    def test_large_image_resized_below_max_dim(self, tmp_path):
        from app.web import _resize_photo
        src = _make_jpg(tmp_path / "big.jpg", 4000, 3000)
        result = _resize_photo(src)
        img = Image.open(result)
        assert max(img.size) <= 2048, f"Expected ≤2048px, got {img.size}"

    def test_small_image_not_upscaled(self, tmp_path):
        from app.web import _resize_photo
        src = _make_jpg(tmp_path / "small.jpg", 800, 600)
        result = _resize_photo(src)
        img = Image.open(result)
        assert img.size == (800, 600), "Small image must not be upscaled"

    def test_aspect_ratio_preserved(self, tmp_path):
        from app.web import _resize_photo
        src = _make_jpg(tmp_path / "wide.jpg", 4000, 1000)  # 4:1 landscape
        result = _resize_photo(src)
        w, h = Image.open(result).size
        assert abs(w / h - 4.0) < 0.05, f"Aspect ratio should be ~4:1, got {w}/{h}"

    def test_file_size_reduced_for_large_image(self, tmp_path):
        from app.web import _resize_photo
        # Write a 4000×3000 high-quality JPEG — will be a few MB
        img = Image.new("RGB", (4000, 3000), color=(128, 64, 32))
        src = tmp_path / "large.jpg"
        img.save(str(src), "JPEG", quality=95)
        orig_size = src.stat().st_size
        result = _resize_photo(src)
        assert result.stat().st_size < orig_size, "Resized file should be smaller"

    def test_exif_stripped(self, tmp_path):
        from app.web import _resize_photo
        src = _make_jpg_with_exif(tmp_path / "exif.jpg", 3000, 2000)
        assert _jpeg_has_exif(src), "Test setup: source should have EXIF"
        result = _resize_photo(src)
        assert not _jpeg_has_exif(result), "EXIF must be stripped after _resize_photo"

    def test_output_is_jpeg(self, tmp_path):
        from app.web import _resize_photo
        src = _make_jpg(tmp_path / "photo.png", 800, 600)
        src = src.with_suffix(".png")
        Image.new("RGB", (800, 600)).save(str(src), "PNG")
        result = _resize_photo(src)
        assert result.suffix == ".jpg", "Output must be .jpg"
        # Verify it's a valid JPEG
        img = Image.open(result)
        assert img.format == "JPEG"

    def test_output_smaller_than_high_quality(self, tmp_path):
        """quality=85 output should be smaller than quality=99 for the same image."""
        img = Image.new("RGB", (2000, 2000), color=(100, 150, 200))
        high_q = tmp_path / "hq.jpg"
        img.save(str(high_q), "JPEG", quality=99)

        from app.web import _resize_photo
        src = tmp_path / "src.jpg"
        img.save(str(src), "JPEG", quality=99)
        result = _resize_photo(src)
        assert result.stat().st_size < high_q.stat().st_size, \
            "quality=85 output should be smaller than quality=99 baseline"


# ---------------------------------------------------------------------------
# 9. draft_creator vinted_guard — oversized photo compression
# ---------------------------------------------------------------------------

class TestVintedGuard:
    """Tests for draft_creator.py _upload_photos() fallback compression."""

    @staticmethod
    def _make_noisy_jpg(path: Path, w: int = 4000, h: int = 3000) -> Path:
        """Create a JPEG with pseudo-random pixels to defeat JPEG compression."""
        img = Image.new("RGB", (w, h))
        pixels = [((i * 37 + j * 13) % 256, (i * 11) % 256, (j * 17) % 256)
                  for i in range(h) for j in range(w)]
        img.putdata(pixels)
        img.save(str(path), "JPEG", quality=98)
        return path

    def test_oversized_photo_compressed(self, tmp_path, capsys):
        """A photo over 8MB is compressed to a temp file; temp file is ≤8MB."""
        from unittest.mock import MagicMock
        from app.draft_creator import _upload_photos

        big = self._make_noisy_jpg(tmp_path / "front.jpg")
        if big.stat().st_size <= 8 * 1024 * 1024:
            pytest.skip("Could not generate a file large enough for this test")

        # Capture file sizes DURING set_input_files (before cleanup)
        captured_sizes: list[int] = []
        captured_paths: list[str] = []

        def capture(selector, paths):
            captured_paths.extend(paths)
            captured_sizes.extend(Path(p).stat().st_size for p in paths)

        mock_page = MagicMock()
        mock_page.set_input_files.side_effect = capture
        _upload_photos(mock_page, tmp_path)

        out = capsys.readouterr().out
        assert "[vinted_guard]" in out, "Should log [vinted_guard] when compressing"
        assert len(captured_paths) == 1
        assert Path(captured_paths[0]) != big, "Should upload a temp copy, not the original"
        assert captured_sizes[0] <= 8 * 1024 * 1024, \
            f"Compressed upload should be ≤8MB, got {captured_sizes[0]}"

    def test_normal_photo_not_recompressed(self, tmp_path):
        """A photo under 8MB is passed through as-is."""
        from unittest.mock import MagicMock
        from app.draft_creator import _upload_photos

        _make_jpg(tmp_path / "front.jpg", 1200, 900)

        captured_paths: list[str] = []
        mock_page = MagicMock()
        mock_page.set_input_files.side_effect = lambda sel, paths: captured_paths.extend(paths)
        _upload_photos(mock_page, tmp_path)

        assert len(captured_paths) == 1
        assert Path(captured_paths[0]) == tmp_path / "front.jpg"

    def test_compressed_exif_stripped(self, tmp_path, capsys):
        """EXIF must be absent from the compressed upload temp file."""
        from unittest.mock import MagicMock
        from app.draft_creator import _upload_photos

        # Use a real noisy photo with injected EXIF, large enough to trigger guard
        big_exif = _make_jpg_with_exif(
            tmp_path / "front.jpg", 4000, 3000
        )
        # Overwrite with noisy pixels + EXIF so it's big AND has EXIF
        noisy = self._make_noisy_jpg(tmp_path / "front_noisy.jpg")
        noisy_bytes = noisy.read_bytes()
        # Inject EXIF into the noisy JPEG
        exif_payload = b"Exif\x00\x00" + b"\x00" * 20
        app1 = struct.pack(">HH", 0xFFE1, len(exif_payload) + 2) + exif_payload
        big_exif.write_bytes(noisy_bytes[:2] + app1 + noisy_bytes[2:])

        if big_exif.stat().st_size <= 8 * 1024 * 1024:
            pytest.skip("Could not generate large enough file for EXIF strip test")

        captured_data: list[bytes] = []

        def capture(selector, paths):
            for p in paths:
                pp = Path(p)
                if pp.exists():
                    captured_data.append(pp.read_bytes())

        mock_page = MagicMock()
        mock_page.set_input_files.side_effect = capture
        _upload_photos(mock_page, tmp_path)

        assert captured_data, "No file data was captured"
        # Write captured bytes to a temp file and check for EXIF
        check = tmp_path / "check.jpg"
        check.write_bytes(captured_data[0])
        assert not _jpeg_has_exif(check), \
            "EXIF must be stripped from the vinted_guard compressed file"
