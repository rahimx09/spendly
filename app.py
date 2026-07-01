import os
import re
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for

from database.db import create_user, init_db, seed_db

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

@app.route("/")
def landing():
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
                session["user_id"] = user_id
                return redirect(url_for("profile"))

        return render_template(
            "register.html",
            error=error,
            name=name,
            email=email,
        )

    return render_template("register.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
