"""User profile — load/save operator preferences from data/user_profile.json.

Profile drives:
- pricing_mode  → band position offset in pricing.py
- vinted_experience → in-app guidance visibility
- intent / volume   → reseller-oriented language in UI
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

_PATH = Path("data/user_profile.json")

DEFAULTS: dict = {
    "intent": "mixed",                  # casual | reseller | mixed
    "volume": "low",                    # low | medium | high
    "category_focus": "mixed",          # everyday | premium | sportswear | mixed
    "vinted_experience": "occasional",  # new | occasional | experienced
    "pricing_mode": "balanced",         # speed | price | balanced
    # Set by onboarding (/welcome).
    "name": "",
    "email": "",
    "marketing_opt_in": False,
    "photo_mode": "guided",             # guided | pro
    "onboarded_at": None,
}

# Onboarding answers -> allowed values (anything else is rejected, not guessed).
CHOICES = {
    "intent": {"casual", "mixed", "reseller"},
    "volume": {"low", "medium", "high"},
    "vinted_experience": {"new", "occasional", "experienced"},
    "pricing_mode": {"speed", "balanced", "price"},
    "photo_mode": {"guided", "pro"},
}
DAILY_GOAL = {"low": 1, "medium": 3, "high": 6}
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}")


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


def daily_goal(profile: dict) -> int:
    return DAILY_GOAL.get(profile.get("volume"), 1)


def onboard(body) -> dict:
    """Validate onboarding answers and save them. Raises ValueError with a short reason."""
    if not isinstance(body, dict):
        raise ValueError("Answers missing.")
    name = " ".join(str(body.get("name") or "").split())[:40]
    email = str(body.get("email") or "").strip().lower()
    if not name:
        raise ValueError("Add your name.")
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise ValueError("Check your email address.")
    profile = load()
    for key, allowed in CHOICES.items():
        if key in body:
            if body[key] not in allowed:
                raise ValueError(f"Choose an option for {key.replace('_', ' ')}.")
            profile[key] = body[key]
    profile.update(name=name, email=email, marketing_opt_in=body.get("marketing_opt_in") is True,
                   onboarded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    save(profile)
    return profile
