from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(120), nullable=True)
    bio = db.Column(db.String(280), nullable=True)
    profile_image = db.Column(db.String(255), nullable=True)
    show_online_status = db.Column(db.Boolean, nullable=False, default=True)
    show_last_seen = db.Column(db.Boolean, nullable=False, default=True)
    message_permission = db.Column(db.String(20), nullable=False, default="everyone")
    notification_messages = db.Column(db.Boolean, nullable=False, default=True)
    notification_requests = db.Column(db.Boolean, nullable=False, default=True)
    notification_sound = db.Column(db.Boolean, nullable=False, default=True)
    vibration_enabled = db.Column(db.Boolean, nullable=False, default=True)
    theme_mode = db.Column(db.String(12), nullable=False, default="dark")
    accent_theme = db.Column(db.String(12), nullable=False, default="purple")
    font_size = db.Column(db.String(12), nullable=False, default="medium")
    auto_download_media = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def display_label(self):
        return self.display_name or self.username
