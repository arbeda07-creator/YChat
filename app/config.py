import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent


def normalize_database_url(database_url):
    if database_url and database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url and database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development").lower()
    SECRET_KEY = os.environ.get("SECRET_KEY")
    MESSAGES_FILE = os.environ.get("MESSAGES_FILE", str(BASE_DIR / "messages.json"))
    PRIVATE_MESSAGES_FILE = os.environ.get(
        "PRIVATE_MESSAGES_FILE",
        str(BASE_DIR / "instance" / "private_messages.json"),
    )
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "instance" / "uploads"))
    # Keep enough room for multipart form metadata around the uploaded file.
    MAX_CONTENT_LENGTH = 9 * 1024 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_NAME = "ychat_session"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_REFRESH_EACH_REQUEST = True
    MAX_MESSAGE_LENGTH = 2000
    MAX_VOICE_BYTES = 2 * 1024 * 1024
    MAX_PROFILE_IMAGE_BYTES = 8 * 1024 * 1024
    LOGIN_FAILURE_LIMIT = 5
    LOGIN_LOCKOUT_SECONDS = 300
    TRUST_PROXY_HEADERS = False
    REDIS_URL = os.environ.get("REDIS_URL")
    RATELIMIT_STORAGE_URI = REDIS_URL or "memory://"
    FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "").lower() in {"1", "true", "yes"}


class DevelopmentConfig(Config):
    SECRET_KEY = Config.SECRET_KEY or "dev-change-me"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'ychat.sqlite3'}"


class ProductionConfig(Config):
    APP_ENV = "production"
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.environ.get("DATABASE_URL"))
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    FORCE_HTTPS = True
    TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "").lower() in {"1", "true", "yes"}

    @classmethod
    def init_app(cls):
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set in production.")
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL must be set in production.")
        if not cls.REDIS_URL:
            raise RuntimeError("REDIS_URL must be set in production for shared rate limiting.")


def get_config():
    app_env = os.environ.get("APP_ENV", "development").lower()

    if app_env == "production":
        ProductionConfig.init_app()
        return ProductionConfig

    return DevelopmentConfig
