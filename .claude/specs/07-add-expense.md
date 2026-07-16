# Spec: Add Expense

## Overview
This feature turns the placeholder `/expenses/add` route into a working
expense-entry screen. A signed-in user fills out a form (amount, category,
date, optional description); the values are validated server-side and the
expense is inserted into the already-existing `expenses` table. It is the
first write operation against `expenses` (Steps 1–6 were all read/reporting),
and it feeds every existing view — the profile summary, transaction table, and
category breakdown all update live once an expense is saved.

## Depends on
- Step 1 — Database setup (the `expenses` table already exists with
  `user_id`, `amount`, `category`, `date`, `description`, `created_at`).
- Step 4 — Profile page (the landing/redirect flow that routes a signed-in
  user into authenticated views).
- Step 3 — Login and logout (session wiring that `g.user` relies on).

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in
- `POST /expenses/add` — validate + insert a new expense, then redirect to
  `/profile` on success or re-render the form with errors — logged-in

If no new routes: state "No new routes".

## Database changes
No database changes. The `expenses` table already exists in
`database/db.py`'s `SCHEMA` with every column the form needs
(`user_id`, `amount`, `category`, `date`, `description`). This step only adds
an `add_expense(...)` write helper and uses `INSERT ... VALUES (?, ?, ?, ?, ?)`
with parameterised bindings.

## Templates
- **Create:** `templates/expenses/add.html` — the add-expense form, extending
  `base.html`. Fields: amount (number, step="0.01", min="0.01"), category
  (`<select>` built from the `CATEGORIES` tuple — Food, Transport, Bills,
  Health, Entertainment, Shopping, Other), date (`<input type="date">`,
  defaulting to today), description (optional text, max ~200 chars). Reuses
  existing form/error styling from `register.html`.
- **Modify:** `templates/base.html` — in the signed-in `nav-links` block,
  add an "Add expense" link/button pointing at `url_for('add_expense')` so
  users can reach the form from anywhere (use the `request.endpoint ==
  'add_expense'` pattern already used for the Analytics active state).

## Files to change
- `app.py` — replace the `add_expense()` placeholder (currently returns a
  string) with the GET/POST handler; import the new `add_expense` db helper.
- `database/db.py` — add an `add_expense(user_id, amount, category, date,
  description)` function.
- `templates/base.html` — add the "Add expense" nav link for signed-in users.

## Files to create
- `templates/expenses/add.html`
- `tests/test_07-add-expense.py` — per-project convention, one spec-driven
  test file per step.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — plain `sqlite3` only.
- Parameterised queries only — never interpolate user input into SQL.
- Passwords hashed with werkzeug (n/a for this step's writes, but keep the
  existing auth path untouched).
- Use CSS variables — never hardcode hex values (reuse the `--*` tokens
  already defined in `static/css/style.css`).
- All templates extend `base.html`.
- Server-side validation must be authoritative; the client form is a
  convenience only.
- Validation rules (mirror the defensive style of `register()`):
  - `amount` — parse as `float`; reject empty, non-numeric, `<= 0`, and an
    absurd upper bound (e.g. `> 1_000_000_000`). Two-decimal money value.
  - `category` — must be exactly one of the `CATEGORIES` tuple values;
    reject anything else (defends against tampered `<select>` submissions).
  - `date` — must parse as `YYYY-MM-DD` via `datetime.date.fromisoformat`;
    reject empty or malformed. (No future-date restriction — back-dating past
    expenses is legitimate.)
  - `description` — optional; if present, `strip()` and cap length
    (e.g. `200`); store `None` (not `""`) when omitted so the profile table's
    empty cell renders cleanly.
- On POST failure, re-render `add.html` with the previously entered fields
  echoed back (except no password-style concern here) and a single
  human-readable `error` message, exactly like `register()`.
- On success, `redirect(url_for("profile"))` — do NOT keep the user on the
  add screen.
- Insert must set `user_id` from `g.user["id"]`; never trust a client-supplied
  owner.

## Definition of done
- [ ] `database/db.py` has `add_expense(user_id, amount, category, date,
      description)` using a parameterised `INSERT`; calling it stores all five
      values and the new row is readable back from the DB.
- [ ] `GET /expenses/add` while signed in returns the form (HTTP 200,
      contains the amount/category/date/description inputs).
- [ ] `GET /expenses/add` while signed out redirects to `/login`.
- [ ] `POST /expenses/add` with valid data inserts one row for the signed-in
      user and redirects to `/profile` (HTTP 302 → 200 on the target).
- [ ] The new expense immediately appears in `/profile` (transaction table,
      total-spent summary, and category breakdown all reflect it).
- [ ] `POST` with a non-positive / non-numeric amount does NOT insert and
      re-renders the form with an error; previously entered fields are echoed.
- [ ] `POST` with a category not in `CATEGORIES` (incl. a hand-crafted
      request) does NOT insert and re-renders with an error.
- [ ] `POST` with an empty or malformed date does NOT insert and re-renders
      with an error.
- [ ] Optional description over the length cap is rejected or truncated per the
      chosen rule; a blank description stores `NULL`, not an empty string.
- [ ] The "Add expense" link appears in the navbar for signed-in users and is
      marked active on `/expenses/add`.
- [ ] `tests/test_07-add-expense.py` passes (`pytest -q`).
