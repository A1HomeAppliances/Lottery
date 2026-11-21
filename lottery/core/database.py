# ---------------------------------------------------------------------------
# A1 Lucky Spin — SQLite persistence layer
# ---------------------------------------------------------------------------

import sqlite3

from core.config import POOCH


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

    def __init__(self, database_path):
        self.connection = sqlite3.connect(str(database_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

        self.connection.execute(self.SCHEMA.format(name="lottery"))
        self._add_missing_columns()

        if self._username_is_unique():
            self._rebuild_table()

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
                "This invoice number is already registered to another customer."
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

    def close(self):
        self.connection.close()
