# 🎡 A1 Lucky Spin

> A touch-friendly **customer lottery (prize wheel)** application built for **A1 Home Appliances**, written in Python with Kivy.

Customers enter their details and invoice number, spin an animated prize wheel, and instantly see what they won. Every invoice can be played **only once**, and all results are stored locally in an SQLite database.

---

## 📑 Table of Contents

- [Features](#-features)
- [How It Works](#-how-it-works)
- [Prizes & Probabilities](#-prizes--probabilities)
- [Tech Stack](#-tech-stack)
- [Getting Started](#-getting-started)
- [Usage Guide](#-usage-guide)
- [Database](#-database)
- [Customization](#-customization)
- [Project Structure](#-project-structure)
- [Building for Android](#-building-for-android-optional)
- [Known Limitations](#-known-limitations)
- [Credits](#-credits)

---

## ✨ Features

- 🎨 **Modern dark UI** with gold accents, glow effects, and rounded components
- 🎡 **Custom-drawn prize wheel** (36 sectors) with decorative bulbs, hub, and a physical-looking pointer
- 🌀 **Smooth spin animation** (6 full rotations with ease-out) and a pointer that wobbles and settles
- 🔒 **One play per invoice** — enforced at the database level, so it can't be bypassed by restarting the app
- 📱 **Mobile number validation & normalization** — supports Persian/Arabic digits and formats such as `0912…`, `912…`, `98912…`, `0098912…`
- 💾 **Local SQLite storage** — no server or internet connection required
- 🔄 **Automatic database migration** — adds missing columns and fixes legacy schemas on startup
- 🖥️ **Cross-platform** — Windows, Linux, macOS, and Android (via Buildozer)
- 📦 **Single-file application** — the entire app lives in `main.py`

---

## 🧭 How It Works

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│  Login   │ ──► │  Wheel Spin  │ ──► │    Result    │
│  Screen  │     │    Screen    │     │    Screen    │
└──────────┘     └──────────────┘     └──────────────┘
     ▲                                        │
     └────────── Play again (new invoice) ────┘
```

1. **Login** — the customer enters first name, last name, mobile number, and invoice number.
2. **Validation** — all fields are checked, the phone number is normalized, and the invoice is registered (or verified) in the database.
3. **Spin** — a random sector is selected and the result is **saved to the database before the animation starts**, which prevents cheating by closing the app mid-spin.
4. **Result** — the prize is displayed. Winners are asked to contact the A1 team to claim it.

---

## 🎁 Prizes & Probabilities

The wheel has **36 sectors**. Each sector has an equal chance of being selected.

| Prize          | Sectors | Probability |
| -------------- | :-----: | :---------: |
| Pooch (no win) |   18    |   50.00 %   |
| Wall clock     |    8    |   22.22 %   |
| Crystal        |    2    |    5.56 %   |
| Chini          |    2    |    5.56 %   |
| Bloor          |    2    |    5.56 %   |
| Gold coin      |    2    |    5.56 %   |
| Carpet frame   |    2    |    5.56 %   |

> 💡 To change the odds, simply edit the `GIFTS` list in `main.py` (see [Customization](#-customization)).

---

## 🛠 Tech Stack

| Component | Technology                          |
| --------- | ----------------------------------- |
| Language  | Python 3.8+                         |
| UI / GFX  | [Kivy](https://kivy.org/)           |
| Database  | SQLite 3 (Python standard library)  |

---

## 🚀 Getting Started

### Prerequisites

- Python **3.8 or newer**
- `pip`

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/<repository-name>.git
cd <repository-name>
```

### 2. (Recommended) Create a virtual environment

```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install kivy
```

### 4. Run the app

```bash
python3 main.py
```

On first launch, the `lottery.db` database file is created automatically next to `main.py`.

---

## 📖 Usage Guide

### For the cashier / operator

1. Launch the application.
2. Enter the customer's **first name**, **last name**, **mobile number**, and **invoice number**.
3. Press **Login**.
4. Hand the device to the customer and let them press **Spin!**.
5. After the result screen appears, press **Play again with a new invoice** to serve the next customer.

### Validation rules

| Field          | Rule                                                                 |
| -------------- | -------------------------------------------------------------------- |
| First / Last   | Required                                                             |
| Mobile number  | Must be a valid Iranian mobile number (`09XXXXXXXXX`) after normalization |
| Invoice number | Positive integer, fewer than 12 digits                               |

### Error messages

| Situation                                         | Behavior                                                |
| ------------------------------------------------- | ------------------------------------------------------- |
| Invoice already played                            | Shows the previous result and asks for a new invoice    |
| Invoice registered with a different phone number  | Rejected: *"already registered to another customer"*   |
| Database failure                                  | Asks the user to contact the system administrator       |

---

## 🗄 Database

The app uses a single SQLite file (`lottery.db`) with one table:

```sql
CREATE TABLE lottery (
    factorID      INTEGER NOT NULL PRIMARY KEY,  -- Invoice number
    username      TEXT,                          -- "First Last"
    first_name    TEXT,
    last_name     TEXT,
    phone         TEXT,                          -- Normalized: 09XXXXXXXXX
    lottery_check INTEGER NOT NULL DEFAULT 0,    -- 0 = not played, 1 = played
    prize         TEXT NOT NULL DEFAULT 'pooch',
    played_at     TEXT                           -- Local timestamp of the spin
);
```

### Viewing the results

```bash
sqlite3 lottery.db "SELECT factorID, first_name, last_name, phone, prize, played_at FROM lottery WHERE lottery_check = 1;"
```

Or open `lottery.db` with [DB Browser for SQLite](https://sqlitebrowser.org/).

### Listing only the winners

```bash
sqlite3 lottery.db "SELECT * FROM lottery WHERE lottery_check = 1 AND prize != 'pooch';"
```

### Automatic migrations

On startup the app will:

- Add any missing columns (`first_name`, `last_name`, `phone`, `played_at`) to older databases
- Rebuild the table if a legacy `UNIQUE` constraint on `username` is detected

---

## 🎛 Customization

All settings are at the top of `main.py`.

### Change prizes or probabilities

Edit the `GIFTS` list. Each entry is one sector on the wheel — add more entries of a prize to make it more likely.

```python
GIFTS = [
    "crystal", "pooch", "chini", "pooch", ...
]
```

> If you add a **new prize name**, also add a color for it in `PRIZE_COLORS`.

### Change colors

```python
GOLD       = get_color_from_hex("#F4C95D")
BACKGROUND = get_color_from_hex("#0E0F1A")
PANEL      = get_color_from_hex("#1A1C2B")

PRIZE_COLORS = {
    "crystal": "#29B6F6",
    "gold coin": "#FFC107",
    ...
}
```

### Change the app title

```python
APP_TITLE = "A1 Lucky Spin"
```

### Change the database location

```python
DATABASE_PATH = Path(__file__).resolve().with_name("lottery.db")
```

### Change the spin duration / rotations

In `WheelScreen.spin_wheel`:

```python
final_angle = current - delta - 360 * 6                      # number of full rotations
animation = Animation(angle=final_angle, duration=5.8, t="out_quart")  # duration in seconds
```

---

## 📂 Project Structure

```
.
├── main.py        # The entire application
├── lottery.db     # Created automatically on first run
└── README.md
```

### Inside `main.py`

| Section                 | Description                                                           |
| ----------------------- | --------------------------------------------------------------------- |
| Kivy configuration      | Disables problematic touchpad provider (fixes `/dev/input/event*` errors on Linux) |
| Configuration           | Title, DB path, prizes, color palette                                 |
| Phone / digit helpers   | Persian/Arabic digit conversion and phone normalization               |
| `LotteryDatabase`       | SQLite access, schema creation, migration, one-play enforcement       |
| UI helpers              | `RoundedPanel`, `RoundedButton`, `StyledInput`, `BaseScreen`          |
| `WheelWidget`           | Custom-drawn wheel (sectors, labels, bulbs, hub)                      |
| `PointerWidget`         | Animated pointer (wobble & settle)                                    |
| `LoginScreen`           | Form + validation                                                     |
| `WheelScreen`           | Spin logic and animation                                              |
| `ResultScreen`          | Prize / thank-you display                                             |
| `LotteryApp`            | App entry point and screen manager                                    |

---

## 📱 Building for Android (optional)

The app can be packaged as an APK using [Buildozer](https://github.com/kivy/buildozer) (Linux or WSL recommended).

```bash
pip install buildozer
buildozer init
```

In the generated `buildozer.spec`, set at least:

```ini
title = A1 Lucky Spin
package.name = a1luckyspin
package.domain = com.a1
source.include_exts = py
requirements = python3,kivy
orientation = portrait
```

Then build:

```bash
buildozer -v android debug
```

The APK will be created in the `bin/` directory.

> ⚠️ On Android, the database is stored next to the app files. For production use, consider moving `DATABASE_PATH` to `App.user_data_dir` so data survives app updates.

---

## ⚠️ Known Limitations

- **No invoice verification:** any invoice number entered is accepted and registered automatically. The app does not check it against a real sales system.
- **Local database only:** results are not synchronized between devices. Use one device per branch, or collect the `lottery.db` files manually.
- **Phone validation is Iran-specific** (`09XXXXXXXXX`).
- **No admin panel:** results must be read directly from the database.

Pull requests addressing any of these are welcome.

---

## 🧪 Troubleshooting

| Problem                                        | Solution                                                               |
| ---------------------------------------------- | ---------------------------------------------------------------------- |
| Cannot type in text fields on Linux            | Already handled by `Config.set('input', 'mouse', ...)` at the top of `main.py`. Keep it **above** all other Kivy imports. |
| `ModuleNotFoundError: No module named 'kivy'`  | Run `pip install kivy` inside your active virtual environment.         |
| Window looks too small / large                 | Adjust `Window.size` in `LotteryApp.build`.                            |
| Want to let a customer play again with the same invoice (testing) | Delete the row or run `UPDATE lottery SET lottery_check = 0 WHERE factorID = <id>;` |

---

## 👤 Credits

- **Developer:** CAgent_47
- **Built for:** A1 Home Appliances

---

## 📄 License

This project is proprietary software created for A1 Home Appliances.
All rights reserved. Contact the owner for usage or redistribution permissions.

<!-- If you prefer an open-source license, replace this section with MIT / Apache-2.0 and add a LICENSE file. -->
