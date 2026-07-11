import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import click
from flask import current_app

from app.extensions import db
from app.models import Message


def _read(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise click.ClickException(f"Expected a JSON array in {path}")
    return value


def _parse_time(value):
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _backup(path):
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def import_json_messages(delete_originals=False):
    public_path = Path(current_app.config["MESSAGES_FILE"])
    private_path = Path(current_app.config["PRIVATE_MESSAGES_FILE"])
    public_records, private_records = _read(public_path), _read(private_path)
    backups = [_backup(path) for path in (public_path, private_path)]
    imported = 0

    for record in public_records:
        legacy_id = int(record.get("id", 0))
        if legacy_id <= 0 or Message.query.filter_by(legacy_source="public", legacy_id=legacy_id).first():
            continue
        db.session.add(Message(
            sender=str(record.get("username", "unknown"))[:80], room="public",
            body=str(record.get("message", "")), status="accepted",
            read_by=[str(record.get("username", "unknown"))[:80]], reactions={},
            created_at=_parse_time(record.get("time")), legacy_source="public", legacy_id=legacy_id,
        ))
        imported += 1

    private_by_legacy = {}
    for record in private_records:
        legacy_id = int(record.get("id", 0))
        existing = Message.query.filter_by(legacy_source="private", legacy_id=legacy_id).first()
        if existing:
            private_by_legacy[legacy_id] = existing
            continue
        sender = str(record.get("sender", "unknown"))[:80]
        item = Message(
            sender=sender, recipient=str(record.get("receiver", "unknown"))[:80], room="private",
            body=str(record.get("message", "")), message_type=str(record.get("message_type", "text"))[:20],
            audio=record.get("audio"), reactions=dict(record.get("reactions") or {}),
            status=str(record.get("status", "accepted"))[:20],
            requested_by=str(record.get("requested_by") or sender)[:80],
            read_by=list(record.get("read_by") or [sender]), created_at=_parse_time(record.get("time")),
            legacy_source="private", legacy_id=legacy_id,
        )
        db.session.add(item)
        db.session.flush()
        private_by_legacy[legacy_id] = item
        imported += 1

    for record in private_records:
        reply_id = record.get("reply_to")
        item = private_by_legacy.get(int(record.get("id", 0)))
        reply = private_by_legacy.get(int(reply_id)) if reply_id else None
        if item and reply:
            item.reply_to_id = reply.id

    db.session.commit()
    if delete_originals:
        for path, backup in zip((public_path, private_path), backups):
            if path.exists() and backup and backup.exists():
                path.unlink()
    return imported, [str(item) for item in backups if item]


@click.command("import-json-messages")
@click.option("--delete-originals", is_flag=True, help="Delete JSON originals after verified .bak copies exist.")
def import_json_messages_command(delete_originals):
    """Import legacy JSON chat history into the transactional database."""
    imported, backups = import_json_messages(delete_originals=delete_originals)
    click.echo(f"Imported {imported} messages. Backups: {', '.join(backups) or 'none'}")
