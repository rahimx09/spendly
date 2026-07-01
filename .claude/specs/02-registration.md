# Spec: Registration

## Overview

Turn the existing `/register` GET-render stub into a working registration
flow. A new visitor can submit the form on `templates/register.html`,
the server validates the input, hashes the password with `werkzeug`,
inserts a row into the `users` table, signs the user in, and redirects
them to the (currently placeholder) profile page. Failed submissions
re-render the form with a human-readable error. This unlocks every
authenticated feature in the Spendly roadmap (login, expenses, profile).

## Depends on

- Step 1 — Database Setup (the `users` table with `id`, `name`, `email`,
  `password_hash`, and the `UNIQUE` constraint on `email` already exist
  in `database/db.py`).

## Routes

- `GET  /register`  — render the registration form — public
- `POST /register`  — validate, create user, log them in, redirect to
  `/profile` — public

`GET /register` already exists in `app.py` and will be kept; the
behaviour stays the same. The new work is the `POST` handler and the
plumbing it needs.

## Database changes

No database changes. The `users` table from Step 1 already has every
column this feature needs. The `email` column's `UNIQUE` constraint is
relied on to detect duplicates — duplicate registrations surface as a
friendly validation error rather than a 500.

## Templates

- **Modify:** `templates/register.html`
  - Repoint the form `action` from the hard-coded `/register` to
    `url_for("register")` for consistency with the rest of the app.
  - On a re-render after a validation failure, preserve the submitted
    `name` and `email` in the inputs (never the password) so the user
    does not have to retype them.
  - Keep the existing `auth-error` block — the POST handler will
    populate `error` when validation fails.
  - No other markup changes; the existing CSS (`.auth-error`,
    `.form-input`, `.btn-submit`) already covers the error and field
    states.

## Files to change

- `app.py`
  - Import `request`, `redirect`, `url_for`, `session`, `flash` (or
    pass `error` directly to the template — see Rules).
  - Add a `SECRET_KEY` to the Flask app (required for `session` to
    sign cookies). Read from env var `SPENDLY_SECRET_KEY` with a
    development fallback so the app still starts without config.
  - Refactor the existing `register()` view to dispatch on method:
    `GET` renders the form, `POST` performs the validation + insert +
    login + redirect flow.
  - Add a small `create_user(name, email, password)` helper in
    `database/db.py` so the route stays a thin handler and the data
    layer owns the INSERT.
- `database/db.py`
  - Add `create_user(name, email, password) -> int` returning the new
    user's `id`. Hashes the password with `werkzeug.security`, runs
    the INSERT with parameterised SQL, raises `sqlite3.IntegrityError`
    on the unique-email conflict so the route can catch it.
- `templates/register.html`
  - See Templates → Modify above.
- `tests/test_02_registration.py` *(new — see Files to create)*

## Files to create

- `tests/__init__.py` — empty package marker so pytest discovers the
  new test file.
- `tests/test_02_registration.py` — covers happy path (user created,
  logged in, redirected), duplicate email (no new row, friendly
  error, re-render with the email preserved), short password (no row,
  validation error), missing fields (no row, validation error),
  password is stored as a hash (never plaintext, never equal to the
  submitted value), session has `user_id` set after success. Uses
  `pytest-flask`'s `client` fixture and a temporary SQLite file
  isolated per test (so seeded data is not corrupted).
- `.env.example` *(optional, only if `SECRET_KEY` env var is adopted
  in a later step — not strictly required for this spec)*. Skipped
  for this step; the in-code dev fallback is enough.

## New dependencies

No new dependencies. `werkzeug.security` is already in
`requirements.txt`. The new tests use `pytest` and `pytest-flask`,
both already installed.

## Rules for implementation

- No SQLAlchemy or ORMs — keep using stdlib `sqlite3` from
  `database/db.py`.
- All SQL must be parameterised (`?` placeholders). Never use f-strings
  or `.format()` to build SQL.
- Passwords are hashed with `werkzeug.security.generate_password_hash`
  inside `create_user`. The plaintext password must never be logged,
  flashed, written to the database, or returned in a response.
- The `users.email` column is `UNIQUE`. Catch `sqlite3.IntegrityError`
  in the route and render a friendly "Email already registered"
  error — do not let it 500.
- Validation rules (enforced in the route before any DB call):
  - `name`: stripped, non-empty, max 100 characters.
  - `email`: stripped, lowercased, must match a basic email regex
    (`^[^@\s]+@[^@\s]+\.[^@\s]+$` is enough; the goal is to catch
    obvious garbage, not RFC-perfect validation), max 254 characters.
  - `password`: minimum 8 characters (matches the placeholder hint
    on the form), max 128 characters. No complexity rules yet — out
    of scope for this step.
- On success: write `session["user_id"] = user_id`, then
  `redirect(url_for("profile"))`. `/profile` is currently a placeholder
  string — that is fine for this step; it becomes a real page in
  Step 4. The redirect target proves the session is set.
- On validation failure: re-render `register.html` with `error` set
  and the submitted `name`/`email` filled back in. Do not use Flask's
  `flash` for this — the form has a dedicated `.auth-error` block, so
  a direct template variable is the simplest, most consistent fit.
- All new Flask routes use `url_for(...)` for redirects and link
  generation. No hard-coded paths.
- All new templates extend `base.html`.
- Use CSS variables (`--ink`, `--accent`, `--danger`, etc.) — never
  hardcode hex values in new CSS.
- `SECRET_KEY` is read from `os.environ.get("SPENDLY_SECRET_KEY", ...)`
  with a clearly-marked development-only fallback so the app still
  starts in dev. Do not ship a real production key in source.
- `create_user` lives in `database/db.py` next to `get_db`/`init_db`/
  `seed_db` so all data-layer code stays in one place.

## Definition of done

- [ ] `GET /register` still renders the form with no behavioural
      change.
- [ ] `POST /register` with valid `name`, `email`, and a password of
      8+ characters inserts a new row into `users` and redirects
      (HTTP 302) to `/profile`.
- [ ] After a successful registration, `session["user_id"]` is set
      to the new user's id and the password stored in the DB is a
      werkzeug hash — not the submitted plaintext, and not equal to
      it.
- [ ] `POST /register` with an email that already exists in `users`
      returns HTTP 200, re-renders the form with the friendly
      "Email already registered" error, and does **not** insert a
      new row.
- [ ] `POST /register` with an empty `name`, empty `email`, malformed
      `email`, or a password shorter than 8 characters returns HTTP
      200, re-renders the form with a specific error message, and
      does **not** insert a new row.
- [ ] On a re-render after a failure, the `name` and `email` fields
      are pre-filled with the submitted values; the `password` field
      is always empty.
- [ ] All SQL queries in the new code use `?` placeholders — no
      f-strings, `.format()`, or `%` interpolation in SQL.
- [ ] The plaintext password never appears in the response body, in
      the database, in any log line, or in the rendered HTML.
- [ ] The new tests in `tests/test_02_registration.py` pass under
      `python -m pytest tests/test_02_registration.py -v`.
- [ ] The dev server (`python app.py`) starts cleanly with no new
      startup errors and the `/register` form is reachable at
      http://localhost:5001/register.
