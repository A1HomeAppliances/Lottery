"""Wheel arrangement logic and default seed data.

The wheel is a circular sequence of sector names. To avoid two adjacent
sectors showing the same gift (which looks broken), we need a *circular
arrangement without adjacent duplicates*. The necessary and sufficient
condition for such an arrangement is `max_count * 2 <= total`.
"""

import random
import time

# Seed data — used only the very first time the `wheel_items` table is empty.
# After that, the admin panel owns the truth; this list is never re-applied.
DEFAULT_WHEEL_ITEMS = [
    {"name": "سکه طلا",      "count": 1, "color": "#F2B632", "is_pooch": 0},
    {"name": "بلور",         "count": 2, "color": "#A56BD1", "is_pooch": 0},
    {"name": "پوچ",          "count": 3, "color": "#262B40", "color2": "#1E2336", "is_pooch": 1},
    {"name": "کریستال",      "count": 2, "color": "#38B6F0", "is_pooch": 0},
    {"name": "ساعت دیواری",  "count": 2, "color": "#E8605E", "is_pooch": 0},
    {"name": "فرش",          "count": 2, "color": "#86B84A", "is_pooch": 0},
    {"name": "تابلو فرش",    "count": 4, "color": "#C77D3A", "is_pooch": 0},
    {"name": "جام کریستالی", "count": 6, "color": "#2BA89A", "is_pooch": 0},
]

DEFAULT_POOCH_COLORS = ("#262B40", "#1E2336")


def shuffle_without_adjacent(counts, timeout=2.0):
    """Return a circular arrangement of `counts` (dict name -> count) where
    no two adjacent names (including last & first) are identical.

    Returns None if no arrangement is possible within `timeout` seconds.
    """
    total = sum(counts.values())
    if total == 0:
        return []

    # Necessary & sufficient feasibility condition.
    if max(counts.values()) * 2 > total:
        return None

    deadline = time.time() + timeout
    rng = random.SystemRandom()

    def search(remaining, result, index):
        if index == total:
            return result[:]
        if time.time() > deadline:
            return None

        candidates = [n for n, c in remaining.items() if c > 0]
        rng.shuffle(candidates)                     # randomise ties …
        candidates.sort(key=lambda n: remaining[n], reverse=True)  # … then greedily prefer rare-large
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

    return search(dict(counts), [], 0)


def build_arrangement(items):
    """Given a list of wheel_items dicts (with at least `name` and `count`),
    return a circular list of names or None if infeasible.
    """
    counts = {i["name"]: i["count"] for i in items if i["count"] > 0}
    if not counts:
        return []
    return shuffle_without_adjacent(counts)
