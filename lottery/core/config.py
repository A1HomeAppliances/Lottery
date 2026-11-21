from pathlib import Path

APP_TITLE = "A1 Lucky Spin"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILENAME = "lottery.db"
WEB_DIR = PROJECT_ROOT / "web"

POOCH = "Pooch"

GIFTS = [
    "Crystal", "Pooch", "Sugar", "Pooch", "Crystal Glass", "Carpet",
    "Gold Coin", "Pooch", "Wall Clock", "Pooch", "Wall Clock", "Crystal",
    "Carpet", "Pooch", "Wall Clock", "Pooch", "Wall Clock", "Pooch",
    "Crystal", "Pooch", "Sugar", "Pooch", "Crystal Glass", "Carpet",
    "Gold Coin", "Pooch", "Wall Clock", "Pooch", "Wall Clock", "Crystal",
    "Carpet", "Pooch", "Wall Clock", "Pooch", "Wall Clock", "Pooch",
]

# Prize colours live ONLY on the wheel sectors.
PRIZE_COLORS = {
    "Crystal": "#38B6F0",
    "Sugar": "#A56BD1",
    "Crystal Glass": "#2BA89A",
    "Gold Coin": "#F2B632",
    "Wall Clock": "#E8605E",
    "Carpet": "#86B84A",
}
POOCH_COLORS = ("#262B40", "#1E2336")
