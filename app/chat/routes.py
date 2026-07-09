import json

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    render_template,
    request,
    stream_with_context,
)
from flask_login import current_user, login_required

from app.chat.storage import (
    get_messages,
    get_private_messages,
    save_message,
    save_private_message,
    wait_for_messages_after,
)
from app.models import User


chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/")
@login_required
def index():
    return render_template("chat/index.html")


@chat_bp.get("/users")
@login_required
def user_search():
    query = request.args.get("q", "").strip()
    users = []

    if query:
        users = (
            User.query.filter(User.id != current_user.id)
            .filter(User.username.ilike(f"%{query}%"))
            .order_by(User.username.asc())
            .limit(20)
            .all()
        )

    return render_template("chat/users.html", query=query, users=users)


@chat_bp.get("/dm/<username>")
@login_required
def private_chat(username):
    other_user = User.query.filter_by(username=username).first_or_404()
    if other_user.id == current_user.id:
        return abort(404)

    return render_template("chat/private.html", other_user=other_user)


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

    messages = get_private_messages(current_user.username, other_user.username)
    response = jsonify(
        {
            "messages": [
                {
                    "id": message["id"],
                    "username": message["sender"],
                    "receiver": message["receiver"],
                    "time": message["time"],
                    "message": message["message"],
                }
                for message in messages
            ]
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
    return jsonify(
        {
            "message": {
                "id": message["id"],
                "username": message["sender"],
                "receiver": message["receiver"],
                "time": message["time"],
                "message": message["message"],
            }
        }
    ), 201


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
