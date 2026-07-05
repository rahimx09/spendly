"""Tests for the /login and /logout endpoints (Step 3 — Login and Logout)."""
from database.db import create_user, get_db


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

# A pre-seeded demo user. Matches the spec's "demo@spendly.com / demo123"
# so the happy-path test exercises the same credentials a real user would.
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


# ------------------------------------------------------------------ #
# GET /login                                                          #
# ------------------------------------------------------------------ #

def test_get_login_renders_form(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # The form posts back to /login via url_for.
    assert 'action="/login"' in body
    # No error shown on a clean GET.
    assert "Invalid email or password" not in body


# ------------------------------------------------------------------ #
# POST /login — happy path                                            #
# ------------------------------------------------------------------ #

def test_post_valid_credentials_sets_session_and_redirects(client):
    _seed_demo_user()
    resp = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # Successful sign-in lands the user on their profile page.
    assert resp.headers["Location"].endswith("/profile")

    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None


def test_post_valid_credentials_redirects_to_profile(client):
    _seed_demo_user()
    resp = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=True,
    )
    # Land on the user's profile page (200 + the user info card).
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert DEMO_NAME in body
    assert DEMO_EMAIL in body
    # The "Welcome back" marketing copy is gone from the /profile route.
    assert "Welcome back" not in body


# ------------------------------------------------------------------ #
# POST /login — credential failures (generic error)                   #
# ------------------------------------------------------------------ #

def test_post_wrong_password_shows_generic_error(client):
    _seed_demo_user()
    resp = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": "wrong-password"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Invalid email or password" in body

    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_post_unknown_email_shows_same_generic_error(client):
    """Unknown email and wrong password must show the same error
    so an attacker cannot enumerate which emails are registered.
    """
    _seed_demo_user()
    resp = client.post(
        "/login",
        data={"email": "ghost@example.com", "password": "whatever"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Invalid email or password" in body
    # The error wording must be identical to the wrong-password case.
    assert "not found" not in body.lower()
    assert "no account" not in body.lower()
    assert "no user" not in body.lower()

    with client.session_transaction() as sess:
        assert "user_id" not in sess


# ------------------------------------------------------------------ #
# POST /login — case-insensitive email                                #
# ------------------------------------------------------------------ #

def test_post_email_is_case_insensitive(client):
    _seed_demo_user()
    for variant in ("Demo@Spendly.com", "DEMO@SPENDLY.COM", "demo@SPENDLY.com"):
        # Sign out between iterations — once the first variant
        # succeeds, the next POST would hit the "signed-in user
        # can't reach /login" guard and redirect to /landing instead of
        # /profile. Logging out keeps each iteration a clean
        # sign-in attempt.
        with client.session_transaction() as sess:
            sess.pop("user_id", None)

        resp = client.post(
            "/login",
            data={"email": variant, "password": DEMO_PASSWORD},
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"variant {variant!r} should succeed"
        assert resp.headers["Location"].endswith("/profile")


# ------------------------------------------------------------------ #
# POST /login — validation failures                                   #
# ------------------------------------------------------------------ #

def test_post_empty_email(client):
    resp = client.post(
        "/login",
        data={"email": "", "password": "whatever"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "email" in resp.get_data(as_text=True).lower()
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_post_empty_password(client):
    resp = client.post(
        "/login",
        data={"email": "anyone@example.com", "password": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "password" in resp.get_data(as_text=True).lower()
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_post_malformed_email(client):
    resp = client.post(
        "/login",
        data={"email": "not-an-email", "password": "whatever"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "valid email" in resp.get_data(as_text=True).lower()
    with client.session_transaction() as sess:
        assert "user_id" not in sess


# ------------------------------------------------------------------ #
# POST /login — form repopulation & password safety                   #
# ------------------------------------------------------------------ #

def test_post_preserves_email_on_failure_but_not_password(client):
    _seed_demo_user()
    submitted = "demo@spendly.com"
    resp = client.post(
        "/login",
        data={"email": submitted, "password": "wrong-password"},
        follow_redirects=False,
    )
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # The email is pre-filled in the input.
    assert f'value="{submitted}"' in body
    # The password input has no value= and the wrong password is
    # never echoed anywhere in the response.
    assert 'value="wrong-password"' not in body
    assert "wrong-password" not in body


def test_post_response_never_leaks_plaintext_password(client):
    """The plaintext password must never appear in the rendered HTML
    on the failure path."""
    _seed_demo_user()
    resp_fail = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": "definitely-wrong"},
        follow_redirects=False,
    )
    assert "definitely-wrong" not in resp_fail.get_data(as_text=True)


# ------------------------------------------------------------------ #
# /logout                                                             #
# ------------------------------------------------------------------ #

def test_logout_clears_session_and_redirects_to_login(client):
    _seed_demo_user()
    # Sign in first.
    client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    with client.session_transaction() as sess:
        assert "user_id" in sess

    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_when_not_signed_in_is_safe(client):
    """logout() must not 500 when no user is signed in."""
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


# ------------------------------------------------------------------ #
# Navbar state swap                                                   #
# ------------------------------------------------------------------ #

def test_navbar_shows_sign_in_links_when_not_logged_in(client):
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert b"Sign in" in resp.data
    assert b"Get started" in resp.data
    assert b"Sign out" not in resp.data


def test_navbar_shows_user_name_and_sign_out_when_logged_in(client):
    _seed_demo_user()
    client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )

    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert DEMO_NAME.encode() in resp.data
    assert b"Sign out" in resp.data
    # The public "Get started" CTA is hidden when signed in.
    assert b"Get started" not in resp.data


# ------------------------------------------------------------------ #
# Landing page — signed-in branch                                     #
# ------------------------------------------------------------------ #

def test_landing_shows_marketing_copy_when_signed_out(client):
    """When no user is signed in, the landing page keeps its
    marketing hero (Create free account CTA, etc.)."""
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Create free account" in body
    assert "Welcome back" not in body


def test_signed_in_landing_shows_welcome_message(client):
    _seed_demo_user()
    client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )

    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # The signed-in branch: a personal welcome with the user's name.
    assert "Welcome back" in body
    assert DEMO_NAME in body
    # The public marketing CTA is hidden when signed in.
    assert "Create free account" not in body


def test_signed_in_landing_has_sign_out_link(client):
    _seed_demo_user()
    client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )

    resp = client.get("/")
    body = resp.get_data(as_text=True)
    # The Sign out link points at /logout via url_for.
    assert 'href="/logout"' in body


# ------------------------------------------------------------------ #
# Auth-page guard — signed-in users can't reach /login or /register   #
# ------------------------------------------------------------------ #

def _sign_in(client):
    """Helper: log the demo user in via POST /login. Returns the user id."""
    _seed_demo_user()
    client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    with client.session_transaction() as sess:
        return sess.get("user_id")


def test_get_login_redirects_to_landing_when_signed_in(client):
    _sign_in(client)
    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    # The form must not render — a 302 short-circuits before the
    # template, so the response body is the redirect itself.
    body = resp.get_data(as_text=True)
    assert 'action="/login"' not in body
    # The auth form is not rendered — the 302 short-circuits before
    # the template, so the body is just the redirect itself. The
    # form's submit button text would be the only other tell, so
    # we assert the form did not render.


def test_post_login_redirects_to_landing_when_signed_in(client):
    """POSTing to /login while signed in must not overwrite the session."""
    existing_user_id = _sign_in(client)

    resp = client.post(
        "/login",
        data={"email": "other@example.com", "password": "anything"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")

    # The existing user_id must be preserved — the guard redirects,
    # it must not pop or replace the session.
    with client.session_transaction() as sess:
        assert sess.get("user_id") == existing_user_id


def test_get_register_redirects_to_landing_when_signed_in(client):
    _sign_in(client)
    resp = client.get("/register", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    body = resp.get_data(as_text=True)
    assert 'action="/register"' not in body


def test_post_register_redirects_to_landing_when_signed_in(client):
    """POSTing to /register while signed in must not create a new user."""
    _sign_in(client)

    # Count users before — to assert the POST is fully blocked, not
    # just redirected after side effects.
    conn = get_db()
    try:
        before = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    finally:
        conn.close()

    resp = client.post(
        "/register",
        data={
            "name": "Imposter",
            "email": "imposter@example.com",
            "password": "validpass123",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")

    conn = get_db()
    try:
        after = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    finally:
        conn.close()
    assert after == before, "POST /register must not create a user when signed in"


def test_get_login_still_renders_form_when_signed_out(client):
    """Regression guard: the public path must still work."""
    resp = client.get("/login")
    assert resp.status_code == 200
    assert 'action="/login"' in resp.get_data(as_text=True)


def test_get_register_still_renders_form_when_signed_out(client):
    """Regression guard: the public path must still work."""
    resp = client.get("/register")
    assert resp.status_code == 200
    assert 'action="/register"' in resp.get_data(as_text=True)
