import io
import json
import zipfile
import pytest
from PIL import Image
from app.services import item_backup, model_usage, sales_history


def test_fresh_analysis_can_be_exported_restored_and_exported_again(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(model_usage, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(sales_history, "read_all", lambda: [])
    monkeypatch.setattr(sales_history, "restore", lambda rows: 0)
    root = tmp_path / "source"
    root.mkdir()
    folder = "upload_retest_" + "a" * 32
    item = root / folder
    item.mkdir()
    listing = dict(
        title="Peter Millar Polo Shirt S",
        description="Seller notes.",
        brand="Peter Millar",
        item_type="polo shirt",
        gender="men's",
        colour="Multi",
        tagged_size="S",
        normalized_size="S",
        materials=["92% Polyester", "8% Spandex"],
        category="Men > Polo Shirts",
        price_gbp=25,
        material_source="label_ocr_consensus",
        material_verification={
            "status": "readable",
            "pairs": [["main", 92, "Polyester"], ["main", 8, "Spandex"]],
        },
    )
    (item / "listing.json").write_text(json.dumps(listing))
    (item / "analysis.json").write_text(json.dumps({"listing": listing}))
    (item / "reanalysis.json").write_text(json.dumps({"source": "upload_deadbeef"}))
    Image.new("RGB", (80, 100), "white").save(item / "material.jpg")
    backup = item_backup.export(root, folder)
    restored = tmp_path / "restored"
    assert item_backup.restore(backup, restored) == [folder]
    assert (restored / folder / "material.jpg").read_bytes() == (
        item / "material.jpg"
    ).read_bytes()
    result = json.loads((restored / folder / "listing.json").read_text())
    assert (
        result["materials"] == listing["materials"]
        and result["material_verification"] == listing["material_verification"]
    )
    assert (
        json.loads((restored / folder / "reanalysis.json").read_text())["source"]
        == "upload_deadbeef"
    )
    assert item_backup.export(restored, folder)


@pytest.mark.parametrize(
    "folder",
    [
        "upload_retest_" + "a" * 31,
        "upload_retest_" + "a" * 33,
        "upload_retest_../secret",
        "../upload_deadbeef",
    ],
)
def test_invalid_retest_paths_still_rejected(folder):
    assert not item_backup.FOLDER.fullmatch(folder)
