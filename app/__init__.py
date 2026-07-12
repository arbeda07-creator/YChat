from flask import Flask, jsonify, redirect, render_template, request
from pathlib import Path
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix
from redis import RedisError
from redis import from_url as redis_from_url

from app.config import get_config
from app.extensions import db, limiter, login_manager


def create_app(config_class=None):
    app = Flask(__name__, instance_relative_config=True)
    config_class = config_class or get_config()
    app.config.from_object(config_class)
    _configure_rate_limit_storage(app)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if app.config.get("TRUST_PROXY_HEADERS"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from app.auth.routes import auth_bp, public_auth_bp
    from app.chat.routes import chat_bp
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_auth_bp)
    app.register_blueprint(chat_bp)
    from app.migrations.import_json_messages import import_json_messages_command
    app.cli.add_command(import_json_messages_command)
    _register_security_hooks(app)
    from app.security import init_security
    init_security(app)

    with app.app_context():
        db.create_all()
        _ensure_user_profile_columns()

    return app


def _configure_rate_limit_storage(app):
    app.config.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    redis_url = app.config.get("REDIS_URL")
    if not redis_url:
        if app.config.get("APP_ENV") == "production":
            raise RuntimeError("REDIS_URL must be set in production for shared rate limiting.")
        app.config["RATELIMIT_STORAGE_URI"] = "memory://"
        return
    try:
        redis_from_url(redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
        app.config["RATELIMIT_STORAGE_URI"] = redis_url
    except (RedisError, OSError) as error:
        if app.config.get("APP_ENV") == "production":
            raise RuntimeError("Redis is required and must be reachable in production.") from error
        app.logger.warning("Redis unavailable; using development-only in-memory rate limiting.")
        app.config["RATELIMIT_STORAGE_URI"] = "memory://"


def _should_force_https(app):
    host = request.host.split(":", 1)[0].lower()
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    return (
        host not in local_hosts
        and (
            app.config.get("FORCE_HTTPS", False)
            or host.endswith(".pythonanywhere.com")
        )
    )


def _register_security_hooks(app):
    @app.before_request
    def redirect_to_https():
        if _should_force_https(app) and not request.is_secure:
            return redirect(request.url.replace(f"{request.scheme}://", "https://", 1), code=308)
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; img-src 'self' data:; media-src 'self' blob:; "
            "script-src 'self'; style-src 'self'; connect-src 'self'",
        )
        response.headers.setdefault("Cache-Control", "no-store" if request.path.startswith(("/auth", "/api")) else "private")
        if _should_force_https(app) or request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "Request is too large."}), 413

    @app.errorhandler(500)
    def internal_error(_error):
        return render_template("errors/500.html"), 500


def _ensure_user_profile_columns():
    existing_columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
    missing_columns = {
        "display_name": "VARCHAR(120)",
        "bio": "VARCHAR(280)",
        "profile_image": "VARCHAR(255)",
        "show_online_status": "BOOLEAN NOT NULL DEFAULT TRUE",
        "show_last_seen": "BOOLEAN NOT NULL DEFAULT TRUE",
        "message_permission": "VARCHAR(20) NOT NULL DEFAULT 'everyone'",
        "notification_messages": "BOOLEAN NOT NULL DEFAULT TRUE",
        "notification_requests": "BOOLEAN NOT NULL DEFAULT TRUE",
        "notification_sound": "BOOLEAN NOT NULL DEFAULT TRUE",
        "vibration_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "theme_mode": "VARCHAR(12) NOT NULL DEFAULT 'dark'",
        "accent_theme": "VARCHAR(12) NOT NULL DEFAULT 'purple'",
        "font_size": "VARCHAR(12) NOT NULL DEFAULT 'medium'",
        "auto_download_media": "BOOLEAN NOT NULL DEFAULT TRUE",
    }

    table_name = '"user"' if db.engine.dialect.name != "sqlite" else "user"
    for column_name, column_type in missing_columns.items():
        if column_name not in existing_columns:
            db.session.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            )
    db.session.commit()
