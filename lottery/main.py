"""
Lucky Spin - A1 Customer Lottery
Single-file Kivy application.

Requirements:
    pip install kivy

Run:
    python3 main.py
"""

# ---------------------------------------------------------------------------
# KIVY CONFIGURATION (MUST BE BEFORE OTHER KIVY IMPORTS)
# Fixes the "/dev/input/event5" permission error that breaks typing.
# ---------------------------------------------------------------------------
from kivy.config import Config
# Disable the problematic touchpad/mouse provider
Config.set('input', 'mouse', 'mouse,disable_multitouch')

import math
import random
import re
import sqlite3
from pathlib import Path

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import (
    Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate,
    RoundedRectangle, Triangle,
)
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex, platform


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

APP_TITLE = "A1 Lucky Spin"
DATABASE_PATH = Path(__file__).resolve().with_name("lottery.db")

POOCH = "pooch"  # formerly "پوچ"

GIFTS = [
    "Crystal", "Pooch", "Chini", "Pooch", "Bloor", "Tablo Farsh",
    "Sekke Tala", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Crystal",
    "Tablo Farsh", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Pooch",
    "Crystal", "Pooch", "Chini", "Pooch", "Bloor", "Tablo Farsh",
    "Sekke Tala", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Crystal",
    "Tablo Farsh", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Pooch",
]
GOLD = get_color_from_hex("#F4C95D")
GOLD_LIGHT = get_color_from_hex("#FFE7A3")
BACKGROUND = get_color_from_hex("#0E0F1A")
PANEL = get_color_from_hex("#1A1C2B")
PANEL_LIGHT = get_color_from_hex("#262A3D")
TEXT = get_color_from_hex("#F5F2EA")
MUTED = get_color_from_hex("#A9A8B8")
RED = get_color_from_hex("#EF6F72")

PRIZE_COLORS = {
    "crystal": "#29B6F6",
    "chini": "#AB47BC",
    "bloor": "#26A69A",
    "gold coin": "#FFC107",
    "wall clock": "#EF5350",
    "carpet frame": "#7CB342",
}
POOCH_COLORS = ("#2E3354", "#232844")


def sector_color(index):
    prize = GIFTS[index]
    if prize == POOCH:
        return get_color_from_hex(POOCH_COLORS[(index // 2) % 2])
    return get_color_from_hex(PRIZE_COLORS[prize])


def text_color_for(rgba):
    luminance = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
    return (0.08, 0.08, 0.10, 1) if luminance > 0.55 else (1, 1, 1, 1)


# ---------------------------------------------------------------------------
# Phone / digit helpers
# ---------------------------------------------------------------------------

_DIGIT_TABLE = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def digits_only(substring, from_undo=False):
    return re.sub(r"\D", "", substring.translate(_DIGIT_TABLE))


def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw.translate(_DIGIT_TABLE))
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits if re.fullmatch(r"09\d{9}", digits) else None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

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
            prize TEXT NOT NULL DEFAULT 'pooch',
            played_at TEXT
        )
    """

    def __init__(self, database_path):
        self.connection = sqlite3.connect(str(database_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(self.SCHEMA.format(name="lottery"))
        self._add_missing_columns()
        if self._username_is_unique():
            self._rebuild_table()
        self.connection.commit()

    def _add_missing_columns(self):
        existing = {row["name"] for row in self.connection.execute("PRAGMA table_info(lottery)")}
        for column, kind in self.EXTRA_COLUMNS.items():
            if column not in existing:
                self.connection.execute(f"ALTER TABLE lottery ADD COLUMN {column} {kind}")

    def _username_is_unique(self):
        for index in self.connection.execute("PRAGMA index_list(lottery)"):
            if index["unique"]:
                columns = [row["name"] for row in self.connection.execute(f'PRAGMA index_info("{index["name"]}")')]
                if columns == ["username"]:
                    return True
        return False

    def _rebuild_table(self):
        connection = self.connection
        connection.execute("DROP TABLE IF EXISTS lottery_new")
        connection.execute(self.SCHEMA.format(name="lottery_new"))
        with connection:
            connection.execute("""
                INSERT INTO lottery_new
                    (factorID, username, first_name, last_name, phone, lottery_check, prize, played_at)
                SELECT factorID, username, first_name, last_name, phone,
                       COALESCE(lottery_check, 0), COALESCE(prize, 'pooch'), played_at
                FROM lottery
            """)
            connection.execute("DROP TABLE lottery")
            connection.execute("ALTER TABLE lottery_new RENAME TO lottery")

    def get_invoice(self, factor_id):
        return self.connection.execute(
            "SELECT factorID, username, first_name, last_name, phone, lottery_check, prize FROM lottery WHERE factorID = ?",
            (factor_id,),
        ).fetchone()

    def register_invoice(self, first_name, last_name, phone, factor_id):
        row = self.get_invoice(factor_id)
        if row is None:
            self.connection.execute(
                "INSERT INTO lottery (factorID, username, first_name, last_name, phone, lottery_check, prize) VALUES (?, ?, ?, ?, ?, 0, 'pooch')",
                (factor_id, f"{first_name} {last_name}", first_name, last_name, phone),
            )
        elif not row["phone"]:
            self.connection.execute(
                "UPDATE lottery SET username = ?, first_name = ?, last_name = ?, phone = ? WHERE factorID = ?",
                (f"{first_name} {last_name}", first_name, last_name, phone, factor_id),
            )
        elif row["phone"] != phone:
            raise ValueError("This invoice number is already registered to another customer.")
        self.connection.commit()
        return self.get_invoice(factor_id)

    def mark_as_played(self, factor_id, prize):
        cursor = self.connection.execute(
            "UPDATE lottery SET prize = ?, lottery_check = 1, played_at = datetime('now', 'localtime') WHERE factorID = ? AND lottery_check = 0",
            (prize, factor_id),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def close(self):
        self.connection.close()


# ---------------------------------------------------------------------------
# UI Helpers
# ---------------------------------------------------------------------------

def make_label(text, size=18, color=TEXT, bold=False, halign="center", height=None):
    label = Label(
        text=text, color=color, font_size=dp(size), bold=bold,
        halign=halign, valign="middle", size_hint_y=None,
        height=dp(height if height else max(34, size * 2.0)),
    )
    label.bind(size=lambda inst, value: setattr(inst, "text_size", value))
    return label


class RoundedPanel(BoxLayout):
    def __init__(self, fill=PANEL, border=None, radius=20, **kwargs):
        super().__init__(**kwargs)
        self.radius = dp(radius)
        with self.canvas.before:
            self._fill_color = Color(*fill)
            self._fill = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self._border_color = Color(*(border or (0, 0, 0, 0)))
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self.radius), width=dp(1.3))
        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._fill.pos = self.pos
        self._fill.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, self.radius)

    def set_border(self, rgba):
        self._border_color.rgba = rgba


class RoundedButton(Button):
    def __init__(self, base_color=GOLD, foreground=BACKGROUND, radius=16, **kwargs):
        super().__init__(
            background_normal="", background_down="", background_disabled_normal="",
            background_color=(0, 0, 0, 0), color=foreground,
            disabled_color=(foreground[0], foreground[1], foreground[2], 0.6),
            bold=True, **kwargs,
        )
        self.base_color = base_color
        with self.canvas.before:
            self._color = Color(*base_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._update, size=self._update, state=self._refresh, disabled=self._refresh)

    def _update(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _refresh(self, *_):
        base = self.base_color
        if self.disabled:
            self._color.rgba = (base[0], base[1], base[2], 0.35)
        elif self.state == "down":
            self._color.rgba = (base[0] * 0.82, base[1] * 0.82, base[2] * 0.82, 1)
        else:
            self._color.rgba = base


def make_button(text, callback, background=GOLD, foreground=BACKGROUND, height=54, font_size=17):
    button = RoundedButton(
        text=text, base_color=background, foreground=foreground,
        size_hint_y=None, height=dp(height), font_size=dp(font_size),
    )
    button.bind(on_release=callback)
    return button


class StyledInput(TextInput):
    """Simplest possible form, no canvas.before so typing works 100%"""
    def __init__(self, hint, **kwargs):
        super().__init__(
            hint_text=hint,
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            height=dp(56),
            font_size=dp(16),
            foreground_color=TEXT,
            hint_text_color=(MUTED[0], MUTED[1], MUTED[2], 0.75),
            cursor_color=GOLD,
            cursor_width=dp(1.6),
            selection_color=(GOLD[0], GOLD[1], GOLD[2], 0.35),
            background_normal="",
            background_active="",
            background_disabled_normal="",
            # Dark gray background via Kivy itself
            background_color=(0.15, 0.16, 0.23, 1),
            **kwargs,
        )

class BaseScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*BACKGROUND)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(0.50, 0.30, 0.95, 0.11)
            self._glow_a = Ellipse()
            Color(GOLD[0], GOLD[1], GOLD[2], 0.07)
            self._glow_b = Ellipse()
        self.bind(pos=self._layout_background, size=self._layout_background)

    def _layout_background(self, *_):
        x, y = self.pos
        w, h = self.size
        big = max(w, h) * 0.9
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._glow_a.pos = (x - big * 0.35, y + h - big * 0.55)
        self._glow_a.size = (big, big)
        self._glow_b.pos = (x + w - big * 0.6, y - big * 0.4)
        self._glow_b.size = (big, big)


# ---------------------------------------------------------------------------
# Wheel + pointer
# ---------------------------------------------------------------------------

class WheelWidget(Widget):
    angle = NumericProperty(0)
    _rotation = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._textures = {}
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def on_angle(self, _instance, value):
        if self._rotation is not None:
            self._rotation.angle = value

    def _texture(self, text, font_size):
        key = (text, round(font_size, 1))
        if key not in self._textures:
            label = CoreLabel(text=text, font_size=font_size, bold=True)
            label.refresh()
            self._textures[key] = label.texture
        return self._textures[key]

    def redraw(self, *_):
        self.canvas.clear()
        if len(self._textures) > 60:
            self._textures.clear()
        if self.width <= 0 or self.height <= 0:
            return

        cx, cy = self.center
        outer = min(self.width, self.height) / 2 - dp(2)
        rim = dp(13)
        radius = outer - rim
        count = len(GIFTS)
        step = 360.0 / count
        font_size = max(dp(8), radius * 0.062)

        with self.canvas:
            Color(GOLD[0], GOLD[1], GOLD[2], 0.13)
            glow = outer + dp(10)
            Ellipse(pos=(cx - glow, cy - glow), size=(glow * 2, glow * 2))

            PushMatrix()
            self._rotation = Rotate(angle=self.angle, origin=(cx, cy))

            Color(*GOLD)
            Ellipse(pos=(cx - outer, cy - outer), size=(outer * 2, outer * 2))
            Color(0.09, 0.09, 0.14, 1)
            inner_rim = outer - dp(3)
            Ellipse(pos=(cx - inner_rim, cy - inner_rim), size=(inner_rim * 2, inner_rim * 2))

            for i in range(count):
                Color(*sector_color(i))
                Ellipse(
                    pos=(cx - radius, cy - radius), size=(radius * 2, radius * 2),
                    angle_start=i * step, angle_end=(i + 1) * step, segments=12,
                )

            Color(1, 1, 1, 0.28)
            for i in range(count):
                a = math.radians(90 - i * step)
                Line(points=[cx, cy, cx + radius * math.cos(a), cy + radius * math.sin(a)], width=dp(0.9))

            for i, prize in enumerate(GIFTS):
                texture = self._texture(prize, font_size)
                if texture is None:
                    continue
                color = sector_color(i)
                theta = math.radians(90 - (i + 0.5) * step)
                tx = cx + radius * 0.66 * math.cos(theta)
                ty = cy + radius * 0.66 * math.sin(theta)
                w, h = texture.size

                PushMatrix()
                Rotate(angle=math.degrees(theta), origin=(tx, ty))
                tc = text_color_for(color)
                alpha = 0.6 if prize == POOCH else 1
                Color(tc[0], tc[1], tc[2], alpha)
                Rectangle(texture=texture, pos=(tx - w / 2, ty - h / 2), size=(w, h))
                PopMatrix()

            Color(*GOLD)
            Line(circle=(cx, cy, radius), width=dp(2.5))

            bulb_radius = outer - rim / 2 - dp(1)
            bulb = dp(6.4)
            for i in range(count):
                a = math.radians(90 - i * step)
                bx = cx + bulb_radius * math.cos(a)
                by = cy + bulb_radius * math.sin(a)
                Color(*(GOLD_LIGHT if i % 2 == 0 else (1, 1, 1, 1)))
                Ellipse(pos=(bx - bulb / 2, by - bulb / 2), size=(bulb, bulb))

            PopMatrix()

            Color(0, 0, 0, 0.35)
            Ellipse(pos=(cx - dp(36), cy - dp(38)), size=(dp(72), dp(72)))
            Color(*GOLD)
            Ellipse(pos=(cx - dp(32), cy - dp(32)), size=(dp(64), dp(64)))
            Color(0.07, 0.08, 0.12, 1)
            Ellipse(pos=(cx - dp(26), cy - dp(26)), size=(dp(52), dp(52)))

            hub_texture = self._texture("A1", dp(20))
            if hub_texture is not None:
                hw, hh = hub_texture.size
                Color(*GOLD_LIGHT)
                Rectangle(texture=hub_texture, pos=(cx - hw / 2, cy - hh / 2), size=(hw, hh))


class PointerWidget(Widget):
    angle = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.wobble_animation = None
        self.settle_animation = None
        self.bind(pos=self.redraw, size=self.redraw, angle=self.redraw)
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        pivot_x = self.center_x
        pivot_y = self.top - dp(12)
        half = dp(15)
        tip = dp(46)

        with self.canvas:
            PushMatrix()
            Rotate(angle=self.angle, origin=(pivot_x, pivot_y))

            Color(0, 0, 0, 0.35)
            Triangle(points=[
                pivot_x - half + dp(2), pivot_y - dp(2),
                pivot_x + half + dp(2), pivot_y - dp(2),
                pivot_x + dp(2), pivot_y - tip - dp(2),
            ])

            Color(*RED)
            Triangle(points=[
                pivot_x - half, pivot_y,
                pivot_x + half, pivot_y,
                pivot_x, pivot_y - tip,
            ])
            Color(*GOLD_LIGHT)
            Line(points=[pivot_x - half, pivot_y, pivot_x, pivot_y - tip, pivot_x + half, pivot_y], width=dp(1.4))

            Color(*GOLD)
            Ellipse(pos=(pivot_x - dp(9), pivot_y - dp(9)), size=(dp(18), dp(18)))
            Color(0.07, 0.08, 0.12, 1)
            Ellipse(pos=(pivot_x - dp(4), pivot_y - dp(4)), size=(dp(8), dp(8)))
            PopMatrix()

    def start_wobble(self):
        self.stop_animations()
        sequence = (
            Animation(angle=13, duration=0.075, t="out_quad") +
            Animation(angle=-13, duration=0.075, t="out_quad") +
            Animation(angle=9, duration=0.075, t="out_quad") +
            Animation(angle=-9, duration=0.075, t="out_quad")
        )
        sequence.repeat = True
        self.wobble_animation = sequence
        sequence.start(self)

    def settle(self):
        self.stop_animations()
        animation = (
            Animation(angle=-17, duration=0.12, t="out_quad") +
            Animation(angle=9, duration=0.12, t="out_quad") +
            Animation(angle=-4, duration=0.14, t="out_quad") +
            Animation(angle=0, duration=0.18, t="out_back")
        )
        self.settle_animation = animation
        animation.start(self)

    def stop_animations(self):
        if self.wobble_animation:
            self.wobble_animation.cancel(self)
            self.wobble_animation = None
        if self.settle_animation:
            self.settle_animation.cancel(self)
            self.settle_animation = None


# ---------------------------------------------------------------------------
# Login screen
# ---------------------------------------------------------------------------

class LoginScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app

        root = BoxLayout(
            orientation="vertical", padding=[dp(26), dp(28), dp(26), dp(24)], spacing=dp(14),
        )

        root.add_widget(Widget(size_hint_y=0.55))
        root.add_widget(make_label("A1 Lucky Spin", 38, GOLD, True))
        root.add_widget(make_label("Customer Lottery", 13, MUTED, True))
        root.add_widget(Widget(size_hint_y=0.2))

        card = RoundedPanel(
            fill=PANEL, border=(GOLD[0], GOLD[1], GOLD[2], 0.35),
            orientation="vertical", size_hint_y=None, height=dp(320),
            padding=[dp(20), dp(20), dp(20), dp(20)], spacing=dp(12),
        )

        grid = GridLayout(cols=2, spacing=dp(12), size_hint_y=None, height=dp(124))

        self.first_input = StyledInput(hint="First Name")
        self.last_input = StyledInput(hint="Last Name")
        self.phone_input = StyledInput(hint="Mobile Number", input_filter=digits_only, input_type="tel")
        self.factor_input = StyledInput(hint="Invoice Number", input_filter=digits_only, input_type="number")

        grid.add_widget(self.first_input)
        grid.add_widget(self.last_input)
        grid.add_widget(self.phone_input)
        grid.add_widget(self.factor_input)
        card.add_widget(grid)

        self.error_label = make_label("", 13, RED, height=48)
        card.add_widget(self.error_label)

        card.add_widget(make_button("Login", self.login))
        root.add_widget(card)

        root.add_widget(Widget(size_hint_y=0.7))
        root.add_widget(make_label("Good luck!", 12, MUTED, True))

        self.add_widget(root)

        self._inputs = (self.first_input, self.last_input, self.phone_input, self.factor_input)
        # Ensure only one field is focused (gold) at a time
        for field in self._inputs:
            field.bind(focus=self._on_field_focus)

    def _on_field_focus(self, instance, focused):
        if focused:
            for other in self._inputs:
                if other is not instance and other.focus:
                    other.focus = False

    def login(self, *_):
        self.error_label.text = ""
        for field in self._inputs:
            field.focus = False

        first_name = " ".join(self.first_input.text.split())
        last_name = " ".join(self.last_input.text.split())
        phone_text = self.phone_input.text.strip()
        factor_text = self.factor_input.text.strip()

        if not (first_name and last_name and phone_text and factor_text):
            self.error_label.text = "Please fill in all fields."
            return

        phone = normalize_phone(phone_text)
        if phone is None:
            self.error_label.text = "Please enter a valid mobile number (e.g. 09123456789)."
            return

        try:
            factor_id = int(factor_text)
        except ValueError:
            factor_id = 0
        if not 0 < factor_id < 10 ** 12:
            self.error_label.text = "Invoice number must be a positive integer."
            return

        try:
            customer = self.app_ref.database.register_invoice(first_name, last_name, phone, factor_id)
        except ValueError as error:
            self.error_label.text = str(error)
            return
        except sqlite3.Error:
            self.error_label.text = "Database error. Please contact the system administrator."
            return

        if customer["lottery_check"] == 1:
            previous_prize = customer["prize"] or POOCH
            self.error_label.text = (
                f"This invoice has already been used (result: {previous_prize}). "
                f"Please enter a new invoice number to play again."
            )
            return

        wheel_screen = self.manager.get_screen("wheel")
        wheel_screen.prepare_customer(first_name, factor_id)

        self.manager.transition = FadeTransition(duration=0.55)
        self.manager.current = "wheel"

    def clear(self):
        for field in self._inputs:
            field.text = ""
            field.focus = False
        self.error_label.text = ""


# ---------------------------------------------------------------------------
# Wheel screen
# ---------------------------------------------------------------------------

class WheelScreen(BaseScreen):
    POINTER_EXTRA = 25

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app
        self.current_name = ""
        self.current_factor = 0
        self.is_spinning = False
        self.has_played = False
        self.selected_index = None

        root = BoxLayout(
            orientation="vertical", padding=[dp(20), dp(18), dp(20), dp(20)], spacing=dp(8),
        )

        self.welcome_label = make_label("Welcome", 21, GOLD, True)
        root.add_widget(self.welcome_label)
        root.add_widget(make_label("Developer: CAgent_47", 12, MUTED, True))

        self.wheel_area = FloatLayout(size_hint_y=1)

        self.wheel = WheelWidget(size_hint=(None, None), size=(dp(300), dp(300)))
        self.wheel_area.add_widget(self.wheel)

        self.pointer = PointerWidget(size_hint=(None, None), size=(dp(56), dp(70)))
        self.wheel_area.add_widget(self.pointer)

        self.wheel_area.bind(pos=self.layout_board, size=self.layout_board)
        root.add_widget(self.wheel_area)

        self.status_label = make_label("", 14, MUTED)
        root.add_widget(self.status_label)

        self.spin_button = make_button("Spin!", self.spin_wheel, height=65, font_size=20)
        self.spin_button.size_hint_y = 0.1
        root.add_widget(self.spin_button)

        self.back_button = make_button(
            "Back", self.back_to_login,
            background=PANEL_LIGHT, foreground=TEXT, height=46, font_size=14,
        )
        root.add_widget(self.back_button)

        self.add_widget(root)

    def layout_board(self, *_):
        area = self.wheel_area
        extra = dp(self.POINTER_EXTRA)

        # Make the wheel larger (by reducing the pointer gap from available height)
        diameter = min(area.width - dp(10), area.height)
        diameter = max(diameter, dp(120))

        self.wheel.size = (diameter, diameter)

        # Move the wheel slightly up
        self.wheel.center = (area.center_x, area.center_y)

        # Exact top edge of the wheel so the triangle sits right on it
        rim_top = self.wheel.center_y + (diameter / 2) - dp(2)

        self.pointer.center_x = area.center_x
        # Align the pointer height relative to the wheel edge
        self.pointer.top = rim_top + dp(0)

    def prepare_customer(self, display_name, factor_id):
        self.current_name = display_name
        self.current_factor = factor_id
        self.is_spinning = False
        self.has_played = False
        self.selected_index = None
        self.welcome_label.text = f"Welcome, {display_name}"
        self.status_label.text = ""
        self.spin_button.disabled = False
        self.spin_button.text = "Spin!"
        self.wheel.angle = 0
        self.pointer.stop_animations()
        self.pointer.angle = 0

    def spin_wheel(self, *_):
        if self.is_spinning or self.has_played:
            return

        self.is_spinning = True
        self.spin_button.disabled = True
        self.spin_button.text = "Spinning..."
        self.status_label.text = ""

        self.selected_index = random.randrange(len(GIFTS))
        prize = GIFTS[self.selected_index]

        try:
            saved = self.app_ref.database.mark_as_played(self.current_factor, prize)
        except sqlite3.Error:
            saved = False

        if not saved:
            self.is_spinning = False
            self.spin_button.text = "Used"
            self.status_label.text = "This invoice has already been used."
            return

        self.has_played = True
        self.pointer.start_wobble()

        step = 360.0 / len(GIFTS)
        target = (self.selected_index + 0.5) * step
        target += random.uniform(-0.38, 0.38) * step

        current = self.wheel.angle
        delta = (current - target) % 360
        final_angle = current - delta - 360 * 6

        animation = Animation(angle=final_angle, duration=5.8, t="out_quart")
        animation.bind(on_complete=lambda *_: self.finish_spin(prize))
        animation.start(self.wheel)

    def finish_spin(self, prize):
        self.pointer.settle()
        self.status_label.text = "The wheel has stopped."
        Clock.schedule_once(lambda _dt: self.show_result(prize), 0.8)

    def show_result(self, prize):
        self.is_spinning = False
        self.spin_button.text = "Used"
        result_screen = self.manager.get_screen("result")
        result_screen.show_prize(self.current_name, prize)
        self.manager.transition = FadeTransition(duration=0.65)
        self.manager.current = "result"

    def back_to_login(self, *_):
        if self.is_spinning:
            return
        self.manager.get_screen("login").clear()
        self.manager.transition = FadeTransition(duration=0.4)
        self.manager.current = "login"


# ---------------------------------------------------------------------------
# Result screen + Confetti
# ---------------------------------------------------------------------------

class ConfettiParticle(Widget):
    def __init__(self, x, y, color, **kwargs):
        super().__init__(**kwargs)
        self.pos = (x, y)
        self.size = (dp(10), dp(15))
        self._color = color
        with self.canvas:
            Color(*self._color)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


class ResultScreen(BaseScreen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app
        self.confetti_widgets = []
        self.confetti_event = None

        root = BoxLayout(
            orientation="vertical", padding=[dp(28), dp(28), dp(28), dp(28)], spacing=dp(14),
        )

        root.add_widget(Widget(size_hint_y=0.4))

        self.title_label = make_label("CONGRATULATIONS!", 26, GOLD, True)
        root.add_widget(self.title_label)

        self.subtitle_label = make_label("", 15, MUTED)
        root.add_widget(self.subtitle_label)

        self.prize_panel = RoundedPanel(
            fill=PANEL, border=(1, 1, 1, 0.1),
            size_hint_y=None, height=dp(130),
            padding=[dp(12), dp(12), dp(12), dp(12)],
        )
        self.prize_label = make_label("", 31, GOLD_LIGHT, True)
        self.prize_label.size_hint_y = 1
        self.prize_panel.add_widget(self.prize_label)
        root.add_widget(self.prize_panel)

        self.message_label = make_label("", 15, TEXT, height=56)
        root.add_widget(self.message_label)

        root.add_widget(Widget(size_hint_y=0.3))

        self.again_button = make_button(
            "PLAY AGAIN WITH A NEW INVOICE", self.logout,
            height=58, font_size=16,
        )
        root.add_widget(self.again_button)

        root.add_widget(Widget(size_hint_y=0.35))
        self.add_widget(root)

    def show_prize(self, name, prize):
        self.prize_label.text = prize.upper()
        self.stop_confetti()  # پاک کردن کاغذهای قبلی

        if prize == POOCH:
            accent = (1, 1, 1, 0.18)
            self.title_label.text = "THANK YOU FOR PLAYING!"
            self.title_label.color = GOLD_LIGHT
            self.subtitle_label.text = f"{name}, today may not be your day..."
            self.message_label.text = "Every spin is a new memory. Thank you for being part of A1!"
            self.prize_label.color = MUTED
        else:
            prize_color = get_color_from_hex(PRIZE_COLORS[prize])
            accent = (prize_color[0], prize_color[1], prize_color[2], 1)
            self.title_label.text = "CONGRATULATIONS!"
            self.title_label.color = GOLD
            self.subtitle_label.text = f"{name}, you are a winner!"
            self.message_label.text = "Please contact the A1 team to claim your prize."
            self.prize_label.color = prize_color
            
            # شروع افکت کاغذ رنگی فقط اگر جایزه Pooch نباشه
            self.start_confetti()

        self.prize_panel.set_border(accent)
        self.prize_label.opacity = 0
        Animation(opacity=1, duration=0.45).start(self.prize_label)

    # ------------------- کدهای مربوط به کاغذ رنگی -------------------
    def start_confetti(self):
        self.stop_confetti()
        # ساخت ۱۰۰ تا کاغذ رنگی در بالای صفحه
        colors = [
            GOLD, RED, 
            get_color_from_hex("#29B6F6"), # آبی
            get_color_from_hex("#AB47BC"), # بنفش
            get_color_from_hex("#7CB342"), # سبز
            get_color_from_hex("#FFC107")  # زرد
        ]
        
        for _ in range(100):
            x = random.uniform(0, Window.width)
            y = Window.height + random.uniform(10, 300)
            color = random.choice(colors)
            p = ConfettiParticle(x, y, color)
            self.add_widget(p)
            self.confetti_widgets.append(p)

        # آپدیت کردن موقعیتشون ۶۰ بار در ثانیه
        self.confetti_event = Clock.schedule_interval(self.update_confetti, 1/60.0)

    def update_confetti(self, dt):
        finished = True
        for p in self.confetti_widgets:
            # سرعت سقوط و باد
            speed_y = random.uniform(150, 350) * dt
            speed_x = math.sin(Clock.get_time() * 3 + p.center_x) * 80 * dt
            
            p.y -= speed_y
            p.x += speed_x
            
            # اگر کاغذ به پایین‌ترین نقطه رسید
            if p.top > 0:
                finished = False

        if finished:
            self.stop_confetti()
            return False  # متوقف کردن تایمر
        return True

    def stop_confetti(self):
        if self.confetti_event:
            self.confetti_event.cancel()
            self.confetti_event = None
        for p in self.confetti_widgets:
            self.remove_widget(p)
        self.confetti_widgets.clear()
    # ----------------------------------------------------------------

    def logout(self, *_):
        self.stop_confetti()
        self.manager.get_screen("login").clear()
        self.manager.transition = FadeTransition(duration=0.4)
        self.manager.current = "login"
# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class LotteryApp(App):
    title = APP_TITLE

    def build(self):
        Window.clearcolor = BACKGROUND
        Window.softinput_mode = "below_target"

        if platform in ("win", "linux", "macosx"):
            Window.minimum_width = 360
            Window.minimum_height = 640
            Window.size = (480, 850)

        self.database = LotteryDatabase(DATABASE_PATH)

        manager = ScreenManager(transition=FadeTransition(duration=0.5))
        manager.add_widget(LoginScreen(self, name="login"))
        manager.add_widget(WheelScreen(self, name="wheel"))
        manager.add_widget(ResultScreen(self, name="result"))
        return manager

    def on_stop(self):
        if hasattr(self, "database"):
            self.database.close()


if __name__ == "__main__":
    LotteryApp().run()
