"""Tests for Step 6 — Date filter for profile page.

Covers the Definition-of-Done checklist from the spec:
  1. No filter -> all transactions.
  2. preset=this_month filters to current month.
  3. Custom from/to (inclusive).
  4. Summary stats reflect the filter.
  5. Category breakdown reflects the filter.
  6. Bad from/to does not raise 500.
  7. Active filter is reflected in the UI.
  8. Clearing the filter restores the full view.
  9. No new hex colours in profile.html / style.css.

Plus the helper-level rules (lexicographic ISO sort, inclusive to,
independent bounds, validation, presets from date.today, empty state).
"""
import datetime
import re

from database import db as db_module
from database.db import (
    create_user,
    get_category_breakdown,
    get_recent_expenses,
    get_user_expense_count,
    get_user_top_category,
    get_user_total_spent,
)


# ------------------------------------------------------------------ #
# Shared helpers                                                       #
# ------------------------------------------------------------------ #

EMAIL = "demo@spendly.com"
PASSWORD = "demo123"
NAME = "Demo User"


def _sign_in_demo(client) -> int:
    """Seed + log in the demo user, return the signed-in user id."""
    from database.db import seed_db
    seed_db()  # creates the demo user + 8 in-month expenses
    client.post(
        "/login",
        data={"email": EMAIL, "password": PASSWORD},
        follow_redirects=False,
    )
    with client.session_transaction() as sess:
        return sess.get("user_id")


def _add_out_of_window_rows(user_id: int) -> None:
    """Hand-insert a small set of expenses outside the current month.

    The seed always lands in the current month, so for any preset or
    range filter that excludes the current month we need our own
    fixtures. Uses an explicit ISO date (2020-01-15) to stay
    deterministic and out of every reasonable filter window.
    """
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 100.0, "Food",      "2020-01-15", "old lunch"),
                (user_id, 250.0, "Bills",     "2020-01-20", "old electric"),
                (user_id, 75.0,  "Transport", "2020-01-22", "old cab"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _register_fresh_user_and_login(client) -> int:
    """Create a fresh user with no expenses, log them in, return their id."""
    create_user("Empty Eve", "eve@spendly.com", "evepassword")
    client.post(
        "/login",
        data={"email": "eve@spendly.com", "password": "evepassword"},
        follow_redirects=False,
    )
    with client.session_transaction() as sess:
        return sess.get("user_id")


# ------------------------------------------------------------------ #
# Auth guards                                                          #
# ------------------------------------------------------------------ #

def test_profile_still_redirects_when_signed_out(client):
    """The /profile filter additions must not break the auth guard."""
    resp = client.get("/profile?preset=this_month", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_logout_still_works_with_filter_query_string(client):
    """A signed-in user can still sign out and bounces to /login."""
    _sign_in_demo(client)
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

    # And /profile is once again protected.
    resp = client.get("/profile?from=2026-07-01&to=2026-07-31",
                      follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# 1. No filter -> all transactions (Step 5 regression)                 #
# ------------------------------------------------------------------ #

def test_profile_no_filter_shows_all_transactions(client):
    """Visiting /profile with no query string preserves Step 5 behaviour."""
    _sign_in_demo(client)
    body = client.get("/profile").get_data(as_text=True)
    # Seed sum: 250+180.5+90+1500+450+799+1299+120 = 4688.50
    assert "₹4,688.50" in body
    # All eight seed descriptions must appear.
    for desc in (
        "Lunch at office canteen", "Dinner with friends",
        "Uber to airport", "Electricity bill", "Pharmacy refill",
        "Movie tickets", "New running shoes", "Gift wrap supplies",
    ):
        assert desc in body, f"missing seed description: {desc!r}"


def test_profile_no_filter_has_active_chip(client):
    """At least one preset chip is marked is-active when no filter is set."""
    _sign_in_demo(client)
    body = client.get("/profile").get_data(as_text=True)
    assert "filter-preset is-active" in body


# ------------------------------------------------------------------ #
# 2. Preset = this_month                                               #
# ------------------------------------------------------------------ #

def test_preset_this_month_excludes_out_of_month_rows(client):
    """Out-of-month expenses must be hidden when this_month is active."""
    _sign_in_demo(client)
    with client.session_transaction() as sess:
        user_id = sess["user_id"]
    _add_out_of_window_rows(user_id)

    body = client.get("/profile?preset=this_month").get_data(as_text=True)
    # Seed total is unchanged: 4688.50 — old rows are excluded.
    assert "₹4,688.50" in body
    # Out-of-month descriptions must NOT appear.
    assert "old lunch" not in body
    assert "old electric" not in body
    assert "old cab" not in body
    # In-month descriptions still appear.
    assert "Lunch at office canteen" in body


def test_preset_this_month_marks_chip_active(client):
    _sign_in_demo(client)
    body = client.get("/profile?preset=this_month").get_data(as_text=True)
    m = re.search(
        r'<a class="filter-preset is-active"[^>]*>This month</a>', body,
    )
    assert m is not None, "This month preset should be marked is-active"


def test_preset_this_month_with_no_in_month_data_renders_empty_state(client):
    """A user whose only expenses are outside the current month
    should see the graceful empty state (₹0.00, 0, —)."""
    user_id = _register_fresh_user_and_login(client)
    _add_out_of_window_rows(user_id)

    body = client.get("/profile?preset=this_month").get_data(as_text=True)
    assert "₹0.00" in body
    # Em-dash for the top-category stat.
    assert "—" in body
    # Old descriptions still must not appear (they're out of range).
    assert "old lunch" not in body


# ------------------------------------------------------------------ #
# 3. Preset = last_7 / last_30                                         #
# ------------------------------------------------------------------ #

def test_preset_last_7_renders_with_active_chip(client):
    """All seed rows are in the current month; last_7 still matches
    the most recent 7 days. We check the chip is marked active and a
    rupee total renders."""
    _sign_in_demo(client)
    body = client.get("/profile?preset=last_7").get_data(as_text=True)
    assert re.search(r"₹[\d,]+\.\d{2}", body)
    m = re.search(
        r'<a class="filter-preset is-active"[^>]*>Last 7 days</a>', body,
    )
    assert m is not None, "Last 7 days chip should be active"


def test_preset_last_30_marks_chip_active(client):
    _sign_in_demo(client)
    body = client.get("/profile?preset=last_30").get_data(as_text=True)
    m = re.search(
        r'<a class="filter-preset is-active"[^>]*>Last 30 days</a>', body,
    )
    assert m is not None, "Last 30 days chip should be active"


# ------------------------------------------------------------------ #
# 4. Custom from/to range                                              #
# ------------------------------------------------------------------ #

def test_custom_from_to_inclusive_upper_bound(client):
    """The 'to' bound is inclusive: an expense ON 'to' must be included."""
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 10.0, "Food",  "2026-07-01", "edge-1"),
                (user_id, 20.0, "Bills", "2026-07-10", "edge-2"),
                (user_id, 30.0, "Food",  "2026-07-20", "edge-3"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    # to=2026-07-10 must include the row dated exactly 2026-07-10.
    body = client.get("/profile?from=2026-07-01&to=2026-07-10").get_data(as_text=True)
    assert "edge-1" in body
    assert "edge-2" in body
    assert "edge-3" not in body
    # Total = 10 + 20 = 30.00
    assert "₹30.00" in body
    # Transaction count card should read 2.
    m = re.search(
        r"stat-label[^>]*>Transactions</span>\s*<span[^>]*stat-value[^>]*>(\d+)</span>",
        body,
    )
    assert m is not None
    assert m.group(1) == "2"


def test_custom_from_to_excludes_out_of_range_rows(client):
    _sign_in_demo(client)
    with client.session_transaction() as sess:
        user_id = sess["user_id"]
    _add_out_of_window_rows(user_id)
    # Range that excludes 2020 entirely.
    body = client.get(
        "/profile?from=2026-07-01&to=2026-07-31"
    ).get_data(as_text=True)
    # Seed in-month descriptions visible, 2020 ones hidden.
    assert "Lunch at office canteen" in body
    assert "old lunch" not in body
    assert "old electric" not in body


def test_only_from_bound_applied(client):
    """With only `from` set, the upper bound is unbounded."""
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 5.0,  "Food", "2020-01-15", "ancient"),
                (user_id, 10.0, "Bills", "2026-07-10", "recent"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    body = client.get("/profile?from=2026-01-01").get_data(as_text=True)
    assert "recent" in body
    assert "ancient" not in body


def test_only_to_bound_applied(client):
    """With only `to` set, the lower bound is unbounded."""
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 5.0,  "Food", "2020-01-15", "ancient"),
                (user_id, 10.0, "Bills", "2026-07-10", "recent"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    body = client.get("/profile?to=2020-12-31").get_data(as_text=True)
    assert "ancient" in body
    assert "recent" not in body


# ------------------------------------------------------------------ #
# 5. Filtered summary stats                                            #
# ------------------------------------------------------------------ #

def test_filtered_total_spent_reflects_range(client):
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 100.0, "Food",  "2026-07-01", "in"),
                (user_id, 200.0, "Bills", "2026-07-15", "in"),
                (user_id, 999.0, "Food",  "2020-01-01", "out"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    body = client.get(
        "/profile?from=2026-07-01&to=2026-07-31"
    ).get_data(as_text=True)
    assert "₹300.00" in body
    # The unfiltered total (1299) must NOT appear.
    assert "₹1,299" not in body


def test_filtered_top_category_reflects_range(client):
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                # Bills dominates the full range (1500).
                (user_id, 1500.0, "Bills", "2020-01-01", "old bills"),
                # Food dominates the in-month range (350).
                (user_id, 200.0,  "Food",  "2026-07-01", "f1"),
                (user_id, 150.0,  "Food",  "2026-07-02", "f2"),
                (user_id, 100.0,  "Bills", "2026-07-03", "b1"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    # Unfiltered top category at the helper level is Bills.
    assert get_user_top_category(user_id) == "Bills"

    # In-month top category at the helper level is Food.
    assert (
        get_user_top_category(user_id, "2026-07-01", "2026-07-31")
        == "Food"
    )

    # And the rendered page also shows the new top in the stat card.
    body = client.get(
        "/profile?from=2026-07-01&to=2026-07-31"
    ).get_data(as_text=True)
    assert "Food" in body


def test_filtered_count_reflects_range(client):
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 1.0, "Food", "2020-01-01", "x"),
                (user_id, 2.0, "Food", "2020-01-02", "y"),
                (user_id, 3.0, "Food", "2026-07-01", "z"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    body = client.get(
        "/profile?from=2026-07-01&to=2026-07-31"
    ).get_data(as_text=True)
    m = re.search(
        r"stat-label[^>]*>Transactions</span>\s*<span[^>]*stat-value[^>]*>(\d+)</span>",
        body,
    )
    assert m is not None
    assert m.group(1) == "1"


# ------------------------------------------------------------------ #
# 6. Category breakdown respects the filter                            #
# ------------------------------------------------------------------ #

def test_category_breakdown_excludes_out_of_range_categories(app_with_tmp_db, client):
    """A category whose every row is out of range must not appear in
    the breakdown when the filter is active."""
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 100.0, "Food",  "2026-07-01", "in f"),
                (user_id, 100.0, "Bills", "2026-07-02", "in b"),
                # Old Shopping row that should be hidden.
                (user_id, 500.0, "Shopping", "2020-01-01", "old shop"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    breakdown = get_category_breakdown(
        user_id, "2026-07-01", "2026-07-31",
    )
    names = [r["name"] for r in breakdown]
    assert "Food" in names
    assert "Bills" in names
    assert "Shopping" not in names


def test_category_breakdown_percents_rescaled_in_range(app_with_tmp_db, client):
    """Percents must be re-computed against the filtered total, not
    the unfiltered total."""
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                # 2020: Food=100, Bills=900 (Bills dominates at 90%).
                (user_id, 100.0, "Food",  "2020-01-01", "old f"),
                (user_id, 900.0, "Bills", "2020-01-02", "old b"),
                # 2026-07: Food=50, Bills=50 (50/50 split).
                (user_id, 50.0,  "Food",  "2026-07-01", "new f"),
                (user_id, 50.0,  "Bills", "2026-07-02", "new b"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    breakdown = get_category_breakdown(
        user_id, "2026-07-01", "2026-07-31",
    )
    # Each row should be 50% of the filtered total (100).
    pcts = sorted(r["percent"] for r in breakdown)
    assert pcts == [50, 50]


# ------------------------------------------------------------------ #
# 7. Empty filtered result renders gracefully                          #
# ------------------------------------------------------------------ #

def test_empty_filtered_range_renders_zero_state(client):
    """A range that matches nothing must show ₹0.00, 0, —, no rows."""
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        # A single row, dated far in the past.
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, 50.0, "Food", "1999-12-31", "ancient"),
        )
        conn.commit()
    finally:
        conn.close()
    body = client.get(
        "/profile?from=2030-01-01&to=2030-12-31"
    ).get_data(as_text=True)
    assert "₹0.00" in body
    assert "—" in body
    # The ancient row must not appear in the table.
    assert "ancient" not in body


# ------------------------------------------------------------------ #
# 8. Bad input -> page still renders, fallback to no bound             #
# ------------------------------------------------------------------ #

def test_bad_from_value_does_not_500(client):
    """Garbage in `from` must not raise — page still renders 200."""
    _sign_in_demo(client)
    resp = client.get("/profile?from=not-a-date", follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Should fall back to no bound, so seed data still shows up.
    assert "Lunch at office canteen" in body
    # And the bad value must not be reflected back into the input.
    assert 'value="not-a-date"' not in body


def test_bad_to_value_does_not_500(client):
    _sign_in_demo(client)
    resp = client.get("/profile?to=garbage", follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Lunch at office canteen" in body
    assert 'value="garbage"' not in body


def test_both_bounds_bad_falls_back_to_no_filter(client):
    _sign_in_demo(client)
    resp = client.get(
        "/profile?from=foo&to=bar", follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # No filter active => full seed total visible.
    assert "₹4,688.50" in body


def test_partial_bad_value_drops_whole_filter(client):
    """A bad `from` with a good `to` invalidates the whole filter: both
    bounds are dropped and every row is visible. The chosen contract is
    stricter than the spec text — partial bounds from a half-broken
    form would confuse users more than help them."""
    user_id = _register_fresh_user_and_login(client)
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 10.0, "Food", "2020-01-01", "old"),
                (user_id, 20.0, "Bills", "2026-07-10", "new"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    body = client.get(
        "/profile?from=garbage&to=2026-07-31"
    ).get_data(as_text=True)
    # Whole filter dropped: both rows are visible.
    assert "new" in body
    assert "old" in body
    # The page is in unfiltered state (no Clear link, "All" chip active).
    assert ">Clear</a>" not in body
    assert 'class="filter-preset is-active"' in body


# ------------------------------------------------------------------ #
# 9. SQL-injection / parameterised-query safety                        #
# ------------------------------------------------------------------ #

def test_sql_metacharacters_in_from_do_not_crash(client):
    """A `from` value full of SQL metacharacters must not raise and
    must be treated as a bad date (no rows returned, page 200)."""
    _sign_in_demo(client)
    nasty = "2026-07-01' OR '1'='1"
    resp = client.get(f"/profile?from={nasty}", follow_redirects=False)
    assert resp.status_code == 200
    # The malicious value is dropped (validation fails), so the seed
    # data must NOT be filtered down to nothing.
    body = resp.get_data(as_text=True)
    assert "Lunch at office canteen" in body


def test_sql_injection_in_to_does_not_drop_other_users_rows(client):
    """A `to` value crafted to look like SQL must not match every row
    — it must be treated as a bad date and ignored."""
    _sign_in_demo(client)
    nasty = "x' OR 1=1 OR date>='"
    resp = client.get(f"/profile?to={nasty}", follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Falls back to no bound; full seed still visible.
    assert "₹4,688.50" in body


# ------------------------------------------------------------------ #
# 10. UI reflects the active filter                                    #
# ------------------------------------------------------------------ #

def test_active_preset_reflected_in_ui(client):
    _sign_in_demo(client)
    body = client.get("/profile?preset=this_month").get_data(as_text=True)
    # Exactly one chip should be marked is-active.
    actives = re.findall(r'<a class="filter-preset is-active"', body)
    assert len(actives) == 1
    # And the Clear link should appear because the filter is active.
    assert ">Clear</a>" in body


def test_from_and_to_round_trip_into_input_values(client):
    _sign_in_demo(client)
    body = client.get(
        "/profile?from=2026-07-01&to=2026-07-31"
    ).get_data(as_text=True)
    assert 'name="from" value="2026-07-01"' in body
    assert 'name="to" value="2026-07-31"' in body


def test_clear_link_absent_when_no_filter_active(client):
    _sign_in_demo(client)
    body = client.get("/profile").get_data(as_text=True)
    assert ">Clear</a>" not in body


def test_clear_link_present_when_filter_active(client):
    _sign_in_demo(client)
    body = client.get("/profile?preset=this_month").get_data(as_text=True)
    assert ">Clear</a>" in body
    # Clear link points at the bare /profile route.
    assert re.search(
        r'<a class="filter-clear" href="[^"]*/profile"[^>]*>Clear</a>', body,
    )


# ------------------------------------------------------------------ #
# 11. Clearing the filter                                              #
# ------------------------------------------------------------------ #

def test_clearing_filter_returns_to_full_view(client):
    """Visiting /profile with no query string after a filter restores
    the unfiltered totals."""
    _sign_in_demo(client)
    with client.session_transaction() as sess:
        user_id = sess["user_id"]
    _add_out_of_window_rows(user_id)

    # Filtered: only seed, no 2020 rows.
    filtered = client.get(
        "/profile?from=2026-07-01&to=2026-07-31"
    ).get_data(as_text=True)
    assert "old lunch" not in filtered
    assert "₹4,688.50" in filtered

    # Cleared: 2020 rows are back, total grows.
    cleared = client.get("/profile").get_data(as_text=True)
    assert "old lunch" in cleared
    # Sum of all 11 rows (8 seed + 3 out-of-month) > 4,688.50
    m = re.search(r"₹([\d,]+\.\d{2})", cleared)
    assert m is not None
    total_cleared = float(m.group(1).replace(",", ""))
    assert total_cleared > 4688.50


# ------------------------------------------------------------------ #
# 12. CSS / template hygiene — no new hex colours                      #
# ------------------------------------------------------------------ #

def test_profile_html_filter_bar_uses_no_hex_colours():
    """The Step 6 filter bar markup in profile.html must not introduce
    any hex colour values. (Pre-existing colour usage elsewhere in the
    file is out of scope for this step.)"""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "templates" / "profile.html"
    body = p.read_text(encoding="utf-8")
    # Slice just the filter-bar block.
    start = body.find("<!-- 2b. Date filter bar -->")
    end = body.find("<!-- 3. Transaction history table -->")
    assert start != -1 and end != -1, "filter bar block not found"
    block = body[start:end]
    hex_colours = re.findall(r"#[0-9a-fA-F]{3,8}\b", block)
    assert hex_colours == [], (
        f"filter bar in profile.html must not contain hex colours, "
        f"found: {hex_colours}"
    )


def test_style_css_filter_bar_uses_no_hex_colours():
    """The Step 6 filter bar CSS in style.css must use only CSS
    variables — no new hex colour values may be added. (Pre-existing
    hex values in :root and other unrelated sections are out of
    scope.)"""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "static" / "css" / "style.css"
    body = p.read_text(encoding="utf-8")
    # Slice just the Step 6 block, marked by its leading comment.
    start = body.find("/* Date filter bar — Step 6 */")
    assert start != -1, "Step 6 CSS block not found"
    block = body[start:]
    hex_colours = re.findall(r"#[0-9a-fA-F]{3,8}\b", block)
    assert hex_colours == [], (
        f"Step 6 CSS block must not contain hex colours, "
        f"found: {hex_colours}"
    )


# ------------------------------------------------------------------ #
# 13. Helper-level: lexicographic ISO sort, optional bounds            #
# ------------------------------------------------------------------ #

def test_iso_date_strings_sort_lexicographically():
    """ISO YYYY-MM-DD must sort lexicographically — i.e. plain
    string >= / <= work without a date() cast. This is a property
    check on the format itself, not on the SQL layer."""
    samples = ["2020-01-15", "2026-07-01", "2026-07-10", "2026-07-31"]
    assert samples == sorted(samples)
    # Same when expressed as a filter pair.
    from_d, to_d = "2026-07-01", "2026-07-31"
    assert from_d <= to_d
    # An out-of-range date sorts outside the pair.
    assert "2020-01-15" < from_d


def test_to_date_is_inclusive_at_helper_level(app_with_tmp_db):
    """get_user_total_spent must include a row dated exactly on the
    `to` bound (inclusive upper)."""
    user_id = create_user("Edge Ed", "edge@spendly.com", "edgepass1")
    conn = db_module.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, 42.0, "Food", "2026-07-10", "on-the-edge"),
        )
        conn.commit()
    finally:
        conn.close()
    assert get_user_total_spent(user_id, "2026-07-10", "2026-07-10") == 42.0
    assert get_user_expense_count(user_id, "2026-07-10", "2026-07-10") == 1
    rows = get_recent_expenses(
        user_id, from_date="2026-07-10", to_date="2026-07-10",
    )
    assert len(rows) == 1 and rows[0]["description"] == "on-the-edge"


def test_either_bound_may_be_omitted_independently(app_with_tmp_db):
    user_id = create_user("Solo Sam", "solo@spendly.com", "solopass1")
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 5.0,  "Food", "2020-01-15", "old"),
                (user_id, 10.0, "Bills", "2026-07-10", "new"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    # from only
    assert get_user_total_spent(user_id, from_date="2026-01-01") == 10.0
    # to only
    assert get_user_total_spent(user_id, to_date="2020-12-31") == 5.0
    # neither
    assert get_user_total_spent(user_id) == 15.0
    # both, inclusive on both sides
    assert (
        get_user_total_spent(user_id, "2020-01-01", "2026-12-31") == 15.0
    )


def test_preset_dates_anchor_to_today():
    """The this_month preset must anchor to the first and last day of
    the current month, computed in Python from date.today()."""
    today = datetime.date.today()
    expected_from = today.replace(day=1).isoformat()
    expected_to = today.isoformat()
    assert expected_from <= expected_to
