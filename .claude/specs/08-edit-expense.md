# Spec: Edit Expense

## Overview
This feature turns the placeholder `/expenses/<id>/edit` route into a working
edit screen. A signed-in user opens an existing expense (by clicking "Edit"
from the profile transaction table), updates any of its fields (amount,
category, date, description), and the change is written back to the
already-existing `expenses` table. The route enforces ownership — users can
only edit their own expenses; any other row is treated as "not found" so the
endpoint never reveals whether someone else's id exists. The edit form
mirrors the add-expense screen so the input/validation/error UX is
consistent, and a successful save lands the user back on `/profile` with
the updated row visible.

## Depends on
- Step 1 — Database setup (the `expenses` table already exists with
  `id`, `user_id`, `amount`, `category`, `date`, `description`).
- Step 3 — Login and logout (session wiring that `g.user` relies on).
- Step 4 — Profile page (the transaction table that the "Edit" link lives in).
- Step 7 — Add expense (the validation rules, `CATEGORIES` import, and form
  styling the edit screen reuses).

## Routes
- `GET /expenses/<id>/edit` — render the edit-expense form pre-filled with
  the row's current values — logged-in
- `POST /expenses/<id>/edit` — validate + update the row, then redirect to
  `/profile` on success or re-render the form with errors — logged-in

If no new routes: state "No new routes".

## Database changes
No database changes. The `expenses` table already exists in
`database/db.py`'s `SCHEMA` with every column the form edits
(`amount`, `category`, `date`, `description`). This step adds an
`update_expense(user_id, expense_id, amount, category, date, description)`
write helper that scopes the `UPDATE` by `user_id` AND `id` so a missing
or wrong-owner row simply affects zero rows (the route translates that to
a 404-style redirect, not an error).

## Templates
- **Create:** `templates/expenses/edit.html` — the edit-expense form,
  extending `base.html`. Mirrors `templates/expenses/add.html` field-for-field
  (amount, category `<select>` built from `CATEGORIES`, date, description) but
  pre-fills each input from the loaded `expense` dict on GET and re-fills
  from the user's submission on POST failure. Submit button label is
  "Save changes".
- **Modify:** `templates/profile.html` — in the recent-transactions table
  row, add an "Edit" link/button pointing at
  `url_for('edit_expense', id=expense.id)` so users can reach the edit screen
  from the row they want to change. (Step 9 will add a sibling Delete link.)

## Files to change
- `app.py` — replace the `edit_expense(id)` placeholder (currently returns
  a string) with the GET/POST handler; import the new `update_expense` and
  `get_expense_by_id` db helpers.
- `database/db.py` — add two helpers:
  - `get_expense_by_id(user_id, expense_id)` — fetch one row scoped to the
    signed-in user; returns `None` for both "no such id" and "not your
    expense" so the route can treat them identically.
  - `update_expense(user_id, expense_id, amount, category, date,
    description)` — parameterised `UPDATE ... WHERE id = ? AND user_id = ?`
    returning the affected row count.
- `templates/profile.html` — add the per-row "Edit" link to the
  transactions table.

## Files to create
- `templates/expenses/edit.html`
- `tests/test_08-edit-expense.py` — per-project convention, one spec-driven
  test file per step.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — plain `sqlite3` only.
- Parameterised queries only — never interpolate user input into SQL. The
  `UPDATE` binds `user_id` and `expense_id` alongside the new values, so a
  hand-crafted request targeting someone else's row still cannot mutate it.
- Passwords hashed with werkzeug (n/a for this step, but keep the existing
  auth path untouched).
- Use CSS variables — never hardcode hex values (reuse the `--*` tokens
  already defined in `static/css/style.css`).
- All templates extend `base.html`.
- Server-side validation must be authoritative; the client form is a
  convenience only.
- **Ownership model.** A single source of truth:
  `get_expense_by_id(user_id, expense_id)` and `update_expense(user_id,
  expense_id, ...)` both scope by `user_id` AND `id`. The route never reads
  an expense without passing `g.user["id"]`. A foreign id (or an id that
  does not exist) is treated as a 404-style redirect to `/profile` with no
  error message — never leak existence.
- **Idempotency.** A POST that re-submits the same values still issues
  the `UPDATE` (returning 1 row) and redirects to `/profile`. There is no
  "no changes" short-circuit in the route — keeping the path linear makes
  the redirect-vs-render decision simple.
- **Validation rules** (mirror Step 7's `add_expense`):
  - `amount` — parse as `float`; reject empty, non-numeric, `<= 0`, and
    `> AMOUNT_MAX` (1_000_000_000). Two-decimal money value.
  - `category` — must be exactly one of the `CATEGORIES` tuple values;
    reject anything else.
  - `date` — must parse as `YYYY-MM-DD` via `datetime.date.fromisoformat`;
    reject empty or malformed. (No future-date restriction — back-dating
    past expenses is legitimate.)
  - `description` — optional; if present, `strip()` and cap length
    (`DESCRIPTION_MAX` = 200); store `None` (not `""`) when blank.
- On POST failure (validation error OR row not found), re-render
  `edit.html` with the previously entered fields echoed back, the loaded
  row's values as a fallback, and a single human-readable `error` message.
  For row-not-found, the re-render still uses the submitted values (so the
  user can copy them down) but the error reads "Expense not found."
- On success, `redirect(url_for("profile"))` — do NOT keep the user on
  the edit screen.
- GET on a foreign or missing id also redirects to `/profile` (no
  rendering, no error toast). The redirect target is always
  `url_for("profile")` — never echo the requested id back in the URL.
- Update must scope by `user_id` from `g.user["id"]`; never trust a
  client-supplied owner.

## Definition of done
- [ ] `database/db.py` has `get_expense_by_id(user_id, expense_id)` that
      returns a `sqlite3.Row` (or `dict`) for the row whose `id` matches AND
      whose `user_id` matches; returns `None` otherwise.
- [ ] `database/db.py` has `update_expense(user_id, expense_id, amount,
      category, date, description)` that runs a parameterised
      `UPDATE expenses SET amount=?, category=?, date=?, description=?
      WHERE id = ? AND user_id = ?` and returns the affected row count.
- [ ] `GET /expenses/<id>/edit` while signed in, for a row owned by the
      user, returns the form (HTTP 200) pre-filled with that row's amount,
      category, date, and description.
- [ ] `GET /expenses/<id>/edit` while signed out redirects to `/login`.
- [ ] `GET /expenses/<id>/edit` for an id owned by a different user
      redirects to `/profile` (HTTP 302 → 200) without rendering the form
      and without leaking that the id exists.
- [ ] `GET /expenses/<id>/edit` for a non-existent id redirects to
      `/profile` without an error message.
- [ ] `POST /expenses/<id>/edit` with valid data updates the row in place
      and redirects to `/profile` (HTTP 302 → 200). The change is visible
      in the transaction table on the next `/profile` render.
- [ ] `POST` with a non-positive / non-numeric amount does NOT update and
      re-renders the form with an error; the previously entered fields are
      echoed.
- [ ] `POST` with a category not in `CATEGORIES` (incl. a hand-crafted
      request) does NOT update and re-renders with an error.
- [ ] `POST` with an empty or malformed date does NOT update and re-renders
      with an error.
- [ ] `POST /expenses/<id>/edit` for an id owned by a different user does
      NOT update that row (zero rows affected) and redirects to `/profile`.
- [ ] An optional description over the length cap is rejected or truncated
      per the chosen rule; a blank description stores `NULL`, not an empty
      string.
- [ ] The "Edit" link appears on each row of the profile transaction table
      and points at `url_for('edit_expense', id=...)`.
- [ ] `tests/test_08-edit-expense.py` passes (`pytest -q`).
