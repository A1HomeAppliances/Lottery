"""
Application logic shared by the Android WebView bridge and the desktop dev
server. No Kivy imports here, so it is easy to test.

The web UI calls it as  backend.handle(method, params) -> dict.
"""
import logging
import random
import sqlite3
import threading

from core.config import GIFTS, POOCH, POOCH_COLORS, PRIZE_COLORS
from core.database import LotteryDatabase
from core.utils import digits_only, normalize_phone

log = logging.getLogger("a1.backend")
_rng = random.SystemRandom()          # unpredictable result for a real lottery


def _fail(message):
    return {"ok": False, "error": message}


class Backend:

    def __init__(self, database_path):
        self.db = LotteryDatabase(database_path)
        self._lock = threading.Lock()

    def close(self):
        self.db.close()

    def handle(self, method, params):
        fn = getattr(self, f"rpc_{method}", None) \
            if isinstance(method, str) and method.isidentifier() else None
        if fn is None or not callable(fn):
            return _fail("Unknown request.")
        try:
            with self._lock:
                return fn(params if isinstance(params, dict) else {})
        except sqlite3.Error:
            log.exception("database error")
            return _fail("Database error.")
        except Exception:
            log.exception("unexpected error")
            return _fail("Something went wrong.")

    # ---- RPC methods ---------------------------------------------------

    def rpc_config(self, _p):
        return {
            "ok": True, "gifts": GIFTS, "pooch": POOCH,
            "prizeColors": PRIZE_COLORS, "poochColors": list(POOCH_COLORS),
        }

    def rpc_register(self, p):
        first = " ".join(str(p.get("first", "")).split())[:60]
        last = " ".join(str(p.get("last", "")).split())[:60]
        phone_raw = str(p.get("phone", "")).strip()
        invoice_raw = digits_only(p.get("invoice", ""))

        if not (first and last and phone_raw and invoice_raw):
            return _fail("Please fill in all fields.")

        phone = normalize_phone(phone_raw)
        if phone is None:
            return _fail("Invalid mobile number (e.g. 09123456789).")

        invoice = int(invoice_raw) if len(invoice_raw) <= 12 else 0
        if not 0 < invoice < 10 ** 12:
            return _fail("Invoice number must be a positive integer.")

        try:
            row = self.db.register_invoice(first, last, phone, invoice)
        except ValueError as exc:
            return _fail(str(exc))

        if row["lottery_check"] == 1:
            return _fail(
                f"Invoice already used (result: {row['prize'] or POOCH}). "
                "Enter a new invoice number."
            )
        return {"ok": True, "name": first, "invoice": invoice}

    def rpc_spin(self, p):
        invoice = int(digits_only(p.get("invoice", "")) or 0)
        row = self.db.get_invoice(invoice)
        if row is None or row["lottery_check"] == 1:
            return _fail("This invoice has already been used.")

        index = _rng.randrange(len(GIFTS))
        prize = GIFTS[index]
        if not self.db.mark_as_played(invoice, prize):
            return _fail("This invoice has already been used.")
        return {"ok": True, "index": index, "prize": prize}

    def rpc_exit(self, _p):
        return {"ok": True}
