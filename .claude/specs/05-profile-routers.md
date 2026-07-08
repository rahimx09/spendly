# Spec: Profile Page Backend Routers

## Overview
This step replaces the hardcoded data in `/profile` (shipped in Step 4) with live database queries so the user info card, summary stats, transaction history, and category breakdown all reflect the signed-in user's real data. The route already authenticates with `g.user`; this step adds the read-side data-layer functions (`get_user_total_spent`, `get_user_expense_count`, `get_user_top_category`, `get_recent_expenses`, `get_category_breakdown`) and rewrites the `/profile` view to call them. No new routes — the existing `/profile` route is the only thing changing.

## Depends on
- Step 1: Database setup — `users` and `expenses` tables exist
- Step 2: Registration — users are creatable
- Step 3: Login + Logout — `session["user_id"]` is set and `g.user` is populated
- Step 4: Profile page — `profile.html` template and `/profile` view exist with hardcoded context

## Routes
No new routes. The existing `/profile` view (currently in `app.py` lines 168-213) is rewritten to:
- Redirect unauthenticated users to `/login` (unchanged)
- Replace all hardcoded dicts/lists with calls to new db-layer functions
- Pass the resulting context to `profile.html` (template variable names unchanged)

## Database changes
No database changes. The existing `users` and `expenses` tables are sufficient. All new queries are `SELECT` only.

## Templates
- Modify: `templates/profile.html` — no structural change required. The variable names already match (`user.name`, `user.email`, `user.member_since`, `user.initials`, `summary[*]`, `transactions[*]`, `categories[*]`). The `₹{{ "%.2f"|format(t.amount) }}` line works as-is. The `cat-bar` inline `style="width: {{ c.percent }}%"` is the template's existing convention — keep it (it's a per-row width, not a colour).

## Files to change
- `app.py` — rewrite the `/profile` view to query the database instead of using hardcoded data. The `user` dict, `summary` list, `transactions` list, and `categories` list become derived from real data.
- `database/db.py` — add five new read-side helper functions (described below). All take a `user_id: int` and return either a primitive (int/float/str) or a list of dicts ready for the template.

## Files to create
None.

## New data-layer functions (added to `database/db.py`)
All functions take `user_id: int` as the only meaningful argument. All queries are parameterised. Each opens and closes its own connection (same pattern as the existing `find_user_by_id`).

1. `get_user_total_spent(user_id: int) -> float` — `SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?`. Returns `0.0` when the user has no expenses.

2. `get_user_expense_count(user_id: int) -> int` — `SELECT COUNT(*) FROM expenses WHERE user_id = ?`. Returns `0` when empty.

3. `get_user_top_category(user_id: int) -> str | None` — `SELECT category FROM expenses WHERE user_id = ? GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1`. Returns `None` when the user has no expenses. The profile view should display the string `"—"` (em dash) when the result is `None` so the template doesn't render an empty badge.

4. `get_recent_expenses(user_id: int, limit: int = 8) -> list[dict]` — `SELECT date, description, category, amount FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?`. Returns a list of dicts with keys `date`, `description`, `category`, `amount` — the exact shape the template iterates. Returns `[]` when empty (the template's `{% for %}` already handles empty).

5. `get_category_breakdown(user_id: int) -> list[dict]` — `SELECT category, SUM(amount) AS amount FROM expenses WHERE user_id = ? GROUP BY category ORDER BY amount DESC`. Then in Python, compute each row's `percent` against the total (rounded to the nearest integer with `round`); include the `name` alias for `category` and a `percent` field. Returns `[]` when empty.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never string-format SQL
- All new db functions follow the same open/close pattern as `find_user_by_id`
- All new functions live in `database/db.py` — keep `app.py` thin (it only renders)
- Keep the `user` dict shape stable: `{name, email, member_since, initials}` so the template is untouched
- `member_since` should be formatted as `"March 2026"` (e.g. `"%B %Y"`) from `g.user["created_at"]` — do not display the raw ISO timestamp
- `initials` should be the first two letters of the name, uppercased, falling back to `"DU"` when the name is empty (mirrors the Step 4 fallback)
- Summary stat values are strings (the template renders `{{ s.value }}` directly) — pre-format `₹4,688.50` style strings in `app.py` so the template stays free of `intcomma` filters
- Transaction amount formatting: `app.py` passes raw `float`; the template's existing `{{ "%.2f"|format(t.amount) }}` handles two-decimal display
- Use CSS variables — never hardcode hex values
- All templates extend `base.html` (no change to this)
- Do NOT add any inline `style=` to the template; the existing `style="width: {{ c.percent }}%"` is the only allowed inline style and is already present
- The route must remain logged-in only; preserve the existing `if g.user is None: return redirect(url_for("login"))` guard

## Definition of done
- [ ] Visiting `/profile` while logged in shows the signed-in user's actual name, email, and "Member since" month/year (parsed from `created_at`)
- [ ] Avatar initials reflect the first two letters of the actual name
- [ ] The "Total spent" stat matches `SUM(amount)` over the user's expenses, formatted as `₹X,XXX.XX` (or `₹0.00` when no expenses exist)
- [ ] The "Transactions" stat matches `COUNT(*)` over the user's expenses
- [ ] The "Top category" stat shows the category with the largest `SUM(amount)`, or `—` when the user has no expenses
- [ ] The transaction history table shows the user's most recent expenses (date desc, capped at 8), in the real shape `{date, description, category, amount}`
- [ ] The category breakdown rows reflect real per-category totals, with `percent` = `round(category_sum / total * 100)` and rows sorted by amount descending
- [ ] If a user has zero expenses, the page still renders (no crashes; stats show `₹0.00`, `0`, `—`, empty table, empty breakdown)
- [ ] All new functions in `database/db.py` use parameterised queries
- [ ] `app.py` only renders — no SQL outside `database/db.py`
- [ ] Logging in as `demo@spendly.com` / `demo123` (the Step 1 seed user) reproduces the original 8 transactions in the same order
- [ ] A freshly registered user (zero expenses) shows a clean empty state rather than the demo user's data
