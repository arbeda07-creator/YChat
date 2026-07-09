from flask import Flask, redirect, request
from pathlib import Path
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import get_config
from app.extensions import db, login_manager


def create_app(config_class=None):
    app = Flask(__name__, instance_relative_config=True)
    config_class = config_class or get_config()
    app.config.from_object(config_class)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
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
    _register_security_hooks(app)

    with app.app_context():
        db.create_all()
        _ensure_user_profile_columns()

    return app


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
        if _should_force_https(app) or request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


def _ensure_user_profile_columns():
    existing_columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
    missing_columns = {
        "display_name": "VARCHAR(120)",
        "bio": "VARCHAR(280)",
        "profile_image": "VARCHAR(255)",
    }

    table_name = '"user"' if db.engine.dialect.name != "sqlite" else "user"
    for column_name, column_type in missing_columns.items():
        if column_name not in existing_columns:
            db.session.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            )
    db.session.commit()
