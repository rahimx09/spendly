# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository overview

**Spendly** — a personal expense-tracking web app built incrementally in numbered steps. The codebase is a work-in-progress teaching project: some routes are placeholder strings ("coming in Step N") waiting for the corresponding feature to be implemented. The current focus is **Step 1 — Database Setup** (`database/db.py`).

## Stack

- **Backend:** Python 3 + Flask 3.1.3
- **Database:** SQLite (file: `expense_tracker.db`, gitignored)
- **Templating:** Jinja2 (`templates/`)
- **Static:** Hand-written CSS (`static/css/style.css`), vanilla JS (`static/js/main.js`)
- **Testing:** pytest 8.3.5 + pytest-flask 1.3.0 (no tests exist yet)

No database ORM — plain `sqlite3` from stdlib.

## Setup & run

```bash
# Activate the venv (already in repo at venv/)
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

# Start the dev server (debug on, port 5001)
python app.py
```

Open http://localhost:5001. The landing page is at `/`; auth pages are `/login` and `/register`.

## Project layout

```
app.py                  Flask app + all routes (current + placeholders)
database/
  db.py                 Step 1 task: get_db(), init_db(), seed_db()
  __init__.py           empty
templates/
  base.html             layout shell (nav, footer, block hooks)
  landing.html          marketing landing page
  login.html, register.html
  terms.html, privacy.html
static/
  css/style.css
  js/main.js            currently empty (comment only)
requirements.txt
```

## Architecture notes

- **Single `app.py`** owns all routes. Real routes (`/`, `/register`, `/login`, `/terms`, `/privacy`) render templates; placeholder routes (`/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`) currently return strings and will be filled in across subsequent steps.
- **`database/db.py` is intentionally a stub** — Step 1. The header comment in the file specifies the contract it must implement:
  - `get_db()` — returns a `sqlite3` connection with `row_factory` set to `sqlite3.Row` and `PRAGMA foreign_keys = ON`
  - `init_db()` — creates all tables via `CREATE TABLE IF NOT EXISTS`
  - `seed_db()` — inserts sample/development data
- **No session/auth wiring yet.** Forms in `login.html` and `register.html` are GET renders for now — they post to `/login` and `/register` but no `POST` handlers exist yet. Those land in a later step.
- **Templates extend `base.html`** and override `{% block title %}`, `{% block content %}`, optionally `{% block head %}` and `{% block scripts %}`. URL generation goes through `url_for(...)` — never hard-code paths.
- **Brand:** "Spendly", currency symbol `₹`. Keep terminology consistent with this.

## Conventions

- Keep `app.py` as the single route module unless it gets unwieldy; introduce a package (e.g. `app/`) only when there is a real reason.
- Database file lives at the project root as `expense_tracker.db` and is in `.gitignore` — never commit it.
- `venv/` is also gitignored; don't add it.
- Use **stdlib `sqlite3` only** — no SQLAlchemy/ORM unless a later step explicitly introduces it.
- Passwords must be **hashed** (e.g. `werkzeug.security.generate_password_hash`) — never stored in plaintext. `werkzeug` is already in `requirements.txt`.
- When extending `db.py`, follow the contract in its header docstring: `get_db` returns a connection with `Row` factory + foreign keys on; `init_db` and `seed_db` should be safely re-runnable (`IF NOT EXISTS` / `INSERT OR IGNORE`).
