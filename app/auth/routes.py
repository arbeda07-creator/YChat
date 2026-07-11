from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import User
from app.security import client_key, clear_rate_limit, is_safe_redirect, log_value, rate_limit


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
public_auth_bp = Blueprint("public_auth", __name__)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
USERNAME_RE = __import__("re").compile(r"^[A-Za-z0-9_.-]{3,40}$")


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


def _strong_password(password):
    return (12 <= len(password) <= 128 and any(c.islower() for c in password)
            and any(c.isupper() for c in password) and any(c.isdigit() for c in password))


def _rotate_session():
    csrf = session.get("_csrf_token")
    session.clear()
    if csrf:
        session["_csrf_token"] = csrf
    session["last_seen"] = int(__import__("time").time())
    session.permanent = True


@public_auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().casefold()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
        elif not USERNAME_RE.fullmatch(username):
            flash("Username must be 3-40 characters using letters, numbers, dot, dash, or underscore.", "error")
        elif not _strong_password(password):
            flash("Password must be 12-128 characters and include upper, lower, and numeric characters.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        elif User.query.filter(db.func.lower(User.username) == username.casefold()).first():
            flash("Registration could not be completed with those details.", "error")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            _rotate_session()
            login_user(user, fresh=True)
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
        normalized_username = username.casefold()
        key = client_key(normalized_username)
        if not rate_limit("login", key, current_app.config["LOGIN_FAILURE_LIMIT"], current_app.config["LOGIN_LOCKOUT_SECONDS"]):
            current_app.logger.warning("login_rate_limited remote=%s account=%s", log_value(request.remote_addr), log_value(username))
            flash("Sign-in is temporarily unavailable. Please try again later.", "error")
            return render_template("auth/login.html"), 429
        user = User.query.filter(db.func.lower(User.username) == normalized_username).first()

        if user and user.check_password(password):
            clear_rate_limit("login", key)
            _rotate_session()
            login_user(user, fresh=True)
            flash("You are signed in.", "success")
            next_page = request.args.get("next")
            return redirect(next_page if next_page and is_safe_redirect(next_page) else url_for("chat.index"))

        current_app.logger.warning("login_failed remote=%s account=%s", log_value(request.remote_addr), log_value(username))
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

                image.stream.seek(0, 2)
                size = image.stream.tell()
                image.stream.seek(0)
                if size <= 0 or size > current_app.config["MAX_PROFILE_IMAGE_BYTES"]:
                    flash("Profile image is empty or too large.", "error")
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
    session.clear()
    flash("You are signed out.", "info")
    return redirect(url_for("auth.login"))
