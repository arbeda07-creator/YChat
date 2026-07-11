import threading
from datetime import datetime, timezone

from sqlalchemy import and_, or_

from app.extensions import db
from app.models import Message


_message_condition = threading.Condition()


def _iso(value):
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _record(message):
    if message.room == "public":
        return {
            "id": message.id,
            "username": message.sender,
            "time": _iso(message.created_at),
            "message": message.body,
        }
    return {
        "id": message.id,
        "sender": message.sender,
        "receiver": message.recipient,
        "time": _iso(message.created_at),
        "message": message.body,
        "message_type": message.message_type or "text",
        "audio": message.audio,
        "reply_to": message.reply_to_id,
        "reactions": dict(message.reactions or {}),
        "status": message.status or "accepted",
        "requested_by": message.requested_by or message.sender,
        "read_by": list(message.read_by or [message.sender]),
    }


def _conversation_filter(username_a, username_b):
    return or_(
        and_(Message.sender == username_a, Message.recipient == username_b),
        and_(Message.sender == username_b, Message.recipient == username_a),
    )


def _conversation_query(username_a, username_b):
    return Message.query.filter(Message.room == "private").filter(
        _conversation_filter(username_a, username_b)
    )


def get_messages():
    return [_record(item) for item in Message.query.filter_by(room="public").order_by(Message.id).all()]


def get_messages_after(last_id):
    return [
        _record(item)
        for item in Message.query.filter(Message.room == "public", Message.id > last_id)
        .order_by(Message.id).all()
    ]


def wait_for_messages_after(last_id, timeout=15):
    # The database is authoritative. This local condition only reduces latency in a
    # single worker; every wake/timeout re-queries shared storage.
    with _message_condition:
        _message_condition.wait(timeout=timeout)
    return get_messages_after(last_id)


def get_conversation_status(username_a, username_b):
    records = _conversation_query(username_a, username_b).order_by(Message.id).all()
    statuses = {item.status for item in records}
    if not records:
        return None
    if "accepted" in statuses:
        return "accepted"
    if "pending" in statuses:
        return "pending"
    return records[-1].status


def get_private_messages(username_a, username_b, include_pending=False):
    statuses = ["accepted", "pending"] if include_pending else ["accepted"]
    records = _conversation_query(username_a, username_b).filter(Message.status.in_(statuses)).order_by(Message.id).all()
    return [_record(item) for item in records]


def get_private_inbox(username):
    records = Message.query.filter(
        Message.room == "private",
        or_(Message.sender == username, Message.recipient == username),
    ).order_by(Message.id).all()
    conversations = {}
    for item in records:
        message = _record(item)
        status, sender, receiver = item.status, item.sender, item.recipient
        if status == "pending":
            if receiver == username:
                existing = conversations.get(sender)
                if not existing or item.id > existing["last_message"]["id"]:
                    conversations[sender] = {"type": "request", "username": sender, "last_message": message, "unread": 1}
            continue
        if status != "accepted":
            continue
        other = receiver if sender == username else sender
        unread = 1 if receiver == username and username not in (item.read_by or []) else 0
        existing = conversations.get(other)
        if not existing:
            conversations[other] = {"type": "private", "username": other, "last_message": message, "unread": unread}
        else:
            existing["unread"] += unread
            if item.id > existing["last_message"]["id"]:
                existing["last_message"] = message
    private = [item for item in conversations.values() if item["type"] == "private"]
    requests = [item for item in conversations.values() if item["type"] == "request"]
    return {
        "private": sorted(private, key=lambda item: item["last_message"]["id"], reverse=True),
        "requests": sorted(requests, key=lambda item: item["last_message"]["id"], reverse=True),
        "request_count": len(requests),
        "private_unread_count": sum(item["unread"] for item in private),
    }


def mark_private_messages_read(username, other_username):
    records = _conversation_query(username, other_username).filter_by(
        recipient=username, status="accepted"
    ).all()
    changed = False
    for item in records:
        read_by = list(item.read_by or [])
        if username not in read_by:
            item.read_by = read_by + [username]
            changed = True
    if changed:
        db.session.commit()
    return changed


def _find_conversation_message(username_a, username_b, message_id):
    try:
        target_id = int(message_id)
    except (TypeError, ValueError):
        return None
    return _conversation_query(username_a, username_b).filter_by(id=target_id).first()


def save_private_message(sender, receiver, body, reply_to=None, audio=None):
    current = _conversation_query(sender, receiver).order_by(Message.id).all()
    if any(item.status == "rejected" for item in current):
        return None
    status = "accepted" if any(item.status == "accepted" for item in current) else "pending"
    reply = _find_conversation_message(sender, receiver, reply_to)
    item = Message(
        sender=sender, recipient=receiver, room="private", body=body,
        message_type="voice" if audio else "text", audio=audio,
        reply_to_id=reply.id if reply else None, reactions={}, status=status,
        requested_by=current[0].requested_by if current else sender, read_by=[sender],
    )
    db.session.add(item)
    db.session.commit()
    return _record(item)


def set_private_reaction(username, other_username, message_id, emoji):
    item = _find_conversation_message(username, other_username, message_id)
    if not item or item.status != "accepted":
        return None
    reactions = dict(item.reactions or {})
    if reactions.get(username) == emoji:
        reactions.pop(username, None)
    else:
        reactions[username] = emoji
    item.reactions = reactions
    db.session.commit()
    return _record(item)


def accept_message_request(receiver, requester):
    records = _conversation_query(receiver, requester).filter_by(recipient=receiver, status="pending").all()
    if not records:
        return False
    for item in records:
        item.status = "accepted"
    db.session.commit()
    return True


def reject_message_request(receiver, requester):
    count = _conversation_query(receiver, requester).filter_by(recipient=receiver, status="pending").delete(synchronize_session=False)
    db.session.commit()
    return bool(count)


def delete_private_message(username, other_username, message_id):
    item = _find_conversation_message(username, other_username, message_id)
    if not item or item.sender != username:
        return False
    db.session.delete(item)
    db.session.commit()
    return True


def delete_private_conversation(username, other_username):
    count = _conversation_query(username, other_username).delete(synchronize_session=False)
    db.session.commit()
    return bool(count)


def save_message(username, body):
    item = Message(sender=username, recipient=None, room="public", body=body, status="accepted", read_by=[username], reactions={})
    db.session.add(item)
    db.session.commit()
    with _message_condition:
        _message_condition.notify_all()
    return _record(item)
