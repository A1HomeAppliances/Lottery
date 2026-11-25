import logging
import math
import sqlite3
from contextlib import closing

from core.config import POOCH
from core.utils import digits_only
from .dbconnect import connect

log = logging.getLogger("a1.queries")


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------- read ----

def get_stats():
    with closing(connect()) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)                                        AS registered,
                   COALESCE(SUM(lottery_check = 1), 0)             AS played,
                   COALESCE(SUM(lottery_check = 1 AND prize != ?), 0) AS wins
            FROM lottery
            """,
            (POOCH,),
        ).fetchone()
    registered, played, wins = row["registered"], row["played"], row["wins"]
    return {
        "total_registered": registered,
        "total_played": played,
        "total_wins": wins,
        "total_pending": registered - played,
        "success_rate": round(wins / played * 100, 1) if played else 0,
    }


def get_prize_breakdown():
    """How many times each real prize has actually been won."""
    with closing(connect()) as conn:
        rows = conn.execute(
            """
            SELECT prize, COUNT(*) AS count
            FROM lottery
            WHERE lottery_check = 1 AND prize != ?
            GROUP BY prize
            ORDER BY count DESC, prize
            """,
            (POOCH,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_users_paginated(search="", page=1, per_page=10):
    text = " ".join(str(search).split())
    digits = digits_only(text)

    clauses, args = [], []
    if text:
        like = f"%{_escape_like(text)}%"
        for col in ("first_name", "last_name", "username"):
            clauses.append(f"{col} LIKE ? ESCAPE '\\'")
            args.append(like)
    if digits:
        like = f"%{digits}%"
        clauses.append("phone LIKE ?")
        clauses.append("CAST(factorID AS TEXT) LIKE ?")
        args += [like, like]
    where = ("WHERE " + " OR ".join(clauses)) if clauses else ""

    with closing(connect()) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM lottery {where}", args
        ).fetchone()[0]

        pages = max(1, math.ceil(total / per_page))
        page = min(max(1, int(page)), pages)

        rows = conn.execute(
            f"""
            SELECT factorID, first_name, last_name, phone,
                   lottery_check, prize, played_at
            FROM lottery
            {where}
            ORDER BY lottery_check DESC, COALESCE(played_at, '') DESC, factorID DESC
            LIMIT ? OFFSET ?
            """,
            args + [per_page, (page - 1) * per_page],
        ).fetchall()
    return [dict(r) for r in rows], total, page


# --------------------------------------------------------------- write ----

def create_user(invoice_id, first_name, last_name, phone,
                prize=POOCH, lottery_check=0, played_at=None):
    try:
        with closing(connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO lottery (factorID, username, first_name, last_name,
                                     phone, lottery_check, prize, played_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (invoice_id, f"{first_name} {last_name}", first_name, last_name,
                 phone, lottery_check, prize, played_at),
            )
        return True
    except sqlite3.Error:
        log.exception("create_user failed")
        return False


def edit_user(invoice_id, first_name, last_name, phone,
              lottery_check, prize, played_at):
    try:
        with closing(connect()) as conn, conn:
            cur = conn.execute(
                """
                UPDATE lottery
                SET username = ?, first_name = ?, last_name = ?, phone = ?,
                    lottery_check = ?, prize = ?, played_at = ?
                WHERE factorID = ?
                """,
                (f"{first_name} {last_name}", first_name, last_name, phone,
                 lottery_check, prize, played_at, invoice_id),
            )
        return cur.rowcount == 1
    except sqlite3.Error:
        log.exception("edit_user failed")
        return False


def delete_factor(invoice_id):
    try:
        with closing(connect()) as conn, conn:
            cur = conn.execute(
                "DELETE FROM lottery WHERE factorID = ?", (invoice_id,)
            )
        return cur.rowcount > 0
    except sqlite3.Error:
        log.exception("delete_factor failed")
        return False
