import datetime
import os
import re
import sqlite3

from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    find_user_by_email,
    find_user_by_id,
    get_category_breakdown,
    get_recent_expenses,
    get_user_expense_count,
    get_user_top_category,
    get_user_total_spent,
    init_db,
    seed_db,
)

app = Flask(__name__)

# Session cookies are signed with this key. In production, set
# SPENDLY_SECRET_KEY to a strong random value. The fallback here
# lets the dev server start without any external config.
app.secret_key = os.environ.get(
    "SPENDLY_SECRET_KEY",
    "dev-only-not-for-production",
)

# Validation bounds for the registration form.
NAME_MAX, EMAIL_MAX, PW_MIN, PW_MAX = 100, 254, 8, 128
# Lightweight email shape check — catches obvious garbage, not
# RFC-perfect validation (out of scope for this step).
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.before_request
def load_signed_in_user():
    """Attach the current user to `g` once per request, when signed in.

    The navbar reads `g.user` to decide between the signed-in and
    public link sets. We guard on `session.get("user_id")` so pages
    with no signed-in user pay zero DB cost.
    """
    user_id = session.get("user_id")
    g.user = find_user_by_id(user_id) if user_id else None


# Endpoints that only make sense for signed-out visitors. A signed-in
# user revisiting /login or /register would just re-render the form
# (or, worse, POST a second account / overwrite the session), so we
# bounce them to the landing page. Adding a future route to this set
# is the entire opt-in cost.
SIGNED_OUT_ONLY_ENDPOINTS = {"login", "register"}


@app.before_request
def block_auth_pages_when_signed_in():
    """Redirect signed-in users away from sign-in / sign-up pages.

    Runs after `load_signed_in_user` (Flask runs before_request hooks
    in registration order), so `g.user` is already populated. The
    endpoint filter excludes `/` and other public routes — important,
    otherwise the redirect target would itself be blocked and we'd
    loop.
    """
    if g.user is not None and request.endpoint in SIGNED_OUT_ONLY_ENDPOINTS:
        return redirect(url_for("landing"))
    return None


@app.route("/")
def landing():
    if g.user is not None:
        return redirect(url_for("profile"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        # Validate. Order matters — first failing rule wins so the
        # user gets the most relevant message.
        if not name:
            error = "Please enter your name."
        elif len(name) > NAME_MAX:
            error = "Name is too long (max 100 characters)."
        elif not email:
            error = "Please enter your email."
        elif len(email) > EMAIL_MAX or not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < PW_MIN:
            error = "Password must be at least 8 characters."
        elif len(password) > PW_MAX:
            error = "Password is too long (max 128 characters)."
        else:
            try:
                user_id = create_user(name, email, password)
            except sqlite3.IntegrityError:
                error = "An account with that email already exists."
            else:
                # Account created — send the user to /login so they
                # explicitly sign in. We deliberately do NOT set
                # session["user_id"] here; auto-signing-in bypasses
                # the password re-entry that protects the account.
                return redirect(url_for("login"))

        return render_template(
            "register.html",
            error=error,
            name=name,
            email=email,
        )

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        # Validate. Order matters — first failing rule wins so the
        # user gets the most relevant message.
        if not email:
            error = "Please enter your email."
        elif len(email) > EMAIL_MAX or not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif not password:
            error = "Please enter your password."
        elif len(password) > PW_MAX:
            error = "Password is too long (max 128 characters)."
        else:
            # Look up the user, then verify. We do NOT distinguish
            # "no such email" from "wrong password" in the response —
            # same generic error either way is the standard
            # anti-enumeration pattern.
            user = find_user_by_email(email)
            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                return redirect(url_for("profile"))
            error = "Invalid email or password."

        return render_template("login.html", error=error, email=email)

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Authenticated routes                                                 #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    if g.user is None:
        return redirect(url_for("login"))

    user_id = g.user["id"]

    # `created_at` is the SQLite `datetime('now')` literal, e.g.
    # "2026-03-15 12:34:56". Slicing the first 10 chars before
    # strptime keeps the parse robust to that format and to
    # any future migration that drops the time component.
    member_since = datetime.datetime.strptime(
        g.user["created_at"][:10], "%Y-%m-%d"
    ).strftime("%B %Y")

    user = {
        "name": g.user["name"],
        "email": g.user["email"],
        "member_since": member_since,
        "initials": (g.user["name"][:2] or "DU").upper(),
    }

    total = get_user_total_spent(user_id)
    count = get_user_expense_count(user_id)
    top = get_user_top_category(user_id)

    summary = [
        {"label": "Total spent",  "value": f"₹{total:,.2f}", "icon": "wallet"},
        {"label": "Transactions", "value": str(count),         "icon": "receipt"},
        {"label": "Top category", "value": top or "—",         "icon": "tag"},
    ]

    transactions = get_recent_expenses(user_id)
    categories = get_category_breakdown(user_id)

    return render_template(
        "profile.html",
        user=user,
        summary=summary,
        transactions=transactions,
        categories=categories,
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/analytics")
def analytics():
    if g.user is None:
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/logout")
def logout():
    # pop(..., None) is safe whether or not a user is signed in —
    # no KeyError, no 500.
    session.pop("user_id", None)
    return redirect(url_for("login"))


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
