"""User profile — load/save operator preferences from data/user_profile.json.

Profile drives:
- pricing_mode  → band position offset in pricing.py
- vinted_experience → in-app guidance visibility
- intent / volume   → reseller-oriented language in UI
"""
import json
from pathlib import Path

_PATH = Path("data/user_profile.json")

DEFAULTS: dict = {
    "intent": "mixed",                  # casual | reseller | mixed
    "volume": "low",                    # low | medium | high
    "category_focus": "mixed",          # everyday | premium | sportswear | mixed
    "vinted_experience": "occasional",  # new | occasional | experienced
    "pricing_mode": "balanced",         # speed | price | balanced
}


def load() -> dict:
    """Return user profile. Falls back to defaults on missing file or any error."""
    try:
        if _PATH.exists():
            data = json.loads(_PATH.read_text())
            return {**DEFAULTS, **data}
    except Exception:
        pass
    return dict(DEFAULTS)


def save(profile: dict) -> None:
    """Persist profile. Only saves recognised keys — ignores junk fields."""
    clean = {k: profile[k] for k in DEFAULTS if k in profile}
    _PATH.write_text(json.dumps(clean, indent=2))


def is_reseller(profile: dict) -> bool:
    """True for resellers or high-volume sellers (drives UI language)."""
    return profile.get("intent") == "reseller" or profile.get("volume") in ("medium", "high")


def show_guidance(profile: dict) -> bool:
    """True if the operator should see extra in-app guidance hints."""
    return profile.get("vinted_experience") == "new"
