from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
public_auth_bp = Blueprint("public_auth", __name__)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def _is_allowed_image(file_storage):
    filename = secure_filename(file_storage.filename or "")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return False, extension

    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    is_image = (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"GIF87a")
        or header.startswith(b"GIF89a")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )
    if not is_image:
        return False, extension

    return True, extension


@public_auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
        elif len(username) < 3:
            flash("Username must be at least 3 characters.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Welcome to YChat 2.0.", "success")
            return redirect(url_for("chat.index"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash("You are signed in.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("chat.index"))

        flash("Invalid username or password.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        bio = request.form.get("bio", "").strip()
        image = request.files.get("profile_image")

        if len(display_name) > 120:
            flash("Display name is too long.", "error")
        elif len(bio) > 280:
            flash("Bio is too long.", "error")
        else:
            current_user.display_name = display_name or None
            current_user.bio = bio or None

            if image and image.filename:
                is_allowed, extension = _is_allowed_image(image)
                if not is_allowed:
                    flash("Please upload a valid image file.", "error")
                    return render_template("auth/profile.html")

                upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
                upload_dir.mkdir(parents=True, exist_ok=True)
                filename = f"user-{current_user.id}-{uuid4().hex}.{extension}"
                image.save(upload_dir / filename)
                current_user.profile_image = filename

            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You are signed out.", "info")
    return redirect(url_for("auth.login"))
