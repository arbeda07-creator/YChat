import json

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    render_template,
    request,
    stream_with_context,
    url_for,
)
from flask_login import current_user, login_required
from flask_socketio import join_room

from app.chat.storage import (
    accept_message_request,
    get_conversation_status,
    get_messages,
    get_private_inbox,
    get_private_messages,
    mark_private_messages_read,
    reject_message_request,
    save_message,
    save_private_message,
    wait_for_messages_after,
)
from app.extensions import socketio
from app.models import User


chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/")
@login_required
def index():
    query = request.args.get("q", "").strip()
    users = _search_users(query)
    inbox = get_private_inbox(current_user.username)
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
    inbox = get_private_inbox(current_user.username)
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


def _message_payload(message):
    return {
        "id": message["id"],
        "username": message["sender"],
        "receiver": message["receiver"],
        "time": message["time"],
        "message": message["message"],
    }


def _emit_dm_updates(*usernames):
    for username in set(usernames):
        socketio.emit(
            "dm_update",
            get_private_inbox(username),
            to=username,
        )


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
        _emit_dm_updates(current_user.username)

    response = jsonify(
        {
            "status": status,
            "messages": [_message_payload(message) for message in messages],
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

    payload = request.get_json(silent=True) or request.form
    body = str(payload.get("message", "")).strip()

    if not body:
        return jsonify({"error": "Message cannot be empty."}), 400
    if len(body) > 2000:
        return jsonify({"error": "Message is too long."}), 400

    message = save_private_message(current_user.username, other_user.username, body)
    if not message:
        return jsonify({"error": "This message request was rejected."}), 403

    _emit_dm_updates(current_user.username, other_user.username)
    socketio.emit("private_message", _message_payload(message), to=current_user.username)
    socketio.emit("private_message", _message_payload(message), to=other_user.username)
    return jsonify({"message": _message_payload(message)}), 201


@chat_bp.post("/api/dm/<username>/accept")
@login_required
def accept_private_request_api(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    if not accept_message_request(current_user.username, other_user.username):
        return jsonify({"error": "Message request was not found."}), 404

    _emit_dm_updates(current_user.username, other_user.username)
    return jsonify({"ok": True, "redirect": url_for("chat.private_chat", username=username)})


@chat_bp.post("/api/dm/<username>/reject")
@login_required
def reject_private_request_api(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    if not reject_message_request(current_user.username, other_user.username):
        return jsonify({"error": "Message request was not found."}), 404

    _emit_dm_updates(current_user.username, other_user.username)
    return jsonify({"ok": True})


@chat_bp.get("/api/dm/summary")
@login_required
def private_summary_api():
    response = jsonify(get_private_inbox(current_user.username))
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


@socketio.on("connect")
def socket_connect():
    if current_user.is_authenticated:
        join_room(current_user.username)
        socketio.emit("dm_update", get_private_inbox(current_user.username))
