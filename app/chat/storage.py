import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


_file_lock = threading.Lock()
_message_condition = threading.Condition()


def _messages_path():
    from flask import current_app

    return Path(current_app.config["MESSAGES_FILE"])


def _private_messages_path():
    from flask import current_app

    return Path(current_app.config["PRIVATE_MESSAGES_FILE"])


def _read_messages(path):
    try:
        with path.open("r", encoding="utf-8") as messages_file:
            data = json.load(messages_file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    return data if isinstance(data, list) else []


def get_messages():
    with _file_lock:
        return _read_messages(_messages_path())


def get_messages_after(last_id):
    with _file_lock:
        return [
            message
            for message in _read_messages(_messages_path())
            if int(message.get("id", 0)) > last_id
        ]


def wait_for_messages_after(last_id, timeout=15):
    with _message_condition:
        _message_condition.wait(timeout=timeout)

    return get_messages_after(last_id)


def _conversation_matches(message, username_a, username_b):
    sender = message.get("sender")
    receiver = message.get("receiver")
    return (
        sender == username_a
        and receiver == username_b
    ) or (
        sender == username_b
        and receiver == username_a
    )


def _private_messages():
    records = _read_messages(_private_messages_path())
    for record in records:
        record.setdefault("status", "accepted")
        record.setdefault("requested_by", record.get("sender"))
        record.setdefault("read_by", [record.get("sender")])
    return records


def _write_private_messages(path, messages):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as messages_file:
        json.dump(messages, messages_file, ensure_ascii=False, indent=2)
        messages_file.flush()
        os.fsync(messages_file.fileno())
    os.replace(temporary_path, path)


def _conversation_records(messages, username_a, username_b):
    return [
        message
        for message in messages
        if _conversation_matches(message, username_a, username_b)
    ]


def get_conversation_status(username_a, username_b):
    with _file_lock:
        records = _conversation_records(_private_messages(), username_a, username_b)

    if not records:
        return None
    if any(message.get("status") == "accepted" for message in records):
        return "accepted"
    if any(message.get("status") == "pending" for message in records):
        return "pending"
    return records[-1].get("status")


def get_private_messages(username_a, username_b, include_pending=False):
    allowed_statuses = {"accepted"}
    if include_pending:
        allowed_statuses.add("pending")

    with _file_lock:
        return [
            message
            for message in _conversation_records(_private_messages(), username_a, username_b)
            if message.get("status") in allowed_statuses
        ]


def get_private_inbox(username):
    with _file_lock:
        messages = _private_messages()

    conversations = {}
    request_count = 0

    for message in messages:
        status = message.get("status")
        sender = message.get("sender")
        receiver = message.get("receiver")
        if username not in {sender, receiver}:
            continue

        if status == "pending":
            if receiver == username:
                key = sender
                existing = conversations.get(key)
                if not existing or message["id"] > existing["last_message"]["id"]:
                    conversations[key] = {
                        "type": "request",
                        "username": sender,
                        "last_message": message,
                        "unread": 1,
                    }
            continue

        if status != "accepted":
            continue

        other_user = receiver if sender == username else sender
        existing = conversations.get(other_user)
        unread_increment = (
            1
            if receiver == username and username not in message.get("read_by", [])
            else 0
        )
        if not existing:
            conversations[other_user] = {
                "type": "private",
                "username": other_user,
                "last_message": message,
                "unread": unread_increment,
            }
        else:
            existing["unread"] += unread_increment
            if message["id"] > existing["last_message"]["id"]:
                existing["last_message"] = message

    private_conversations = [
        conversation
        for conversation in conversations.values()
        if conversation["type"] == "private"
    ]
    message_requests = [
        conversation
        for conversation in conversations.values()
        if conversation["type"] == "request"
    ]
    request_count = len(message_requests)

    return {
        "private": sorted(
            private_conversations,
            key=lambda item: item["last_message"]["id"],
            reverse=True,
        ),
        "requests": sorted(
            message_requests,
            key=lambda item: item["last_message"]["id"],
            reverse=True,
        ),
        "request_count": request_count,
        "private_unread_count": sum(item["unread"] for item in private_conversations),
    }


def mark_private_messages_read(username, other_username):
    path = _private_messages_path()
    changed = False

    with _file_lock:
        messages = _private_messages()
        for message in messages:
            if (
                _conversation_matches(message, username, other_username)
                and message.get("receiver") == username
                and message.get("status") == "accepted"
                and username not in message.get("read_by", [])
            ):
                message.setdefault("read_by", []).append(username)
                changed = True
        if changed:
            _write_private_messages(path, messages)

    return changed


def save_private_message(sender, receiver, body):
    path = _private_messages_path()

    with _file_lock:
        messages = _private_messages()
        current_records = _conversation_records(messages, sender, receiver)
        if any(message.get("status") == "rejected" for message in current_records):
            return None
        status = "accepted" if any(
            message.get("status") == "accepted" for message in current_records
        ) else "pending"
        message = {
            "id": max((item.get("id", 0) for item in messages), default=0) + 1,
            "sender": sender,
            "receiver": receiver,
            "time": datetime.now(timezone.utc).isoformat(),
            "message": body,
            "status": status,
            "requested_by": current_records[0].get("requested_by", sender)
            if current_records
            else sender,
            "read_by": [sender],
        }
        messages.append(message)
        _write_private_messages(path, messages)

    return message


def accept_message_request(receiver, requester):
    path = _private_messages_path()
    changed = False

    with _file_lock:
        messages = _private_messages()
        for message in messages:
            if (
                _conversation_matches(message, receiver, requester)
                and message.get("status") == "pending"
                and message.get("receiver") == receiver
            ):
                message["status"] = "accepted"
                changed = True
        if changed:
            _write_private_messages(path, messages)

    return changed


def reject_message_request(receiver, requester):
    path = _private_messages_path()

    with _file_lock:
        messages = _private_messages()
        next_messages = [
            message
            for message in messages
            if not (
                _conversation_matches(message, receiver, requester)
                and message.get("status") == "pending"
                and message.get("receiver") == receiver
            )
        ]
        changed = len(next_messages) != len(messages)
        if changed:
            _write_private_messages(path, next_messages)

    return changed


def delete_private_message(username, other_username, message_id):
    path = _private_messages_path()

    with _file_lock:
        messages = _private_messages()
        next_messages = [
            message
            for message in messages
            if not (
                int(message.get("id", 0)) == message_id
                and _conversation_matches(message, username, other_username)
            )
        ]
        changed = len(next_messages) != len(messages)
        if changed:
            _write_private_messages(path, next_messages)

    return changed


def delete_private_conversation(username, other_username):
    path = _private_messages_path()

    with _file_lock:
        messages = _private_messages()
        next_messages = [
            message
            for message in messages
            if not _conversation_matches(message, username, other_username)
        ]
        changed = len(next_messages) != len(messages)
        if changed:
            _write_private_messages(path, next_messages)

    return changed


def save_message(username, body):
    path = _messages_path()

    with _file_lock:
        messages = _read_messages(path)
        message = {
            "id": max((item.get("id", 0) for item in messages), default=0) + 1,
            "username": username,
            "time": datetime.now(timezone.utc).isoformat(),
            "message": body,
        }
        messages.append(message)

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        with temporary_path.open("w", encoding="utf-8") as messages_file:
            json.dump(messages, messages_file, ensure_ascii=False, indent=2)
            messages_file.flush()
            os.fsync(messages_file.fileno())
        os.replace(temporary_path, path)

    with _message_condition:
        _message_condition.notify_all()

    return message
