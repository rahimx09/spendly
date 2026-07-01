"""Seed N random expenses for a given user across the past M months."""
import datetime
import random
import sys
from pathlib import Path

# Make the project root importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from database.db import get_db

# (category, amount_low, amount_high, relative_weight)
# Higher weight = picked more often. Food is most common;
# Health and Entertainment are the rarest.
CATEGORY_POOL = [
    ("Food",          50,  800,  30),
    ("Transport",     20,  500,  20),
    ("Bills",         200, 3000, 12),
    ("Health",        100, 2000,  6),
    ("Entertainment", 100, 1500,  8),
    ("Shopping",      200, 5000, 14),
    ("Other",         50,  1000, 10),
]

# Realistic Indian descriptions per category — random descriptions,
# not ad-hoc strings, so the data feels plausible.
DESCRIPTIONS = {
    "Food": [
        "Lunch at office canteen", "Dinner with friends",
        "Chai and samosa", "Biryani takeout", "South Indian thali",
        "Street food — chaat", "Breakfast at cafe", "Dominos pizza",
        "Zomato order", "Swiggy delivery", "Cold coffee",
        "Momos and soup", "Dosa and chutney", "Subway sandwich",
    ],
    "Transport": [
        "Uber to office", "Auto rickshaw", "Ola cab to airport",
        "Metro card recharge", "Petrol refill", "Rapido bike ride",
        "Bus pass monthly", "Train ticket", "Parking fee",
        "Cab to station", "Diesel for car",
    ],
    "Bills": [
        "Electricity bill", "Wifi bill", "Mobile recharge",
        "Gas cylinder", "Water bill", "DTH recharge",
        "Credit card bill", "Broadband", "Maintenance charge",
        "House rent share",
    ],
    "Health": [
        "Pharmacy refill", "Doctor consultation", "Gym membership",
        "Health supplements", "Lab test", "Dental checkup",
        "Eye checkup", "Medicines",
    ],
    "Entertainment": [
        "Movie tickets", "Netflix subscription", "Spotify premium",
        "Book purchase", "Concert ticket", "Gaming top-up",
        "Amusement park", "Theatre show",
    ],
    "Shopping": [
        "Groceries", "New running shoes", "T-shirt", "Jeans",
        "Mobile cover", "Kitchen utensil", "Bed sheet set",
        "Headphones", "Smartwatch strap", "Cosmetics",
        "Gift wrap supplies", "Online order Amazon",
    ],
    "Other": [
        "Gift for friend", "Haircut", "Laundry", "Donation",
        "Newspaper", "Magazine subscription", "Stationery",
        "Household cleaner", "Phone repair",
    ],
}


def _random_date(months: int) -> str:
    """Return a random ISO date within the past `months` months, up to today."""
    today = datetime.date.today()
    # Cap the start date to roughly `months` months back.
    start_year = today.year
    start_month = today.month - months
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start = datetime.date(start_year, start_month, 1)
    delta_days = (today - start).days
    if delta_days <= 0:
        return today.isoformat()
    offset = random.randint(0, delta_days)
    return (today - datetime.timedelta(days=offset)).isoformat()


def _build_expense(user_id: int, months: int) -> tuple:
    """Pick a category (weighted), a realistic amount, a description, and a date."""
    categories = [c[0] for c in CATEGORY_POOL]
    weights    = [c[3] for c in CATEGORY_POOL]
    category   = random.choices(categories, weights=weights, k=1)[0]
    low, high  = next((c[1], c[2]) for c in CATEGORY_POOL if c[0] == category)
    amount     = round(random.uniform(low, high), 2)
    desc       = random.choice(DESCRIPTIONS[category])
    date       = _random_date(months)
    return (user_id, amount, category, date, desc)


def main(user_id: int, count: int, months: int) -> None:
    conn = get_db()
    try:
        # One transaction: roll back everything on any failure.
        rows = [_build_expense(user_id, months) for _ in range(count)]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

        # Summary stats over what we just inserted.
        cur = conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM expenses "
            "WHERE user_id = ? AND rowid IN ("
            "  SELECT rowid FROM expenses WHERE user_id = ? "
            "  ORDER BY rowid DESC LIMIT ?"
            ")",
            (user_id, user_id, count),
        )
        min_date, max_date, inserted = cur.fetchone()

        sample = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 5",
            (user_id,),
        ).fetchall()

        print(f"Inserted: {inserted}")
        print(f"Date range: {min_date} -> {max_date}")
        print("Sample (5 most recent):")
        for r in sample:
            # Use Rs. instead of ₹ for stdout — Windows console (cp1252) can't encode ₹.
            print(f"  #{r['id']:>3}  {r['date']}  Rs.{r['amount']:>8.2f}  "
                  f"{r['category']:<14} {r['description']}")
    except Exception as exc:
        # No rollback here: the commit() above has already succeeded,
        # so any error from this point is a reporting/print failure,
        # not a data-integrity failure.
        print(f"Error after commit (data IS inserted): {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    # Args are validated by the slash command before this script runs.
    main(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
