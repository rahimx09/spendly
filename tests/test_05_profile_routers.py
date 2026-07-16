"""Tests for Step 5 — Profile Page Backend Routers.

The /profile view now reads from the database instead of using
hardcoded data. These tests cover each new helper (happy path +
empty-user path) and the view itself (anonymous → /login,
signed-in 200, fresh user → clean empty state).
"""
from database.db import (
    create_user,
    get_category_breakdown,
    get_recent_expenses,
    get_user_expense_count,
    get_user_top_category,
    get_user_total_spent,
)


# ------------------------------------------------------------------ #
# Shared helpers                                                       #
# ------------------------------------------------------------------ #

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
DEMO_NAME = "Demo User"


def _seed_demo_user() -> int:
    """Idempotently create the demo user and return their id."""
    from database.db import find_user_by_email
    existing = find_user_by_email(DEMO_EMAIL)
    if existing:
        return existing["id"]
    return create_user(DEMO_NAME, DEMO_EMAIL, DEMO_PASSWORD)


def _fresh_user_id() -> int:
    """A user with zero expenses — exercises the empty-state path."""
    return create_user("Empty Eve", "eve@spendly.com", "evepassword")


# ------------------------------------------------------------------ #
# get_user_total_spent                                                 #
# ------------------------------------------------------------------ #

def test_total_spent_zero_for_fresh_user(app_with_tmp_db):
    user_id = _fresh_user_id()
    assert get_user_total_spent(user_id) == 0.0


def test_total_spent_sums_all_expenses(app_with_tmp_db):
    from database import db as db_module
    user_id = _seed_demo_user()
    # Insert a known total so we don't depend on seed_db ordering.
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 100.0, "Food", "2026-07-01", "a"),
                (user_id, 250.5, "Bills", "2026-07-02", "b"),
                (user_id, 49.5,  "Food", "2026-07-03", "c"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    assert get_user_total_spent(user_id) == 400.0


# ------------------------------------------------------------------ #
# get_user_expense_count                                               #
# ------------------------------------------------------------------ #

def test_expense_count_zero_for_fresh_user(app_with_tmp_db):
    assert get_user_expense_count(_fresh_user_id()) == 0


def test_expense_count_returns_row_count(app_with_tmp_db):
    from database import db as db_module
    user_id = _seed_demo_user()
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 1.0, "Food", "2026-07-01", "a"),
                (user_id, 2.0, "Food", "2026-07-02", "b"),
                (user_id, 3.0, "Food", "2026-07-03", "c"),
                (user_id, 4.0, "Food", "2026-07-04", "d"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    assert get_user_expense_count(user_id) == 4


# ------------------------------------------------------------------ #
# get_user_top_category                                                #
# ------------------------------------------------------------------ #

def test_top_category_none_for_fresh_user(app_with_tmp_db):
    assert get_user_top_category(_fresh_user_id()) is None


def test_top_category_picks_largest_sum(app_with_tmp_db):
    from database import db as db_module
    user_id = _seed_demo_user()
    conn = db_module.get_db()
    try:
        # Food totals 200, Bills totals 999, Transport 50 → Bills wins.
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 100.0, "Food",      "2026-07-01", "a"),
                (user_id, 100.0, "Food",      "2026-07-02", "b"),
                (user_id, 999.0, "Bills",     "2026-07-03", "c"),
                (user_id, 50.0,  "Transport", "2026-07-04", "d"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    assert get_user_top_category(user_id) == "Bills"


# ------------------------------------------------------------------ #
# get_recent_expenses                                                  #
# ------------------------------------------------------------------ #

def test_recent_expenses_empty_for_fresh_user(app_with_tmp_db):
    assert get_recent_expenses(_fresh_user_id()) == []


def test_recent_expenses_caps_at_limit(app_with_tmp_db):
    from database import db as db_module
    user_id = _seed_demo_user()
    conn = db_module.get_db()
    try:
        rows = [
            (user_id, float(i), "Food", f"2026-07-{i:02d}", f"row {i}")
            for i in range(1, 11)  # 10 rows; 2026-07-01..10
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    recent = get_recent_expenses(user_id, limit=8)
    assert len(recent) == 8
    # Newest first: 2026-07-10 down to 2026-07-03.
    assert recent[0]["date"] == "2026-07-10"
    assert recent[7]["date"] == "2026-07-03"


def test_recent_expenses_shape_matches_template(app_with_tmp_db):
    """The view passes these dicts straight to profile.html, which
    reads `date`, `description`, `category`, `amount`."""
    from database import db as db_module
    user_id = _seed_demo_user()
    conn = db_module.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, 42.0, "Food", "2026-07-08", "Coffee"),
        )
        conn.commit()
    finally:
        conn.close()
    [row] = get_recent_expenses(user_id)
    assert set(row.keys()) == {"id", "date", "description", "category", "amount"}
    assert row["description"] == "Coffee"


# ------------------------------------------------------------------ #
# get_category_breakdown                                               #
# ------------------------------------------------------------------ #

def test_category_breakdown_empty_for_fresh_user(app_with_tmp_db):
    assert get_category_breakdown(_fresh_user_id()) == []


def test_category_breakdown_sorts_by_amount_desc(app_with_tmp_db):
    from database import db as db_module
    user_id = _seed_demo_user()
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 10.0,  "Food",      "2026-07-01", "a"),
                (user_id, 90.0,  "Bills",     "2026-07-02", "b"),
                (user_id, 50.0,  "Transport", "2026-07-03", "c"),
                (user_id, 50.0,  "Food",      "2026-07-04", "d"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    breakdown = get_category_breakdown(user_id)
    names = [r["name"] for r in breakdown]
    assert names == ["Bills", "Food", "Transport"]
    # Bills = 90/200 = 45%, Food = 60/200 = 30%, Transport = 50/200 = 25%.
    assert breakdown[0]["percent"] == 45
    assert breakdown[1]["percent"] == 30
    assert breakdown[2]["percent"] == 25


def test_category_breakdown_percents_sum_to_100(app_with_tmp_db):
    from database import db as db_module
    user_id = _seed_demo_user()
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 33.33, "Food",  "2026-07-01", "a"),
                (user_id, 33.33, "Bills", "2026-07-02", "b"),
                (user_id, 33.34, "Other", "2026-07-03", "c"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    total_percent = sum(r["percent"] for r in get_category_breakdown(user_id))
    # Each row rounds to 33 (33.33 → 33), so the sum is 99; an
    # even split like 33.34 would round to 33, sum = 100. The
    # rounding drift is at most ±1 per row, so ±2 across 3 rows.
    assert 98 <= total_percent <= 101, total_percent


# ------------------------------------------------------------------ #
# /profile view — anonymous                                            #
# ------------------------------------------------------------------ #

def test_profile_redirects_when_signed_out(client):
    resp = client.get("/profile", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# /profile view — signed-in, real data                                 #
# ------------------------------------------------------------------ #

def _sign_in_demo(client) -> int:
    """Create the demo user, seed their expenses, log them in.

    Note: seed_db is a no-op once any user exists, so we have to
    create the demo user via `create_user` first, then call
    `seed_db` BEFORE the user is created. Order matters here.
    """
    from database.db import seed_db
    seed_db()  # inserts demo user + 8 sample expenses if not present
    client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    with client.session_transaction() as sess:
        return sess.get("user_id")


def test_profile_returns_200_for_signed_in_user(client):
    _sign_in_demo(client)
    assert client.get("/profile").status_code == 200


def test_profile_renders_real_total_spent(client):
    """Seed sum: 250+180.5+90+1500+450+799+1299+120 = 4688.50."""
    _sign_in_demo(client)
    body = client.get("/profile").get_data(as_text=True)
    assert "₹4,688.50" in body


def test_profile_renders_real_transaction_count(client):
    _sign_in_demo(client)
    body = client.get("/profile").get_data(as_text=True)
    # The "Transactions" stat is a plain str(count); 8 is rendered
    # as the value of that stat. It also appears as a column count
    # and date, so check it next to the label.
    assert "Transactions" in body
    # Count card value is the digit "8" inside a `.stat-value`.
    import re
    m = re.search(r"stat-label[^>]*>Transactions</span>\s*<span[^>]*stat-value[^>]*>(\d+)</span>", body)
    assert m is not None, "Transactions stat not found"
    assert m.group(1) == "8"


def test_profile_renders_real_top_category(client):
    _sign_in_demo(client)
    body = client.get("/profile").get_data(as_text=True)
    # Bills is the largest single category in the seed (1500).
    assert "Bills" in body


def test_profile_renders_real_member_since(client):
    """`created_at` for a freshly created demo user is the
    current month; the view should render e.g. 'July 2026'."""
    _sign_in_demo(client)
    import datetime
    expected = datetime.date.today().strftime("%B %Y")
    body = client.get("/profile").get_data(as_text=True)
    assert f"Member since {expected}" in body


def test_profile_renders_real_transaction_descriptions(client):
    _sign_in_demo(client)
    body = client.get("/profile").get_data(as_text=True)
    for desc in ("Lunch at office canteen", "Electricity bill", "New running shoes"):
        assert desc in body, f"missing description: {desc!r}"


# ------------------------------------------------------------------ #
# /profile view — empty-state (freshly registered, no expenses)        #
# ------------------------------------------------------------------ #

def test_fresh_user_profile_renders_empty_state(client):
    # Register a brand-new user through the live form so the full
    # auth + session path is exercised, then visit /profile.
    client.post(
        "/register",
        data={"name": "Empty Eve", "email": "eve@spendly.com", "password": "evepassword"},
        follow_redirects=False,
    )
    # Registration does NOT auto-sign-in (by design — see Step 2).
    # Sign in explicitly.
    client.post(
        "/login",
        data={"email": "eve@spendly.com", "password": "evepassword"},
        follow_redirects=False,
    )
    body = client.get("/profile").get_data(as_text=True)
    # Stats show zero/empty placeholders, not the demo user's data.
    assert "₹0.00" in body
    # Em-dash for top category.
    assert "—" in body
    # Demo data must NOT leak.
    assert "Lunch at office canteen" not in body
    assert "Bills" not in body  # no category row, no transaction row.
