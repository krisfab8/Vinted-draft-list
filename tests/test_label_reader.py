from copy import deepcopy
from unittest.mock import patch
import shutil
import pytest
from PIL import Image, ImageDraw, ImageFont
from app.services import label_reader, label_safety
from app import extractor

READING = dict(
    status="readable",
    pairs=[("main", 92.0, "Polyester"), ("main", 8.0, "Spandex")],
    text="92% POLYESTER\n8% SPANDEX",
)


@pytest.mark.parametrize(
    "materials",
    [
        ["88% Nylon", "12% Spandex"],
        ["8% Polyester", "92% Spandex"],
        ["Shell: 92% Polyester", "Shell: 8% Spandex", "Lining: 100% Polyester"],
        ["92% Polyester"],
    ],
)
def test_wrong_numbers_missing_fibres_and_invented_sections_withheld(materials):
    item = dict(materials=materials, material_confidence="high")
    label_reader.check(item, READING)
    label_safety.suppress_uncertain(item)
    assert item["materials"] == [] and item["material_reading_candidate"] == materials
    assert "materials" in item["low_confidence_fields"]


def test_verified_fibres_can_skip_paid_material_recheck():
    item = dict(
        materials=["92% Polyester", "8% Elastane"],
        material_confidence="medium",
        low_confidence_fields=["materials"],
    )
    label_reader.check(item, READING)
    assert item["material_confidence"] == "high"
    assert not extractor._should_reread_material(item)


def test_unreadable_independent_label_does_not_accept_self_certified_quote():
    item = dict(materials=["100% Polyester"], material_confidence="high")
    label_reader.check(item, dict(status="unreadable", pairs=[]))
    label_safety.suppress_uncertain(item)
    assert item["materials"] == []


def test_quoted_single_composition_cannot_prove_both_shell_and_lining():
    assert not label_safety.composition_supported(
        ["Shell: 100% Polyester", "Lining: 100% Polyester"], "100% POLYESTER"
    )
    assert not label_safety.composition_supported(
        ["92% Polyester"], "92% POLYESTER\n8% SPANDEX"
    )
    assert label_safety.composition_supported(
        ["92% Polyester", "8% Elastane"], "92% POLYESTER\n8% SPANDEX"
    )


def test_initial_high_confidence_conflict_gets_one_recheck_and_final_independent_gate():
    item = dict(
        brand="Peter Millar",
        brand_confidence="high",
        item_type="shirt",
        materials=["88% Nylon", "12% Spandex"],
        material_confidence="high",
        confidence=1,
        low_confidence_fields=[],
        fabric_mill=None,
    )
    with patch.object(extractor, "_load_photos", return_value=([], {})), patch.object(
        extractor, "_extract_claude", return_value=(deepcopy(item), {})
    ), patch.object(extractor, "VISION_PROVIDER", "claude-haiku"), patch.object(
        label_reader, "read_folder", return_value=READING
    ), patch.object(
        extractor,
        "_reread_material_photo",
        return_value=dict(
            materials=["88% Nylon", "12% Spandex"],
            composition_label_text="88% NYLON\n12% SPANDEX",
        ),
    ) as retry, patch(
        "app.services.measurements.analyze", return_value=[]
    ):
        result, _ = extractor.extract("/tmp/no-paid-material-test")
    assert retry.call_count == 1 and result["materials"] == []
    assert result["material_verification"]["pairs"] == READING["pairs"]


def test_local_reader_rectifies_and_reads_rotated_composition_without_model(tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    pytest.importorskip("cv2")
    tag = Image.new("RGB", (460, 240), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    draw = ImageDraw.Draw(tag)
    draw.text((35, 65), "92% POLYESTER", font=font, fill="black")
    draw.text((35, 120), "8% SPANDEX", font=font, fill="black")
    tag = tag.rotate(32, expand=True, fillcolor=(20, 80, 120))
    photo = Image.new("RGB", (1000, 800), (20, 80, 120))
    photo.paste(tag, (160, 180))
    path = tmp_path / "material.png"
    photo.save(path)
    prepared, reading = label_reader.prepare(path)
    assert reading["status"] == "readable" and label_reader.matches(
        ["92% Polyester", "8% Spandex"], reading
    )
    assert reading["preparation"]["rectified"] and prepared.width < photo.width
    assert Image.open(path).size == (1000, 800)


def test_writer_cannot_reintroduce_unverified_percentages():
    from app.listing_writer import finalize_listing

    item = dict(
        brand="Peter Millar",
        item_type="shirt",
        tagged_size="S",
        normalized_size="S",
        colour="Multi",
        gender="men's",
        materials=[],
        material_confidence="medium",
        material_reading_candidate=["88% Nylon", "12% Spandex"],
        material_verification=READING,
        low_confidence_fields=["materials"],
        brand_confidence="high",
        condition_summary="Very good used condition",
    )
    proposed = dict(
        item,
        title="Peter Millar Nylon Shirt Mens S",
        description="88% Nylon, 12% Spandex shirt.",
        materials=["88% Nylon", "12% Spandex"],
        price_gbp=25,
        category="Men > Shirts",
    )
    final = finalize_listing(proposed, item)
    assert (
        final["materials"] == []
        and "88%" not in final["description"]
        and "Spandex" not in final["description"]
    )
    assert final["material_verification"] == READING


@pytest.mark.parametrize(
    "materials",
    [
        [],
        ["62% Polyester", "26% Polyester", "8% Spandex"],
        ["88% Nylon", "12% Spandex"],
    ],
)
def test_agreeing_literal_reads_recover_materials_instead_of_blank(materials):
    item = dict(
        materials=materials,
        material_confidence="low",
        low_confidence_fields=["materials"],
    )
    reading = dict(READING, consensus=True)
    label_reader.check(item, reading)
    label_safety.suppress_uncertain(item)
    assert item["materials"] == ["92% Polyester", "8% Spandex"]
    assert (
        item["material_confidence"] == "high"
        and "materials" not in item["low_confidence_fields"]
    )
    assert item["material_source"] == "label_ocr_consensus"
    assert not extractor._should_reread_material(item)


def test_single_local_read_cannot_override_a_conflicting_model():
    item = dict(materials=["88% Nylon", "12% Spandex"], material_confidence="high")
    label_reader.check(item, dict(READING, consensus=False))
    label_safety.suppress_uncertain(item)
    assert not item["materials"]


def test_moderate_local_read_needs_matching_ai_composition():
    reading = dict(
        status="unreadable",
        pairs=[],
        attempts=[dict(candidate_pairs=READING["pairs"], min_confidence=0.92)],
    )
    wrong = dict(materials=["88% Nylon", "12% Spandex"], material_confidence="high")
    label_reader.check(wrong, reading)
    assert wrong["material_confidence"] == "medium"
    corrected = dict(
        materials=["92% Polyester", "8% Spandex"], material_confidence="medium"
    )
    label_reader.check(corrected, reading)
    assert corrected["material_confidence"] == "high"


def test_conflicting_ocr_never_recovers_facts_even_when_one_view_matches_ai():
    reading = dict(
        READING,
        status="conflicting_ocr",
        consensus=True,
        attempts=[dict(candidate_pairs=READING["pairs"], min_confidence=0.99)],
    )
    item = dict(materials=["92% Polyester", "8% Spandex"], material_confidence="high")
    label_reader.check(item, reading)
    label_safety.suppress_uncertain(item)
    assert item["materials"] == []


def test_focused_recheck_sends_only_label_crop_and_original(tmp_path):
    import json
    from types import SimpleNamespace as NS

    Image.new("RGB", (100, 150), "white").save(tmp_path / "material.jpg")
    response = NS(
        content=[
            NS(
                text=json.dumps(
                    dict(
                        materials=["92% Polyester", "8% Spandex"],
                        composition_label_text="92% POLYESTER\n8% SPANDEX",
                    )
                )
            )
        ],
        stop_reason="end_turn",
        usage=NS(input_tokens=100, output_tokens=40),
    )
    with patch.object(extractor.anthropic, "Anthropic") as client:
        client.return_value.messages.create.return_value = response
        result = extractor._reread_composition_crop(tmp_path, "test-model")
        call = client.return_value.messages.create.call_args.kwargs
    assert result["materials"] == ["92% Polyester", "8% Spandex"]
    content = call["messages"][0]["content"]
    assert sum(v["type"] == "image" for v in content) == 2
    assert "92%" not in content[-1]["text"] and "brand blend" in content[-1]["text"]


def test_consensus_flows_through_full_extraction_without_paid_material_retry(tmp_path):
    item = dict(
        brand="Peter Millar",
        brand_confidence="high",
        item_type="polo shirt",
        materials=["62% Polyester", "26% Polyester", "8% Spandex"],
        material_confidence="high",
        confidence=0.78,
        low_confidence_fields=[],
        fabric_mill=None,
    )
    with patch.object(extractor, "_load_photos", return_value=([], {})), patch.object(
        extractor, "_extract_claude", return_value=(deepcopy(item), {})
    ), patch.object(extractor, "VISION_PROVIDER", "claude-haiku"), patch.object(
        label_reader, "read_folder", return_value=dict(READING, consensus=True)
    ), patch.object(
        extractor, "_reread_composition_crop"
    ) as focused, patch.object(
        extractor, "_reread_material_photo"
    ) as full, patch(
        "app.services.measurements.analyze", return_value=[]
    ):
        result, _ = extractor.extract(tmp_path)
    assert result["materials"] == ["92% Polyester", "8% Spandex"]
    assert result["material_model_candidate"] == item["materials"]
    focused.assert_not_called()
    full.assert_not_called()
