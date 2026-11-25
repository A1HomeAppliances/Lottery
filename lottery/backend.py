"""
Application logic shared by the Android WebView bridge and the desktop dev
server. No Kivy imports here, so it is easy to test.

The web UI calls it as  backend.handle(method, params) -> dict.
"""
import logging
import random
import sqlite3
import threading
import hashlib
import secrets
import time

from core.config import GIFTS, POOCH, POOCH_COLORS, PRIZE_COLORS
from core.database import LotteryDatabase
from core.utils import digits_only, normalize_phone
from dbmanagement import dbconnect, queries

log = logging.getLogger("a1.backend")
_rng = random.SystemRandom()          # unpredictable result for a real lottery


def _fail(message):
    return {"ok": False, "error": message}


class Backend:

    PER_PAGE = 10

    def __init__(self, database_path):
        dbconnect.configure(database_path)
        self.db = LotteryDatabase(database_path)
        self._lock = threading.Lock()

        # Admin Security Variables
        self._admin_sessions = set()
        self._login_attempts = {}
        self._lockout_until = {}

    def close(self):
        self.db.close()

    def handle(self, method, params):
        fn = getattr(self, f"rpc_{method}", None) \
            if isinstance(method, str) and method.isidentifier() else None
        if fn is None or not callable(fn):
            return _fail("درخواست نامعتبر است.")
        try:
            with self._lock:
                return fn(params if isinstance(params, dict) else {})
        except sqlite3.Error:
            log.exception("database error")
            return _fail("خطا در پایگاه داده.")
        except Exception:
            log.exception("unexpected error")
            return _fail("مشکلی پیش آمد.")

    # ---- User RPC methods -----------------------------------------------

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
            return _fail("لطفاً همهٔ فیلدها را پر کنید.")

        phone = normalize_phone(phone_raw)
        if phone is None:
            return _fail("شمارهٔ موبایل نامعتبر است (نمونه: 09123456789).")

        invoice = int(invoice_raw) if len(invoice_raw) <= 12 else 0
        if not 0 < invoice < 10 ** 12:
            return _fail("شمارهٔ فاکتور باید یک عدد صحیح مثبت باشد.")

        try:
            row = self.db.register_invoice(first, last, phone, invoice)
        except ValueError as exc:
            return _fail(str(exc))

        if row["lottery_check"] == 1:
            return _fail(
                f"این فاکتور قبلاً استفاده شده است (نتیجه: {row['prize'] or POOCH}). "
                "شمارهٔ فاکتور جدیدی وارد کنید."
            )
        # نام کامل برگردانده می‌شود تا در UI درست نمایش داده شود
        return {"ok": True, "name": f"{first} {last}", "invoice": invoice}

    def rpc_spin(self, p):
        invoice = int(digits_only(p.get("invoice", "")) or 0)
        row = self.db.get_invoice(invoice)
        if row is None or row["lottery_check"] == 1:
            return _fail("این فاکتور قبلاً استفاده شده است.")

        index = _rng.randrange(len(GIFTS))
        prize = GIFTS[index]
        if not self.db.mark_as_played(invoice, prize):
            return _fail("این فاکتور قبلاً استفاده شده است.")
        return {"ok": True, "index": index, "prize": prize}

    def rpc_exit(self, _p):
        return {"ok": True}

    # ---- Admin Security & Helpers ---------------------------------------

    def _hash_password(self, password, salt=None):
        if salt is None:
            salt = secrets.token_bytes(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return salt.hex() + ":" + pwd_hash.hex()

    def _verify_password(self, password, stored):
        salt_hex, hash_hex = stored.split(':')
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return secrets.compare_digest(expected.hex(), hash_hex)

    def _is_admin_locked(self, ip="local"):
        if ip in self._lockout_until:
            if time.time() < self._lockout_until[ip]:
                return True
            else:
                del self._lockout_until[ip]
                self._login_attempts[ip] = 0
        return False

    def _record_failed_attempt(self, ip="local"):
        self._login_attempts[ip] = self._login_attempts.get(ip, 0) + 1
        if self._login_attempts[ip] >= 5:  # Lock after 5 fails
            self._lockout_until[ip] = time.time() + 300  # Lock for 5 minutes
            return True
        return False

    def _check_auth(self, p):
        token = p.get("token")
        return token in self._admin_sessions

    # ---- Admin RPC methods ----------------------------------------------

    def rpc_admin_status(self, _p):
        setup_done = self.db.get_admin_config("admin_pass") is not None
        return {"ok": True, "initialized": setup_done}

    def rpc_admin_setup(self, p):
        if self.db.get_admin_config("admin_pass") is not None:
            return _fail("مدیر قبلاً تنظیم شده است.")

        username = str(p.get("username", "")).strip()
        password = str(p.get("password", ""))

        if len(username) < 4 or len(password) < 8:
            return _fail("نام کاربری حداقل ۴ و رمز عبور حداقل ۸ کاراکتر باشد.")

        hashed = self._hash_password(password)
        self.db.set_admin_config("admin_user", username)
        self.db.set_admin_config("admin_pass", hashed)
        return {"ok": True}

    def rpc_admin_login(self, p):
        if self._is_admin_locked():
            return _fail("تلاش‌های ناموفق زیاد. لطفاً ۵ دقیقه دیگر تلاش کنید.")

        username = str(p.get("username", "")).strip()
        password = str(p.get("password", ""))

        stored_user = self.db.get_admin_config("admin_user")
        stored_pass = self.db.get_admin_config("admin_pass")

        if not stored_user or not stored_pass:
            return _fail("پنل مدیریت هنوز راه‌اندازی نشده است.")

        if username == stored_user and self._verify_password(password, stored_pass):
            self._login_attempts["local"] = 0
            token = secrets.token_hex(32)
            self._admin_sessions.add(token)
            return {"ok": True, "token": token}
        else:
            locked = self._record_failed_attempt()
            if locked:
                return _fail("رمز عبور اشتباه است. حساب شما به مدت ۵ دقیقه قفل شد.")
            return _fail("نام کاربری یا رمز عبور اشتباه است.")

    def rpc_admin_logout(self, p):
        token = p.get("token")
        if token in self._admin_sessions:
            self._admin_sessions.remove(token)
        return {"ok": True}

    def rpc_admin_dashboard(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")

        try:
            page = int(p.get("page", 1))
        except (TypeError, ValueError):
            page = 1
        search = str(p.get("search", ""))[:60]

        users, total, page = queries.get_users_paginated(search, page, self.PER_PAGE)
        return {
            "ok": True,
            "stats": queries.get_stats(),
            "prizes": queries.get_prize_breakdown(),
            "users": users,
            "total": total,
            "page": page,
            "per_page": self.PER_PAGE,
        }
