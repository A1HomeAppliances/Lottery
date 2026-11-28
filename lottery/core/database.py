# ---------------------------------------------------------------------------
# A1 Lucky Spin — SQLite persistence layer
# ---------------------------------------------------------------------------

import sqlite3

from core.config import POOCH
from core.wheel import DEFAULT_POOCH_COLORS, DEFAULT_WHEEL_ITEMS


class LotteryDatabase:

    EXTRA_COLUMNS = {
        "first_name": "TEXT",
        "last_name": "TEXT",
        "phone": "TEXT",
        "played_at": "TEXT",
    }

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS {name} (
            factorID INTEGER NOT NULL PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            lottery_check INTEGER NOT NULL DEFAULT 0,
            prize TEXT NOT NULL DEFAULT '%s',
            played_at TEXT
        )
    """ % POOCH

    WHEEL_SCHEMA = """
        CREATE TABLE IF NOT EXISTS wheel_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            count INTEGER NOT NULL DEFAULT 1,
            color TEXT,
            color2 TEXT,
            is_pooch INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """

    def __init__(self, database_path):
        self.connection = sqlite3.connect(str(database_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

        self.connection.execute(self.SCHEMA.format(name="lottery"))
        self._add_missing_columns()

        # --- Admin Config Table ---
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS admin_config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # --- Wheel Items Table ---
        self.connection.execute(self.WHEEL_SCHEMA)

        if self._username_is_unique():
            self._rebuild_table()

        self._seed_wheel_items_if_empty()
        self.connection.commit()

    def _add_missing_columns(self):
        existing = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(lottery)")
        }
        for column, kind in self.EXTRA_COLUMNS.items():
            if column not in existing:
                self.connection.execute(
                    f"ALTER TABLE lottery ADD COLUMN {column} {kind}"
                )

    def _username_is_unique(self):
        for index in self.connection.execute("PRAGMA index_list(lottery)"):
            if index["unique"]:
                columns = [
                    row["name"]
                    for row in self.connection.execute(
                        f'PRAGMA index_info("{index["name"]}")'
                    )
                ]
                if columns == ["username"]:
                    return True
        return False

    def _rebuild_table(self):
        connection = self.connection

        connection.execute("DROP TABLE IF EXISTS lottery_new")
        connection.execute(self.SCHEMA.format(name="lottery_new"))

        with connection:
            connection.execute(
                """
                INSERT INTO lottery_new
                    (factorID, username, first_name, last_name, phone,
                     lottery_check, prize, played_at)
                SELECT factorID, username, first_name, last_name, phone,
                       COALESCE(lottery_check, 0),
                       COALESCE(prize, ?),
                       played_at
                FROM lottery
                """,
                (POOCH,),
            )
            connection.execute("DROP TABLE lottery")
            connection.execute("ALTER TABLE lottery_new RENAME TO lottery")

    def get_invoice(self, factor_id):
        return self.connection.execute(
            """
            SELECT factorID, username, first_name, last_name,
                   phone, lottery_check, prize
            FROM lottery
            WHERE factorID = ?
            """,
            (factor_id,),
        ).fetchone()

    def register_invoice(self, first_name, last_name, phone, factor_id):
        row = self.get_invoice(factor_id)
        full_name = f"{first_name} {last_name}"

        if row is None:
            self.connection.execute(
                """
                INSERT INTO lottery
                    (factorID, username, first_name, last_name,
                     phone, lottery_check, prize)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (factor_id, full_name, first_name, last_name, phone, POOCH),
            )
        elif not row["phone"]:
            self.connection.execute(
                """
                UPDATE lottery
                SET username = ?, first_name = ?, last_name = ?, phone = ?
                WHERE factorID = ?
                """,
                (full_name, first_name, last_name, phone, factor_id),
            )
        elif row["phone"] != phone:
            raise ValueError(
                "این شمارهٔ فاکتور قبلاً برای مشتری دیگری ثبت شده است."
            )

        self.connection.commit()
        return self.get_invoice(factor_id)

    def mark_as_played(self, factor_id, prize):
        cursor = self.connection.execute(
            """
            UPDATE lottery
            SET prize = ?, lottery_check = 1,
                played_at = datetime('now', 'localtime')
            WHERE factorID = ? AND lottery_check = 0
            """,
            (prize, factor_id),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    # --- Admin Methods ---

    def get_admin_config(self, key):
        row = self.connection.execute(
            "SELECT value FROM admin_config WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_admin_config(self, key, value):
        self.connection.execute(
            "INSERT INTO admin_config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.connection.commit()

    # --- Wheel Items Methods ---

    def _seed_wheel_items_if_empty(self):
        count = self.connection.execute(
            "SELECT COUNT(*) FROM wheel_items"
        ).fetchone()[0]
        if count > 0:
            return
        for i, item in enumerate(DEFAULT_WHEEL_ITEMS):
            self.connection.execute(
                """INSERT INTO wheel_items
                   (name, count, color, color2, is_pooch, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    item["name"],
                    item["count"],
                    item.get("color"),
                    item.get("color2"),
                    int(item.get("is_pooch", 0)),
                    i,
                ),
            )

    def get_wheel_items(self):
        rows = self.connection.execute(
            "SELECT * FROM wheel_items ORDER BY sort_order, id"
        ).fetchall()
        return [dict(r) for r in rows]

    def add_wheel_item(self, name, count, color):
        """Insert a non-pooch item. Raises sqlite3.IntegrityError on name clash."""
        max_order = self.connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM wheel_items"
        ).fetchone()[0]
        cur = self.connection.execute(
            """INSERT INTO wheel_items (name, count, color, is_pooch, sort_order)
               VALUES (?, ?, ?, 0, ?)""",
            (name, count, color, max_order + 1),
        )
        self.connection.commit()
        return cur.lastrowid

    def update_wheel_item(self, item_id, *, name=None, count=None,
                          color=None, color2=None):
        fields, values = [], []
        if name is not None:
            fields.append("name = ?");       values.append(name)
        if count is not None:
            fields.append("count = ?");      values.append(count)
        if color is not None:
            fields.append("color = ?");      values.append(color)
        if color2 is not None:
            fields.append("color2 = ?");     values.append(color2)
        if not fields:
            return True
        values.append(item_id)
        cur = self.connection.execute(
            f"UPDATE wheel_items SET {', '.join(fields)} WHERE id = ?", values
        )
        self.connection.commit()
        return cur.rowcount == 1

    def delete_wheel_item(self, item_id):
        """Delete a wheel item — the pooch row is protected."""
        cur = self.connection.execute(
            "DELETE FROM wheel_items WHERE id = ? AND is_pooch = 0", (item_id,)
        )
        self.connection.commit()
        return cur.rowcount == 1

    def close(self):
        self.connection.close()
