"""Tests for the /profile endpoint (Step 4 — Profile Page)."""
import re

from database.db import create_user, get_db


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

# Reuse the same demo user from test_03 so the happy path matches
# what a real user would experience.
DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
DEMO_NAME = "Demo User"


def _seed_demo_user() -> int:
    """Create the demo user and return their id. Idempotent."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)
        ).fetchone()
    finally:
        conn.close()
    if row:
        return row["id"]
    return create_user(DEMO_NAME, DEMO_EMAIL, DEMO_PASSWORD)


def _sign_in(client) -> int:
    """Log the demo user in via POST /login. Returns the user id."""
    _seed_demo_user()
    client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    with client.session_transaction() as sess:
        return sess.get("user_id")


# ------------------------------------------------------------------ #
# GET /profile — unauthenticated                                      #
# ------------------------------------------------------------------ #

def test_get_profile_redirects_to_login_when_signed_out(client):
    resp = client.get("/profile", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

    with client.session_transaction() as sess:
        assert "user_id" not in sess


# ------------------------------------------------------------------ #
# GET /profile — authenticated                                        #
# ------------------------------------------------------------------ #

def test_get_profile_returns_200_when_signed_in(client):
    _sign_in(client)
    resp = client.get("/profile")
    assert resp.status_code == 200


def test_profile_shows_user_name_and_email(client):
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)
    assert DEMO_NAME in body
    assert DEMO_EMAIL in body


# ------------------------------------------------------------------ #
# Summary stats — at least 3 values                                   #
# ------------------------------------------------------------------ #

def test_profile_shows_three_summary_stats(client):
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)
    # Three labels from the hardcoded data.
    assert "Total spent" in body
    assert "Transactions" in body
    assert "Top category" in body
    # And their values.
    assert "₹4,688.50" in body
    assert "Bills" in body


# ------------------------------------------------------------------ #
# Transaction history — at least 3 rows                               #
# ------------------------------------------------------------------ #

def test_profile_shows_three_transaction_rows(client):
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)
    # Three real descriptions from the hardcoded data.
    assert "Lunch at office canteen" in body
    assert "Electricity bill" in body
    assert "New running shoes" in body


# ------------------------------------------------------------------ #
# Category breakdown — at least 3 categories                          #
# ------------------------------------------------------------------ #

def test_profile_shows_seven_categories(client):
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)
    for cat in ("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"):
        assert cat in body, f"missing category {cat!r}"


# ------------------------------------------------------------------ #
# Category badge uses a CSS class, not inline color                   #
# ------------------------------------------------------------------ #

def test_profile_uses_cat_badge_class(client):
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)
    assert "cat-badge" in body
    # No inline colour style sneaks in (only allowed inline is the
    # bar `width: NN%`, which is layout, not color).
    assert "background:" not in body
    assert "background-color:" not in body
    assert "color:" not in body


# ------------------------------------------------------------------ #
# Navbar logged-in state is shown                                     #
# ------------------------------------------------------------------ #

def test_profile_navbar_shows_user_name_and_sign_out(client):
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)
    assert DEMO_NAME in body
    assert "Sign out" in body
    assert 'href="/logout"' in body


# ------------------------------------------------------------------ #
# Spec rule: no hex values in profile.html                            #
# ------------------------------------------------------------------ #

def test_profile_html_has_no_hex_colors(client):
    """The spec forbids hex colour values in profile.html.

    We scan the rendered response body for any `#xxxxxx` pattern
    that looks like a colour literal. None should appear.
    """
    _sign_in(client)
    body = client.get("/profile").get_data(as_text=True)
    # A colour literal is `#` followed by 3, 4, 6, or 8 hex digits.
    matches = re.findall(r"#[0-9a-fA-F]{3,8}\b", body)
    real_hexes = [m for m in matches if len(m) - 1 in (3, 4, 6, 8)]
    assert real_hexes == [], f"hex literals found in body: {real_hexes}"


# ------------------------------------------------------------------ #
# Regression: signed-out /profile still redirects                     #
# ------------------------------------------------------------------ #

def test_get_profile_redirects_even_after_logout(client):
    _sign_in(client)
    client.get("/logout", follow_redirects=False)
    resp = client.get("/profile", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
