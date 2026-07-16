"""Tests for Step 8 — Edit Expense.

Covers the Definition-of-Done checklist from the spec:
  1. db.get_expense_by_id(user_id, expense_id) returns the row for an
     owned id, and None for a foreign or non-existent id.
  2. db.update_expense(user_id, expense_id, ...) returns the affected
     row count; a foreign id affects zero rows and the row is unchanged.
  3. GET /expenses/<id>/edit while signed out -> 302 to /login.
  4. GET /expenses/<id>/edit while signed in, for an owned row ->
     200 with the form pre-filled from the row.
  5. GET renders every CATEGORIES value in the <select>.
  6. GET for a foreign id -> 302 to /profile with no form rendered.
  7. GET for a non-existent id -> 302 to /profile with no error.
  8. POST with valid data updates the row and redirects to /profile;
     the change shows up on /profile.
  9. POST amount validation (empty / non-numeric / non-positive /
     too large / NaN / inf) rejects, echoes bad input, leaves row
     unchanged.
 10. POST category validation: anything outside CATEGORIES rejects;
     every CATEGORIES value is accepted.
 11. POST date validation (empty / malformed) rejects; past and
     future dates are both allowed.
 12. POST description: blank stores NULL; overlong is rejected or
     truncated to <= 200.
 13. POST for a foreign or non-existent id -> 302 to /profile, row
     unchanged (ownership invariant).
 14. Security: POST cannot inject user_id and overwrite ownership.
 15. Profile transaction table shows an Edit link for every row,
     pointing at /expenses/<id>/edit.
"""
import uuid

import pytest

from database import db as db_module
from database.db import (
    CATEGORIES, add_expense, create_user, get_db,
    get_expense_by_id, update_expense,
)


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


def _seed_expense(uid: int, amount: float = 100.0, category: str = "Food",
                  date: str = "2026-07-10",
                  description: str = "seed") -> int:
    """Insert one expense owned by `uid` and return its id."""
    return add_expense(uid, amount, category, date, description)


def _row(eid: int) -> dict | None:
    """Read an expense row back as a plain dict (or None if missing)."""
    conn = get_db()
    try:
        r = conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses WHERE id = ?",
            (eid,),
        ).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


# ------------------------------------------------------------------ #
# 1. DB helper — get_expense_by_id                                     #
# ------------------------------------------------------------------ #

def test_get_expense_by_id_returns_owned_row():
    """get_expense_by_id must return the row whose (id, user_id) match."""
    uid = create_user("Owner", f"{uuid.uuid4()}@example.com", "password123")
    eid = _seed_expense(uid, 199.99, "Transport", "2026-07-01", "Cab ride")

    row = get_expense_by_id(uid, eid)
    assert row is not None
    assert row["id"] == eid
    assert row["user_id"] == uid
    assert row["amount"] == 199.99
    assert row["category"] == "Transport"
    assert row["date"] == "2026-07-01"
    assert row["description"] == "Cab ride"


def test_get_expense_by_id_returns_none_for_foreign_id():
    """A foreign id (owned by another user) must return None — the
    route cannot distinguish 'not your row' from 'no such row'."""
    a = create_user("A", f"{uuid.uuid4()}@example.com", "password123")
    b = create_user("B", f"{uuid.uuid4()}@example.com", "password123")
    eid = _seed_expense(b)
    assert get_expense_by_id(a, eid) is None
    # And owner B can still see it.
    assert get_expense_by_id(b, eid) is not None


def test_get_expense_by_id_returns_none_for_non_existent_id():
    """A non-existent id must return None."""
    uid = create_user("Tester", f"{uuid.uuid4()}@example.com", "password123")
    assert get_expense_by_id(uid, 99999) is None


# ------------------------------------------------------------------ #
# 2. DB helper — update_expense                                        #
# ------------------------------------------------------------------ #

def test_update_expense_changes_owned_row_and_returns_one():
    """update_expense must mutate an owned row in place and return 1."""
    uid = create_user("Updater", f"{uuid.uuid4()}@example.com", "password123")
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")

    rc = update_expense(uid, eid, 250.50, "Health", "2026-07-16", "after")
    assert rc == 1

    row = _row(eid)
    assert row is not None
    assert row["amount"] == 250.50
    assert row["category"] == "Health"
    assert row["date"] == "2026-07-16"
    assert row["description"] == "after"


def test_update_expense_returns_zero_for_foreign_id_and_leaves_row():
    """A foreign id must affect zero rows and leave the original row
    unchanged. This is the ownership invariant at the DB layer."""
    a = create_user("A", f"{uuid.uuid4()}@example.com", "password123")
    b = create_user("B", f"{uuid.uuid4()}@example.com", "password123")
    eid = _seed_expense(b, 100.0, "Food", "2026-07-10", "before")

    rc = update_expense(a, eid, 999.99, "Hacked", "2099-01-01", "nope")
    assert rc == 0

    # The original row, owned by B, is untouched.
    row = _row(eid)
    assert row["user_id"] == b
    assert row["amount"] == 100.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-07-10"
    assert row["description"] == "before"


def test_update_expense_returns_zero_for_non_existent_id():
    """A non-existent id must affect zero rows (no exception)."""
    uid = create_user("Tester", f"{uuid.uuid4()}@example.com", "password123")
    assert update_expense(uid, 99999, 1.0, "Food", "2026-07-10", None) == 0


def test_update_expense_stores_none_for_blank_description():
    """An empty description must persist as NULL, not ''."""
    uid = create_user("Tester", f"{uuid.uuid4()}@example.com", "password123")
    eid = _seed_expense(uid)
    update_expense(uid, eid, 50.0, "Food", "2026-07-10", None)
    assert _row(eid)["description"] is None


# ------------------------------------------------------------------ #
# 3. GET /expenses/<id>/edit — auth + ownership                        #
# ------------------------------------------------------------------ #

def test_get_edit_redirects_to_login_when_signed_out(client):
    """GET /expenses/<id>/edit while signed out -> 302 to /login."""
    resp = client.get("/expenses/1/edit", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_get_edit_returns_200_with_prefilled_form_when_signed_in(client):
    """GET /expenses/<id>/edit for an owned row -> 200 with the form
    pre-filled from the loaded row's values."""
    import re
    uid = _sign_in(client)
    eid = _seed_expense(uid, 250.50, "Food", "2026-07-16", "Lunch at office canteen")

    resp = client.get(f"/expenses/{eid}/edit", follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # All four inputs present.
    assert 'name="amount"' in body
    assert 'name="category"' in body
    assert 'name="date"' in body
    assert 'name="description"' in body
    # Form posts to itself via url_for('edit_expense', id=…).
    assert f'action="/expenses/{eid}/edit"' in body
    # Submit button reads "Save changes".
    assert ">Save changes<" in body
    # The row's current amount, date, and description are pre-filled.
    assert 'value="250.5"' in body
    assert 'value="2026-07-16"' in body
    assert 'value="Lunch at office canteen"' in body
    # The category option for the row's category is the selected one.
    # (Jinja may render the selected attribute on its own line, so allow
    # any whitespace between the value and the attribute.)
    assert re.search(
        r'<option\s+value="Food"\s+selected\b', body
    ) is not None, "Food option should be marked selected"


def test_get_edit_renders_every_category(client):
    """The <select> must offer one <option> per CATEGORIES entry."""
    uid = _sign_in(client)
    eid = _seed_expense(uid)
    body = client.get(f"/expenses/{eid}/edit").get_data(as_text=True)
    for c in CATEGORIES:
        assert f'value="{c}"' in body, f"missing option for category {c!r}"


def test_get_edit_redirects_to_profile_for_foreign_id(client):
    """A signed-in user GET-ing a foreign id is silently redirected to
    /profile — no form rendered, no existence leak."""
    a = _sign_in(client, email="a@example.com")
    b = create_user("B", f"{uuid.uuid4()}@example.com", "password123")
    eid = _seed_expense(b)

    resp = client.get(f"/expenses/{eid}/edit", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    # The response body must NOT contain any of the form fields.
    body = resp.get_data(as_text=True)
    assert 'name="amount"' not in body
    assert 'name="category"' not in body
    assert 'name="date"' not in body
    assert 'name="description"' not in body
    # And the foreign row is unchanged.
    assert _row(eid)["user_id"] == b


def test_get_edit_redirects_to_profile_for_non_existent_id(client):
    """A non-existent id silently redirects to /profile with no error."""
    _sign_in(client)
    resp = client.get("/expenses/9999/edit", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    body = resp.get_data(as_text=True)
    # No form rendered.
    assert 'name="amount"' not in body
    # No error shown.
    assert "auth-error" not in body


# ------------------------------------------------------------------ #
# 4. POST /expenses/<id>/edit — happy path                             #
# ------------------------------------------------------------------ #

def test_post_valid_updates_row_and_redirects_to_profile(client):
    """A valid POST updates the row in place and redirects to /profile;
    the change is visible on the next /profile render."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")

    resp = client.post(
        f"/expenses/{eid}/edit", data=VALID, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")

    # The row reflects the new values.
    row = _row(eid)
    assert row["user_id"] == uid
    assert row["amount"] == 250.50
    assert row["category"] == "Food"
    assert row["date"] == "2026-07-16"
    assert row["description"] == "Lunch at office canteen"


def test_post_valid_reflects_on_profile(client):
    """After a successful POST, /profile must show the new amount and
    description in the transaction table."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")

    client.post(f"/expenses/{eid}/edit", data=VALID, follow_redirects=True)
    body = client.get("/profile").get_data(as_text=True)
    assert "₹250.50" in body
    assert "Lunch at office canteen" in body


# ------------------------------------------------------------------ #
# 5. POST validation — amount                                           #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("bad_amount", ["", "abc", "0", "-5"])
def test_post_bad_amount_rejects_and_echoes_fields(client, bad_amount):
    """Empty / non-numeric / non-positive amounts reject, do not update,
    and the form re-renders with the entered fields echoed back."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "amount": bad_amount}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "auth-error" in body
    # The row is NOT updated — read it back, assert unchanged.
    row = _row(eid)
    assert row["amount"] == 100.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-07-10"
    assert row["description"] == "before"
    # The bad amount is echoed in the rendered input.
    assert f'value="{bad_amount}"' in body


@pytest.mark.parametrize("bad_amount", ["2000000000", "1000000001"])
def test_post_amount_above_one_billion_rejects(client, bad_amount):
    """amount > AMOUNT_MAX (1_000_000_000) must reject without updating."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "amount": bad_amount}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _row(eid)["amount"] == 100.0


@pytest.mark.parametrize("bad_amount", ["NaN", "nan", "inf", "-inf", "Infinity"])
def test_post_nan_or_inf_amount_rejected(client, bad_amount):
    """NaN / inf must reject the same way as non-numeric input — they
    pass float() but break SQL aggregates, so they must never update."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "amount": bad_amount}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _row(eid)["amount"] == 100.0


# ------------------------------------------------------------------ #
# 6. POST validation — category                                         #
# ------------------------------------------------------------------ #

def test_post_hand_crafted_category_rejects(client):
    """A category not in CATEGORIES (forged by hand) must reject without
    updating the row."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "category": "Hacked"}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _row(eid)["category"] == "Food"


@pytest.mark.parametrize("category", list(CATEGORIES))
def test_post_each_valid_category_works(client, category):
    """Every value in CATEGORIES must be accepted on POST."""
    uid = _sign_in(client, email=f"{category.lower()}@example.com")
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "category": category}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 302, (
        f"category {category!r} should be accepted but got {resp.status_code}"
    )
    assert resp.headers["Location"].endswith("/profile")
    assert _row(eid)["category"] == category


# ------------------------------------------------------------------ #
# 7. POST validation — date                                             #
# ------------------------------------------------------------------ #

def test_post_empty_date_rejects(client):
    """An empty date must reject and not update."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "date": ""}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _row(eid)["date"] == "2026-07-10"


@pytest.mark.parametrize("bad_date", ["not-a-date", "2025/01/01", "2026-13-40",
                                      "2026-02-30"])
def test_post_malformed_date_rejects(client, bad_date):
    """Malformed dates must reject and not update."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "date": bad_date}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "auth-error" in resp.get_data(as_text=True)
    assert _row(eid)["date"] == "2026-07-10"


def test_post_past_date_is_allowed(client):
    """Back-dating is legitimate — a past date must be accepted."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "date": "2020-01-15"}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    assert _row(eid)["date"] == "2020-01-15"


def test_post_future_date_is_allowed(client):
    """The spec explicitly states there is no future-date restriction —
    a future date must be accepted."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "date": "2099-12-31"}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 302
    assert _row(eid)["date"] == "2099-12-31"


# ------------------------------------------------------------------ #
# 8. POST validation — description                                      #
# ------------------------------------------------------------------ #

def test_post_blank_description_stores_null(client):
    """A blank description must store NULL, not ''."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "description": ""}

    client.post(f"/expenses/{eid}/edit", data=data, follow_redirects=False)
    assert _row(eid)["description"] is None


def test_post_whitespace_only_description_stores_null(client):
    """A whitespace-only description is stripped to '' then stored as NULL."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    data = {**VALID, "description": "   \t  "}

    client.post(f"/expenses/{eid}/edit", data=data, follow_redirects=False)
    assert _row(eid)["description"] is None


def test_post_long_description_is_capped_at_or_below_200_chars(client):
    """Description over 200 chars is either rejected (no row updated)
    OR truncated to <= 200 chars on the way to the DB."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "before")
    long_desc = "x" * 250
    data = {**VALID, "description": long_desc}

    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    if resp.status_code == 200:
        # Rejection path: description was rejected, row unchanged.
        assert _row(eid)["description"] == "before"
    else:
        # Truncation path: row was updated but description is capped.
        assert resp.status_code == 302
        stored = _row(eid)["description"]
        assert stored is not None
        assert len(stored) <= 200


# ------------------------------------------------------------------ #
# 9. POST ownership — foreign / non-existent id                         #
# ------------------------------------------------------------------ #

def test_post_foreign_id_redirects_to_profile_and_leaves_row(client):
    """A signed-in user POST-ing a foreign id is silently redirected to
    /profile and the foreign row is unchanged. This is the ownership
    invariant at the route layer."""
    a = _sign_in(client, email="a@example.com")
    b = create_user("B", f"{uuid.uuid4()}@example.com", "password123")
    eid = _seed_expense(b, 100.0, "Food", "2026-07-10", "before")

    resp = client.post(
        f"/expenses/{eid}/edit", data=VALID, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")

    # The foreign row is untouched.
    row = _row(eid)
    assert row["user_id"] == b
    assert row["amount"] == 100.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-07-10"
    assert row["description"] == "before"


def test_post_non_existent_id_redirects_to_profile(client):
    """A non-existent id silently redirects to /profile with no error."""
    _sign_in(client)
    resp = client.post(
        "/expenses/9999/edit", data=VALID, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    body = resp.get_data(as_text=True)
    assert "auth-error" not in body


# ------------------------------------------------------------------ #
# 10. Security — POST cannot inject user_id                             #
# ------------------------------------------------------------------ #

def test_post_cannot_inject_user_id(client):
    """A client cannot change the owner of a row by sending a forged
    user_id field; the UPDATE must always use g.user['id']."""
    attacker_id = _sign_in(client, email="attacker@example.com")
    victim_id = create_user("Victim", f"{uuid.uuid4()}@example.com",
                            "password123")
    assert victim_id != attacker_id

    # Sign in as the victim and seed one of their own expenses, then
    # verify the attacker cannot reassign it by POSTing with a
    # user_id field.
    with client.session_transaction() as sess:
        sess["user_id"] = victim_id
    eid = _seed_expense(victim_id, 100.0, "Food", "2026-07-10", "before")

    # Switch back to the attacker and forge a POST with user_id=attacker.
    with client.session_transaction() as sess:
        sess["user_id"] = attacker_id
    data = {**VALID, "user_id": str(attacker_id)}

    # The attacker POSTs to the victim's row — update_expense scopes
    # by user_id, so the WHERE clause matches zero rows. The route
    # must redirect (not 500, not 200, not silently "succeed").
    resp = client.post(
        f"/expenses/{eid}/edit", data=data, follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")

    # The victim's row is still owned by the victim AND the values
    # are still the original ones (no UPDATE happened).
    row = _row(eid)
    assert row["user_id"] == victim_id
    assert row["amount"] == 100.0
    assert row["category"] == "Food"
    assert row["description"] == "before"


# ------------------------------------------------------------------ #
# 11. Profile table — Edit link                                         #
# ------------------------------------------------------------------ #

def test_profile_renders_edit_link_for_every_row(client):
    """The /profile transaction table must show an Edit link for every
    row, pointing at /expenses/<id>/edit."""
    uid = _sign_in(client)
    eid_1 = _seed_expense(uid, 100.0, "Food", "2026-07-10", "row1")
    eid_2 = _seed_expense(uid, 200.0, "Transport", "2026-07-11", "row2")
    eid_3 = _seed_expense(uid, 300.0, "Bills", "2026-07-12", "row3")

    body = client.get("/profile").get_data(as_text=True)
    for eid in (eid_1, eid_2, eid_3):
        assert f'href="/expenses/{eid}/edit"' in body, (
            f"missing Edit link for row id={eid}"
        )
    # The link label is "Edit".
    assert ">Edit<" in body


def test_profile_edit_link_uses_url_for_endpoint(client):
    """The Edit link's href must be generated by url_for('edit_expense',
    id=…), so the link survives any future URL-prefix change."""
    uid = _sign_in(client)
    eid = _seed_expense(uid)
    body = client.get("/profile").get_data(as_text=True)
    # Verify the URL is /expenses/<id>/edit (the route's URL pattern).
    assert f"/expenses/{eid}/edit" in body


# ------------------------------------------------------------------ #
# 12. End-to-end smoke                                                  #
# ------------------------------------------------------------------ #

def test_edit_round_trip_preserves_all_fields(client):
    """End-to-end: seed → edit to new values → read back matches."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 50.0, "Food", "2026-07-01", "old")

    data = {
        "amount": "999.99",
        "category": "Entertainment",
        "date": "2026-08-15",
        "description": "Concert tickets",
    }
    resp = client.post(f"/expenses/{eid}/edit", data=data, follow_redirects=False)
    assert resp.status_code == 302

    row = _row(eid)
    assert row["user_id"] == uid
    assert row["amount"] == 999.99
    assert row["category"] == "Entertainment"
    assert row["date"] == "2026-08-15"
    assert row["description"] == "Concert tickets"


def test_get_edit_page_signed_out_then_signed_in_renders_form(client):
    """Signed out -> guarded redirect; signed in -> form pre-fills."""
    uid = _sign_in(client)
    eid = _seed_expense(uid, 100.0, "Food", "2026-07-10", "Lunch")

    # Switch to signed out.
    with client.session_transaction() as sess:
        sess.pop("user_id", None)
    r1 = client.get(f"/expenses/{eid}/edit", follow_redirects=False)
    assert r1.status_code == 302
    assert r1.headers["Location"].endswith("/login")

    # Sign back in.
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    r2 = client.get(f"/expenses/{eid}/edit", follow_redirects=False)
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert 'value="100' in body       # the loaded amount
    assert 'value="Lunch"' in body    # the loaded description
