"""Password-protected hosted app: the owner plus sellers the owner invites, each with separate data.

The owner signs in with APP_USERNAME / APP_PASSWORD. Invited sellers sign up from a one-time link and get
their own listings, photos, sales and cloud copies (app/services/accounts.py). Browser automation is
deliberately unavailable here.
"""
import hashlib
import hmac
import json
import os
import re
import time
from datetime import timedelta
from urllib.parse import urlsplit

from flask import g, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app import config
from app.services import accounts
from app.web import app

_FOLDER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_BROWSER_ROUTES = {"/create-draft", "/edit-draft", "/login/start", "/login/save"}
_GENERATION_ROUTES = {"/upload", "/create-listing"}
# Reachable without signing in: the sign-in page itself, health checks, styles/scripts, privacy note.
_PUBLIC = {"/health", "/signin", "/signup", "/reset", "/privacy", "/manifest.json", "/favicon.ico"}
_SIGNIN_LIMIT, _SIGNIN_WINDOW = 8, 300   # attempts per IP per 5 minutes
_signin_attempts: dict[str, list[float]] = {}


def _safe_next(target):
    """Only redirect back to a path on this site."""
    return target if isinstance(target, str) and target.startswith("/") and not target.startswith("//") else "/"


def _rate_limited(ip):
    now = time.time()
    recent = [t for t in _signin_attempts.get(ip, []) if now - t < _SIGNIN_WINDOW]
    _signin_attempts[ip] = recent
    return len(recent) >= _SIGNIN_LIMIT


def web_items_dir():
    from app import web
    return web.ITEMS_DIR


def valid_folder(folder):
    if not isinstance(folder, str) or not _FOLDER.fullmatch(folder):
        return False
    root = config.ITEMS_DIR.resolve()
    target = (root / folder).resolve()
    return target != root and target.is_relative_to(root)


def provider_status(provider):
    keys = {"openai": ("OPENAI_API_KEY", config.OPENAI_API_KEY),
            "claude-haiku": ("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY)}
    if provider not in keys:
        return {"provider": "unsupported", "ready": False,
                "issue": "unsupported_provider", "key_variable": None}
    name, key = keys[provider]
    return {"provider": provider, "ready": bool(key), "key_variable": name,
            "issue": None if key else "missing_key"}


def _status_after_restore(folder):
    from app import web
    listing = json.loads((web.ITEMS_DIR / folder / "listing.json").read_text())
    web._sync_item_status(folder, listing)


def _start_cloud_store():
    """Restore drafts from Backblaze B2 when configured; never block startup on it."""
    from app import web
    from app.services import cloud_store
    status_after_restore = _status_after_restore

    try:
        from app.services import user_profile
        return cloud_store.from_environment(web.ITEMS_DIR, on_restored=status_after_restore,
                                            profile_path=user_profile._PATH.resolve())
    except Exception as error:
        cloud_store.log.error("Cloud storage failed to start (%s)", type(error).__name__)
        return None


def _tidy_duplicates(cloud):
    """Merge copies left by the old "Analyse photos again"; never block startup on it."""
    from app import web
    from app.services import removed_items
    try:
        if cloud:   # duplicate pairs need their full files before merging (only a few)
            for target in web.ITEMS_DIR.glob("upload_retest_*"):
                try:
                    source = json.loads((target / "reanalysis.json").read_text()).get("source")
                except (OSError, ValueError, AttributeError):
                    continue
                if cloud.hydrate(target.name) and source and (web.ITEMS_DIR / source).is_dir():
                    cloud.hydrate(source)
        result = removed_items.merge_retests(web.ITEMS_DIR)
        for folder in result["merged"]:
            web._sync_item_status(folder, json.loads((web.ITEMS_DIR / folder / "listing.json").read_text()))
        if result["removed"]:
            app.logger.warning("Tidied %d duplicate listings (%d merged)", len(result["removed"]), len(result["merged"]))
            if cloud:
                cloud.request_sync()
    except Exception as error:
        app.logger.error("Duplicate tidy-up failed (%s)", type(error).__name__)


def create_app():
    username = os.getenv("APP_USERNAME", "kristian")
    password = os.getenv("APP_PASSWORD", "")
    if len(password) < 6:
        raise RuntimeError("Hosted test requires APP_PASSWORD of at least 6 characters")
    app.config["HOSTED_TEST"] = True
    accounts.install_scoped_paths()   # per-person paths follow whoever is signed in
    # Session cookie for the sign-in page. Changing APP_PASSWORD signs everyone out.
    app.secret_key = os.getenv("SECRET_KEY") or hmac.new(password.encode(), b"vinted-session", hashlib.sha256).hexdigest()
    app.config.update(SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "1") == "1",
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=timedelta(days=30))
    session_token = hmac.new(password.encode(), username.encode(), hashlib.sha256).hexdigest()

    def credentials_ok(name, secret):
        return hmac.compare_digest((name or "").encode(), username.encode()) \
            and hmac.compare_digest((secret or "").encode(), password.encode())
    cloud = _start_cloud_store()
    app.extensions["cloud_store"] = cloud
    _tidy_duplicates(cloud)
    if cloud:
        accounts.attach_cloud(cloud.client, cloud.bucket)
    seller_stores = {}

    def store_for(account_id):
        """The owner's cloud copy, or the seller's own (started and restored on first use)."""
        if account_id is None or not cloud:
            return cloud
        store = seller_stores.get(account_id)
        if store is None:
            from app.services import cloud_store
            root = accounts.root_for(account_id)
            store = cloud_store.CloudStore(cloud.client, cloud.bucket, root / "items", _status_after_restore,
                                           root / "data" / "user_profile.json",
                                           prefix=f"users/{account_id}/", account_id=account_id)
            seller_stores[account_id] = store
            try:
                store.restore_all()
                store.sync()
            except Exception as error:
                app.logger.error("Seller cloud copy failed to start (%s)", type(error).__name__)
            store.start()
        return store
    app.extensions["current_cloud"] = lambda: store_for(accounts.current())

    def signed_in_account():
        """"owner", a seller's id, or None. Owner: the session token or basic auth; seller: session + version."""
        auth = request.authorization
        if hmac.compare_digest(str(session.get("auth", "")).encode(), session_token.encode()) \
                or (auth and auth.type == "basic" and credentials_ok(auth.username, auth.password)):
            return "owner"
        account = accounts.get(session.get("acct"))
        if account and hmac.compare_digest(str(session.get("acct_v", "")).encode(), accounts.session_version(account).encode()):
            return account["id"]
        return None

    @app.get("/api/provider-status")
    def api_provider_status():
        # Protected by the same password gate; never return any credential value.
        return jsonify(single_pass=config.ENABLE_SINGLE_PASS,
                       vision=provider_status(config.VISION_PROVIDER),
                       listing=provider_status(config.LISTING_PROVIDER),
                       anthropic_key_configured=bool(config.ANTHROPIC_API_KEY),
                       openai_key_configured=bool(config.OPENAI_API_KEY),
                       cloud_storage=cloud.status if cloud else {"enabled": False})

    @app.route("/signin", methods=["GET", "POST"])
    def signin():
        error = None
        if request.method == "POST":
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
            if _rate_limited(ip):
                error = "Too many tries. Wait a few minutes."
            elif credentials_ok(request.form.get("username", "").strip(), request.form.get("password", "")):
                session.clear()
                session["auth"] = session_token
                session.permanent = True
                return redirect(_safe_next(request.args.get("next")))
            elif (seller := accounts.check(request.form.get("username", ""), request.form.get("password", ""))):
                session.clear()
                session["acct"], session["acct_v"] = seller["id"], accounts.session_version(seller)
                session.permanent = True
                return redirect(_safe_next(request.args.get("next")))
            else:
                _signin_attempts.setdefault(ip, []).append(time.time())
                error = "That username or password isn't right."
        return render_template("signin.html", error=error), (401 if error else 200)

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        """An invited seller makes their account (one-time link from the owner's Settings)."""
        code = request.values.get("invite", "")
        if not accounts.invite_ok(code):
            return render_template("signup.html", invalid=True), 404
        error = None
        if request.method == "POST":
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
            if _rate_limited(ip):
                error = "Too many tries. Wait a few minutes."
            else:
                _signin_attempts.setdefault(ip, []).append(time.time())
                try:
                    seller = accounts.sign_up(code, request.form.get("name", ""), request.form.get("email", ""),
                                              request.form.get("password", ""), owner_username=username)
                except ValueError as problem:
                    error = str(problem)
                else:
                    session.clear()
                    session["acct"], session["acct_v"] = seller["id"], accounts.session_version(seller)
                    session.permanent = True
                    return redirect("/welcome")
        return render_template("signup.html", invalid=False, error=error, code=code,
                               form=request.form), (400 if error else 200)

    @app.post("/api/accounts/invite")
    def account_invite():
        if accounts.current() is not None:
            return jsonify(error="Only the owner can invite sellers"), 403
        code = accounts.create_invite()
        return jsonify(link=request.host_url.rstrip("/") + "/signup?invite=" + code, days=accounts.INVITE_DAYS)

    @app.get("/api/accounts")
    def account_list():
        if accounts.current() is not None:
            return jsonify(error="Only the owner can see sellers"), 403
        return jsonify(sellers=accounts.sellers())

    @app.post("/api/accounts/<seller_id>/remove")
    def account_remove(seller_id):
        if accounts.current() is not None:
            return jsonify(error="Only the owner can remove sellers"), 403
        return (jsonify(removed=True) if accounts.remove(seller_id) else (jsonify(error="No such seller"), 404))

    @app.post("/api/accounts/<seller_id>/reset")
    def account_reset_link(seller_id):
        if accounts.current() is not None:
            return jsonify(error="Only the owner can make reset links"), 403
        try:
            code = accounts.create_reset(seller_id)
        except ValueError as problem:
            return jsonify(error=str(problem)), 404
        return jsonify(link=request.host_url.rstrip("/") + "/reset?code=" + code, hours=accounts.RESET_HOURS)

    @app.post("/api/accounts/password")
    def account_password():
        """A seller changes their own password (stays signed in here, signed out elsewhere)."""
        if accounts.current() is None:
            return jsonify(error="The owner's password is set in Render (APP_PASSWORD)"), 400
        body = request.get_json(silent=True) or {}
        try:
            seller = accounts.change_password(accounts.current(), body.get("current", ""), body.get("new", ""))
        except ValueError as problem:
            return jsonify(error=str(problem)), 422
        session["acct_v"] = accounts.session_version(seller)
        return jsonify(changed=True)

    @app.route("/reset", methods=["GET", "POST"])
    def reset_password():
        """One-time link from the owner: the seller picks a new password and is signed in."""
        code = request.values.get("code", "")
        seller = accounts.reset_account(code)
        if not seller:
            return render_template("signup.html", invalid=True, reset=True), 404
        error = None
        if request.method == "POST":
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
            if _rate_limited(ip):
                error = "Too many tries. Wait a few minutes."
            else:
                _signin_attempts.setdefault(ip, []).append(time.time())
                try:
                    seller = accounts.use_reset(code, request.form.get("password", ""))
                except ValueError as problem:
                    error = str(problem)
                else:
                    session.clear()
                    session["acct"], session["acct_v"] = seller["id"], accounts.session_version(seller)
                    session.permanent = True
                    return redirect("/")
        return render_template("signup.html", invalid=False, reset=True, error=error, code=code,
                               email=seller["email"], form={}), (400 if error else 200)

    @app.get("/api/accounts/usage")
    def account_usage():
        """This month: the owner sees spend for everyone and the limits; a seller sees their own listings."""
        from app.services import usage_limits
        limits = accounts.limits()
        if accounts.current() is None:
            return jsonify(limits=limits, **usage_limits.everyone())
        used = usage_limits.usage()
        return jsonify(items=used["items"], seller_items=limits["seller_items"])

    @app.post("/api/accounts/limits")
    def account_limits():
        if accounts.current() is not None:
            return jsonify(error="Only the owner can change limits"), 403
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(limits=accounts.set_limits(body.get("monthly_cap_gbp"), body.get("seller_items")))
        except ValueError as problem:
            return jsonify(error=str(problem)), 422

    @app.post("/signout")
    def signout():
        session.clear()
        return redirect("/signin")

    @app.before_request
    def protect_test_app():
        if request.path in _PUBLIC or request.path.startswith("/static/"):
            if request.method not in {"GET", "HEAD"} and request.path in {"/signin", "/signup", "/reset"}:
                origin = request.headers.get("Origin")
                if origin and urlsplit(origin).netloc != request.host:
                    return jsonify(error="Cross-site request rejected"), 403
            return None
        who = signed_in_account()
        if who is None:
            # Pages go to the sign-in screen; app requests get a plain 401.
            if request.method == "GET" and "text/html" in request.headers.get("Accept", ""):
                return redirect("/signin?next=" + request.full_path.rstrip("?"))
            return jsonify(error="Sign in to this private test"), 401
        # From here on this request reads and writes only the signed-in person's files.
        account_id = None if who == "owner" else who
        g.account_token = accounts.enter(account_id)
        accounts.ensure_ready(account_id)
        cloud_here = store_for(account_id)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            if (origin and urlsplit(origin).netloc != request.host) or request.headers.get("Sec-Fetch-Site") == "cross-site":
                return jsonify(error="Cross-site request rejected"), 403
        folder = (request.view_args or {}).get("folder")
        body = request.get_json(silent=True)
        if isinstance(body, dict) and "folder" in body:
            folder = body["folder"]
        if folder is not None and not valid_folder(folder):
            return jsonify(error="Invalid item folder"), 400
        # Restored as a summary after a wake-up: fetch the item's photos the first time it's used.
        if cloud_here:
            wanted = folder if folder is not None and request.method != "DELETE" else None
            if request.path == "/api/private/backup":
                wanted = request.args.get("folder")
                if not wanted:   # full backup download: everything
                    for item in list(web_items_dir().glob("upload_*")):
                        cloud_here.hydrate(item.name)
            if wanted and not request.path.endswith("/_thumb.jpg") and valid_folder(wanted):
                cloud_here.hydrate(wanted)
        if request.path in _BROWSER_ROUTES or request.path.startswith("/tracker/refresh/"):
            return jsonify(error="Vinted browser operations require the local app", code="LOCAL_BROWSER_REQUIRED"), 503
        if request.path == "/auth/status":
            return jsonify(logged_in="missing", method="local_only", expires_at=None)
        if request.path in _GENERATION_ROUTES or request.path.startswith("/regen/"):
            from app.services import usage_limits
            stop = usage_limits.blocked(account_id, folder)
            if stop:
                return jsonify(error=stop, code="USAGE_LIMIT"), 429
        if request.path in _GENERATION_ROUTES or request.path.startswith("/regen/"):
            stages = [("LISTING_PROVIDER", provider_status(config.LISTING_PROVIDER))]
            if request.path in _GENERATION_ROUTES:
                stages.append(("VISION_PROVIDER", provider_status(config.VISION_PROVIDER)))
            for variable, status in stages:
                if status["issue"] == "unsupported_provider":
                    return jsonify(error=f"Set {variable} to claude-haiku or openai in Render Environment.",
                                   code="UNSUPPORTED_PROVIDER"), 503
                if not status["ready"]:
                    return jsonify(error=f"The server cannot detect {status['key_variable']}. Add it in Render Environment and save and deploy.",
                                   code="PROVIDER_KEY_MISSING"), 503

    @app.teardown_request
    def leave_account(_error=None):
        token = g.pop("account_token", None)
        if token is not None:
            accounts.leave(token)

    @app.after_request
    def private_headers(response):
        cloud_here = store_for(accounts.current()) if "account_token" in g else None
        if cloud_here and request.method not in {"GET", "HEAD", "OPTIONS"} and response.status_code < 400:
            cloud_here.request_sync()
        # Routes may catch their own exceptions and return raw SDK tracebacks.
        # Sanitize those responses too; the global error handler never sees them.
        if response.status_code >= 500 and response.status_code != 503:
            response.set_data(app.json.dumps({
                "error": "Listing operation failed. Check API settings or try again.",
                "code": "OPERATION_FAILED",
            }))
            response.content_type = "application/json"
        elif response.status_code >= 400 and response.is_json:
            payload = response.get_json(silent=True)
            serialized = app.json.dumps(payload)
            secrets = (config.ANTHROPIC_API_KEY, config.OPENAI_API_KEY,
                       config.GOOGLE_AI_API_KEY, password)
            if any(secret and secret in serialized for secret in secrets) or "Traceback (most recent call last)" in serialized:
                response.set_data(app.json.dumps({"error": "Operation failed; check API settings."}))
        # Static files (versioned links) and photos may be cached; private pages never are.
        from app.web import cache_policy
        policy = cache_policy(request.path, bool(request.args.get("v"))) if response.status_code in (200, 304) else None
        response.headers["Cache-Control"] = policy or "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.errorhandler(Exception)
    def private_error(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.description), error.code
        # SDK exception messages can contain credentials, including nested causes.
        app.logger.error("Private test operation failed (%s)", type(error).__name__)
        return jsonify(error="Operation failed; check the private server logs"), 500

    @app.context_processor
    def private_context():
        seller = accounts.get(accounts.current()) if "account_token" in g else None
        return {"hosted_test": True, "is_owner": "account_token" in g and seller is None,
                "account_email": seller["email"] if seller else None,
                "account_key": seller["id"] if seller else None, "hosted_vision_model": config.OPENAI_VISION_MODEL
                if config.VISION_PROVIDER == "openai" else config.HAIKU_MODEL}

    return app
