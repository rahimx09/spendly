# Spec: Date Filter For Profile Page

## Overview
This feature adds a date-range filter to the profile page so a signed-in user can
narrow the transaction history, summary stats, and category breakdown to a chosen
window (e.g. this month, last 7 days, or a custom from/to range). It builds on the
real DB-backed `/profile` view from Step 5 by parameterising the existing queries
with optional date bounds, so every figure on the page (total spent, transaction
count, top category, recent transactions, category breakdown) reflects only the
filtered period. The goal is to make the dashboard genuinely useful for reviewing
spend over time without introducing a new ORM or changing the schema.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` TEXT column must exist)
- Step 2: Registration (user accounts must be creatable)
- Step 3: Login + Logout (session must be set; `/profile` must be protected)
- Step 4: Profile page (DB-backed view exists)
- Step 5: Profile routers (`get_user_total_spent`, `get_user_expense_count`,
  `get_user_top_category`, `get_recent_expenses`, `get_category_breakdown` exist)

## Routes
No new routes. The filter is applied via query-string parameters on the existing
`GET /profile` route (e.g. `?from=2026-07-01&to=2026-07-31&preset=this_month`), so
the URL is shareable and the user can clear the filter by visiting `/profile` with
no query string.

## Database changes
No database changes. The existing `expenses.date` TEXT column (ISO `YYYY-MM-DD`)
is sufficient for range filtering with `>=` / `<=` comparisons.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter bar above the transaction history section with:
    - A set of preset buttons/links: "All", "This month", "Last 7 days", "Last 30 days"
    - Optional `from` and `to` date `<input type="date">` fields with a "Apply" button
  - Preserve the existing four sections; only their data changes based on the filter
  - Pass the currently active filter back to the template so the UI reflects state
    (which preset is active, what from/to values are set)

## Files to change
- `app.py`
  - Extend the `/profile` view to read `request.args` for `from`, `to`, and `preset`;
    resolve them into `(from_date, to_date)` bounds (or `None` for unbounded).
  - Pass the date bounds into every data-access helper so totals, counts, top
    category, transactions, and category breakdown all respect the filter.
  - Pass the active filter values to `profile.html` for UI state.
- `database/db.py`
  - Update `get_user_total_spent`, `get_user_expense_count`, `get_user_top_category`,
    `get_recent_expenses`, and `get_category_breakdown` to accept optional
    `from_date` / `to_date` parameters (default `None`) that append
    `AND date >= ? AND date <= ?` when provided, using parameterised queries.
- `templates/profile.html`
  - Add the filter bar UI (see Templates section).
- `static/css/style.css`
  - Add styles for the filter bar, preset buttons, and date inputs using existing
    CSS variables only.

## Files to create
None.

## New dependencies
None.

## Rules for implementation
- No SQLAlchemy or ORMs — raw sqlite3 via `get_db()` only.
- Parameterised queries only — date bounds must be passed as `?` placeholders,
  never string-formatted into SQL.
- When only one bound is provided, still filter on it (e.g. `from` only →
  `date >= ?`; `to` only → `date <= ?`).
- Date comparison is on the ISO `YYYY-MM-DD` string, which sorts lexicographically,
  so plain `>=` / `<=` work without `date()` casts.
- Validate `from`/`to` with `datetime.date.fromisoformat`; on a bad value fall back
  to no bound (ignore the invalid param) rather than raising a 500.
- `to` is inclusive: cap the upper bound at end-of-day by comparing against the
  raw `YYYY-MM-DD` value with `<=`.
- Passwords stay hashed with werkzeug (no auth changes in this step).
- Use CSS variables — never hardcode hex values; no inline styles.
- All templates extend `base.html`.
- Preset resolution (this month / last 7 / last 30) must be computed in Python from
  `datetime.date.today()` and turned into `from`/`to` bounds — do not rely on SQL
  date math for presets.
- Empty filtered result must render gracefully: totals show `₹0.00`, count `0`,
  top category `—`, empty transaction table, empty category breakdown.

## Definition of done
- [ ] Visiting `/profile` with no query string shows all transactions (unchanged behaviour).
- [ ] `GET /profile?preset=this_month` shows only expenses whose `date` is in the current month.
- [ ] `GET /profile?from=YYYY-MM-DD&to=YYYY-MM-DD` shows only expenses within that inclusive range.
- [ ] Summary stats (total spent, transaction count, top category) reflect the filtered range.
- [ ] Category breakdown reflects the filtered range.
- [ ] A bad `from`/`to` value (e.g. `?from=not-a-date`) does not raise a 500 — page still renders.
- [ ] The active filter (preset or from/to) is reflected in the UI so the user sees what is applied.
- [ ] Clearing the filter (visiting `/profile`) returns to the full unfiltered view.
- [ ] No hex colour values are added to `profile.html` or `style.css` — only CSS variables.
