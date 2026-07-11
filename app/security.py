import hashlib
import hmac
import logging
import re
import secrets
import time
from urllib.parse import urljoin, urlparse

from flask import abort, current_app, jsonify, request, session
from flask_login import current_user, logout_user
from app.extensions import limiter


_safe_log = re.compile(r"[^A-Za-z0-9_.:@-]")


def log_value(value):
    return _safe_log.sub("?", str(value))[:120]


def client_key(identity=""):
    # remote_addr is trustworthy because proxy headers are accepted only when explicitly enabled.
    raw = f"{request.remote_addr or 'unknown'}|{identity.casefold()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def rate_limit(bucket, key, limit, window_seconds):
    storage_key = f"ychat:{bucket}:{key}"
    return limiter.storage.incr(storage_key, window_seconds) <= limit


def clear_rate_limit(bucket, key):
    limiter.storage.clear(f"ychat:{bucket}:{key}")


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def is_safe_redirect(target):
    base = urlparse(request.host_url)
    candidate = urlparse(urljoin(request.host_url, target or ""))
    return candidate.scheme in {"http", "https"} and candidate.netloc == base.netloc


def init_security(app):
    app.config.setdefault("LOGIN_FAILURE_LIMIT", 5)
    app.config.setdefault("LOGIN_LOCKOUT_SECONDS", 300)
    app.config.setdefault("MAX_MESSAGE_LENGTH", 2000)
    app.config.setdefault("MAX_VOICE_BYTES", 2 * 1024 * 1024)
    app.config.setdefault("MAX_PROFILE_IMAGE_BYTES", 2 * 1024 * 1024)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def enforce_security():
        if current_user.is_authenticated:
            now = int(time.time())
            last_seen = session.get("last_seen", now)
            if now - int(last_seen) > int(app.permanent_session_lifetime.total_seconds()):
                logout_user()
                session.clear()
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Authentication required."}), 401
            session["last_seen"] = now
            session.permanent = True

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            expected = session.get("_csrf_token", "")
            if not expected or not hmac.compare_digest(str(supplied), str(expected)):
                current_app.logger.warning(
                    "csrf_rejected path=%s remote=%s",
                    log_value(request.path), log_value(request.remote_addr),
                )
                return jsonify({"error": "Request could not be verified."}), 400


def security_logger():
    return logging.getLogger("ychat.security")
