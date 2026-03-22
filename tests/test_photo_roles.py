"""
Unit tests for app/services/photo_roles.py.

Uses synthetic Pillow images to avoid filesystem dependencies.
"""
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


# ── Image factories ───────────────────────────────────────────────────────────

def _make_image(path: Path, w: int, h: int, bg: tuple, text_band: bool = False):
    """Create a test image and save it."""
    img = Image.new("RGB", (w, h), bg)
    if text_band:
        # Simulate a text label: add a band of alternating black/white pixels
        draw = ImageDraw.Draw(img)
        for x in range(0, w, 4):
            draw.line([(x, h // 3), (x, 2 * h // 3)], fill=(0, 0, 0), width=2)
    img.save(path, "JPEG")
    return path


def _garment_photo(path: Path, portrait: bool = True):
    """Tall portrait, colourful garment-like image."""
    w, h = (400, 600) if portrait else (600, 400)
    return _make_image(path, w, h, bg=(80, 100, 140))  # blue-ish garment


def _label_photo(path: Path):
    """Landscape, bright background with text band = label-like image."""
    return _make_image(path, 500, 350, bg=(230, 230, 230), text_band=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestImageStats:

    def test_aspect_portrait(self, tmp_path):
        from app.services.photo_roles import _image_stats
        p = _garment_photo(tmp_path / "g.jpg", portrait=True)
        st = _image_stats(p)
        assert st["aspect"] < 1.0, "portrait should have aspect < 1"

    def test_aspect_landscape(self, tmp_path):
        from app.services.photo_roles import _image_stats
        p = _label_photo(tmp_path / "l.jpg")
        st = _image_stats(p)
        assert st["aspect"] > 1.0, "landscape label should have aspect > 1"

    def test_bright_label_higher_brightness(self, tmp_path):
        from app.services.photo_roles import _image_stats
        garment = _garment_photo(tmp_path / "g.jpg")
        label = _label_photo(tmp_path / "l.jpg")
        g_st = _image_stats(garment)
        l_st = _image_stats(label)
        assert l_st["brightness"] > g_st["brightness"]

    def test_label_has_higher_edge_density(self, tmp_path):
        from app.services.photo_roles import _image_stats
        garment = _garment_photo(tmp_path / "g.jpg")
        label = _label_photo(tmp_path / "l.jpg")
        g_st = _image_stats(garment)
        l_st = _image_stats(label)
        assert l_st["edge_density"] > g_st["edge_density"]


class TestScoreRoles:

    def test_garment_scores_higher_for_front(self, tmp_path):
        from app.services.photo_roles import _image_stats, _score_roles
        p = _garment_photo(tmp_path / "g.jpg")
        st = _image_stats(p)
        scores = _score_roles(st, order=0)
        # With order prior at index 0, front should score highest
        assert scores["front"] >= scores["brand"]
        assert scores["front"] >= scores["material"]

    def test_label_scores_higher_for_brand_at_index_1(self, tmp_path):
        from app.services.photo_roles import _image_stats, _score_roles
        p = _label_photo(tmp_path / "l.jpg")
        st = _image_stats(p)
        scores = _score_roles(st, order=1)
        assert scores["brand"] >= scores["front"]

    def test_order_prior_dominates_for_garment_in_position_0(self, tmp_path):
        from app.services.photo_roles import _image_stats, _score_roles
        p = _garment_photo(tmp_path / "g.jpg")
        st = _image_stats(p)
        scores_0 = _score_roles(st, order=0)
        scores_3 = _score_roles(st, order=3)
        # Front score higher when order=0 vs order=3
        assert scores_0["front"] > scores_3["front"]

    def test_back_score_lower_than_front_same_photo(self, tmp_path):
        from app.services.photo_roles import _image_stats, _score_roles
        p = _garment_photo(tmp_path / "g.jpg")
        st = _image_stats(p)
        scores = _score_roles(st, order=99)  # no order prior
        assert scores["front"] >= scores["back"]


class TestAssignRoles:

    def test_single_photo_gets_front(self, tmp_path):
        from app.services.photo_roles import assign_roles
        p = _garment_photo(tmp_path / "g.jpg")
        role_map, confidence = assign_roles([p])
        assert "front" in role_map
        assert role_map["front"] == p

    def test_ordered_upload_assigns_correctly(self, tmp_path):
        """Well-ordered upload: front, brand, model_size, material should map correctly."""
        from app.services.photo_roles import assign_roles
        paths = [
            _garment_photo(tmp_path / "p0.jpg"),
            _label_photo(tmp_path / "p1.jpg"),
            _label_photo(tmp_path / "p2.jpg"),
            _label_photo(tmp_path / "p3.jpg"),
        ]
        role_map, confidence = assign_roles(paths)
        assert role_map["front"] == paths[0]
        assert role_map["brand"] == paths[1]

    def test_extra_photos_get_extra_names(self, tmp_path):
        from app.services.photo_roles import assign_roles, PIPELINE_ROLES
        # 6 photos — first 5 fill pipeline roles, 6th becomes extra
        paths = [
            _garment_photo(tmp_path / f"p{i}.jpg") for i in range(6)
        ]
        role_map, _ = assign_roles(paths)
        extra_keys = [k for k in role_map if k.startswith("extra_")]
        assert len(extra_keys) >= 1

    def test_empty_input(self):
        from app.services.photo_roles import assign_roles
        role_map, confidence = assign_roles([])
        assert role_map == {}
        assert confidence == {}

    def test_no_duplicate_assignments(self, tmp_path):
        from app.services.photo_roles import assign_roles
        paths = [
            _garment_photo(tmp_path / f"p{i}.jpg") for i in range(4)
        ]
        role_map, _ = assign_roles(paths)
        assigned_paths = [v for v in role_map.values() if v is not None]
        # No path should be assigned to two roles
        assert len(assigned_paths) == len(set(assigned_paths))

    def test_confidence_between_0_and_1(self, tmp_path):
        from app.services.photo_roles import assign_roles
        paths = [_garment_photo(tmp_path / f"p{i}.jpg") for i in range(3)]
        _, confidence = assign_roles(paths)
        for role, score in confidence.items():
            assert 0.0 <= score <= 1.0, f"{role} confidence {score} out of range"


class TestLowConfidenceRoles:

    def test_returns_empty_when_all_confident(self):
        from app.services.photo_roles import low_confidence_roles
        result = low_confidence_roles({"front": 0.9, "brand": 0.8, "model_size": 0.7})
        assert result == []

    def test_flags_low_confidence_role(self):
        from app.services.photo_roles import low_confidence_roles, LOW_CONFIDENCE_THRESHOLD
        result = low_confidence_roles({"front": 0.9, "brand": LOW_CONFIDENCE_THRESHOLD - 0.01})
        assert "brand" in result

    def test_does_not_flag_extras(self):
        from app.services.photo_roles import low_confidence_roles
        # extra_ roles should never be flagged even at low confidence
        result = low_confidence_roles({"extra_01": 0.1, "front": 0.9})
        assert "extra_01" not in result
