from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Message


chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        body = request.form.get("body", "").strip()

        if not body:
            flash("Message cannot be empty.", "error")
        elif len(body) > 2000:
            flash("Message is too long.", "error")
        else:
            message = Message(body=body, author=current_user)
            db.session.add(message)
            db.session.commit()
            return redirect(url_for("chat.index"))

    messages = (
        Message.query.order_by(Message.created_at.asc(), Message.id.asc())
        .limit(100)
        .all()
    )
    return render_template("chat/index.html", messages=messages)
