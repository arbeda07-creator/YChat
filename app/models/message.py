from datetime import datetime, timezone

from app.extensions import db


class Message(db.Model):
    __tablename__ = "chat_message"

    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(80), nullable=False, index=True)
    recipient = db.Column(db.String(80), nullable=True, index=True)
    room = db.Column(db.String(80), nullable=False, default="public", index=True)
    body = db.Column(db.Text, nullable=False, default="")
    message_type = db.Column(db.String(20), nullable=False, default="text")
    status = db.Column(db.String(20), nullable=False, default="accepted", index=True)
    requested_by = db.Column(db.String(80), nullable=True)
    read_by = db.Column(db.JSON, nullable=False, default=list)
    reactions = db.Column(db.JSON, nullable=False, default=dict)
    audio = db.Column(db.JSON, nullable=True)
    reply_to_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_message.id", ondelete="SET NULL"),
        nullable=True,
    )
    legacy_source = db.Column(db.String(32), nullable=True)
    legacy_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    reply_to = db.relationship("Message", remote_side=[id])

    __table_args__ = (
        db.UniqueConstraint("legacy_source", "legacy_id", name="uq_chat_message_legacy"),
        db.Index("ix_chat_conversation", "sender", "recipient", "created_at"),
    )
