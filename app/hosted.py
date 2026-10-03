"""Password-protected, single-operator OCR/review test deployment.

Not a multi-user beta. Browser automation is deliberately unavailable here.
"""
import hmac
import os
import re
from urllib.parse import urlsplit

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from app import config
from app.web import app

_FOLDER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_BROWSER_ROUTES = {"/create-draft", "/edit-draft", "/login/start", "/login/save"}
_GENERATION_ROUTES = {"/upload", "/create-listing"}


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


def create_app():
    username = os.getenv("APP_USERNAME", "kristian")
    password = os.getenv("APP_PASSWORD", "")
    if len(password) < 24:
        raise RuntimeError("Hosted test requires APP_PASSWORD of at least 24 characters")
    app.config["HOSTED_TEST"] = True

    @app.get("/api/provider-status")
    def api_provider_status():
        # Protected by the same password gate; never return any credential value.
        return jsonify(vision=provider_status(config.VISION_PROVIDER),
                       listing=provider_status(config.LISTING_PROVIDER),
                       anthropic_key_configured=bool(config.ANTHROPIC_API_KEY),
                       openai_key_configured=bool(config.OPENAI_API_KEY))

    @app.before_request
    def protect_test_app():
        if request.path == "/health" and request.method == "GET":
            return None
        auth = request.authorization
        if not auth or auth.type != "basic" or not (
            hmac.compare_digest((auth.username or "").encode(), username.encode())
            and hmac.compare_digest((auth.password or "").encode(), password.encode())
        ):
            return jsonify(error="Sign in to this private test"), 401, {
                "WWW-Authenticate": 'Basic realm="Vinted private test", charset="UTF-8"'
            }
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
        if request.path in _BROWSER_ROUTES or request.path.startswith("/tracker/refresh/"):
            return jsonify(error="Vinted browser operations require the local app", code="LOCAL_BROWSER_REQUIRED"), 503
        if request.path == "/auth/status":
            return jsonify(logged_in="missing", method="local_only", expires_at=None)
        if request.path in _GENERATION_ROUTES or request.path.startswith(("/regen/", "/reprice/")):
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

    @app.after_request
    def private_headers(response):
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
        response.headers["Cache-Control"] = "no-store"
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
        return {"hosted_test": True, "hosted_vision_model": config.OPENAI_VISION_MODEL
                if config.VISION_PROVIDER == "openai" else config.HAIKU_MODEL}

    return app
