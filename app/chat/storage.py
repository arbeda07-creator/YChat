import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


_file_lock = threading.Lock()


def _messages_path():
    from flask import current_app

    return Path(current_app.config["MESSAGES_FILE"])


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

    return message
