"""Seller accounts on the hosted app: the owner plus sellers the owner invites.

The owner signs in with APP_USERNAME / APP_PASSWORD and keeps the data exactly where it always was.
Each invited seller gets their own folder (accounts/<id>/items and accounts/<id>/data) and their own
cloud prefix (users/<id>/): listings, photos, sales, profile, logs and costs never mix.

Which account a request (or a background cloud-sync thread) belongs to is a context variable. Every
per-person path in the app (ITEMS_DIR, the item and sales databases, the profile, logs, cost log) is a
ScopedPath that resolves through it, so existing code keeps using the same names. Shared knowledge
(price memory, brand aliases) stays shared.
"""
from __future__ import annotations

import contextvars
import importlib
import json
import logging
import os
import re
import secrets
import threading
import time
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

log = logging.getLogger("accounts")

ROOT = Path(__file__).resolve().parent.parent.parent
ACCOUNTS_DIR = ROOT / "accounts"
CLOUD_KEY = "accounts/registry.json"
INVITE_DAYS = 7
MIN_PASSWORD = 8
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
_ID = re.compile(r"^a[0-9a-f]{10}$")

_current: contextvars.ContextVar[str | None] = contextvars.ContextVar("account", default=None)  # None = owner
_lock = threading.Lock()
_cloud = None   # (client, bucket) once cloud backup is on

# Every per-person path in the app. Owner paths stay as they are; sellers get the same layout in their folder.
SCOPED = [   # (module, attribute, where it lives inside a seller's folder)
    ("app.config", "ITEMS_DIR", "items"), ("app.web", "ITEMS_DIR", "items"), ("app.extractor", "ITEMS_DIR", "items"),
    ("app.web", "COST_LOG", "data/cost_log.csv"),
    ("app.services.item_store", "_DATA_DIR", "data"), ("app.services.item_store", "DB_PATH", "data/items.db"),
    ("app.services.sales_history", "DB_PATH", "data/sales.db"),
    ("app.services.user_profile", "_PATH", "data/user_profile.json"),
    ("app.services.removed_items", "PATH", "data/removed_items.json"),
    ("app.services.model_usage", "LEDGER_PATH", "data/model_calls.jsonl"),
    ("app.run_logger", "_DATA_DIR", "data"), ("app.run_logger", "LOG_PATH", "data/run_logs.jsonl"),
    ("app.run_logger", "CORRECTIONS_PATH", "data/corrections.jsonl"),
]


# ── Which account is active ──────────────────────────────────────────────────

def current() -> str | None:
    return _current.get()


def root_for(account_id: str) -> Path:
    if not _ID.fullmatch(account_id or ""):
        raise ValueError("bad account id")
    return ACCOUNTS_DIR / account_id


class scope:
    """with accounts.scope(account_id): ... — everything inside reads and writes that account's files."""

    def __init__(self, account_id: str | None):
        self.account_id = account_id

    def __enter__(self):
        self._token = _current.set(self.account_id)
        return self

    def __exit__(self, *exc):
        _current.reset(self._token)


def enter(account_id: str | None):
    """For request hooks: returns a token for leave()."""
    return _current.set(account_id)


def leave(token) -> None:
    _current.reset(token)


class ScopedPath(os.PathLike):
    """A path that points at the active account's copy (the owner's when no seller is active)."""

    def __init__(self, owner_path, rel):
        self._owner = Path(owner_path)
        self._rel = Path(rel)

    def path(self) -> Path:
        account_id = _current.get()
        return self._owner if account_id is None else root_for(account_id) / self._rel

    def __fspath__(self):
        return str(self.path())

    def __str__(self):
        return str(self.path())

    def __repr__(self):
        return f"ScopedPath({self.path()!r})"

    def __truediv__(self, other):
        return self.path() / other

    def __eq__(self, other):
        return self.path() == (other.path() if isinstance(other, ScopedPath) else other)

    def __hash__(self):
        return hash(self.path())

    def __getattr__(self, name):
        return getattr(self.path(), name)


def install_scoped_paths() -> None:
    """Hosted mode only: make every per-person path follow the active account."""
    for module_name, attr, rel in SCOPED:
        module = importlib.import_module(module_name)
        value = getattr(module, attr)
        if not isinstance(value, ScopedPath):
            setattr(module, attr, ScopedPath(value, rel))


def ensure_ready(account_id: str | None) -> None:
    """First use of a seller's space: create the folders and empty databases."""
    if account_id is None:
        return
    root = root_for(account_id)
    if (root / "data" / "items.db").exists():
        return
    (root / "items").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    with scope(account_id):
        from app.services import item_store
        item_store.init_db()


# ── The registry of sellers and invites ──────────────────────────────────────

def _registry_path() -> Path:
    return ACCOUNTS_DIR / "registry.json"


def _load() -> dict:
    try:
        data = json.loads(_registry_path().read_text())
        if isinstance(data, dict):
            data.setdefault("accounts", {})
            data.setdefault("invites", {})
            return data
    except (OSError, ValueError):
        pass
    return {"accounts": {}, "invites": {}}


def _save(data: dict) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, indent=1, sort_keys=True).encode()
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.replace(path)
    if _cloud:
        client, bucket = _cloud
        try:
            client.put_object(Bucket=bucket, Key=CLOUD_KEY, Body=body, ContentType="application/json")
        except Exception as error:   # logged, never blocks a sign-up; retried on the next change
            log.error("Accounts: cloud save failed (%s)", type(error).__name__)


def attach_cloud(client, bucket) -> None:
    """Keep the registry in the bucket too (a restart wipes local disk). Restores it if missing here."""
    global _cloud
    _cloud = (client, bucket)
    if _registry_path().exists():
        return
    try:
        body = client.get_object(Bucket=bucket, Key=CLOUD_KEY)["Body"].read()
        data = json.loads(body)
        if isinstance(data, dict):
            _registry_path().parent.mkdir(parents=True, exist_ok=True)
            _registry_path().write_bytes(body)
    except Exception as error:
        if "NoSuchKey" not in f"{type(error).__name__} {error}" and "404" not in str(error):
            log.error("Accounts: cloud restore failed (%s)", type(error).__name__)


def create_invite(now: float | None = None) -> str:
    now = now or time.time()
    code = secrets.token_urlsafe(12)
    with _lock:
        data = _load()
        data["invites"] = {c: i for c, i in data["invites"].items() if i.get("expires", 0) > now and not i.get("used_by")}
        data["invites"][code] = {"created": now, "expires": now + INVITE_DAYS * 86400}
        _save(data)
    return code


def invite_ok(code: str, now: float | None = None) -> bool:
    invite = _load()["invites"].get(code or "")
    return bool(invite) and not invite.get("used_by") and invite.get("expires", 0) > (now or time.time())


def sign_up(code: str, name: str, email: str, password: str, owner_username: str = "") -> dict:
    """Create a seller from an invite. Raises ValueError with a message for the form."""
    name, email = (name or "").strip()[:40], (email or "").strip().lower()
    if not name:
        raise ValueError("Add your name.")
    if not _EMAIL.fullmatch(email):
        raise ValueError("That email doesn't look right.")
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"Use a password of at least {MIN_PASSWORD} characters.")
    if owner_username and email == owner_username.strip().lower():
        raise ValueError("Pick a different email.")
    with _lock:
        data = _load()
        invite = data["invites"].get(code or "")
        if not invite or invite.get("used_by") or invite.get("expires", 0) <= time.time():
            raise ValueError("This invite link has expired or been used. Ask for a new one.")
        if any(a["email"] == email for a in data["accounts"].values()):
            raise ValueError("There's already an account with that email. Sign in instead.")
        account_id = "a" + secrets.token_hex(5)
        account = {"id": account_id, "name": name, "email": email, "created": time.time(),
                   "password": generate_password_hash(password)}
        data["accounts"][account_id] = account
        invite["used_by"] = account_id
        _save(data)
    log.warning("Accounts: new seller %s", account_id)
    return account


def check(email: str, password: str) -> dict | None:
    email = (email or "").strip().lower()
    for account in _load()["accounts"].values():
        if account.get("email") == email and not account.get("disabled"):
            return account if check_password_hash(account["password"], password or "") else None
    return None


def get(account_id: str | None) -> dict | None:
    account = _load()["accounts"].get(account_id or "")
    return account if account and not account.get("disabled") else None


def session_version(account: dict) -> str:
    """Changes when the password changes, which signs that seller out everywhere."""
    return account["password"][-16:]


def sellers() -> list[dict]:
    return [{"id": a["id"], "name": a["name"], "email": a["email"], "created": a["created"]}
            for a in sorted(_load()["accounts"].values(), key=lambda a: a["created"]) if not a.get("disabled")]


# ── Limits the owner sets (stored with the registry, so they survive restarts) ──

LIMIT_DEFAULTS = {"monthly_cap_gbp": 20.0, "seller_items": 30}


def limits() -> dict:
    stored = _load().get("limits") or {}
    return {**LIMIT_DEFAULTS, **{k: stored[k] for k in LIMIT_DEFAULTS if k in stored}}


def set_limits(monthly_cap_gbp, seller_items) -> dict:
    try:
        cap, items = round(float(monthly_cap_gbp), 2), int(seller_items)
    except (TypeError, ValueError):
        raise ValueError("Enter numbers for the limits.")
    if not 0 <= cap <= 1000 or not 0 <= items <= 10000:
        raise ValueError("Budget must be £0–£1000 and listings 0–10000.")
    with _lock:
        data = _load()
        data["limits"] = {"monthly_cap_gbp": cap, "seller_items": items}
        _save(data)
    return limits()


# ── Owner tools: remove a seller, one-time password reset links; sellers change their own password ──

RESET_HOURS = 48


def remove(account_id: str) -> bool:
    """Stops sign-in at once (every open session too). Their data stays until deleted."""
    with _lock:
        data = _load()
        account = data["accounts"].get(account_id or "")
        if not account or account.get("disabled"):
            return False
        account["disabled"] = True
        data["resets"] = {c: r for c, r in data.get("resets", {}).items() if r.get("id") != account_id}
        _save(data)
    log.warning("Accounts: seller %s removed", account_id)
    return True


def create_reset(account_id: str, now: float | None = None) -> str:
    now = now or time.time()
    if not get(account_id):
        raise ValueError("No such seller.")
    code = secrets.token_urlsafe(12)
    with _lock:
        data = _load()
        resets = {c: r for c, r in data.get("resets", {}).items() if r.get("expires", 0) > now and r.get("id") != account_id}
        resets[code] = {"id": account_id, "expires": now + RESET_HOURS * 3600}
        data["resets"] = resets
        _save(data)
    return code


def reset_account(code: str, now: float | None = None) -> dict | None:
    reset = _load().get("resets", {}).get(code or "")
    if not reset or reset.get("expires", 0) <= (now or time.time()):
        return None
    return get(reset["id"])


def _set_password(account_id: str, password: str) -> dict:
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"Use a password of at least {MIN_PASSWORD} characters.")
    with _lock:
        data = _load()
        account = data["accounts"].get(account_id or "")
        if not account or account.get("disabled"):
            raise ValueError("No such seller.")
        account["password"] = generate_password_hash(password)
        data["resets"] = {c: r for c, r in data.get("resets", {}).items() if r.get("id") != account_id}
        _save(data)
    return account


def use_reset(code: str, password: str) -> dict:
    """Set a new password from a reset link (works once). Signs the seller out everywhere else."""
    account = reset_account(code)
    if not account:
        raise ValueError("This reset link has expired or been used. Ask for a new one.")
    return _set_password(account["id"], password)


def change_password(account_id: str, current: str, new: str) -> dict:
    account = get(account_id)
    if not account or not check_password_hash(account["password"], current or ""):
        raise ValueError("Your current password isn't right.")
    return _set_password(account_id, new)
