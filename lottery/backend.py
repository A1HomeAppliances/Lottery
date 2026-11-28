"""
Application logic shared by the Android WebView bridge and the desktop dev
server. No Kivy imports here, so it is easy to test.

The web UI calls it as  backend.handle(method, params) -> dict.
"""
import logging
import random
import re
import sqlite3
import threading
import hashlib
import secrets
import time

from core.config import POOCH
from core.database import LotteryDatabase
from core.utils import digits_only, normalize_phone
from core.wheel import DEFAULT_POOCH_COLORS, build_arrangement
from dbmanagement import dbconnect, queries

log = logging.getLogger("a1.backend")
_rng = random.SystemRandom()

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


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

        # Wheel cache — rebuilt on startup and after any admin change.
        self._wheel_cache = None
        self._reload_wheel_cache()

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

    # ---- Wheel cache ----------------------------------------------------

    def _reload_wheel_cache(self):
        items = self.db.get_wheel_items()

        gifts = build_arrangement(items)
        if gifts is None:
            log.warning("Wheel arrangement infeasible; falling back to naive order.")
            gifts = []
            for item in items:
                if item["count"] > 0:
                    gifts.extend([item["name"]] * item["count"])

        prize_colors = {
            i["name"]: i["color"]
            for i in items
            if not i["is_pooch"] and i.get("color")
        }

        pooch_row = next((i for i in items if i["is_pooch"]), None)
        if pooch_row and pooch_row.get("color"):
            pooch_colors = [
                pooch_row["color"],
                pooch_row.get("color2") or DEFAULT_POOCH_COLORS[1],
            ]
        else:
            pooch_colors = list(DEFAULT_POOCH_COLORS)

        self._wheel_cache = {
            "gifts": gifts,
            "prize_colors": prize_colors,
            "pooch_colors": pooch_colors,
            "items": items,
        }

    def _valid_prize_names(self):
        return {item["name"] for item in self._wheel_cache["items"]}

    # ---- User RPC methods -----------------------------------------------

    def rpc_config(self, _p):
        cache = self._wheel_cache
        return {
            "ok": True,
            "gifts": cache["gifts"],
            "pooch": POOCH,
            "prizeColors": cache["prize_colors"],
            "poochColors": cache["pooch_colors"],
        }

    def rpc_register(self, p):
        invoice, err = self._parse_invoice(p.get("invoice", ""))
        if err:
            return err

        data, err = self._validate_user_fields(p)
        if err:
            return err

        try:
            row = self.db.register_invoice(
                data["first"], data["last"], data["phone"], invoice
            )
        except ValueError as exc:
            return _fail(str(exc))

        if row["lottery_check"] == 1:
            return _fail(
                f"این فاکتور قبلاً استفاده شده است (نتیجه: {row['prize'] or POOCH}). "
                "شمارهٔ فاکتور جدیدی وارد کنید."
            )
        return {"ok": True, "name": f"{data['first']} {data['last']}", "invoice": invoice}

    def rpc_spin(self, p):
        invoice = int(digits_only(p.get("invoice", "")) or 0)
        row = self.db.get_invoice(invoice)
        if row is None or row["lottery_check"] == 1:
            return _fail("این فاکتور قبلاً استفاده شده است.")

        gifts = self._wheel_cache["gifts"]
        if not gifts:
            return _fail("گردونه هنوز تنظیم نشده است.")

        index = _rng.randrange(len(gifts))
        prize = gifts[index]
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
            del self._lockout_until[ip]
            self._login_attempts[ip] = 0
        return False

    def _record_failed_attempt(self, ip="local"):
        self._login_attempts[ip] = self._login_attempts.get(ip, 0) + 1
        if self._login_attempts[ip] >= 5:
            self._lockout_until[ip] = time.time() + 300
            return True
        return False

    def _check_auth(self, p):
        token = p.get("token")
        return token in self._admin_sessions

    # ---- Shared validation helpers --------------------------------------

    def _parse_invoice(self, raw):
        invoice_raw = digits_only(raw)
        if not invoice_raw:
            return None, _fail("شمارهٔ فاکتور را وارد کنید.")
        invoice = int(invoice_raw) if len(invoice_raw) <= 12 else 0
        if not 0 < invoice < 10 ** 12:
            return None, _fail("شمارهٔ فاکتور باید یک عدد صحیح مثبت باشد.")
        return invoice, None

    def _validate_user_fields(self, p):
        first = " ".join(str(p.get("first", "")).split())[:60]
        last = " ".join(str(p.get("last", "")).split())[:60]
        phone_raw = str(p.get("phone", "")).strip()

        if not (first and last and phone_raw):
            return None, _fail("لطفاً نام، نام خانوادگی و شمارهٔ موبایل را وارد کنید.")

        phone = normalize_phone(phone_raw)
        if phone is None:
            return None, _fail("شمارهٔ موبایل نامعتبر است (نمونه: 09123456789).")

        return {"first": first, "last": last, "phone": phone}, None

    def _validate_status_prize(self, p, existing_played_at=None, existing_prize=None):
        prize = str(p.get("prize", POOCH))
        # Accept the prize if it is a valid current gift, OR it matches the
        # user's stored prize (handles renaming/deleting gifts safely).
        if prize not in self._valid_prize_names() and prize != existing_prize:
            return None, _fail("جایزهٔ انتخاب‌شده معتبر نیست.")

        try:
            played = int(p.get("played", 0))
            if played not in (0, 1):
                raise ValueError
        except (TypeError, ValueError):
            return None, _fail("وضعیت بازی نامعتبر است.")

        played_at = p.get("played_at")
        if played:
            if played_at:
                played_at = str(played_at)[:30]
            elif existing_played_at:
                played_at = existing_played_at
            else:
                played_at = time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            played_at = None

        return {"prize": prize, "played": played, "played_at": played_at}, None

    def _validate_wheel_item(self, p):
        name = " ".join(str(p.get("name", "")).split())[:40]
        if not name:
            return None, _fail("نام جایزه را وارد کنید.")
        if name == POOCH:
            return None, _fail("نام «پوچ» رزرو شده است.")

        try:
            count = int(p.get("count", 1))
        except (TypeError, ValueError):
            return None, _fail("تعداد باید یک عدد صحیح باشد.")
        if not 1 <= count <= 100:
            return None, _fail("تعداد باید بین ۱ تا ۱۰۰ باشد.")

        color = str(p.get("color", "")).strip()
        if not _HEX_COLOR_RE.match(color):
            return None, _fail("رنگ باید در قالب #RRGGBB باشد.")

        return {"name": name, "count": count, "color": color}, None

    def _wheel_is_feasible(self, items):
        """True if the given list of items can be arranged on the wheel."""
        counts = {i["name"]: i["count"] for i in items if i["count"] > 0}
        if not counts:
            return False
        total = sum(counts.values())
        return max(counts.values()) * 2 <= total

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

    # ---- Admin CRUD — users ---------------------------------------------

    def rpc_admin_create_user(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")

        invoice, err = self._parse_invoice(p.get("invoice", ""))
        if err:
            return err

        data, err = self._validate_user_fields(p)
        if err:
            return err

        status, err = self._validate_status_prize(p)
        if err:
            return err

        ok = queries.create_user(
            invoice,
            data["first"], data["last"], data["phone"],
            prize=status["prize"],
            lottery_check=status["played"],
            played_at=status["played_at"],
        )
        if not ok:
            return _fail("ثبت کاربر ممکن نشد. احتمالاً شمارهٔ فاکتور تکراری است.")
        return {"ok": True}

    def rpc_admin_update_user(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")

        invoice, err = self._parse_invoice(p.get("invoice", ""))
        if err:
            return err

        existing = self.db.get_invoice(invoice)
        if existing is None:
            return _fail("کاربر مورد نظر یافت نشد.")

        data, err = self._validate_user_fields(p)
        if err:
            return err

        status, err = self._validate_status_prize(
            p,
            existing_played_at=existing["played_at"] if existing["lottery_check"] == 1 else None,
            existing_prize=existing["prize"],
        )
        if err:
            return err

        ok = queries.edit_user(
            invoice,
            data["first"], data["last"], data["phone"],
            status["played"], status["prize"], status["played_at"],
        )
        if not ok:
            return _fail("ویرایش کاربر ممکن نشد.")
        return {"ok": True}

    def rpc_admin_delete_user(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")

        invoice, err = self._parse_invoice(p.get("invoice", ""))
        if err:
            return err

        ok = queries.delete_factor(invoice)
        if not ok:
            return _fail("کاربر مورد نظر یافت نشد.")
        return {"ok": True}

    # ---- Admin CRUD — wheel items ---------------------------------------

    def rpc_admin_list_wheel(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")
        return {"ok": True, "items": self._wheel_cache["items"], "pooch": POOCH}

    def rpc_admin_create_wheel_item(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")

        data, err = self._validate_wheel_item(p)
        if err:
            return err

        proposed = self._wheel_cache["items"] + [{
            "name": data["name"], "count": data["count"], "is_pooch": 0,
        }]
        if not self._wheel_is_feasible(proposed):
            return _fail(
                "چیدمان این مقادیر ممکن نیست. تعداد هیچ جایزه‌ای نباید "
                "از نصف کل بخش‌های گردونه بیشتر باشد."
            )

        try:
            self.db.add_wheel_item(data["name"], data["count"], data["color"])
        except sqlite3.IntegrityError:
            return _fail("نام این جایزه قبلاً استفاده شده است.")

        self._reload_wheel_cache()
        return {"ok": True}

    def rpc_admin_update_wheel_item(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")

        try:
            item_id = int(p.get("id", 0))
        except (TypeError, ValueError):
            return _fail("شناسهٔ جایزه نامعتبر است.")

        current = next(
            (i for i in self._wheel_cache["items"] if i["id"] == item_id), None
        )
        if current is None:
            return _fail("جایزه یافت نشد.")

        is_pooch = bool(current["is_pooch"])

        if is_pooch:
            # Pooch: name is fixed, only count + colours can change.
            try:
                count = int(p.get("count", current["count"]))
            except (TypeError, ValueError):
                return _fail("تعداد باید یک عدد صحیح باشد.")
            if not 1 <= count <= 100:
                return _fail("تعداد باید بین ۱ تا ۱۰۰ باشد.")

            color = str(p.get("color", current.get("color") or DEFAULT_POOCH_COLORS[0])).strip()
            color2 = str(p.get("color2", current.get("color2") or DEFAULT_POOCH_COLORS[1])).strip()
            if not _HEX_COLOR_RE.match(color):
                return _fail("رنگ اول باید در قالب #RRGGBB باشد.")
            if not _HEX_COLOR_RE.match(color2):
                return _fail("رنگ دوم باید در قالب #RRGGBB باشد.")

            updated = {**current, "count": count, "color": color, "color2": color2}
            proposed = [updated if i["id"] == item_id else i
                        for i in self._wheel_cache["items"]]
            if not self._wheel_is_feasible(proposed):
                return _fail(
                    "این تغییر چیدمان گردونه را ناممکن می‌کند. تعداد «پوچ» نباید "
                    "از نصف کل بخش‌ها بیشتر باشد."
                )
            self.db.update_wheel_item(
                item_id, count=count, color=color, color2=color2
            )
        else:
            data, err = self._validate_wheel_item(p)
            if err:
                return err

            updated = {**current, **data}
            proposed = [updated if i["id"] == item_id else i
                        for i in self._wheel_cache["items"]]
            if not self._wheel_is_feasible(proposed):
                return _fail(
                    "این تغییر چیدمان گردونه را ناممکن می‌کند. تعداد هیچ جایزه‌ای "
                    "نباید از نصف کل بخش‌ها بیشتر باشد."
                )
            try:
                self.db.update_wheel_item(
                    item_id, name=data["name"],
                    count=data["count"], color=data["color"],
                )
            except sqlite3.IntegrityError:
                return _fail("نام این جایزه قبلاً استفاده شده است.")

        self._reload_wheel_cache()
        return {"ok": True}

    def rpc_admin_delete_wheel_item(self, p):
        if not self._check_auth(p):
            return _fail("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.")

        try:
            item_id = int(p.get("id", 0))
        except (TypeError, ValueError):
            return _fail("شناسهٔ جایزه نامعتبر است.")

        target = next(
            (i for i in self._wheel_cache["items"] if i["id"] == item_id), None
        )
        if target is None:
            return _fail("جایزه یافت نشد.")
        if target["is_pooch"]:
            return _fail("جایزهٔ «پوچ» قابل حذف نیست.")

        remaining = [i for i in self._wheel_cache["items"] if i["id"] != item_id]
        if not self._wheel_is_feasible(remaining):
            return _fail(
                "حذف این جایزه چیدمان گردونه را ناممکن می‌کند. ابتدا جایزهٔ "
                "دیگری اضافه کنید یا تعداد جوایز موجود را افزایش دهید."
            )

        if not self.db.delete_wheel_item(item_id):
            return _fail("حذف جایزه ممکن نشد.")

        self._reload_wheel_cache()
        return {"ok": True}
