import json
from pathlib import Path
from uuid import uuid4

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    stream_with_context,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.chat.storage import (
    accept_message_request,
    delete_private_conversation,
    delete_private_message,
    get_conversation_status,
    get_messages,
    get_private_inbox,
    get_private_messages,
    mark_private_messages_read,
    reject_message_request,
    save_message,
    save_private_message,
    set_private_reaction,
    wait_for_messages_after,
)
from app.models import User


chat_bp = Blueprint("chat", __name__)
ALLOWED_REACTIONS = {"❤️", "😂", "👍", "😮", "😢", "🔥"}
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "m4a",
}


@chat_bp.route("/")
@login_required
def index():
    query = request.args.get("q", "").strip()
    users = _search_users(query)
    inbox = _enrich_inbox(get_private_inbox(current_user.username))
    return render_template(
        "chat/index.html",
        active_tab="private",
        inbox=inbox,
        query=query,
        users=users,
    )


@chat_bp.get("/requests")
@login_required
def message_requests():
    query = request.args.get("q", "").strip()
    inbox = _enrich_inbox(get_private_inbox(current_user.username))
    return render_template(
        "chat/requests.html",
        active_tab="requests",
        inbox=inbox,
        query=query,
    )


def _search_users(query):
    if not query:
        return []

    return (
        User.query.filter(User.id != current_user.id)
        .filter(User.username.ilike(f"%{query}%"))
        .order_by(User.username.asc())
        .limit(20)
        .all()
    )


def _reaction_payload(reactions):
    grouped = {}
    for emoji in reactions.values():
        grouped[emoji] = grouped.get(emoji, 0) + 1
    return [
        {"emoji": emoji, "count": count}
        for emoji, count in grouped.items()
    ]


def _reply_payload(message, messages_by_id, user_cards):
    reply_to = message.get("reply_to")
    if not reply_to:
        return None

    original = messages_by_id.get(int(reply_to))
    if not original:
        return {
            "id": reply_to,
            "deleted": True,
            "display_name": "Deleted message",
            "message": "",
            "message_type": "deleted",
        }

    sender = user_cards.get(original["sender"]) or _user_card(original["sender"])
    return {
        "id": original["id"],
        "deleted": False,
        "username": original["sender"],
        "display_name": sender["display_name"],
        "message": original.get("message") or "Voice message",
        "message_type": original.get("message_type", "text"),
    }


def _message_payload(message, user_cards=None, messages_by_id=None):
    user_cards = user_cards or {}
    messages_by_id = messages_by_id or {}
    sender = user_cards.get(message["sender"]) or _user_card(message["sender"])
    reactions = message.get("reactions", {})
    return {
        "id": message["id"],
        "username": message["sender"],
        "display_name": sender["display_name"],
        "avatar_url": sender["avatar_url"],
        "initial": sender["initial"],
        "receiver": message["receiver"],
        "time": message["time"],
        "message": message.get("message", ""),
        "message_type": message.get("message_type", "text"),
        "audio_url": message.get("audio", {}).get("url") if message.get("audio") else None,
        "audio_name": message.get("audio", {}).get("filename") if message.get("audio") else None,
        "reply": _reply_payload(message, messages_by_id, user_cards),
        "reactions": _reaction_payload(reactions),
        "my_reaction": reactions.get(current_user.username),
        "is_read": (
            message["sender"] == current_user.username
            and message["receiver"] in message.get("read_by", [])
        ),
    }


def _message_payloads(messages, *usernames):
    user_cards = {username: _user_card(username) for username in usernames}
    messages_by_id = {int(message.get("id", 0)): message for message in messages}
    return [_message_payload(message, user_cards, messages_by_id) for message in messages]


def _user_card(username):
    user = User.query.filter_by(username=username).first()
    display_name = user.display_label if user else username
    profile_image = user.profile_image if user else None
    return {
        "username": username,
        "display_name": display_name,
        "avatar_url": url_for("static", filename=f"uploads/{profile_image}")
        if profile_image
        else None,
        "initial": (display_name or username)[:1].upper(),
        "bio": user.bio if user else None,
    }


def _enrich_inbox(inbox):
    for collection_name in ("private", "requests"):
        for conversation in inbox[collection_name]:
            conversation.update(_user_card(conversation["username"]))
    return inbox


def _save_voice_upload(file_storage):
    content_type = (file_storage.mimetype or "").split(";")[0].lower()
    extension = ALLOWED_AUDIO_MIME_TYPES.get(content_type)
    if not extension:
        return None, "Please upload a valid audio recording."

    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size <= 0:
        return None, "Voice message is empty."
    if size > 2 * 1024 * 1024:
        return None, "Voice message is too large."

    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    voice_dir = upload_root / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    original = secure_filename(file_storage.filename or f"voice.{extension}")
    filename = f"voice-{current_user.id}-{uuid4().hex}.{extension}"
    file_storage.save(voice_dir / filename)
    return {
        "filename": filename,
        "original_name": original,
        "content_type": content_type,
        "size": size,
        "url": url_for("static", filename=f"uploads/voice/{filename}"),
    }, None


@chat_bp.get("/users")
@login_required
def user_search():
    query = request.args.get("q", "").strip()
    users = _search_users(query)

    return render_template("chat/users.html", query=query, users=users)


@chat_bp.get("/dm/<username>")
@login_required
def private_chat(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    status = get_conversation_status(current_user.username, other_user.username)
    return render_template(
        "chat/private.html",
        other_user=other_user,
        conversation_status=status,
    )


@chat_bp.get("/api/messages")
@login_required
def messages_api():
    response = jsonify({"messages": get_messages()})
    response.headers["Cache-Control"] = "no-store"
    return response


@chat_bp.get("/api/dm/<username>/messages")
@login_required
def private_messages_api(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    status = get_conversation_status(current_user.username, other_user.username)
    messages = get_private_messages(
        current_user.username,
        other_user.username,
        include_pending=status == "pending",
    )
    if status == "accepted":
        mark_private_messages_read(current_user.username, other_user.username)

    response = jsonify(
        {
            "status": status,
            "messages": _message_payloads(
                messages,
                current_user.username,
                other_user.username,
            ),
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@chat_bp.post("/api/dm/<username>/send")
@login_required
def send_private_api(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        payload = request.form
    else:
        payload = request.get_json(silent=True) or request.form

    body = str(payload.get("message", "")).strip()
    reply_to = payload.get("reply_to") or None
    audio = None
    audio_file = request.files.get("voice")

    if audio_file and audio_file.filename:
        audio, error = _save_voice_upload(audio_file)
        if error:
            return jsonify({"error": error}), 400

    if not body and not audio:
        return jsonify({"error": "Message cannot be empty."}), 400
    if len(body) > 2000:
        return jsonify({"error": "Message is too long."}), 400

    message = save_private_message(
        current_user.username,
        other_user.username,
        body,
        reply_to=reply_to,
        audio=audio,
    )
    if not message:
        return jsonify({"error": "This message request was rejected."}), 403

    return jsonify({"message": _message_payload(message)}), 201


@chat_bp.post("/api/dm/<username>/messages/<int:message_id>/reaction")
@login_required
def react_private_message_api(username, message_id):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    payload = request.get_json(silent=True) or request.form
    emoji = str(payload.get("emoji", "")).strip()
    if emoji not in ALLOWED_REACTIONS:
        return jsonify({"error": "Reaction is not allowed."}), 400

    message = set_private_reaction(
        current_user.username,
        other_user.username,
        message_id,
        emoji,
    )
    if not message:
        return jsonify({"error": "Message was not found."}), 404

    return jsonify({"message": _message_payload(message)})


@chat_bp.delete("/api/dm/<username>/messages/<int:message_id>")
@login_required
def delete_private_message_api(username, message_id):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    if not delete_private_message(current_user.username, other_user.username, message_id):
        return jsonify({"error": "Message was not found."}), 404

    return jsonify({"ok": True})


@chat_bp.delete("/api/dm/<username>/conversation")
@login_required
def delete_private_conversation_api(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    delete_private_conversation(current_user.username, other_user.username)
    return jsonify({"ok": True, "redirect": url_for("chat.index")})


@chat_bp.post("/api/dm/<username>/accept")
@login_required
def accept_private_request_api(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    if not accept_message_request(current_user.username, other_user.username):
        return jsonify({"error": "Message request was not found."}), 404

    return jsonify({"ok": True, "redirect": url_for("chat.private_chat", username=username)})


@chat_bp.post("/api/dm/<username>/reject")
@login_required
def reject_private_request_api(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    if not reject_message_request(current_user.username, other_user.username):
        return jsonify({"error": "Message request was not found."}), 404

    return jsonify({"ok": True})


@chat_bp.get("/api/dm/summary")
@login_required
def private_summary_api():
    response = jsonify(_enrich_inbox(get_private_inbox(current_user.username)))
    response.headers["Cache-Control"] = "no-store"
    return response


@chat_bp.get("/api/messages/stream")
@login_required
def messages_stream_api():
    last_id = request.args.get("last_id", default=0, type=int) or 0

    def stream_messages():
        current_last_id = last_id

        while True:
            messages = wait_for_messages_after(current_last_id)

            if not messages:
                yield ": keep-alive\n\n"
                continue

            current_last_id = max(
                int(message.get("id", current_last_id)) for message in messages
            )
            data = json.dumps({"messages": messages})
            yield f"event: messages\ndata: {data}\n\n"

    response = Response(stream_with_context(stream_messages()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@chat_bp.post("/api/send")
@login_required
def send_api():
    payload = request.get_json(silent=True) or request.form
    body = str(payload.get("message", "")).strip()

    if not body:
        return jsonify({"error": "Message cannot be empty."}), 400
    if len(body) > 2000:
        return jsonify({"error": "Message is too long."}), 400

    message = save_message(current_user.username, body)
    return jsonify({"message": message}), 201
