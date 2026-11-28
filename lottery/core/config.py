from pathlib import Path

APP_TITLE = "گردونه شانس A1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILENAME = "lottery.db"
WEB_DIR = PROJECT_ROOT / "web"

# "پوچ" is a reserved sentinel name — its row lives in `wheel_items` with
# `is_pooch = 1`. Used by backend, queries, and the frontend via `rpc_config`.
POOCH = "پوچ"
