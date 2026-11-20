# ---------------------------------------------------------------------------
# A1 Lucky Spin
# Responsive, minimal Kivy lottery application
# UI redesign only — lottery/database mechanics preserved.
#
# Install:
#   pip install kivy
#
# Run:
#   python3 main.py
# ---------------------------------------------------------------------------

from kivy.config import Config
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
from kivy.uix.anchorlayout import AnchorLayout
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
# GLOBAL CONFIGURATION
# ---------------------------------------------------------------------------

APP_TITLE = "A1 Lucky Spin"
DATABASE_PATH = Path(__file__).resolve().with_name("lottery.db")

POOCH = "Pooch"

GIFTS = [
    "Crystal", "Pooch", "Chini", "Pooch", "Bloor", "Tablo Farsh",
    "Sekke Tala", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Crystal",
    "Tablo Farsh", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Pooch",
    "Crystal", "Pooch", "Chini", "Pooch", "Bloor", "Tablo Farsh",
    "Sekke Tala", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Crystal",
    "Tablo Farsh", "Pooch", "Sa'at Divari", "Pooch", "Sa'at Divari", "Pooch",
]

# Colors
GOLD = get_color_from_hex("#E8B85A")
GOLD_LIGHT = get_color_from_hex("#F4D18A")

BACKGROUND = get_color_from_hex("#0B0D12")
PANEL = get_color_from_hex("#131720")
PANEL_LIGHT = get_color_from_hex("#1B202B")
PANEL_INPUT = get_color_from_hex("#191E28")

TEXT = get_color_from_hex("#F2F1ED")
MUTED = get_color_from_hex("#9298A8")
RED = get_color_from_hex("#E66C70")

HAIRLINE = (1, 1, 1, 0.075)

PRIZE_COLORS = {
    "Crystal": "#38B6F0",
    "Chini": "#A56BD1",
    "Bloor": "#2BA89A",
    "Sekke Tala": "#F2B632",
    "Sa'at Divari": "#E8605E",
    "Tablo Farsh": "#86B84A",
}

POOCH_COLORS = ("#262B40", "#1E2336")


# ---------------------------------------------------------------------------
# RESPONSIVE HELPERS
# ---------------------------------------------------------------------------

def ui_scale():
    short_dp = min(Window.width, Window.height) / dp(1)

    if short_dp <= 400:
        return max(0.82, short_dp / 400.0)

    return min(1.55, (short_dp / 400.0) ** 0.55)


def u(value):
    return dp(value) * ui_scale()


def is_wide():
    return Window.width >= Window.height * 1.15


def fit_height(box):
    kids = box.children

    if not kids:
        box.height = 0
        return

    pad = box.padding

    box.height = (
        sum(c.height for c in kids)
        + box.spacing * (len(kids) - 1)
        + pad[1] + pad[3]
    )


def sector_color(index):
    prize = GIFTS[index]

    if prize == POOCH:
        return get_color_from_hex(POOCH_COLORS[(index // 2) % 2])

    return get_color_from_hex(PRIZE_COLORS.get(prize, "#888888"))


def text_color_for(rgba):
    luminance = (
        0.299 * rgba[0]
        + 0.587 * rgba[1]
        + 0.114 * rgba[2]
    )

    return (0.08, 0.08, 0.10, 1) if luminance > 0.55 else (1, 1, 1, 1)


# ---------------------------------------------------------------------------
# HELPERS
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
# DATABASE
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
            connection.execute("""
                INSERT INTO lottery_new
                    (factorID, username, first_name, last_name, phone,
                     lottery_check, prize, played_at)
                SELECT factorID, username, first_name, last_name, phone,
                       COALESCE(lottery_check, 0),
                       COALESCE(prize, 'pooch'),
                       played_at
                FROM lottery
            """)

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

        if row is None:
            self.connection.execute(
                """
                INSERT INTO lottery
                    (factorID, username, first_name, last_name,
                     phone, lottery_check, prize)
                VALUES (?, ?, ?, ?, ?, 0, 'pooch')
                """,
                (factor_id, f"{first_name} {last_name}",
                 first_name, last_name, phone),
            )

        elif not row["phone"]:
            self.connection.execute(
                """
                UPDATE lottery
                SET username = ?, first_name = ?, last_name = ?, phone = ?
                WHERE factorID = ?
                """,
                (f"{first_name} {last_name}",
                 first_name, last_name, phone, factor_id),
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


# ---------------------------------------------------------------------------
# UI WIDGETS
# ---------------------------------------------------------------------------

class ScaledLabel(Label):

    def __init__(
        self,
        text="",
        size=16,
        color=TEXT,
        bold=False,
        halign="center",
        h=None,
        **kwargs,
    ):
        super().__init__(
            text=text,
            color=color,
            bold=bold,
            halign=halign,
            valign="middle",
            size_hint_y=None,
            **kwargs,
        )

        self.base_font = size
        self.base_h = h or max(26, size * 1.9)

        self.bind(
            size=lambda inst, value: setattr(inst, "text_size", value)
        )

        self.apply_scale()

    def apply_scale(self):
        self.font_size = u(self.base_font)
        self.height = u(self.base_h)


class RoundedPanel(BoxLayout):

    def __init__(self, fill=PANEL, border=HAIRLINE, radius=22, **kwargs):
        super().__init__(**kwargs)

        self.base_radius = radius
        self.radius = u(radius)

        with self.canvas.before:
            Color(*fill)
            self._fill = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self.radius],
            )

            self._border_color = Color(*border)
            self._border = Line(
                rounded_rectangle=(
                    self.x, self.y, self.width, self.height, self.radius
                ),
                width=1,
            )

        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._fill.pos = self.pos
        self._fill.size = self.size
        self._fill.radius = [self.radius]

        self._border.rounded_rectangle = (
            self.x, self.y, self.width, self.height, self.radius
        )

    def apply_scale(self):
        self.radius = u(self.base_radius)
        self._update()

    def set_border(self, rgba):
        self._border_color.rgba = rgba


class RoundedButton(Button):

    def __init__(
        self,
        base_color=GOLD,
        foreground=BACKGROUND,
        radius=16,
        base_h=54,
        base_font=16,
        **kwargs,
    ):
        super().__init__(
            background_normal="",
            background_down="",
            background_disabled_normal="",
            background_color=(0, 0, 0, 0),
            color=foreground,
            disabled_color=(
                foreground[0],
                foreground[1],
                foreground[2],
                0.5,
            ),
            bold=True,
            size_hint_y=None,
            **kwargs,
        )

        self.base_color = base_color
        self.base_radius = radius
        self.base_h = base_h
        self.base_font = base_font

        with self.canvas.before:
            self._color = Color(*base_color)
            self._rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[u(radius)],
            )

        self.bind(
            pos=self._update,
            size=self._update,
            state=self._refresh,
            disabled=self._refresh,
        )

        self.apply_scale()

    def apply_scale(self):
        self.font_size = u(self.base_font)
        self.height = u(self.base_h)
        self._rect.radius = [u(self.base_radius)]

    def _update(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _refresh(self, *_):
        base = self.base_color

        if self.disabled:
            self._color.rgba = (
                base[0] * 0.65,
                base[1] * 0.65,
                base[2] * 0.65,
                0.65,
            )

        elif self.state == "down":
            self._color.rgba = (
                base[0] * 0.88,
                base[1] * 0.88,
                base[2] * 0.88,
                1,
            )

        else:
            self._color.rgba = base


def make_button(
    text,
    callback,
    background=GOLD,
    foreground=BACKGROUND,
    h=54,
    font=16,
):
    button = RoundedButton(
        text=text,
        base_color=background,
        foreground=foreground,
        base_h=h,
        base_font=font,
    )

    button.bind(on_release=callback)
    return button


class StyledInput(TextInput):

    def __init__(self, hint, **kwargs):
        super().__init__(
            hint_text=hint,
            multiline=False,
            write_tab=False,
            size_hint_y=None,
            foreground_color=TEXT,
            hint_text_color=(
                MUTED[0], MUTED[1], MUTED[2], 0.65
            ),
            cursor_color=GOLD,
            selection_color=(
                GOLD[0], GOLD[1], GOLD[2], 0.25
            ),
            background_normal="",
            background_active="",
            background_disabled_normal="",
            background_color=PANEL_INPUT,
            **kwargs,
        )

        self.apply_scale()

    def apply_scale(self):
        self.font_size = u(16)
        self.height = u(56)
        self.cursor_width = max(1, u(1.5))

        pad_x = u(16)
        pad_y = max(0, (self.height - self.line_height) / 2)

        self.padding = [pad_x, pad_y, pad_x, pad_y]


# ---------------------------------------------------------------------------
# BASE SCREEN
# ---------------------------------------------------------------------------

class BaseScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        with self.canvas.before:
            Color(*BACKGROUND)
            self._bg = Rectangle(pos=self.pos, size=self.size)

            Color(0.50, 0.35, 0.95, 0.035)
            self._glow_a = Ellipse()

            Color(GOLD[0], GOLD[1], GOLD[2], 0.025)
            self._glow_b = Ellipse()

        self.bind(pos=self._layout_background, size=self._layout_background)
        Window.bind(size=self._on_window_resize)

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

    def _on_window_resize(self, *_):
        Clock.schedule_once(lambda _dt: self.relayout(), 0)

    def on_pre_enter(self, *args):
        self.relayout()

    def apply_scales(self):
        for widget in self.walk():
            if hasattr(widget, "apply_scale"):
                widget.apply_scale()

    def relayout(self):
        pass


# ---------------------------------------------------------------------------
# WHEEL
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
        outer = min(self.width, self.height) / 2 - 2

        rim = outer * 0.05
        radius = outer - rim

        count = len(GIFTS)
        step = 360.0 / count
        font_size = max(8, radius * 0.062)

        with self.canvas:

            # Shadow
            Color(0, 0, 0, 0.28)

            sh = outer + outer * 0.03

            Ellipse(
                pos=(cx - sh, cy - sh - outer * 0.02),
                size=(sh * 2, sh * 2),
            )

            PushMatrix()
            self._rotation = Rotate(
                angle=self.angle,
                origin=(cx, cy),
            )

            # Rim
            Color(*GOLD)
            Ellipse(
                pos=(cx - outer, cy - outer),
                size=(outer * 2, outer * 2),
            )

            Color(0.09, 0.09, 0.14, 1)

            inner = outer - max(2, outer * 0.012)

            Ellipse(
                pos=(cx - inner, cy - inner),
                size=(inner * 2, inner * 2),
            )

            # Sectors
            for i in range(count):
                Color(*sector_color(i))

                Ellipse(
                    pos=(cx - radius, cy - radius),
                    size=(radius * 2, radius * 2),
                    angle_start=i * step,
                    angle_end=(i + 1) * step,
                    segments=12,
                )

            # Dividers
            Color(1, 1, 1, 0.16)

            for i in range(count):
                a = math.radians(90 - i * step)

                Line(
                    points=[
                        cx, cy,
                        cx + radius * math.cos(a),
                        cy + radius * math.sin(a),
                    ],
                    width=max(0.8, outer * 0.003),
                )

            # Labels
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

                Rotate(
                    angle=math.degrees(theta),
                    origin=(tx, ty),
                )

                tc = text_color_for(color)

                Color(
                    tc[0], tc[1], tc[2],
                    0.6 if prize == POOCH else 1,
                )

                Rectangle(
                    texture=texture,
                    pos=(tx - w / 2, ty - h / 2),
                    size=(w, h),
                )

                PopMatrix()

            # Rim dots
            dot_r = outer - rim / 2
            dot = max(2, rim * 0.34)

            Color(0.09, 0.09, 0.14, 0.85)

            for i in range(count):
                a = math.radians(90 - i * step)

                bx = cx + dot_r * math.cos(a)
                by = cy + dot_r * math.sin(a)

                Ellipse(
                    pos=(bx - dot / 2, by - dot / 2),
                    size=(dot, dot),
                )

            PopMatrix()

            # Hub
            hub = radius * 0.14

            Color(*GOLD)

            Ellipse(
                pos=(cx - hub, cy - hub),
                size=(hub * 2, hub * 2),
            )

            Color(0.07, 0.08, 0.12, 1)

            hub_in = hub * 0.82

            Ellipse(
                pos=(cx - hub_in, cy - hub_in),
                size=(hub_in * 2, hub_in * 2),
            )

            hub_texture = self._texture("A1", max(10, radius * 0.1))

            if hub_texture is not None:
                hw, hh = hub_texture.size

                Color(*GOLD_LIGHT)

                Rectangle(
                    texture=hub_texture,
                    pos=(cx - hw / 2, cy - hh / 2),
                    size=(hw, hh),
                )


# ---------------------------------------------------------------------------
# POINTER
# ---------------------------------------------------------------------------

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

        cx = self.center_x
        top = self.top

        half = self.width * 0.42
        head = self.width * 0.2
        pivot_y = top - head

        with self.canvas:

            PushMatrix()

            Rotate(angle=self.angle, origin=(cx, pivot_y))

            Color(0, 0, 0, 0.3)

            Triangle(
                points=[
                    cx - half + 2, top - 2,
                    cx + half + 2, top - 2,
                    cx + 2, self.y - 2,
                ]
            )

            Color(*RED)

            Triangle(
                points=[
                    cx - half, top,
                    cx + half, top,
                    cx, self.y,
                ]
            )

            Color(*GOLD)

            Ellipse(
                pos=(cx - head, pivot_y - head),
                size=(head * 2, head * 2),
            )

            Color(0.07, 0.08, 0.12, 1)

            Ellipse(
                pos=(cx - head * 0.45, pivot_y - head * 0.45),
                size=(head * 0.9, head * 0.9),
            )

            PopMatrix()

    def start_wobble(self):
        self.stop_animations()

        sequence = (
            Animation(angle=13, duration=0.075, t="out_quad")
            + Animation(angle=-13, duration=0.075, t="out_quad")
            + Animation(angle=9, duration=0.075, t="out_quad")
            + Animation(angle=-9, duration=0.075, t="out_quad")
        )

        sequence.repeat = True

        self.wobble_animation = sequence
        sequence.start(self)

    def settle(self):
        self.stop_animations()

        animation = (
            Animation(angle=-17, duration=0.12, t="out_quad")
            + Animation(angle=9, duration=0.12, t="out_quad")
            + Animation(angle=-4, duration=0.14, t="out_quad")
            + Animation(angle=0, duration=0.18, t="out_back")
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
# LOGIN SCREEN
# ---------------------------------------------------------------------------

class LoginScreen(BaseScreen):

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)

        self.app_ref = app

        anchor = AnchorLayout(anchor_x="center", anchor_y="center")

        self.col = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
        )

        self.title_label = ScaledLabel(
            "A1 Lucky Spin", 34, GOLD, True
        )

        self.sub_label = ScaledLabel(
            "CUSTOMER LOTTERY", 13, MUTED
        )

        self.gap_top = Widget(size_hint_y=None)

        self.card = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
        )

        self.grid = GridLayout(
            cols=1,
            size_hint_y=None,
            row_force_default=True,
        )

        self.first_input = StyledInput(hint="First name")
        self.last_input = StyledInput(hint="Last name")

        self.phone_input = StyledInput(
            hint="Mobile number",
            input_filter=digits_only,
            input_type="tel",
        )

        self.factor_input = StyledInput(
            hint="Invoice number",
            input_filter=digits_only,
            input_type="number",
        )

        for field in (
            self.first_input,
            self.last_input,
            self.phone_input,
            self.factor_input,
        ):
            self.grid.add_widget(field)

        self.error_label = ScaledLabel("", 13, RED, h=46)

        self.login_button = make_button(
            "Continue",
            self.login,
        )

        self.card.add_widget(self.grid)
        self.card.add_widget(self.error_label)
        self.card.add_widget(self.login_button)

        self.gap_bottom = Widget(size_hint_y=None)

        self.footer_label = ScaledLabel(
            "GOOD LUCK", 12, MUTED
        )

        for widget in (
            self.title_label,
            self.sub_label,
            self.gap_top,
            self.card,
            self.gap_bottom,
            self.footer_label,
        ):
            self.col.add_widget(widget)

        anchor.add_widget(self.col)
        self.add_widget(anchor)

        self._inputs = (
            self.first_input,
            self.last_input,
            self.phone_input,
            self.factor_input,
        )

        for field in self._inputs:
            field.bind(focus=self._on_field_focus)

        self.relayout()

    def relayout(self):
        self.apply_scales()

        width = Window.width
        height = Window.height

        wide = width > height and width >= u(700)

        self.col.width = min(width * 0.92, u(480))

        self.gap_top.height = u(20 if height > u(650) else 8)
        self.gap_bottom.height = u(12)

        self.card.padding = [u(20)] * 4
        self.card.spacing = u(14)

        self.grid.cols = 2 if wide else 1
        self.grid.spacing = u(12)
        self.grid.row_default_height = u(56)

        rows = 2 if wide else 4

        self.grid.height = (
            rows * u(56)
            + (rows - 1) * u(12)
        )

        fit_height(self.card)

        self.col.spacing = u(8)

        self.col.height = (
            sum(child.height for child in self.col.children)
            + self.col.spacing * (len(self.col.children) - 1)
        )

        self.apply_scales()

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
            self.error_label.text = (
                "Please enter a valid mobile number "
                "(e.g. 09123456789)."
            )
            return

        try:
            factor_id = int(factor_text)

        except ValueError:
            factor_id = 0

        if not 0 < factor_id < 10 ** 12:
            self.error_label.text = (
                "Invoice number must be a positive integer."
            )
            return

        try:
            customer = self.app_ref.database.register_invoice(
                first_name,
                last_name,
                phone,
                factor_id,
            )

        except ValueError as error:
            self.error_label.text = str(error)
            return

        except sqlite3.Error:
            self.error_label.text = (
                "Database error. Please contact the system administrator."
            )
            return

        if customer["lottery_check"] == 1:
            previous_prize = customer["prize"] or POOCH

            self.error_label.text = (
                f"This invoice was already used (result: {previous_prize}). "
                "Enter a new invoice number to play again."
            )

            return

        wheel_screen = self.manager.get_screen("wheel")

        wheel_screen.prepare_customer(first_name, factor_id)

        self.manager.transition = FadeTransition(duration=0.45)
        self.manager.current = "wheel"

    def clear(self):
        for field in self._inputs:
            field.text = ""
            field.focus = False

        self.error_label.text = ""


# ---------------------------------------------------------------------------
# WHEEL SCREEN
# ---------------------------------------------------------------------------

class WheelScreen(BaseScreen):

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)

        self.app_ref = app

        self.current_name = ""
        self.current_factor = 0

        self.is_spinning = False
        self.has_played = False
        self.selected_index = None

        self.root_box = BoxLayout(orientation="vertical")

        self.head = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
        )

        self.welcome_label = ScaledLabel(
            "Welcome", 20, GOLD, True
        )

        self.dev_label = ScaledLabel(
            "A1 LUCKY SPIN", 11, MUTED, h=22
        )

        self.head.add_widget(self.welcome_label)
        self.head.add_widget(self.dev_label)

        self.top_slot = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
        )

        self.top_slot.add_widget(self.head)

        self.body = BoxLayout(orientation="vertical")

        self.wheel_area = FloatLayout()

        self.wheel = WheelWidget(
            size_hint=(None, None),
            size=(dp(300), dp(300)),
        )

        self.pointer = PointerWidget(
            size_hint=(None, None),
            size=(dp(34), dp(44)),
        )

        self.wheel_area.add_widget(self.wheel)
        self.wheel_area.add_widget(self.pointer)

        self.wheel_area.bind(
            pos=self.layout_board,
            size=self.layout_board,
        )

        self.side = BoxLayout(orientation="vertical")

        self.sp_top = Widget(size_hint_y=None, height=0)

        self.side_slot = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
        )

        self.status_label = ScaledLabel(
            "", 14, MUTED, h=36
        )

        self.spin_button = make_button(
            "Spin!",
            self.spin_wheel,
            h=60,
            font=19,
        )

        self.back_button = make_button(
            "Back",
            self.back_to_login,
            background=PANEL_LIGHT,
            foreground=TEXT,
            h=48,
            font=14,
        )

        self.sp_bottom = Widget(size_hint_y=None, height=0)

        for widget in (
            self.sp_top,
            self.side_slot,
            self.status_label,
            self.spin_button,
            self.back_button,
            self.sp_bottom,
        ):
            self.side.add_widget(widget)

        self.body.add_widget(self.wheel_area)
        self.body.add_widget(self.side)

        self.root_box.add_widget(self.top_slot)
        self.root_box.add_widget(self.body)

        self.add_widget(self.root_box)

        self.relayout()

    def relayout(self):
        self.apply_scales()

        wide = is_wide()
        pad = u(18)

        self.root_box.padding = [pad, pad, pad, pad]
        self.root_box.spacing = u(12)
        self.body.spacing = u(18)

        target = self.side_slot if wide else self.top_slot

        if self.head.parent is not target:
            if self.head.parent:
                self.head.parent.remove_widget(self.head)

            target.add_widget(self.head)

        fit_height(self.head)
        fit_height(self.top_slot)
        fit_height(self.side_slot)

        self.side.spacing = u(14)

        if wide:
            self.body.orientation = "horizontal"

            self.wheel_area.size_hint = (0.68, 1)
            self.side.size_hint = (0.32, 1)

            self.side.padding = [u(20), u(8), u(8), u(8)]

            self.sp_top.size_hint_y = 1
            self.sp_bottom.size_hint_y = 1

        else:
            self.body.orientation = "vertical"

            self.wheel_area.size_hint = (1, 1)
            self.side.size_hint = (1, None)

            self.side.padding = [u(4), u(4), u(4), u(4)]

            self.sp_top.size_hint_y = None
            self.sp_bottom.size_hint_y = None

            self.sp_top.height = 0
            self.sp_bottom.height = 0

            fit_height(self.side)

        self.layout_board()

    def layout_board(self, *_):
        area = self.wheel_area

        if area.width <= 0 or area.height <= 0:
            return

        ph = u(44)
        overlap = u(8)

        self.pointer.size = (u(34), ph)

        used_extra = ph - overlap

        diameter = min(
            area.width - u(12),
            area.height - used_extra - u(8),
        )

        diameter = max(dp(120), diameter)

        self.wheel.size = (diameter, diameter)

        free = max(
            0,
            area.height - (diameter + used_extra),
        )

        wheel_cy = area.y + free / 2 + diameter / 2

        self.wheel.center = (area.center_x, wheel_cy)

        self.pointer.center_x = area.center_x
        self.pointer.y = wheel_cy + diameter / 2 - overlap

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

        # Selection mechanics remain unchanged.
        self.selected_index = random.randrange(len(GIFTS))
        prize = GIFTS[self.selected_index]

        # Save before animation.
        try:
            saved = self.app_ref.database.mark_as_played(
                self.current_factor,
                prize,
            )

        except sqlite3.Error:
            saved = False

        if not saved:
            self.is_spinning = False
            self.spin_button.text = "Used"

            self.status_label.text = (
                "This invoice has already been used."
            )

            return

        self.has_played = True

        self.pointer.start_wobble()

        # Final angle.
        step = 360.0 / len(GIFTS)

        target = (self.selected_index + 0.5) * step
        target += random.uniform(-0.38, 0.38) * step

        current = self.wheel.angle
        delta = (current - target) % 360

        final_angle = current - delta - 360 * 6

        animation = Animation(
            angle=final_angle,
            duration=5.8,
            t="out_quart",
        )

        animation.bind(
            on_complete=lambda *_: self.finish_spin(prize)
        )

        animation.start(self.wheel)

    def finish_spin(self, prize):
        self.pointer.settle()

        self.status_label.text = "The wheel has stopped."

        Clock.schedule_once(
            lambda _dt: self.show_result(prize),
            0.8,
        )

    def show_result(self, prize):
        self.is_spinning = False
        self.spin_button.text = "Used"

        result_screen = self.manager.get_screen("result")

        result_screen.show_prize(self.current_name, prize)

        self.manager.transition = FadeTransition(duration=0.55)
        self.manager.current = "result"

    def back_to_login(self, *_):
        if self.is_spinning:
            return

        self.manager.get_screen("login").clear()

        self.manager.transition = FadeTransition(duration=0.35)
        self.manager.current = "login"


# ---------------------------------------------------------------------------
# CONFETTI
# ---------------------------------------------------------------------------

class ConfettiParticle(Widget):

    def __init__(self, x, y, color, **kwargs):
        kwargs["size_hint"] = (None, None)

        super().__init__(**kwargs)

        self.pos = (x, y)
        self.size = (u(7), u(11))

        self.vy = random.uniform(130, 330) * ui_scale()
        self.phase = random.uniform(0, 6.28)

        with self.canvas:
            Color(*color)

            self._rect = Rectangle(
                pos=self.pos,
                size=self.size,
            )

        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size


# ---------------------------------------------------------------------------
# RESULT SCREEN
# ---------------------------------------------------------------------------

class ResultScreen(BaseScreen):

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)

        self.app_ref = app

        self.confetti_widgets = []
        self.confetti_event = None

        anchor = AnchorLayout(
            anchor_x="center",
            anchor_y="center",
        )

        self.col = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
        )

        self.title_label = ScaledLabel(
            "Congratulations!", 26, GOLD, True
        )

        self.subtitle_label = ScaledLabel(
            "", 15, MUTED
        )

        self.gap_a = Widget(size_hint_y=None)

        self.prize_panel = RoundedPanel(
            orientation="vertical",
            size_hint_y=None,
        )

        self.prize_label = ScaledLabel(
            "", 30, GOLD_LIGHT, True
        )

        self.prize_label.size_hint_y = 1

        self.prize_panel.add_widget(self.prize_label)

        self.message_label = ScaledLabel(
            "", 15, TEXT, h=52
        )

        self.gap_b = Widget(size_hint_y=None)

        self.again_button = make_button(
            "Play again with a new invoice",
            self.logout,
            h=56,
            font=16,
        )

        for widget in (
            self.title_label,
            self.subtitle_label,
            self.gap_a,
            self.prize_panel,
            self.message_label,
            self.gap_b,
            self.again_button,
        ):
            self.col.add_widget(widget)

        anchor.add_widget(self.col)
        self.add_widget(anchor)

        self.relayout()

    def relayout(self):
        self.apply_scales()

        width = Window.width

        self.col.width = min(width * 0.92, u(480))

        self.gap_a.height = u(16)
        self.gap_b.height = u(14)

        self.prize_panel.padding = [u(18)] * 4
        self.prize_panel.height = u(132)

        self.col.spacing = u(8)

        self.col.height = (
            sum(child.height for child in self.col.children)
            + self.col.spacing * (len(self.col.children) - 1)
        )

    def show_prize(self, name, prize):
        self.prize_label.text = prize.upper()

        self.stop_confetti()

        if prize == POOCH:
            accent = (1, 1, 1, 0.14)

            self.title_label.text = "Thank you for playing!"
            self.title_label.color = GOLD_LIGHT

            self.subtitle_label.text = (
                f"{name}, today may not be your day..."
            )

            self.message_label.text = (
                "Every spin is a new memory. "
                "Thank you for being part of A1!"
            )

            self.prize_label.color = MUTED

        else:
            prize_color = get_color_from_hex(
                PRIZE_COLORS.get(prize, "#888888")
            )

            accent = (
                prize_color[0],
                prize_color[1],
                prize_color[2],
                1,
            )

            self.title_label.text = "Congratulations!"
            self.title_label.color = GOLD

            self.subtitle_label.text = (
                f"{name}, you are a winner!"
            )

            self.message_label.text = (
                "Please contact the A1 team to claim your prize."
            )

            self.prize_label.color = prize_color

            self.start_confetti()

        self.prize_panel.set_border(accent)

        self.prize_label.opacity = 0

        Animation(opacity=1, duration=0.45).start(
            self.prize_label
        )

    def start_confetti(self):
        self.stop_confetti()

        colors = (
            [GOLD, RED]
            + [get_color_from_hex(c) for c in PRIZE_COLORS.values()]
        )

        for _ in range(70):
            x = random.uniform(0, Window.width)
            y = Window.height + random.uniform(10, 300)

            particle = ConfettiParticle(
                x,
                y,
                random.choice(colors),
            )

            self.add_widget(particle)
            self.confetti_widgets.append(particle)

        self.confetti_event = Clock.schedule_interval(
            self.update_confetti,
            1 / 60.0,
        )

    def update_confetti(self, dt):
        finished = True
        now = Clock.get_time()

        for p in self.confetti_widgets:
            p.y -= p.vy * dt

            p.x += (
                math.sin(now * 2.5 + p.phase)
                * 60 * ui_scale() * dt
            )

            if p.top > 0:
                finished = False

        if finished:
            self.stop_confetti()
            return False

        return True

    def stop_confetti(self):
        if self.confetti_event:
            self.confetti_event.cancel()
            self.confetti_event = None

        for p in self.confetti_widgets:
            self.remove_widget(p)

        self.confetti_widgets.clear()

    def logout(self, *_):
        self.stop_confetti()

        self.manager.get_screen("login").clear()

        self.manager.transition = FadeTransition(duration=0.35)
        self.manager.current = "login"


# ---------------------------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------------------------

class LotteryApp(App):

    title = APP_TITLE

    def build(self):
        Window.clearcolor = BACKGROUND
        Window.softinput_mode = "below_target"

        if platform in ("win", "linux", "macosx"):
            Window.minimum_width = 360
            Window.minimum_height = 520
            Window.size = (480, 850)

        self.database = LotteryDatabase(DATABASE_PATH)

        manager = ScreenManager(
            transition=FadeTransition(duration=0.4)
        )

        manager.add_widget(
            LoginScreen(self, name="login")
        )

        manager.add_widget(
            WheelScreen(self, name="wheel")
        )

        manager.add_widget(
            ResultScreen(self, name="result")
        )

        return manager

    def on_stop(self):
        if hasattr(self, "database"):
            self.database.close()


if __name__ == "__main__":
    LotteryApp().run()
