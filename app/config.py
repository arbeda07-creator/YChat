import os
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
    SECRET_KEY = os.environ.get("SECRET_KEY")
    MESSAGES_FILE = os.environ.get("MESSAGES_FILE", str(BASE_DIR / "messages.json"))
    PRIVATE_MESSAGES_FILE = os.environ.get(
        "PRIVATE_MESSAGES_FILE",
        str(BASE_DIR / "instance" / "private_messages.json"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False


class DevelopmentConfig(Config):
    SECRET_KEY = Config.SECRET_KEY or "dev-change-me"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'ychat.sqlite3'}"


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.environ.get("DATABASE_URL"))
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"

    @classmethod
    def init_app(cls):
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set in production.")
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL must be set in production.")


def get_config():
    app_env = os.environ.get("APP_ENV", "development").lower()

    if app_env == "production":
        ProductionConfig.init_app()
        return ProductionConfig

    return DevelopmentConfig
