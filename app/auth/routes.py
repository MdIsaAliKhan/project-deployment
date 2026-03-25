"""
auth/routes.py
──────────────
Complete face-authentication implementation:
  • Registration  → capture webcam frame → encode → store as JSON in LONGTEXT column
  • Login (step 1)→ password check (werkzeug hashed)
  • Login (step 2)→ live frame → encode → compare vs stored encoding (tolerance 0.45)
  • Single-face enforcement, no-face handling, proper camera release (JS-side)
"""

import json
import base64
import io
from functools import wraps

import numpy as np
from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import get_db_connection, login_manager
from app.models import User

# ── optional face-recognition import ─────────────────────────────────────────
try:
    import face_recognition
    from PIL import Image
    FACE_LIB_AVAILABLE = True
except ImportError:
    FACE_LIB_AVAILABLE = False

auth_bp = Blueprint("auth", __name__)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def role_required(role):
    """Decorator: restrict route to users with a specific session role."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") != role:
                return redirect(url_for("auth.login"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def redirect_by_role(role: str):
    routes = {"admin": "/admin/dashboard", "teacher": "/teacher/dashboard"}
    return redirect(routes.get(role, "/student/dashboard"))


def decode_b64_to_rgb_array(data_url: str) -> np.ndarray:
    """Convert a base64 data-URL (from <canvas>) into an RGB NumPy array."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.array(img)


def get_face_auth_enabled() -> bool:
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("SELECT setting_value FROM settings WHERE setting_key='face_auth_enabled'")
        row = cur.fetchone()
        conn.close()
        return (row["setting_value"] == "1") if row else True
    except Exception:
        return True


def extract_single_encoding(image_array: np.ndarray):
    """
    Returns (encoding, error_message).
    Enforces exactly ONE face in frame.
    Encoding is a plain Python list (128 floats) ready for json.dumps().
    """
    locations = face_recognition.face_locations(image_array, model="hog")

    if len(locations) == 0:
        return None, "No face detected. Move closer to the camera and ensure good lighting."

    if len(locations) > 1:
        return None, "Multiple faces detected. Only one person should be in frame."

    encodings = face_recognition.face_encodings(image_array, known_face_locations=locations)
    if not encodings:
        return None, "Could not compute face encoding. Please retake the photo."

    return encodings[0].tolist(), None


def _complete_login_user(user: dict):
    """Finalise login after successful face verification."""
    session.pop("pending_face_user_id", None)
    session.pop("pending_face_role", None)
    login_user(User(user))
    session["role"] = user["role"]


# ─────────────────────────────────────────────────────────────────────────────
# USER LOADER
# ─────────────────────────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    conn.close()
    return User(user) if user else None


# ─────────────────────────────────────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/")
def home():
    return redirect(url_for("auth.login"))


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    error             = None
    face_auth_enabled = get_face_auth_enabled()

    if request.method == "POST":
        name           = request.form["name"].strip()
        email          = request.form["email"].strip().lower()
        password       = request.form["password"]
        role           = request.form["role"]
        face_image_b64 = request.form.get("face_image", "").strip()
        face_json      = None

        # ── Face encoding ──────────────────────────────────────────────────
        if face_auth_enabled:
            if not face_image_b64:
                error = "Please capture your face photo before registering."
            elif not FACE_LIB_AVAILABLE:
                pass  # Library missing — skip silently (dev mode)
            else:
                try:
                    img_array = decode_b64_to_rgb_array(face_image_b64)
                    encoding, enc_error = extract_single_encoding(img_array)
                    if enc_error:
                        error = enc_error
                    else:
                        face_json = json.dumps(encoding)
                except Exception as exc:
                    error = f"Face processing error: {exc}"

        # ── Hash password and save to DB ───────────────────────────────────
        if not error:
            hashed_pw = generate_password_hash(password)
            conn = get_db_connection()
            cur  = conn.cursor()
            try:
                cur.execute(
                    """INSERT INTO users (name, email, password, role, face_descriptor)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (name, email, hashed_pw, role, face_json)
                )
                conn.commit()
            except Exception:
                error = "Email already registered. Please use a different email."
            finally:
                conn.close()

            if not error:
                return redirect(url_for("auth.login"))

    return render_template("register.html",
                           error=error,
                           face_auth_enabled=face_auth_enabled)


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN  (step 1 — password)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error             = None
    face_auth_enabled = get_face_auth_enabled()

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        conn.close()

        # Support both hashed passwords (new) and plain text (old admin seed)
        password_ok = False
        if user:
            stored_pw = user["password"]
            if stored_pw.startswith("pbkdf2:") or stored_pw.startswith("scrypt:"):
                password_ok = check_password_hash(stored_pw, password)
            else:
                # Plain text — legacy rows (admin seed in schema.sql)
                password_ok = (stored_pw == password)

        if user and password_ok:
            if user.get("is_blocked"):
                return render_template("student/blocked.html")

            # Admin bypasses face auth
            if face_auth_enabled and user["role"] != "admin":
                session["pending_face_user_id"] = user["id"]
                session["pending_face_role"]    = user["role"]
                return redirect(url_for("auth.face_verify"))

            login_user(User(user))
            session["role"] = user["role"]
            return redirect_by_role(user["role"])

        error = "Incorrect email or password. Please try again."

    return render_template("login.html",
                           error=error,
                           face_auth_enabled=face_auth_enabled)


# ─────────────────────────────────────────────────────────────────────────────
# FACE VERIFY  (step 2 — face match)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/face-verify", methods=["GET", "POST"])
def face_verify():
    pending_id   = session.get("pending_face_user_id")
    pending_role = session.get("pending_face_role")

    if not pending_id:
        return redirect(url_for("auth.login"))

    error     = None
    TOLERANCE = 0.45

    if request.method == "POST":
        face_image_b64 = request.form.get("face_image", "").strip()

        if not face_image_b64:
            error = "No image captured. Please allow camera access and try again."

        elif not FACE_LIB_AVAILABLE:
            # FIX Bug 1: was calling undefined _complete_login(pending_id)
            # Now correctly fetches user from DB then calls _complete_login_user(user)
            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id=%s", (pending_id,))
            user = cur.fetchone()
            conn.close()
            if not user:
                session.pop("pending_face_user_id", None)
                session.pop("pending_face_role", None)
                return redirect(url_for("auth.login"))
            _complete_login_user(user)
            return redirect_by_role(pending_role)

        else:
            conn = get_db_connection()
            cur  = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id=%s", (pending_id,))
            user = cur.fetchone()
            conn.close()

            if not user:
                session.pop("pending_face_user_id", None)
                session.pop("pending_face_role", None)
                return redirect(url_for("auth.login"))

            stored_json = user.get("face_descriptor")
            if not stored_json:
                _complete_login_user(user)
                return redirect_by_role(user["role"])

            try:
                img_array = decode_b64_to_rgb_array(face_image_b64)
                live_encoding, enc_error = extract_single_encoding(img_array)
            except Exception as exc:
                error = f"Could not process image: {exc}"
                live_encoding = None
                enc_error     = None

            if not error:
                if enc_error:
                    error = enc_error
                else:
                    stored_encoding = np.array(json.loads(stored_json))
                    live_enc_array  = np.array(live_encoding)

                    distance = face_recognition.face_distance(
                        [stored_encoding], live_enc_array
                    )[0]

                    if distance <= TOLERANCE:
                        _complete_login_user(user)
                        return redirect_by_role(user["role"])
                    else:
                        confidence = round((1.0 - distance) * 100, 1)
                        error = (
                            f"Face not recognised (similarity: {confidence}%). "
                            "Ensure good lighting, look directly at the camera, and try again."
                        )

    return render_template("face_verify.html", error=error)


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
