from pathlib import Path
import random

APP_TITLE = "gardone shans A1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILENAME = "lottery.db"
WEB_DIR = PROJECT_ROOT / "web"

POOCH = "پوچ"

GIFT_COUNTS = {
    "سکه طلا": 1,
    "بلور": 2,
    "پوچ": 3,
    "کریستال": 2,
    "ساعت دیواری": 2,
    "فرش": 2,
    "تابلو فرش": 4,
    "جام کریستالی": 6,
}


def _shuffle_without_adjacent(counts, attempts=500):

    rng = random.SystemRandom()
    total = sum(counts.values())

    def search(remaining, result, index):
        if index == total:
            return result[:]

        candidates = [name for name, count in remaining.items() if count > 0]
        rng.shuffle(candidates)
        candidates.sort(key=lambda name: remaining[name], reverse=True)

        for name in candidates:
            if index > 0 and result[-1] == name:
                continue
            if index == total - 1 and result[0] == name:
                continue

            remaining[name] -= 1
            result.append(name)
            solved = search(remaining, result, index + 1)
            if solved is not None:
                return solved
            result.pop()
            remaining[name] += 1

        return None

    for _ in range(attempts):
        remaining = dict(counts)
        solved = search(remaining, [], 0)
        if solved is not None:
            return solved

    raise RuntimeError("ساخت آرایش بدون آیتم‌های هم‌نام مجاور ممکن نشد.")


GIFTS = _shuffle_without_adjacent(GIFT_COUNTS)

PRIZE_COLORS = {
    "کریستال": "#38B6F0",
    "بلور": "#A56BD1",
    "جام کریستالی": "#2BA89A",
    "سکه طلا": "#F2B632",
    "ساعت دیواری": "#E8605E",
    "فرش": "#86B84A",
    "تابلو فرش": "#C77D3A",
}
POOCH_COLORS = ("#262B40", "#1E2336")
