from flask_login import LoginManager
from flask_limiter import Limiter
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(key_func=lambda: "global", default_limits=[])
