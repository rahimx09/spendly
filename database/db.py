"""SQLite data layer for Spendly."""
import datetime
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

# Absolute path to expense_tracker.db at the project root.
DB_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.db"

# Fixed category list — keep in sync with templates/forms when those land.
CATEGORIES = (
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      REAL    NOT NULL,
    category    TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    description TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

DEMO_USER = {
    "name": "Demo User",
    "email": "demo@spendly.com",
    "password": "demo123",
}


def _sample_expenses(user_id: int) -> list[tuple]:
    """Build 8 demo expenses spread across the current month.

    Dates use day-of-month offsets from the 1st so they always fall inside
    the current month, then clamp to today's day so we never write a future
    date if the offset pushes past it.
    """
    today = datetime.date.today()
    first = today.replace(day=1)

    def d(offset: int) -> str:
        day = min(first.day + offset, today.day)
        return today.replace(day=day).isoformat()

    return [
        (user_id, 250.00,  "Food",          d(0), "Lunch at office canteen"),
        (user_id, 180.50,  "Food",          d(1), "Dinner with friends"),
        (user_id, 90.00,   "Transport",     d(2), "Uber to airport"),
        (user_id, 1500.00, "Bills",         d(3), "Electricity bill"),
        (user_id, 450.00,  "Health",        d(4), "Pharmacy refill"),
        (user_id, 799.00,  "Entertainment", d(5), "Movie tickets"),
        (user_id, 1299.00, "Shopping",      d(6), "New running shoes"),
        (user_id, 120.00,  "Other",         d(7), "Gift wrap supplies"),
    ]


def get_db() -> sqlite3.Connection:
    """Open a SQLite connection with Row factory and FK enforcement."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (IF NOT EXISTS)."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def create_user(name: str, email: str, password: str) -> int:
    """Insert a new user and return their id.

    Raises sqlite3.IntegrityError if the email already exists —
    callers should catch it and translate to a user-facing error.
    """
    pw_hash = generate_password_hash(password)
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) "
            "VALUES (?, ?, ?)",
            (name, email, pw_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def find_user_by_email(email: str) -> sqlite3.Row | None:
    """Return the user with the given email, or None.

    Lowercases the email before the query so case variants
    (`Demo@Spendly.com` vs `demo@spendly.com`) all match the
    same row — the same convention `create_user` and the
    registration route already use. Returns None (does not
    raise) when no user has that email.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, password_hash FROM users "
            "WHERE email = ?",
            (email.lower(),),
        ).fetchone()
    finally:
        conn.close()


def find_user_by_id(user_id: int) -> sqlite3.Row | None:
    """Return the user with the given id, or None.

    Used by the navbar to look up the signed-in user's name
    once per request without running a query in the template.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, password_hash FROM users "
            "WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def seed_db() -> None:
    """Insert demo user + 8 sample expenses. No-op if already seeded."""
    conn = get_db()
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return

        pw_hash = generate_password_hash(DEMO_USER["password"])
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (DEMO_USER["name"], DEMO_USER["email"], pw_hash),
        )
        user_id = cur.lastrowid

        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            _sample_expenses(user_id),
        )
        conn.commit()
    finally:
        conn.close()
