"""Tests for _normalise_fabric_mill."""
from app.listing_writer import _normalise_fabric_mill


class TestNormaliseFabricMill:

    def test_strips_fabric_suffix(self):
        assert _normalise_fabric_mill("Loro Piana fabric") == "Loro Piana"

    def test_strips_cloth_suffix(self):
        assert _normalise_fabric_mill("VBC cloth") == "VBC"

    def test_strips_mills_suffix(self):
        assert _normalise_fabric_mill("Reda mills") == "Reda"

    def test_strips_textiles_suffix(self):
        assert _normalise_fabric_mill("Albini textiles") == "Albini"

    def test_no_change_when_clean(self):
        assert _normalise_fabric_mill("Loro Piana") == "Loro Piana"
        assert _normalise_fabric_mill("Vitale Barberis Canonico") == "Vitale Barberis Canonico"

    def test_case_insensitive_strip(self):
        assert _normalise_fabric_mill("Scabal Fabric") == "Scabal"
        assert _normalise_fabric_mill("Dormeuil FABRIC") == "Dormeuil"

    def test_none_returns_none(self):
        assert _normalise_fabric_mill(None) is None

    def test_empty_returns_empty(self):
        assert _normalise_fabric_mill("") == ""

    def test_does_not_strip_mid_word_fabric(self):
        # "fabric" in the middle of a name should not be touched
        assert _normalise_fabric_mill("Tessuti Sondrio") == "Tessuti Sondrio"
