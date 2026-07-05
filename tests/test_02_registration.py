"""Tests for the /register endpoint (Step 2 — Registration)."""
from database.db import create_user, get_db


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

VALID = {"name": "Nitish Kumar", "email": "nitish@example.com", "password": "hunter22!"}


def _user_count() -> int:
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# GET                                                                 #
# ------------------------------------------------------------------ #

def test_get_register_renders_form(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # The auth-error block is empty on a clean GET.
    assert "auth-error" not in body or "Please enter" not in body
    # The form posts back to /register via url_for.
    assert 'action="/register"' in body


# ------------------------------------------------------------------ #
# POST — happy path                                                   #
# ------------------------------------------------------------------ #

def test_post_valid_creates_user_and_redirects(client):
    before = _user_count()
    resp = client.post("/register", data=VALID, follow_redirects=False)
    assert resp.status_code == 302
    # Registration redirects to /login so the new user must
    # explicitly sign in (we do NOT auto-sign-in).
    assert resp.headers["Location"].endswith("/login")
    assert _user_count() == before + 1

    # The user must sign in before the session is populated.
    with client.session_transaction() as sess:
        assert "user_id" not in sess

    # The new user is queryable in the DB.
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email FROM users WHERE email = ?", (VALID["email"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["name"] == "Nitish Kumar"
    assert row["email"] == "nitish@example.com"


def test_post_stores_password_as_hash(client):
    client.post("/register", data=VALID, follow_redirects=False)
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            (VALID["email"],),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    pw_hash = row["password_hash"]
    assert pw_hash != VALID["password"]
    assert len(pw_hash) > 50  # werkzeug hashes are much longer than plaintext
    # werkzeug default scheme markers — covers scrypt, pbkdf2, argon2
    assert any(pw_hash.startswith(p) for p in ("scrypt:", "pbkdf2:", "argon2:"))


# ------------------------------------------------------------------ #
# POST — duplicate email                                              #
# ------------------------------------------------------------------ #

def test_post_duplicate_email_shows_error(client):
    # Pre-seed a user with the same email the test will POST.
    create_user("Existing User", VALID["email"], "differentpass1")
    before = _user_count()

    resp = client.post("/register", data=VALID, follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "already exists" in body.lower()
    assert _user_count() == before  # no new row

    # The submitted email is preserved in the form for convenience.
    assert f'value="{VALID["email"]}"' in body


# ------------------------------------------------------------------ #
# POST — validation failures                                          #
# ------------------------------------------------------------------ #

def test_post_empty_name(client):
    data = {**VALID, "name": ""}
    before = _user_count()
    resp = client.post("/register", data=data, follow_redirects=False)
    assert resp.status_code == 200
    assert "name" in resp.get_data(as_text=True).lower()
    assert _user_count() == before


def test_post_empty_email(client):
    data = {**VALID, "email": ""}
    before = _user_count()
    resp = client.post("/register", data=data, follow_redirects=False)
    assert resp.status_code == 200
    assert "email" in resp.get_data(as_text=True).lower()
    assert _user_count() == before


def test_post_malformed_email(client):
    data = {**VALID, "email": "not-an-email"}
    before = _user_count()
    resp = client.post("/register", data=data, follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "valid email" in body
    assert _user_count() == before


def test_post_short_password(client):
    data = {**VALID, "password": "abc"}  # 3 chars, well under the 8-char min
    before = _user_count()
    resp = client.post("/register", data=data, follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True).lower()
    assert "8 characters" in body
    assert _user_count() == before


# ------------------------------------------------------------------ #
# POST — form repopulation & password safety                          #
# ------------------------------------------------------------------ #

def test_post_preserves_name_and_email_on_failure(client):
    data = {**VALID, "password": "abc"}  # force a failure on password length
    resp = client.post("/register", data=data, follow_redirects=False)
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # The submitted name and email are pre-filled in the inputs.
    assert f'value="{VALID["name"]}"' in body
    assert f'value="{VALID["email"]}"' in body
    # The password input is never echoed — the literal placeholder
    # password is absent and there is no value= on the password input.
    assert "abc" not in body


def test_post_response_does_not_leak_password(client):
    resp = client.post("/register", data=VALID, follow_redirects=False)
    body = resp.get_data(as_text=True)
    assert VALID["password"] not in body
