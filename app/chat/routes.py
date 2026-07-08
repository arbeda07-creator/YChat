from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from app.chat.storage import get_messages, save_message


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
