# Spec: Login and Logout

## Overview

Wire up the existing `/login` and `/logout` routes so a returning
user can authenticate against the `users` table and clear their
session. After logging in, the user is redirected to the (currently
placeholder) profile page — the same target `/register` already uses —
and the navbar reflects their signed-in state. The demo user seeded
in Step 1 (`demo@spendly.com` / `demo123`) becomes the canonical way
to log in and exercise the app end-to-end. This unblocks every
authenticated feature in the Spendly roadmap (profile, expenses).

## Depends on

- Step 1 — Database Setup. The `users` table with `id`, `email`, and
  `password_hash` (a werkzeug hash) must already exist in
  `database/db.py`. Login looks users up by lowercased email and
  verifies the password with `werkzeug.security.check_password_hash`.
- Step 2 — Registration. `/register` already calls `create_user` from
  `database/db.py` and sets `session["user_id"]` on success. Login
  uses the same session key, the same email shape, and shares the
  data-layer pattern established there.

## Routes

- `GET  /login`  — render the login form — public
- `POST /login`  — validate, look up the user, verify the password,
  set `session["user_id"]`, redirect to `/profile` — public
- `GET  /logout` — clear `session["user_id"]` and redirect to
  `/login` — logged-in (silently no-op if no user is signed in,
  rather than 405 or 500)

`GET /login` already exists in `app.py` (currently a no-template-
context render). The new work is the `POST` handler plus the
`/logout` route, which is currently a placeholder string.

## Database changes

No database changes. The `users` table from Step 1 already has every
column this feature needs. Login reads `id`, `email`, and
`password_hash`; it does not write anything. The `email` column's
`UNIQUE` constraint is leveraged implicitly — there is at most one
row per email, so the lookup is unambiguous.

## Templates

- **Modify:** `templates/login.html`
  - Repoint the form `action` from the hard-coded `/login` to
    `url_for("login")` for consistency with `register.html`.
  - On a re-render after a validation or credential failure,
    preserve the submitted `email` in the input (never the
    password) so the user does not have to retype it. The
    `name` field is not present on this form.
  - Keep the existing `auth-error` block — the POST handler will
    populate `error` on failure.
  - No other markup changes; the existing CSS (`.auth-error`,
    `.form-input`, `.btn-submit`) already covers the error and
    field states.
- **Modify:** `templates/base.html`
  - The navbar currently always shows "Sign in" and
    "Get started" links. Swap this for a small Jinja `{% if %}`
    block: when `session.user_id` is set, show the signed-in
    user's name (looked up from the DB once per request — see
    Rules) and a "Sign out" link pointing at
    `url_for("logout")`; otherwise keep the current public
    links. This is the only base.html change — no new CSS is
    required for the navbar swap; the existing `.nav-links` and
    `.nav-cta` styles cover both states.

## Files to change

- `app.py`
  - Import `request`, `redirect`, `url_for`, `session`,
    `check_password_hash` (from `werkzeug.security`).
  - Add a small `find_user_by_email(email) -> sqlite3.Row | None`
    helper in `database/db.py` (see Files to create) and import
    it here.
  - Refactor the existing `login()` view to dispatch on method:
    `GET` renders the form, `POST` performs the validation +
    lookup + verify + login + redirect flow.
  - Replace the placeholder `logout()` view with one that pops
    `session["user_id"]` (use `.pop(..., None)` so it is safe
    even when no user is signed in) and redirects to
    `url_for("login")`.
  - Make the existing `app.secret_key` setup a no-op only if
    `SECRET_KEY` is already set elsewhere — it is already
    handled in Step 2; no change needed.
- `database/db.py`
  - Add `find_user_by_email(email: str) -> sqlite3.Row | None`
    that returns the matching row (with `id`, `name`, `email`,
    `password_hash`) or `None` if no user has that email.
    Lowercases the email before the query so it matches the
    casing used by `create_user` and `/register`'s POST
    handler. Uses a parameterised query.
- `templates/login.html` — see Templates → Modify above.
- `templates/base.html` — see Templates → Modify above.
- `tests/test_03_login_logout.py` *(new — see Files to create)*

## Files to create

- `tests/test_03_login_logout.py` — covers happy path (correct
  email + password sets `session["user_id"]`, redirects to
  `/profile`), wrong password (no session set, friendly
  "Invalid email or password" error, re-render with email
  preserved), unknown email (no session set, same friendly
  error, no information leak about whether the email exists),
  missing fields (no session set, validation error), and
  logout (clears `session["user_id"]`, redirects to `/login`,
  works whether or not the user was signed in). Uses
  `pytest-flask`'s `client` fixture and a temporary SQLite file
  isolated per test.
- No new files in `database/`, `static/`, or `templates/`.

## New dependencies

No new dependencies. `werkzeug.security` is already in
`requirements.txt` (used by Step 1 / Step 2). The new tests use
`pytest` and `pytest-flask`, both already installed.

## Rules for implementation

- No SQLAlchemy or ORMs — keep using stdlib `sqlite3` from
  `database/db.py`.
- All SQL must be parameterised (`?` placeholders). Never use
  f-strings, `.format()`, or `%` interpolation in SQL.
- Passwords are verified with
  `werkzeug.security.check_password_hash(stored_hash, submitted)`
  inside the route (or, preferably, inside
  `find_user_by_email`'s sibling helper — see below). The
  plaintext password must never be logged, flashed, written to
  the database, or returned in a response.
- Use the same "lowercased email" convention as `/register` so
  `demo@spendly.com`, `Demo@Spendly.com`, and
  `DEMO@SPENDLY.COM` all match the same row. `find_user_by_email`
  lowercases the input; the route also lowercases after strip
  for belt-and-braces parity with `create_user`'s callers.
- Validation rules (enforced in the route before any DB call):
  - `email`: stripped, lowercased, must match the same basic
    regex used in Step 2
    (`^[^@\s]+@[^@\s]+\.[^@\s]+$`), max 254 characters.
  - `password`: non-empty, max 128 characters. (No minimum
    length on the login form — the form is for users who
    already have an account; the 8-char minimum is a
    registration rule, not a login rule.)
- On credential failure (no row, or wrong password), respond
  with **the same generic error message**: "Invalid email or
  password." Never distinguish "email not found" from "wrong
  password" in the response — that is the standard anti-enumeration
  pattern, and it matches the placeholder's behaviour
  expectations for this step.
- On success: write `session["user_id"] = user_id`, then
  `redirect(url_for("profile"))`. `/profile` is currently a
  placeholder string — that is fine for this step; it becomes
  a real page in Step 4. The redirect target proves the
  session is set.
- `find_user_by_email` lives in `database/db.py` next to
  `get_db` / `init_db` / `seed_db` / `create_user` so all
  data-layer code stays in one place. Returns `None` (not
  raises) when no row matches.
- `logout()` uses `session.pop("user_id", None)` and
  `redirect(url_for("login"))`. It must be safe to call when
  no user is signed in — no `KeyError`, no 500.
- `base.html` navbar: keep the existing markup. Swap the
  two `<a>` tags inside `.nav-links` for a single Jinja
  conditional. When `session.user_id` is set, look up the
  user's name **once per request** by calling
  `find_user_by_email` for the current user — or, simpler,
  look the user up by `id` with a new `find_user_by_id`
  helper. To avoid a DB hit on every public page render, the
  `{% if %}` block can be guarded by `session.get("user_id")`
  and a small `g.user` populated by a
  `@app.before_request` hook — that is the recommended
  pattern. Do not run a DB query in the template itself.
- All new Flask routes use `url_for(...)` for redirects and
  link generation. No hard-coded paths.
- All new templates extend `base.html`.
- Use CSS variables (`--ink`, `--accent`, `--danger`, etc.)
  — never hardcode hex values in new CSS. No new CSS is
  expected for this step; the existing styles already cover
  the navbar links in both states.
- `SECRET_KEY` is read from
  `os.environ.get("SPENDLY_SECRET_KEY", ...)` with a
  clearly-marked development-only fallback so the app still
  starts in dev. Do not ship a real production key in source.
  (This is already in place from Step 2 — no change.)

## Definition of done

- [ ] `GET /login` still renders the form with no behavioural
      change for a fresh visitor.
- [ ] `POST /login` with the seeded demo credentials
      (`demo@spendly.com` / `demo123`) sets
      `session["user_id"]` and redirects (HTTP 302) to
      `/profile`.
- [ ] `POST /login` with the correct email but a wrong
      password returns HTTP 200, re-renders the form with the
      generic "Invalid email or password" error, and does
      **not** set `session["user_id"]`.
- [ ] `POST /login` with an email that has no row in `users`
      returns HTTP 200, re-renders the form with the same
      generic error (no information leak about whether the
      email exists), and does **not** set
      `session["user_id"]`.
- [ ] `POST /login` with an empty `email`, empty `password`,
      or a malformed `email` returns HTTP 200, re-renders the
      form with a specific validation error, and does **not**
      set `session["user_id"]`.
- [ ] Email matching is case-insensitive: `Demo@Spendly.com`
      and `DEMO@SPENDLY.COM` both log in the same user as
      `demo@spendly.com`.
- [ ] On a re-render after a failure, the `email` field is
      pre-filled with the submitted value; the `password`
      field is always empty.
- [ ] The plaintext password never appears in the response
      body, in the database, in any log line, or in the
      rendered HTML.
- [ ] `GET /logout` clears `session["user_id"]`, redirects
      (HTTP 302) to `/login`, and does not 500 when called
      while no user is signed in.
- [ ] When a user is signed in, the navbar on every page
      shows the user's name and a "Sign out" link instead
      of "Sign in" / "Get started". When no user is signed
      in, the navbar still shows "Sign in" / "Get started".
- [ ] The navbar's signed-in branch does not run a DB query
      on pages where no user is signed in (use
      `@app.before_request` + `g.user`, or guard the lookup
      with `session.get("user_id")`).
- [ ] All SQL queries in the new code use `?` placeholders
      — no f-strings, `.format()`, or `%` interpolation in
      SQL.
- [ ] The new tests in `tests/test_03_login_logout.py` pass
      under
      `python -m pytest tests/test_03_login_logout.py -v`.
- [ ] The dev server (`python app.py`) starts cleanly with no
      new startup errors, `/login` is reachable at
      http://localhost:5001/login, and logging in with the
      demo credentials lands the user on `/profile`.
