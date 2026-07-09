import json

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context
from flask_login import current_user, login_required

from app.chat.storage import get_messages, save_message, wait_for_messages_after


chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/")
@login_required
def index():
    return render_template("chat/index.html")


@chat_bp.get("/api/messages")
@login_required
def messages_api():
    response = jsonify({"messages": get_messages()})
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
