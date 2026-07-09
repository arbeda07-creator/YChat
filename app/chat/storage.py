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


def get_private_messages(username_a, username_b):
    with _file_lock:
        return [
            message
            for message in _read_messages(_private_messages_path())
            if _conversation_matches(message, username_a, username_b)
        ]


def save_private_message(sender, receiver, body):
    path = _private_messages_path()

    with _file_lock:
        messages = _read_messages(path)
        message = {
            "id": max((item.get("id", 0) for item in messages), default=0) + 1,
            "sender": sender,
            "receiver": receiver,
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

    return message


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
