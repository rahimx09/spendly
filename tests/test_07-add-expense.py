"""Tests for Step 7 — Add Expense.

Covers the Definition-of-Done checklist from the spec:
  1. GET /expenses/add while signed in -> 200 with all four inputs.
  2. GET /expenses/add while signed out -> 302 to /login.
  3. POST /expenses/add with valid data -> one row inserted, 302 to /profile,
     and the new expense is reflected on /profile.
  4. db.add_expense(user_id, amount, category, date, description) inserts a
     row that is readable back.
  5. Amount validation: empty / non-numeric / non-positive / absurdly large
     all reject; two-decimal money value passes; previously entered fields
     are echoed on failure.
  6. Category validation: anything not in CATEGORIES rejects; every
     CATEGORIES value is accepted.
  7. Date validation: empty / malformed reject; back-dating is allowed; a
     future date is also allowed (no future-date restriction per spec).
  8. Description validation: blank stores NULL; whitespace-only stores NULL;
     overlong text is rejected or truncated to <= 200 chars.
  9. Security: the insert uses g.user["id"], never a client-supplied user_id.
 10. Navbar: "Add expense" link shows for signed-in users, marked active on
     /expenses/add, and not shown for signed-out users.
"""
import uuid

import pytest

from database import db as db_module
from database.db import CATEGORIES, add_expense, create_user, get_db


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

# A canonical valid payload — one of every field valid in isolation.
VALID = {
    "amount": "250.50",
    "category": "Food",
    "date": "2026-07-16",
    "description": "Lunch at office canteen",
}


def _sign_in(client, email: str = "test@example.com",
             password: str = "password123") -> int:
    """Create a fresh user, bind their id into the test session, return id."""
    uid = create_user("Test User", email, password)
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


def _expense_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# 1. DB helper — parameterised insert + read-back                       #
# ------------------------------------------------------------------ #

def test_db_add_expense_stores_all_columns():
    """add_expense must insert the row and return its id; the row
    is readable back with every column populated correctly."""
    uid = create_user("Helper Tester", f"{uuid.uuid4()}@example.com",
                      "password123")
    eid = add_expense(uid, 199.99, "Transport", "2026-07-01", "Cab ride")
    assert isinstance(eid, int) and eid > 0

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT user_id, amount, category, date, description "
            "FROM expenses WHERE id = ?",
            (eid,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["user_id"] == uid
    assert row["amount"] == 199.99
    assert row["category"] == "Transport"
    assert row["date"] == "2026-07-01"
    assert row["description"] == "Cab ride"


# ------------------------------------------------------------------ #
# 2. Auth guards                                                        #
# ------------------------------------------------------------------ #

def test_get_add_redirects_to_login_when_signed_out(client):
    """GET /expenses/add while signed out -> 302 to /login."""
    resp = client.get("/expenses/add", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_get_add_returns_200_with_form_when_signed_in(client):
    """GET /expenses/add while signed in -> 200 + form fields present."""
    _sign_in(client)
    resp = client.get("/expenses/add", follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # All four inputs present.
    assert 'name="amount"' in body
    assert 'name="category"' in body
    assert 'name="date"' in body
    assert 'name="description"' in body
    # Form posts to itself via url_for('add_expense').
    assert 'action="/expenses/add"' in body


def test_get_add_renders_every_category(client):
    """The <select> must offer one <option> per CATEGORIES entry."""
    _sign_in(client)
    body = client.get("/expenses/add").get_data(as_text=True)
    for c in CATEGORIES:
        assert f'value="{c}"' in body, f"missing option for category {c!r}"


# ------------------------------------------------------------------ #
# 3. POST happy path                                                    #
# ------------------------------------------------------------------ #

def test_post_valid_inserts_one_row_and_redirects_to_profile(client):
    """Valid POST inserts exactly one row for the signed-in user and
    redirects to /profile (HTTP 302)."""
    uid = _sign_in(client)
    before = _expense_count()
    resp = client.post("/expenses/add", data=VALID, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    assert _expense_count() == before + 1

    # The single new row is owned by the signed-in user.
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT user_id, amount, category, date, description "
            "FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row["user_id"] == uid
    assert row["amount"] == 250.50
    assert row["category"] == "Food"
    assert row["date"] == "2026-07-16"
    assert row["description"] == "Lunch at office canteen"


def test_post_valid_two_decimal_amount_works(client):
    """A typical two-decimal money value must be accepted and stored."""
    _sign_in(client)
    data = {**VALID, "amount": "19.99"}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT amount FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert abs(row["amount"] - 19.99) < 1e-9


def test_post_valid_reflects_on_profile(client):
    """After a successful POST, /profile must show the new expense in
    the transaction table and the category breakdown."""
    _sign_in(client)
    client.post("/expenses/add", data=VALID, follow_redirects=True)
    body = client.get("/profile").get_data(as_text=True)
    # The new amount shows up in the transaction table.
    assert "₹250.50" in body
    # The category breakdown shows the new category.
    assert "Food" in body
    # The new description appears in the transaction list.
    assert "Lunch at office canteen" in body


# ------------------------------------------------------------------ #
# 4. Validation — amount                                                #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("bad_amount", ["", "abc", "0", "-5"])
def test_post_bad_amount_rejects_and_echoes_fields(client, bad_amount):
    """Empty / non-numeric / non-positive amounts reject, do not insert,
    and the form re-renders with the entered fields echoed back."""
    _sign_in(client)
    before = _expense_count()
    data = {**VALID, "amount": bad_amount}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # An error is shown to the user.
    assert "auth-error" in body
    # No row was inserted.
    assert _expense_count() == before
    # The previously entered amount is echoed so the user doesn't retype.
    assert f'value="{bad_amount}"' in body


def test_post_amount_above_one_billion_rejects(client):
    """amount > 1_000_000_000 must be rejected (absurd upper bound)."""
    _sign_in(client)
    before = _expense_count()
    data = {**VALID, "amount": "2000000000"}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _expense_count() == before


def test_post_one_billion_amount_rejected(client):
    """The boundary value itself (> 1e9) must reject — the rule is
    strict greater-than, not greater-than-or-equal-to-something-larger."""
    _sign_in(client)
    before = _expense_count()
    data = {**VALID, "amount": "1000000001"}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _expense_count() == before


@pytest.mark.parametrize("bad_amount", ["NaN", "nan", "inf", "-inf", "Infinity"])
def test_post_nan_or_inf_amount_rejected(client, bad_amount):
    """float('nan') and float('inf') pass float() but break every SQL
    aggregate (SUM, AVG) on the user's expenses if allowed through. They
    must be rejected with the same 'invalid amount' error as non-numeric
    input — never inserted."""
    _sign_in(client)
    before = _expense_count()
    data = {**VALID, "amount": bad_amount}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _expense_count() == before


# ------------------------------------------------------------------ #
# 5. Validation — category                                              #
# ------------------------------------------------------------------ #

def test_post_hand_crafted_category_rejects(client):
    """A category not in CATEGORIES (e.g. forged in a hand-crafted POST)
    must reject and not insert."""
    _sign_in(client)
    before = _expense_count()
    data = {**VALID, "category": "Hacked"}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "auth-error" in body
    assert _expense_count() == before
    # The form re-rendered with the category <select> intact.
    assert 'name="category"' in body


@pytest.mark.parametrize("category", list(CATEGORIES))
def test_post_each_valid_category_works(client, category):
    """Every value in CATEGORIES must be accepted on POST."""
    _sign_in(client, email=f"{category.lower()}@example.com")
    data = {**VALID, "category": category}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 302, (
        f"category {category!r} should be accepted but got {resp.status_code}"
    )
    assert resp.headers["Location"].endswith("/profile")


# ------------------------------------------------------------------ #
# 6. Validation — date                                                  #
# ------------------------------------------------------------------ #

def test_post_empty_date_rejects(client):
    """An empty date must reject and not insert."""
    _sign_in(client)
    before = _expense_count()
    data = {**VALID, "date": ""}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _expense_count() == before


@pytest.mark.parametrize("bad_date", ["not-a-date", "2025/01/01", "2026-13-40",
                                      "2026-02-30"])
def test_post_malformed_date_rejects(client, bad_date):
    """Malformed dates (non-ISO, bad month/day) must reject and not insert."""
    _sign_in(client)
    before = _expense_count()
    data = {**VALID, "date": bad_date}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _expense_count() == before


def test_post_past_date_is_allowed(client):
    """Back-dating is legitimate — a date well in the past must be
    accepted (no future-date restriction per spec)."""
    _sign_in(client)
    data = {**VALID, "date": "2020-01-15"}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")


def test_post_future_date_is_allowed(client):
    """The spec explicitly states there is no future-date restriction —
    a future date must be accepted."""
    _sign_in(client)
    data = {**VALID, "date": "2099-12-31"}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")


# ------------------------------------------------------------------ #
# 7. Validation — description                                           #
# ------------------------------------------------------------------ #

def test_post_omitted_description_stores_null(client):
    """A blank/omitted description must store NULL, not ""."""
    _sign_in(client)
    data = {**VALID, "description": ""}
    client.post("/expenses/add", data=data, follow_redirects=False)

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT description FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row["description"] is None


def test_post_whitespace_only_description_stores_null(client):
    """A whitespace-only description must be treated as blank and
    stored as NULL after strip."""
    _sign_in(client)
    data = {**VALID, "description": "   \t  "}
    client.post("/expenses/add", data=data, follow_redirects=False)

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT description FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row["description"] is None


def test_post_long_description_is_capped_at_or_below_200_chars(client):
    """Description over 200 chars is either rejected (no row inserted)
    OR truncated to <= 200 chars on the way to the DB. Either rule
    satisfies the spec — verify the stored value never exceeds 200."""
    _sign_in(client)
    long_desc = "x" * 250
    before = _expense_count()
    data = {**VALID, "description": long_desc}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)

    if resp.status_code == 200:
        # Rejection path: no row inserted.
        assert _expense_count() == before
    else:
        # Truncation path: a row was inserted but the description is
        # capped at or below 200 chars.
        assert resp.status_code == 302
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT description FROM expenses ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        assert row["description"] is not None
        assert len(row["description"]) <= 200


# ------------------------------------------------------------------ #
# 8. Security / data integrity                                          #
# ------------------------------------------------------------------ #

def test_post_cannot_inject_user_id(client):
    """A client cannot overwrite the owner of a row by sending a
    user_id field; the insert must always use g.user['id']."""
    attacker_id = _sign_in(client, email="attacker@example.com",
                           password="password123")
    # Create a second user we will try to attribute the row to.
    victim_id = create_user("Victim", "victim@example.com", "password123")
    assert victim_id != attacker_id

    # Forge a POST that includes a hidden user_id field pointing at
    # the victim. The route must ignore it.
    data = {**VALID, "user_id": str(victim_id)}
    resp = client.post("/expenses/add", data=data, follow_redirects=False)
    assert resp.status_code == 302

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT user_id FROM expenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    # The row belongs to the signed-in user, not the forged value.
    assert row["user_id"] == attacker_id
    assert row["user_id"] != victim_id


# ------------------------------------------------------------------ #
# 9. Navbar                                                             #
# ------------------------------------------------------------------ #

def test_navbar_has_add_expense_link_when_signed_in(client):
    """The "Add expense" nav link must be present for signed-in users."""
    _sign_in(client)
    body = client.get("/expenses/add").get_data(as_text=True)
    assert "Add expense" in body
    # The link must point at /expenses/add via url_for.
    assert 'href="/expenses/add"' in body


def test_navbar_marks_add_expense_link_active_on_add_page(client):
    """When the user is on /expenses/add, the nav link must carry the
    active class (request.endpoint == 'add_expense' pattern)."""
    _sign_in(client)
    body = client.get("/expenses/add").get_data(as_text=True)
    # The active link is identified by the is-active class on a
    # nav-link anchor whose href points at /expenses/add.
    import re
    # Find any <a> ... </a> tag that contains BOTH the is-active class and
    # an href pointing at /expenses/add, with "Add expense" as the label.
    m = re.search(
        r'<a\b[^>]*\bclass="[^"]*\bis-active\b[^"]*"[^>]*\bhref="[^"]*expenses/add"[^>]*>'
        r'[^<]*Add expense[^<]*</a>',
        body,
    )
    assert m is not None, "Add expense nav link should be marked is-active"


def test_navbar_omits_add_expense_link_when_signed_out(client):
    """The "Add expense" nav link must NOT appear for signed-out users."""
    body = client.get("/").get_data(as_text=True)
    assert "Add expense" not in body
    # And the href must not be rendered either.
    assert 'href="/expenses/add"' not in body


# ------------------------------------------------------------------ #
# 10. /profile guard: still works while signed out                      #
# ------------------------------------------------------------------ #

def test_add_page_signed_out_then_signed_in_works_end_to_end(client):
    """End-to-end smoke: sign out -> guarded redirect; sign in ->
    form renders; valid POST -> row inserted and visible on /profile."""
    # Signed out: bounce.
    r1 = client.get("/expenses/add", follow_redirects=False)
    assert r1.status_code == 302
    assert r1.headers["Location"].endswith("/login")

    # Sign in.
    _sign_in(client)

    # GET renders the form.
    r2 = client.get("/expenses/add", follow_redirects=False)
    assert r2.status_code == 200

    # POST inserts and redirects to /profile.
    r3 = client.post("/expenses/add", data=VALID, follow_redirects=True)
    assert r3.status_code == 200
    body = r3.get_data(as_text=True)
    assert "₹250.50" in body
    assert "Lunch at office canteen" in body
