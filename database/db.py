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


def _where_with_user(user_id: int,
                      from_date: str | None = None,
                      to_date: str | None = None) -> tuple[str, list]:
    """Return `WHERE user_id = ? [AND date >= ?] [AND date <= ?]` + bound params.

    Both date bounds are inclusive (`>=` / `<=`). Either may be None, in
    which case that side is unbounded. The static fragment contains only
    hardcoded `AND date ...` literals; user data flows exclusively through
    the bound params, so callers can `conn.execute(sql, params)` with no
    f-string splice. ISO `YYYY-MM-DD` strings sort lexicographically, so
    plain comparison needs no `date()` cast.
    """
    conditions = ["user_id = ?"]
    params: list = [user_id]
    if from_date:
        conditions.append("date >= ?")
        params.append(from_date)
    if to_date:
        conditions.append("date <= ?")
        params.append(to_date)
    return ("WHERE " + " AND ".join(conditions), params)


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


def add_expense(user_id: int, amount: float, category: str,
                date: str, description: str | None) -> int:
    """Insert one expense for `user_id` and return its row id.

    `date` and `category` are expected pre-validated by the caller
    (the route enforces the CATEGORIES membership and ISO-date rules),
    but every value is still bound as a parameter — never interpolated.
    `description` may be None to store NULL (an omitted field).
    """
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
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

    Used by the navbar to look up the signed-in user once per
    request. Includes `created_at` so the profile view can
    render the "Member since" label without an extra round-trip.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, password_hash, created_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def get_user_total_spent(user_id: int,
                         from_date: str | None = None,
                         to_date: str | None = None) -> float:
    """Sum of expense amounts for the user within an optional date range.

    COALESCE collapses the NULL from an empty SUM to 0 so the
    caller never has to special-case the empty path. `from_date`/`to_date`
    are inclusive ISO `YYYY-MM-DD` bounds; either may be None.
    """
    where, params = _where_with_user(user_id, from_date, to_date)
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses "
            f"{where}",
            tuple(params),
        ).fetchone()
        return float(row[0])
    finally:
        conn.close()


def get_user_expense_count(user_id: int,
                           from_date: str | None = None,
                           to_date: str | None = None) -> int:
    """Number of expense rows for the user within an optional date range."""
    where, params = _where_with_user(user_id, from_date, to_date)
    conn = get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM expenses "
            f"{where}",
            tuple(params),
        ).fetchone()[0]
    finally:
        conn.close()


def get_user_top_category(user_id: int,
                          from_date: str | None = None,
                          to_date: str | None = None) -> str | None:
    """Category with the largest sum for the user, or None.

    None means the user has no expenses in range — the view layer
    translates that to an em-dash placeholder so the template
    never renders an empty stat. `from_date`/`to_date` are inclusive
    ISO `YYYY-MM-DD` bounds; either may be None.
    """
    where, params = _where_with_user(user_id, from_date, to_date)
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT category FROM expenses "
            f"{where} "
            "GROUP BY category "
            "ORDER BY SUM(amount) DESC LIMIT 1",
            tuple(params),
        ).fetchone()
        return row["category"] if row else None
    finally:
        conn.close()


def get_recent_expenses(user_id: int,
                        limit: int | None = None,
                        from_date: str | None = None,
                        to_date: str | None = None) -> list[dict]:
    """Most recent expenses for the user, newest first, in range.

    Sort key is `date DESC, id DESC` — `id` breaks ties when
    multiple expenses share a date (date has no time
    component, so insertion order is the natural tiebreaker).
    `from_date`/`to_date` are inclusive ISO `YYYY-MM-DD` bounds;
    either may be None. `limit` defaults to None (return every
    matching row); pass an int to cap the result. Returns plain
    dicts so the template can iterate without surprises from
    sqlite3.Row.
    """
    where, params = _where_with_user(user_id, from_date, to_date)
    sql = (
        "SELECT date, description, category, amount "
        "FROM expenses "
        f"{where} "
        "ORDER BY date DESC, id DESC"
    )
    if limit is not None:
        sql += " LIMIT ?"
        params = [*params, limit]
    conn = get_db()
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_category_breakdown(user_id: int,
                           from_date: str | None = None,
                           to_date: str | None = None) -> list[dict]:
    """Per-category totals with percent-of-spend, biggest first, in range.

    SQL does the aggregation and ordering; Python computes
    each row's percent against the running total so the
    breakdown always sums to ~100 without a second pass.
    `from_date`/`to_date` are inclusive ISO `YYYY-MM-DD` bounds;
    either may be None. Returns [] when the user has no expenses
    in range.
    """
    where, params = _where_with_user(user_id, from_date, to_date)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS amount "
            "FROM expenses "
            f"{where} "
            "GROUP BY category ORDER BY amount DESC",
            tuple(params),
        ).fetchall()
    finally:
        conn.close()

    total = sum(r["amount"] for r in rows)
    breakdown = []
    for r in rows:
        amount = float(r["amount"])
        percent = round(amount / total * 100) if total else 0
        breakdown.append({
            "name": r["category"],
            "amount": amount,
            "percent": percent,
        })
    return breakdown

    total = sum(r["amount"] for r in rows)
    breakdown = []
    for r in rows:
        amount = float(r["amount"])
        percent = round(amount / total * 100) if total else 0
        breakdown.append({
            "name": r["category"],
            "amount": amount,
            "percent": percent,
        })
    return breakdown


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
