"""
Deterministic condition + flaws service.

Pure functions only — no I/O, no AI calls, no side effects.

Responsibilities
----------------
1. Extract a canonical condition level from a freeform condition_summary string.
2. Auto-downgrade that level when flaws_note keywords indicate damage severity.
3. Build the buyer-facing condition_line that appears in the listing description.
4. Inject that line into the description string, replacing any AI condition wording.

Public API
----------
canonical_level(condition_summary)     -> str
auto_downgrade(level, flaws_note)      -> str
default_condition_line(level)          -> str
build_condition_line(level, flaws_note) -> str
apply_condition(listing)               -> dict   (mutates in-place, never raises)
inject_condition_line(listing)         -> None   (mutates description in-place)
"""
from __future__ import annotations

import re

# ── Level extraction ─────────────────────────────────────────────────────────

# Ordered: longer / more specific phrases first to avoid "good" matching before "very good"
_LEVEL_KEYWORDS: list[tuple[str, str]] = [
    ("new with tags",    "New with tags"),
    ("new without tags", "New without tags"),
    ("excellent",        "Excellent"),
    ("very good",        "Very good"),
    ("satisfactory",     "Satisfactory"),
    ("fair",             "Satisfactory"),
    ("good",             "Good"),         # after "very good" to avoid substring clash
]


def canonical_level(condition_summary: str | None) -> str:
    """Extract the canonical condition level from a condition_summary string.

    Returns one of:
        "New with tags", "New without tags", "Excellent",
        "Very good", "Good", "Satisfactory"

    Defaults to "Very good" when no level can be inferred.
    """
    s = (condition_summary or "").lower()
    for keyword, level in _LEVEL_KEYWORDS:
        if keyword in s:
            return level
    return "Very good"


# ── Auto-downgrade ───────────────────────────────────────────────────────────

# Moderate damage → Very good / Excellent downgrades to Good
_MODERATE_KEYWORDS = frozenset({
    "stain", "mark", "scuff", "worn", "bobbling", "pilling",
    "fading", "discolouration", "discoloration", "wear",
})

# Severe damage → any worn condition downgrades to Satisfactory
_SEVERE_KEYWORDS = frozenset({
    "hole", "tear", "rip", "broken zip", "broken button",
    "missing button", "split seam", "fraying", "frayed",
})


def auto_downgrade(level: str, flaws_note: str | None) -> str:
    """Return the appropriate condition level after considering flaws_note.

    Rules:
    - "New with tags" and "New without tags" are never downgraded.
    - Severe keywords (hole, tear, rip…) → floor at "Satisfactory".
    - Moderate keywords (stain, mark, scuff…) → Excellent or Very good → Good.
    - Good and Satisfactory are not further downgraded by moderate keywords.
    - Empty or None flaws_note → level unchanged.
    """
    s = (flaws_note or "").lower()
    if not s:
        return level

    if level in ("New with tags", "New without tags"):
        return level

    if any(kw in s for kw in _SEVERE_KEYWORDS):
        return "Satisfactory"

    if any(kw in s for kw in _MODERATE_KEYWORDS):
        if level in ("Excellent", "Very good"):
            return "Good"

    return level


# ── Condition line builder ────────────────────────────────────────────────────

_DEFAULT_LINES: dict[str, str] = {
    "New with tags":    "New with original tags attached.",
    "New without tags": "New without tags — unworn.",
    "Excellent":        "Excellent used condition — no major flaws noted.",
    "Very good":        "Very good condition — no major flaws noted.",
    "Good":             "Good used condition — normal signs of wear.",
    "Satisfactory":     "Satisfactory condition — visible signs of use.",
}

_LEVEL_PREFIXES: dict[str, str] = {
    "New with tags":    "New with tags",
    "New without tags": "New without tags",
    "Excellent":        "Excellent used condition",
    "Very good":        "Very good condition",
    "Good":             "Good used condition",
    "Satisfactory":     "Satisfactory condition",
}


def default_condition_line(level: str) -> str:
    """Return the conservative default buyer-facing line for a given level."""
    return _DEFAULT_LINES.get(level, _DEFAULT_LINES["Very good"])


def build_condition_line(level: str, flaws_note: str | None) -> str:
    """Build the buyer-facing condition line.

    If flaws_note is absent → conservative default.
    If flaws_note is present → "<Level prefix> — <flaws detail>."
    """
    flaws = (flaws_note or "").strip().rstrip(".")
    if not flaws:
        return default_condition_line(level)

    prefix = _LEVEL_PREFIXES.get(level, "Very good condition")
    return f"{prefix} — {flaws}."


# ── Condition summary rebuilder ───────────────────────────────────────────────

_CLEAN_SUMMARIES: dict[str, str] = {
    "New with tags":    "New with tags — original labels attached.",
    "New without tags": "New without tags — unworn, no original tags.",
    "Excellent":        "Excellent used condition — no major flaws.",
    "Very good":        "Very good used condition — no major flaws.",
    "Good":             "Good used condition — normal signs of wear.",
    "Satisfactory":     "Satisfactory used condition — visible signs of use.",
}


def _rebuild_condition_summary(level: str) -> str:
    """Return a clean, canonical condition_summary for the given level."""
    return _CLEAN_SUMMARIES.get(level, _CLEAN_SUMMARIES["Very good"])


# ── apply_condition ───────────────────────────────────────────────────────────

def apply_condition(listing: dict) -> dict:
    """Apply deterministic condition logic to a listing dict in-place.

    Steps:
    1. Extract canonical level from condition_summary.
    2. Auto-downgrade based on flaws_note keywords.
    3. If downgraded: rewrite condition_summary cleanly (no stale AI note fragments).
    4. Write condition_line (the buyer-facing description line).

    Never raises. Returns listing.
    """
    try:
        return _apply_condition_inner(listing)
    except Exception:
        listing.setdefault("condition_line", "")
        return listing


def _apply_condition_inner(listing: dict) -> dict:
    raw_summary = listing.get("condition_summary") or ""
    flaws_note  = listing.get("flaws_note") or ""

    level      = canonical_level(raw_summary)
    downgraded = auto_downgrade(level, flaws_note)

    if downgraded != level:
        listing["condition_summary"] = _rebuild_condition_summary(downgraded)

    listing["condition_line"] = build_condition_line(downgraded, flaws_note or None)
    return listing


# ── inject_condition_line ─────────────────────────────────────────────────────

# Lines that AI generates despite being told not to — we strip them.
_AI_COND_LINE_RE = re.compile(
    r"^-\s*(?:Very good|Excellent|Good|Satisfactory)[^\n]*condition[^\n]*\n?",
    re.IGNORECASE | re.MULTILINE,
)
_AI_NO_DAMAGE_RE = re.compile(
    r"^-?\s*(?:No visible damage|No holes or stains|No major flaws|No flaws)[^\n]*\n?",
    re.IGNORECASE | re.MULTILINE,
)

# Anchor lines where we insert before
_ANCHOR_RE = re.compile(
    r"^(?:measurements|fast postage|keywords:)",
    re.IGNORECASE,
)


def inject_condition_line(listing: dict) -> None:
    """Modify listing['description'] in-place:

    1. Strip any AI-generated condition or "no damage" lines.
    2. Insert the deterministic condition_line bullet before the
       "Measurements" / "Fast postage" / "Keywords" anchor (or at end).

    No-op if condition_line is absent.
    """
    condition_line = (listing.get("condition_line") or "").strip()
    if not condition_line:
        return

    desc = listing.get("description", "")

    # Strip AI condition violations
    desc = _AI_COND_LINE_RE.sub("", desc)
    desc = _AI_NO_DAMAGE_RE.sub("", desc)

    lines = desc.splitlines()
    insert_idx: int | None = None
    for i, line in enumerate(lines):
        if _ANCHOR_RE.match(line.strip()):
            insert_idx = i
            break

    cond_bullet = f"- {condition_line}"

    if insert_idx is not None:
        # Ensure a blank line before anchor if last content line isn't blank
        if insert_idx > 0 and lines[insert_idx - 1].strip():
            lines.insert(insert_idx, "")
            lines.insert(insert_idx + 1, cond_bullet)
        else:
            lines.insert(insert_idx, cond_bullet)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(cond_bullet)

    desc = "\n".join(lines)
    # Collapse runs of 3+ blank lines to 2
    desc = re.sub(r"\n{3,}", "\n\n", desc).strip()
    listing["description"] = desc
