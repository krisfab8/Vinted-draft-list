"""Items removed on purpose (deleted, merged duplicates, delete-my-data).

Phones and cloud backups can still hold copies; restores check this list so a removed
item never comes back on its own.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.config import ROOT

PATH = ROOT / "data" / "removed_items.json"


def _load() -> set[str]:
    try:
        return set(json.loads(PATH.read_text()))
    except (OSError, ValueError, TypeError):
        return set()


def add(*folders: str) -> None:
    removed = _load() | {f for f in folders if f}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(removed)))
    tmp.replace(PATH)


def contains(folder: str) -> bool:
    return folder in _load()


def clear() -> None:
    PATH.unlink(missing_ok=True)


def _operator_touched(listing: dict, folder: str) -> bool:
    """Seller work that must not be replaced: manual edits, a Vinted draft, or a sale."""
    from app.services import sales_history
    try:
        sold = bool(sales_history.get(folder))
    except Exception:
        sold = False
    return bool(listing.get("manual_fields") or listing.get("draft_url") or sold)


def merge_retests(items_dir: Path) -> dict:
    """One-off tidy-up of copies left by the old "Analyse photos again" (it used to create a
    second listing instead of replacing). The fresh read replaces the original unless the
    seller had already worked on the original (edits, Vinted draft or sale) — then the
    original stays. Either way one listing remains. A copy whose original was deleted stays."""
    from app.services import photo_reanalysis
    merged, removed = [], []
    for target in sorted(Path(items_dir).glob("upload_retest_*")):
        if not target.is_dir():
            continue
        try:
            source_name = json.loads((target / "reanalysis.json").read_text()).get("source")
        except (OSError, ValueError, AttributeError):
            continue
        source = Path(items_dir) / str(source_name)
        if not source_name or not (source / "listing.json").is_file():
            continue
        original = json.loads((source / "listing.json").read_text())
        if (target / "listing.json").is_file() and not _operator_touched(original, source.name):
            listing = json.loads((target / "listing.json").read_text())
            listing.pop("reanalysis_source", None)
            photo_reanalysis.promote(source, target, listing, original)
            merged.append(source.name)
        else:
            shutil.rmtree(target, ignore_errors=True)
        removed.append(target.name)
    if removed:
        add(*removed)
    return {"merged": merged, "removed": removed}
