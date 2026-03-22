"""
Unit tests for app/services/condition.py

Pure-function tests only — no I/O, no AI, no Flask.
"""
import pytest
from app.services import condition


# ── canonical_level ───────────────────────────────────────────────────────────

class TestCanonicalLevel:

    def test_very_good_from_full_string(self):
        assert condition.canonical_level("Very good used condition — clean.") == "Very good"

    def test_excellent(self):
        assert condition.canonical_level("Excellent used condition — barely worn.") == "Excellent"

    def test_good(self):
        assert condition.canonical_level("Good used condition — normal wear.") == "Good"

    def test_satisfactory(self):
        assert condition.canonical_level("Satisfactory used condition — visible use.") == "Satisfactory"

    def test_fair_maps_to_satisfactory(self):
        assert condition.canonical_level("Fair condition.") == "Satisfactory"

    def test_new_with_tags(self):
        assert condition.canonical_level("New with tags — original labels attached.") == "New with tags"

    def test_new_without_tags(self):
        assert condition.canonical_level("New without tags — unworn, no original tags.") == "New without tags"

    def test_very_good_not_confused_with_good(self):
        # "very good" contains "good" but should match "very good" first
        assert condition.canonical_level("Very good condition") == "Very good"

    def test_fallback_unknown_string(self):
        assert condition.canonical_level("some random text") == "Very good"

    def test_fallback_none(self):
        assert condition.canonical_level(None) == "Very good"

    def test_fallback_empty(self):
        assert condition.canonical_level("") == "Very good"

    def test_case_insensitive(self):
        assert condition.canonical_level("VERY GOOD USED CONDITION") == "Very good"


# ── auto_downgrade ────────────────────────────────────────────────────────────

class TestAutoDowngrade:

    def test_no_flaws_no_downgrade(self):
        assert condition.auto_downgrade("Very good", None) == "Very good"

    def test_empty_flaws_no_downgrade(self):
        assert condition.auto_downgrade("Very good", "") == "Very good"

    def test_moderate_stain_downgrades_very_good_to_good(self):
        assert condition.auto_downgrade("Very good", "Small stain on left lapel") == "Good"

    def test_moderate_mark_downgrades_very_good_to_good(self):
        assert condition.auto_downgrade("Very good", "Light mark on sleeve") == "Good"

    def test_moderate_scuff_downgrades_very_good_to_good(self):
        assert condition.auto_downgrade("Very good", "Scuff on toe cap") == "Good"

    def test_moderate_pilling_downgrades_very_good_to_good(self):
        assert condition.auto_downgrade("Very good", "Some pilling on elbows") == "Good"

    def test_moderate_excellent_downgrades_to_good(self):
        assert condition.auto_downgrade("Excellent", "Slight fading on collar") == "Good"

    def test_moderate_does_not_downgrade_good(self):
        assert condition.auto_downgrade("Good", "Light mark on back") == "Good"

    def test_moderate_does_not_downgrade_satisfactory(self):
        assert condition.auto_downgrade("Satisfactory", "Some wear") == "Satisfactory"

    def test_severe_hole_downgrades_very_good_to_satisfactory(self):
        assert condition.auto_downgrade("Very good", "Small hole in left elbow") == "Satisfactory"

    def test_severe_tear_downgrades_good_to_satisfactory(self):
        assert condition.auto_downgrade("Good", "Tear on back seam") == "Satisfactory"

    def test_severe_rip_downgrades_excellent_to_satisfactory(self):
        assert condition.auto_downgrade("Excellent", "Rip at pocket") == "Satisfactory"

    def test_severe_broken_zip_to_satisfactory(self):
        assert condition.auto_downgrade("Very good", "Broken zip — needs repair") == "Satisfactory"

    def test_new_with_tags_never_downgraded_moderate(self):
        assert condition.auto_downgrade("New with tags", "Stain on sleeve") == "New with tags"

    def test_new_without_tags_never_downgraded_severe(self):
        assert condition.auto_downgrade("New without tags", "Hole in pocket") == "New without tags"

    def test_case_insensitive_keyword(self):
        assert condition.auto_downgrade("Very good", "STAIN on collar") == "Good"

    def test_satisfactory_stays_satisfactory_on_severe(self):
        # Already at bottom — no further downgrade
        assert condition.auto_downgrade("Satisfactory", "Hole in elbow") == "Satisfactory"


# ── default_condition_line ────────────────────────────────────────────────────

class TestDefaultConditionLine:

    def test_very_good_default(self):
        line = condition.default_condition_line("Very good")
        assert "Very good" in line
        assert "no major flaws" in line.lower()

    def test_good_default(self):
        line = condition.default_condition_line("Good")
        assert "Good" in line
        assert "wear" in line.lower()

    def test_satisfactory_default(self):
        line = condition.default_condition_line("Satisfactory")
        assert "Satisfactory" in line

    def test_excellent_default(self):
        line = condition.default_condition_line("Excellent")
        assert "Excellent" in line

    def test_new_with_tags_default(self):
        line = condition.default_condition_line("New with tags")
        assert "tags" in line.lower()

    def test_new_without_tags_default(self):
        line = condition.default_condition_line("New without tags")
        assert "unworn" in line.lower() or "without tags" in line.lower()

    def test_unknown_level_falls_back(self):
        line = condition.default_condition_line("Unknown level")
        assert line  # returns something


# ── build_condition_line ──────────────────────────────────────────────────────

class TestBuildConditionLine:

    def test_no_flaws_returns_default(self):
        line = condition.build_condition_line("Very good", None)
        assert "no major flaws" in line.lower()

    def test_empty_flaws_returns_default(self):
        line = condition.build_condition_line("Very good", "")
        assert "no major flaws" in line.lower()

    def test_with_flaws_includes_flaw_text(self):
        line = condition.build_condition_line("Good", "Small stain on left lapel")
        assert "Small stain on left lapel" in line
        assert "Good" in line

    def test_with_flaws_ends_with_period(self):
        line = condition.build_condition_line("Very good", "Mark on collar")
        assert line.endswith(".")

    def test_with_flaws_normalises_trailing_period(self):
        # flaws_note already has a trailing period — should not double up
        line = condition.build_condition_line("Good", "Stain on sleeve.")
        assert not line.endswith("..")

    def test_very_good_with_flaws(self):
        line = condition.build_condition_line("Very good", "Minor scuff on toe cap")
        assert "Very good" in line
        assert "Minor scuff" in line

    def test_satisfactory_with_flaws(self):
        line = condition.build_condition_line("Satisfactory", "Hole in elbow")
        assert "Satisfactory" in line
        assert "Hole in elbow" in line


# ── apply_condition ───────────────────────────────────────────────────────────

class TestApplyCondition:

    def test_sets_condition_line(self):
        listing = {"condition_summary": "Very good used condition — clean."}
        condition.apply_condition(listing)
        assert "condition_line" in listing
        assert listing["condition_line"]

    def test_no_flaws_very_good_default_line(self):
        listing = {"condition_summary": "Very good used condition — clean."}
        condition.apply_condition(listing)
        assert "no major flaws" in listing["condition_line"].lower()

    def test_with_flaws_included_in_line(self):
        listing = {
            "condition_summary": "Very good used condition — clean.",
            "flaws_note": "Small stain on left lapel",
        }
        condition.apply_condition(listing)
        assert "Small stain on left lapel" in listing["condition_line"]

    def test_downgrade_updates_condition_summary(self):
        listing = {
            "condition_summary": "Very good used condition — clean.",
            "flaws_note": "Hole in right elbow",
        }
        condition.apply_condition(listing)
        assert "Satisfactory" in listing["condition_summary"]

    def test_downgrade_rewrites_condition_summary_cleanly(self):
        listing = {
            "condition_summary": "Very good used condition — AI wrote this stale note.",
            "flaws_note": "Stain on collar",
        }
        condition.apply_condition(listing)
        # condition_summary should not contain the stale AI note
        assert "AI wrote this stale note" not in listing["condition_summary"]
        assert "Good" in listing["condition_summary"]

    def test_no_downgrade_preserves_condition_summary(self):
        original = "Very good used condition — clean, no issues."
        listing = {"condition_summary": original}
        condition.apply_condition(listing)
        assert listing["condition_summary"] == original

    def test_never_raises_on_empty_listing(self):
        condition.apply_condition({})  # must not raise

    def test_never_raises_on_none_values(self):
        listing = {"condition_summary": None, "flaws_note": None}
        condition.apply_condition(listing)  # must not raise

    def test_moderate_downgrade_to_good(self):
        listing = {
            "condition_summary": "Very good used condition — clean.",
            "flaws_note": "Light pilling on elbows",
        }
        condition.apply_condition(listing)
        assert "Good" in listing["condition_summary"]
        assert "Light pilling" in listing["condition_line"]

    def test_new_with_tags_not_downgraded(self):
        listing = {
            "condition_summary": "New with tags — original labels attached.",
            "flaws_note": "Stain on sleeve",
        }
        condition.apply_condition(listing)
        assert "New with tags" in listing["condition_summary"]


# ── inject_condition_line ─────────────────────────────────────────────────────

class TestInjectConditionLine:

    def _desc(self, body, *, anchor="Measurements in photos.\nFast postage.\n\nKeywords: test"):
        return f"{body}\n\n{anchor}"

    def test_appends_before_measurements(self):
        listing = {
            "condition_line": "Very good condition — no major flaws noted.",
            "description": self._desc("Barbour shirt in navy.\n\n- Mens size M\n- 100% cotton"),
        }
        condition.inject_condition_line(listing)
        desc = listing["description"]
        cond_pos = desc.index("- Very good condition")
        meas_pos = desc.index("Measurements")
        assert cond_pos < meas_pos

    def test_strips_ai_condition_line(self):
        listing = {
            "condition_line": "Very good condition — no major flaws noted.",
            "description": self._desc(
                "Barbour shirt.\n\n- Mens size M\n- Very good used condition — clean.\n- 100% cotton"
            ),
        }
        condition.inject_condition_line(listing)
        desc = listing["description"]
        # AI line stripped, only our new line remains
        assert desc.count("Very good") == 1

    def test_strips_no_damage_line(self):
        listing = {
            "condition_line": "Good used condition — normal signs of wear.",
            "description": self._desc("Blazer.\n\n- Mens 44R\n- No visible damage, no holes or stains"),
        }
        condition.inject_condition_line(listing)
        assert "No visible damage" not in listing["description"]

    def test_no_op_when_no_condition_line(self):
        original = "Blazer.\n\n- Mens 44R\n\nMeasurements in photos."
        listing = {"condition_line": "", "description": original}
        condition.inject_condition_line(listing)
        assert listing["description"] == original

    def test_appends_at_end_when_no_anchor(self):
        listing = {
            "condition_line": "Good used condition — normal wear.",
            "description": "Blazer.\n\n- Mens 44R",
        }
        condition.inject_condition_line(listing)
        assert listing["description"].endswith("- Good used condition — normal wear.")

    def test_condition_bullet_format(self):
        listing = {
            "condition_line": "Satisfactory condition — visible signs of use.",
            "description": self._desc("Jacket.\n\n- Mens M"),
        }
        condition.inject_condition_line(listing)
        assert "- Satisfactory condition — visible signs of use." in listing["description"]


# ── pipeline.py preserve_user_fields ─────────────────────────────────────────

class TestPreserveFlawsNote:

    def test_preserves_flaws_note_through_regen(self):
        from app.services.pipeline import preserve_user_fields
        existing = {"condition_summary": "Very good used condition.", "flaws_note": "Stain on collar"}
        new_listing = {"condition_summary": "Very good used condition."}
        preserve_user_fields(existing, new_listing)
        assert new_listing["flaws_note"] == "Stain on collar"

    def test_preserves_null_flaws_note(self):
        from app.services.pipeline import preserve_user_fields
        existing = {"condition_summary": "Very good used condition.", "flaws_note": None}
        new_listing = {"condition_summary": "Very good used condition.", "flaws_note": "AI re-detected flaw"}
        preserve_user_fields(existing, new_listing)
        assert new_listing["flaws_note"] is None  # operator explicitly cleared it

    def test_update_overrides_preservation(self):
        from app.services.pipeline import preserve_user_fields
        existing = {"flaws_note": "Old flaw"}
        new_listing = {}
        updates = {"flaws_note": "New operator flaw"}
        preserve_user_fields(existing, new_listing, updates)
        # preserve_user_fields should not overwrite when flaws_note in updates
        assert new_listing.get("flaws_note") != "Old flaw"

    def test_not_added_when_not_in_existing(self):
        from app.services.pipeline import preserve_user_fields
        existing = {"condition_summary": "Very good used condition."}  # no flaws_note key
        new_listing = {}
        preserve_user_fields(existing, new_listing)
        assert "flaws_note" not in new_listing
