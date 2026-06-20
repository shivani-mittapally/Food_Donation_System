"""
Food Donation Management System — v3
Enhanced: Multi-Language Support (EN/TA/HI) + Location Search
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import os
import io
import json
import qrcode
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "food_donation_secret_key_2024"
socketio = SocketIO(app, cors_allowed_origins="*")

# ─── Config ────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "images")
TRANS_DIR     = os.path.join(BASE_DIR, "translations")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
FOOD_CATEGORIES = ["Veg", "Non-Veg", "Fruits", "Bakery", "Cooked Meals", "Packaged Food"]
SUPPORTED_LANGS = {
    "en": "English",
    "hi": "हिंदी",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "kn": "ಕನ್ನಡ",
    "ml": "മലയാളം",
    "bn": "বাংলা",
    "mr": "मराठी",
    "gu": "ગુજરાતી",
    "pa": "ਪੰਜਾਬੀ",
    "ur": "اردو",
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ─── Translation System ────────────────────────────────────────────────────────
_translations = {}

def load_translations():
    global _translations
    for lang in SUPPORTED_LANGS:
        path = os.path.join(TRANS_DIR, f"{lang}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _translations[lang] = json.load(f)

load_translations()


def get_lang():
    return session.get("lang", "en")


def t(section, key, default=None):
    """Get a translation string."""
    lang = get_lang()
    try:
        val = _translations.get(lang, {}).get(section, {}).get(key)
        if val is None:
            val = _translations.get("en", {}).get(section, {}).get(key)
        return val or default or key
    except Exception:
        return default or key


# ─── Helpers ───────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            email      TEXT    UNIQUE NOT NULL,
            password   TEXT    NOT NULL,
            role       TEXT    NOT NULL DEFAULT 'donor',
            phone      TEXT,
            address    TEXT,
            org_name   TEXT,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id     INTEGER NOT NULL,
            donor_name   TEXT    NOT NULL,
            food_type    TEXT    NOT NULL,
            category     TEXT    DEFAULT 'Veg',
            quantity     TEXT    NOT NULL,
            address      TEXT    NOT NULL,
            city         TEXT    DEFAULT '',
            phone        TEXT    NOT NULL,
            cooking_time TEXT,
            expiry_time  TEXT,
            message      TEXT,
            status       TEXT    DEFAULT 'pending',
            priority     TEXT    DEFAULT 'normal',
            image_path   TEXT,
            ngo_id       INTEGER,
            qr_code      TEXT,
            created_at   TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Migrations
    for col, defval in [("priority", "'normal'"), ("category", "'Veg'"), ("city", "''")]:
        try:
            c.execute(f"ALTER TABLE donations ADD COLUMN {col} TEXT DEFAULT {defval}")
            conn.commit()
        except Exception:
            pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS ngos (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER UNIQUE NOT NULL,
            org_name   TEXT    NOT NULL,
            reg_number TEXT,
            focus_area TEXT,
            website    TEXT,
            verified   INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            message    TEXT    NOT NULL,
            is_read    INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS volunteers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            phone      TEXT    NOT NULL,
            email      TEXT,
            vehicle    TEXT,
            status     TEXT    DEFAULT 'available',
            lat        REAL    DEFAULT 17.3850,
            lng        REAL    DEFAULT 78.4867,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_assignments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            donation_id  INTEGER NOT NULL,
            volunteer_id INTEGER NOT NULL,
            status       TEXT    DEFAULT 'assigned',
            assigned_at  TEXT    DEFAULT (datetime('now')),
            picked_at    TEXT,
            delivered_at TEXT,
            notes        TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_rooms (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            donation_id INTEGER UNIQUE NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id    INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            user_name  TEXT    NOT NULL,
            user_role  TEXT    NOT NULL,
            message    TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        )
    """)

    existing = c.execute("SELECT id FROM users WHERE role='admin'").fetchone()
    if not existing:
        c.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, 'admin')",
            ("Admin", "admin@food.com", generate_password_hash("admin123"))
        )

    if c.execute("SELECT COUNT(*) FROM volunteers").fetchone()[0] == 0:
        for v in [
            ("Ravi Kumar",  "+91 98765 11111", "ravi@example.com",  "Bike", "available",    17.3850, 78.4867),
            ("Priya Sharma","+91 98765 22222", "priya@example.com", "Car",  "available",    17.4000, 78.5000),
            ("Arjun Reddy", "+91 98765 33333", "arjun@example.com", "Bike", "on_delivery",  17.3700, 78.4700),
        ]:
            c.execute("INSERT INTO volunteers (name,phone,email,vehicle,status,lat,lng) VALUES (?,?,?,?,?,?,?)", v)

    conn.commit()
    conn.close()


# ─── Language Route ─────────────────────────────────────────────────────────────
@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in SUPPORTED_LANGS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("index"))


# ─── Context processor ──────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    count = 0
    if "user_id" in session:
        conn = get_db()
        row = conn.execute(
            "SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0",
            (session["user_id"],)
        ).fetchone()
        count = row["c"] if row else 0
        conn.close()
    return {
        "notif_count": count,
        "food_categories": FOOD_CATEGORIES,
        "current_lang": get_lang(),
        "supported_langs": SUPPORTED_LANGS,
        "t": t,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    conn = get_db()
    stats = {
        "total_donations": conn.execute("SELECT COUNT(*) FROM donations").fetchone()[0],
        "delivered":       conn.execute("SELECT COUNT(*) FROM donations WHERE status='delivered'").fetchone()[0],
        "donors":          conn.execute("SELECT COUNT(*) FROM users WHERE role='donor'").fetchone()[0],
        "ngos":            conn.execute("SELECT COUNT(*) FROM users WHERE role='ngo'").fetchone()[0],
    }

    # Location search
    location_search = request.args.get("location", "").strip()
    if location_search:
        recent = conn.execute("""
            SELECT food_type, quantity, donor_name, status, priority, category, address, city, created_at
            FROM donations
            WHERE (address LIKE ? OR city LIKE ?)
            ORDER BY created_at DESC LIMIT 20
        """, (f"%{location_search}%", f"%{location_search}%")).fetchall()
    else:
        recent = conn.execute("""
            SELECT food_type, quantity, donor_name, status, priority, category, address, city, created_at
            FROM donations ORDER BY created_at DESC LIMIT 5
        """).fetchall()

    conn.close()
    return render_template("index.html", stats=stats, recent=recent,
                           location_search=location_search)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"]   = user["id"]
            session["user_name"] = user["name"]
            session["user_role"] = user["role"]
            flash(f"Welcome back, {user['name']}! 🎉", "success")
            role = user["role"]
            if role == "admin":
                return redirect(url_for("admin"))
            elif role == "ngo":
                return redirect(url_for("ngo_dashboard"))
            else:
                return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role     = request.form.get("role", "donor")
        phone    = request.form.get("phone", "")
        org_name = request.form.get("org_name", "")

        if not name or not email or not password:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("signup"))

        conn = get_db()
        if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            flash("Email already registered.", "danger")
            conn.close()
            return redirect(url_for("signup"))

        hashed  = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users (name, email, password, role, phone, org_name) VALUES (?,?,?,?,?,?)",
            (name, email, hashed, role, phone, org_name)
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if role == "ngo" and org_name:
            conn.execute("INSERT INTO ngos (user_id, org_name) VALUES (?,?)", (user_id, org_name))
        conn.commit()
        conn.close()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("index"))


# ═══════════════════════════════════════════════════════════════════════════════
# DECORATORS
# ═══════════════════════════════════════════════════════════════════════════════

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user_role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════════════════════════════════════════
# DONOR ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    uid  = session["user_id"]
    donations = conn.execute("""
        SELECT * FROM donations WHERE donor_id=? ORDER BY
        CASE priority WHEN 'emergency' THEN 0 WHEN 'urgent' THEN 1 ELSE 2 END,
        created_at DESC
    """, (uid,)).fetchall()

    stats = {
        "total":     len(donations),
        "pending":   sum(1 for d in donations if d["status"] == "pending"),
        "delivered": sum(1 for d in donations if d["status"] == "delivered"),
        "accepted":  sum(1 for d in donations if d["status"] in ("accepted", "collected")),
        "emergency": sum(1 for d in donations if d["priority"] == "emergency"),
        "urgent":    sum(1 for d in donations if d["priority"] == "urgent"),
    }
    notifications = conn.execute("""
        SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 10
    """, (uid,)).fetchall()
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    return render_template("dashboard.html", donations=donations, stats=stats,
                           notifications=notifications)


@app.route("/donate", methods=["GET", "POST"])
@login_required
def donate():
    if request.method == "POST":
        food_type    = request.form.get("food_type", "")
        category     = request.form.get("category", "Veg")
        quantity     = request.form.get("quantity", "")
        address      = request.form.get("address", "")
        city         = request.form.get("city", "").strip()
        phone        = request.form.get("phone", "")
        cooking_time = request.form.get("cooking_time", "")
        expiry_time  = request.form.get("expiry_time", "")
        message      = request.form.get("message", "")
        priority     = request.form.get("priority", "normal")

        image_path = None
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename and allowed_file(file.filename):
                filename   = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                image_path = filename

        conn = get_db()
        conn.execute("""
            INSERT INTO donations
              (donor_id, donor_name, food_type, category, quantity, address, city, phone,
               cooking_time, expiry_time, message, image_path, priority)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (session["user_id"], session["user_name"],
              food_type, category, quantity, address, city, phone,
              cooking_time, expiry_time, message, image_path, priority))
        conn.commit()
        conn.close()
        flash("Donation submitted successfully! 🙏", "success")
        return redirect(url_for("pending"))
    return render_template("donate.html")


@app.route("/pending")
@login_required
def pending():
    search   = request.args.get("search", "")
    location = request.args.get("location", "")
    priority = request.args.get("priority", "all")
    category = request.args.get("category", "all")
    conn     = get_db()
    uid      = session["user_id"]
    role     = session.get("user_role", "donor")

    query  = "SELECT * FROM donations WHERE status='pending'"
    params = []

    if role == "donor":
        query += " AND donor_id=?"
        params.append(uid)

    if search:
        query += " AND (food_type LIKE ? OR donor_name LIKE ? OR address LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if location:
        query += " AND (address LIKE ? OR city LIKE ?)"
        params.extend([f"%{location}%", f"%{location}%"])

    if priority != "all":
        query += " AND priority=?"
        params.append(priority)

    if category != "all":
        query += " AND category=?"
        params.append(category)

    query += " ORDER BY CASE priority WHEN 'emergency' THEN 0 WHEN 'urgent' THEN 1 ELSE 2 END, created_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("pending.html", donations=rows, search=search,
                           location_filter=location,
                           priority_filter=priority, category_filter=category)


@app.route("/previous")
@login_required
def previous():
    search   = request.args.get("search", "")
    location = request.args.get("location", "")
    priority = request.args.get("priority", "all")
    category = request.args.get("category", "all")
    conn     = get_db()
    uid      = session["user_id"]
    role     = session.get("user_role", "donor")

    query  = "SELECT * FROM donations WHERE status != 'pending'"
    params = []

    if role not in ("admin", "ngo"):
        query += " AND donor_id=?"
        params.append(uid)

    if search:
        query += " AND (food_type LIKE ? OR donor_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if location:
        query += " AND (address LIKE ? OR city LIKE ?)"
        params.extend([f"%{location}%", f"%{location}%"])

    if priority != "all":
        query += " AND priority=?"
        params.append(priority)

    if category != "all":
        query += " AND category=?"
        params.append(category)

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("previous.html", donations=rows, search=search,
                           location_filter=location,
                           priority_filter=priority, category_filter=category)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    uid  = session["user_id"]
    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        phone   = request.form.get("phone", "")
        address = request.form.get("address", "")
        conn.execute("UPDATE users SET name=?, phone=?, address=? WHERE id=?",
                     (name, phone, address, uid))
        conn.commit()
        session["user_name"] = name
        flash("Profile updated! ✅", "success")
    user      = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    total     = conn.execute("SELECT COUNT(*) FROM donations WHERE donor_id=?", (uid,)).fetchone()[0]
    delivered = conn.execute("SELECT COUNT(*) FROM donations WHERE donor_id=? AND status='delivered'", (uid,)).fetchone()[0]
    conn.close()
    return render_template("profile.html", user=user, total=total, delivered=delivered)


# ═══════════════════════════════════════════════════════════════════════════════
# NGO DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/ngo-dashboard")
@login_required
def ngo_dashboard():
    priority_filter = request.args.get("priority", "all")
    category_filter = request.args.get("category", "all")
    location_filter = request.args.get("location", "")
    conn = get_db()

    pending_query  = "SELECT * FROM donations WHERE status='pending'"
    pending_params = []
    if priority_filter != "all":
        pending_query  += " AND priority=?"
        pending_params.append(priority_filter)
    if category_filter != "all":
        pending_query  += " AND category=?"
        pending_params.append(category_filter)
    if location_filter:
        pending_query += " AND (address LIKE ? OR city LIKE ?)"
        pending_params.extend([f"%{location_filter}%", f"%{location_filter}%"])
    pending_query += " ORDER BY CASE priority WHEN 'emergency' THEN 0 WHEN 'urgent' THEN 1 ELSE 2 END, created_at DESC"

    all_pending = conn.execute(pending_query, pending_params).fetchall()

    my_accepted = conn.execute(
        "SELECT d.*, va.status as vol_status, v.name as vol_name FROM donations d "
        "LEFT JOIN volunteer_assignments va ON va.donation_id=d.id "
        "LEFT JOIN volunteers v ON v.id=va.volunteer_id "
        "WHERE d.ngo_id=? AND d.status IN ('accepted','collected','delivered') "
        "ORDER BY d.created_at DESC",
        (session["user_id"],)
    ).fetchall()

    volunteers_raw = conn.execute("SELECT * FROM volunteers ORDER BY status, name").fetchall()
    volunteers = rows_to_list(volunteers_raw)

    stats = {
        "available": conn.execute("SELECT COUNT(*) FROM donations WHERE status='pending'").fetchone()[0],
        "accepted":  sum(1 for d in my_accepted if d["status"] == "accepted"),
        "collected": sum(1 for d in my_accepted if d["status"] == "collected"),
        "delivered": sum(1 for d in my_accepted if d["status"] == "delivered"),
        "emergency": conn.execute("SELECT COUNT(*) FROM donations WHERE status='pending' AND priority='emergency'").fetchone()[0],
        "urgent":    conn.execute("SELECT COUNT(*) FROM donations WHERE status='pending' AND priority='urgent'").fetchone()[0],
    }

    cat_counts = {}
    for cat in FOOD_CATEGORIES:
        cat_counts[cat] = conn.execute(
            "SELECT COUNT(*) FROM donations WHERE status='pending' AND category=?", (cat,)
        ).fetchone()[0]

    conn.close()
    return render_template("ngo_dashboard.html",
                           pending=all_pending,
                           accepted=my_accepted,
                           stats=stats,
                           volunteers=volunteers,
                           priority_filter=priority_filter,
                           category_filter=category_filter,
                           location_filter=location_filter,
                           cat_counts=cat_counts)


@app.route("/accept-donation/<int:don_id>")
@login_required
def accept_donation(don_id):
    conn = get_db()
    conn.execute("UPDATE donations SET status='accepted', ngo_id=? WHERE id=?",
                 (session["user_id"], don_id))
    donation = conn.execute("SELECT * FROM donations WHERE id=?", (don_id,)).fetchone()
    if donation:
        conn.execute("INSERT INTO notifications (user_id, message) VALUES (?,?)",
                     (donation["donor_id"],
                      f"Your donation of '{donation['food_type']}' has been accepted by {session['user_name']}! 🎉"))
        conn.execute("INSERT OR IGNORE INTO chat_rooms (donation_id) VALUES (?)", (don_id,))
    conn.commit()
    conn.close()
    flash("Donation accepted! 🙌", "success")
    return redirect(url_for("ngo_dashboard"))


@app.route("/update-status/<int:don_id>/<string:new_status>")
@login_required
def update_status(don_id, new_status):
    allowed = ["pending", "accepted", "collected", "delivered", "expired"]
    if new_status not in allowed:
        flash("Invalid status.", "danger")
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE donations SET status=? WHERE id=?", (new_status, don_id))
    donation = conn.execute("SELECT * FROM donations WHERE id=?", (don_id,)).fetchone()
    if donation:
        conn.execute("INSERT INTO notifications (user_id, message) VALUES (?,?)",
                     (donation["donor_id"],
                      f"Your donation of '{donation['food_type']}' is now '{new_status}'. 📦"))
    conn.commit()
    conn.close()
    flash(f"Status updated to '{new_status}'.", "success")
    return redirect(request.referrer or url_for("admin"))


# ═══════════════════════════════════════════════════════════════════════════════
# CHAT ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/chat/<int:don_id>")
@login_required
def chat(don_id):
    conn = get_db()
    donation = conn.execute("SELECT * FROM donations WHERE id=?", (don_id,)).fetchone()
    if not donation:
        flash("Donation not found.", "danger")
        return redirect(url_for("dashboard"))

    uid  = session["user_id"]
    role = session.get("user_role")
    if role not in ("admin",) and donation["donor_id"] != uid and donation["ngo_id"] != uid:
        flash("You don't have access to this chat.", "danger")
        return redirect(url_for("dashboard"))

    conn.execute("INSERT OR IGNORE INTO chat_rooms (donation_id) VALUES (?)", (don_id,))
    conn.commit()

    room = conn.execute("SELECT * FROM chat_rooms WHERE donation_id=?", (don_id,)).fetchone()
    messages = conn.execute("""
        SELECT cm.*, u.name as sender_name FROM chat_messages cm
        JOIN users u ON u.id=cm.user_id
        WHERE cm.room_id=?
        ORDER BY cm.created_at ASC
    """, (room["id"],)).fetchall()

    ngo_name = None
    if donation["ngo_id"]:
        ngo_user = conn.execute("SELECT name FROM users WHERE id=?", (donation["ngo_id"],)).fetchone()
        ngo_name = ngo_user["name"] if ngo_user else "NGO"

    conn.close()
    return render_template("chat.html",
                           donation=donation,
                           room_id=room["id"],
                           messages=messages,
                           ngo_name=ngo_name)


@app.route("/api/chat/messages/<int:room_id>")
@login_required
def get_messages(room_id):
    conn = get_db()
    messages = conn.execute("""
        SELECT cm.id, cm.user_id, cm.user_name, cm.user_role, cm.message, cm.created_at
        FROM chat_messages cm WHERE cm.room_id=? ORDER BY cm.created_at ASC
    """, (room_id,)).fetchall()
    conn.close()
    return jsonify(rows_to_list(messages))


@socketio.on("join")
def on_join(data):
    room = str(data.get("room_id"))
    join_room(room)
    emit("status", {"msg": f"{session.get('user_name','User')} has joined the chat."}, to=room)


@socketio.on("leave")
def on_leave(data):
    room = str(data.get("room_id"))
    leave_room(room)


@socketio.on("send_message")
def handle_message(data):
    room_id  = data.get("room_id")
    message  = data.get("message", "").strip()
    if not message or not room_id:
        return

    uid       = session.get("user_id")
    user_name = session.get("user_name", "User")
    user_role = session.get("user_role", "donor")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    conn.execute("""
        INSERT INTO chat_messages (room_id, user_id, user_name, user_role, message, created_at)
        VALUES (?,?,?,?,?,?)
    """, (room_id, uid, user_name, user_role, message, timestamp))
    conn.commit()
    conn.close()

    emit("receive_message", {
        "user_id":   uid,
        "user_name": user_name,
        "user_role": user_role,
        "message":   message,
        "created_at": timestamp,
    }, to=str(room_id))


# ═══════════════════════════════════════════════════════════════════════════════
# VOLUNTEER ROUTES (keeping for assignment functionality, removed live tracking)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/volunteers")
@login_required
def volunteers():
    conn = get_db()
    vols = conn.execute("SELECT * FROM volunteers ORDER BY status, name").fetchall()
    assignments = conn.execute("""
        SELECT va.*, v.name as vol_name, v.phone as vol_phone, v.vehicle,
               d.food_type, d.donor_name, d.address as pickup_addr, d.priority
        FROM volunteer_assignments va
        JOIN volunteers v ON v.id=va.volunteer_id
        JOIN donations d ON d.id=va.donation_id
        ORDER BY va.assigned_at DESC LIMIT 20
    """).fetchall()
    conn.close()
    return render_template("volunteers.html", volunteers=vols, assignments=assignments)


@app.route("/assign-volunteer", methods=["POST"])
@login_required
def assign_volunteer():
    don_id = request.form.get("donation_id", type=int)
    vol_id = request.form.get("volunteer_id", type=int)
    if not don_id or not vol_id:
        flash("Missing data.", "danger")
        return redirect(request.referrer or url_for("ngo_dashboard"))
    conn = get_db()
    conn.execute("DELETE FROM volunteer_assignments WHERE donation_id=?", (don_id,))
    conn.execute("INSERT INTO volunteer_assignments (donation_id, volunteer_id, status) VALUES (?,?,'assigned')",
                 (don_id, vol_id))
    conn.execute("UPDATE volunteers SET status='on_delivery' WHERE id=?", (vol_id,))
    donation = conn.execute("SELECT * FROM donations WHERE id=?", (don_id,)).fetchone()
    vol      = conn.execute("SELECT * FROM volunteers WHERE id=?", (vol_id,)).fetchone()
    if donation:
        conn.execute("INSERT INTO notifications (user_id, message) VALUES (?,?)",
                     (donation["donor_id"],
                      f"Volunteer {vol['name']} has been assigned to collect your '{donation['food_type']}' donation! 🚴"))
    conn.commit()
    conn.close()
    flash("Volunteer assigned successfully! 🚴", "success")
    return redirect(request.referrer or url_for("ngo_dashboard"))


@app.route("/update-assignment/<int:assign_id>/<string:status>")
@login_required
def update_assignment(assign_id, status):
    allowed = ["assigned", "on_the_way", "picked_up", "delivered"]
    if status not in allowed:
        flash("Invalid status.", "danger")
        return redirect(request.referrer)
    conn = get_db()
    now  = datetime.now().isoformat()
    if status == "picked_up":
        conn.execute("UPDATE volunteer_assignments SET status=?, picked_at=? WHERE id=?", (status, now, assign_id))
    elif status == "delivered":
        conn.execute("UPDATE volunteer_assignments SET status=?, delivered_at=? WHERE id=?", (status, now, assign_id))
        assignment = conn.execute("SELECT * FROM volunteer_assignments WHERE id=?", (assign_id,)).fetchone()
        if assignment:
            conn.execute("UPDATE volunteers SET status='available' WHERE id=?", (assignment["volunteer_id"],))
            conn.execute("UPDATE donations SET status='delivered' WHERE id=?", (assignment["donation_id"],))
    else:
        conn.execute("UPDATE volunteer_assignments SET status=? WHERE id=?", (status, assign_id))
    conn.commit()
    conn.close()
    flash(f"Assignment updated to '{status}'.", "success")
    return redirect(request.referrer or url_for("volunteers"))


@app.route("/api/volunteers")
@login_required
def api_volunteers():
    conn = get_db()
    vols = conn.execute("SELECT * FROM volunteers").fetchall()
    conn.close()
    return jsonify(rows_to_list(vols))


# ═══════════════════════════════════════════════════════════════════════════════
# LOCATION SEARCH API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/search-donations")
def api_search_donations():
    location = request.args.get("location", "").strip()
    search   = request.args.get("search", "").strip()
    status   = request.args.get("status", "all")

    conn   = get_db()
    query  = "SELECT id, food_type, quantity, donor_name, address, city, status, priority, category, created_at FROM donations WHERE 1=1"
    params = []

    if location:
        query += " AND (address LIKE ? OR city LIKE ?)"
        params.extend([f"%{location}%", f"%{location}%"])

    if search:
        query += " AND (food_type LIKE ? OR donor_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if status != "all":
        query += " AND status=?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT 50"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/admin")
@admin_required
def admin():
    conn  = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    donations = conn.execute("""
        SELECT * FROM donations
        ORDER BY CASE priority WHEN 'emergency' THEN 0 WHEN 'urgent' THEN 1 ELSE 2 END,
        created_at DESC
    """).fetchall()
    stats = {
        "users":     len(users),
        "donations": len(donations),
        "pending":   sum(1 for d in donations if d["status"] == "pending"),
        "delivered": sum(1 for d in donations if d["status"] == "delivered"),
        "ngos":      sum(1 for u in users if u["role"] == "ngo"),
        "donors":    sum(1 for u in users if u["role"] == "donor"),
        "emergency": sum(1 for d in donations if d["priority"] == "emergency"),
        "urgent":    sum(1 for d in donations if d["priority"] == "urgent"),
    }
    conn.close()
    return render_template("admin.html", users=users, donations=donations, stats=stats)


@app.route("/admin/delete-donation/<int:don_id>")
@admin_required
def delete_donation(don_id):
    conn = get_db()
    conn.execute("DELETE FROM donations WHERE id=?", (don_id,))
    conn.commit()
    conn.close()
    flash("Donation deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/delete-user/<int:uid>")
@admin_required
def delete_user(uid):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    flash("User deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/update-priority/<int:don_id>/<string:priority>")
@admin_required
def update_priority(don_id, priority):
    if priority not in ["normal", "urgent", "emergency"]:
        flash("Invalid priority.", "danger")
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE donations SET priority=? WHERE id=?", (priority, don_id))
    conn.commit()
    conn.close()
    flash(f"Priority updated to '{priority}'.", "success")
    return redirect(request.referrer or url_for("admin"))


# ═══════════════════════════════════════════════════════════════════════════════
# API / UTILITY
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/qr/<int:don_id>")
def generate_qr(don_id):
    img = qrcode.make(f"http://localhost:5000/donation/{don_id}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/donation/<int:don_id>")
def donation_detail(don_id):
    conn = get_db()
    d = conn.execute("SELECT * FROM donations WHERE id=?", (don_id,)).fetchone()
    assignment = conn.execute("""
        SELECT va.*, v.name as vol_name, v.phone as vol_phone, v.vehicle, v.lat, v.lng
        FROM volunteer_assignments va
        JOIN volunteers v ON v.id=va.volunteer_id
        WHERE va.donation_id=?
    """, (don_id,)).fetchone()
    room = None
    if d and d["ngo_id"]:
        room = conn.execute("SELECT id FROM chat_rooms WHERE donation_id=?", (don_id,)).fetchone()
    conn.close()
    if not d:
        flash("Donation not found.", "danger")
        return redirect(url_for("index"))
    return render_template("donation_detail.html", d=d, assignment=assignment, room=room)


@app.route("/api/chart-data")
@login_required
def chart_data():
    conn = get_db()
    uid  = session["user_id"]
    role = session.get("user_role", "donor")
    if role in ("admin", "ngo"):
        rows = conn.execute("SELECT status, COUNT(*) as c FROM donations GROUP BY status").fetchall()
    else:
        rows = conn.execute(
            "SELECT status, COUNT(*) as c FROM donations WHERE donor_id=? GROUP BY status", (uid,)
        ).fetchall()
    conn.close()
    return jsonify({r["status"]: r["c"] for r in rows})


@app.route("/api/monthly-data")
@login_required
def monthly_data():
    conn = get_db()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as c
        FROM donations GROUP BY month ORDER BY month DESC LIMIT 6
    """).fetchall()
    conn.close()
    return jsonify([{"month": r["month"], "count": r["c"]} for r in rows])


@app.route("/api/priority-stats")
@login_required
def priority_stats():
    conn = get_db()
    rows = conn.execute("""
        SELECT priority, COUNT(*) as c FROM donations WHERE status='pending' GROUP BY priority
    """).fetchall()
    conn.close()
    return jsonify({r["priority"]: r["c"] for r in rows})


@app.route("/api/category-stats")
@login_required
def category_stats():
    conn = get_db()
    rows = conn.execute("""
        SELECT category, COUNT(*) as c FROM donations WHERE status='pending' GROUP BY category
    """).fetchall()
    conn.close()
    return jsonify({r["category"]: r["c"] for r in rows})


@app.route("/download-report")
@admin_required
def download_report():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors

        conn = get_db()
        donations = conn.execute("SELECT * FROM donations ORDER BY created_at DESC").fetchall()
        conn.close()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = [Paragraph("Food Donation Report", styles["Title"])]

        data = [["ID", "Donor", "Food Type", "Category", "City", "Qty", "Priority", "Status", "Date"]]
        for d in donations:
            data.append([str(d["id"]), d["donor_name"], d["food_type"],
                         d.get("category", "—"), d.get("city", "—"), d["quantity"],
                         d.get("priority", "normal"), d["status"], d["created_at"][:10]])

        t = Table(data)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2ecc71")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        doc.build(elements)
        buf.seek(0)
        return send_file(buf, mimetype="application/pdf",
                         download_name="donation_report.pdf", as_attachment=True)
    except Exception as e:
        flash(f"PDF error: {e}", "danger")
        return redirect(url_for("admin"))


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    print("=" * 55)
    print("  🍱  Food Donation System — v3 Enhanced")
    print("  Running at: http://localhost:5000")
    print("  Admin login: admin@food.com / admin123")
    print("  New features: Multi-Language + Location Search")
    print("=" * 55)
    socketio.run(app, debug=True, port=5000)
