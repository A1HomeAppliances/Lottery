# A1 Lucky Spin

A customer-facing lottery wheel for **A1**. A customer enters their name,
mobile number and invoice number, then spins a 36-sector wheel to win a prize
(or the "Pooch" consolation). Each invoice can be spun exactly **once** — this
is enforced inside SQLite, not in the UI.

The app targets **Android** (a Kivy shell hosting a full-screen `WebView`) and
also runs in a browser for **desktop preview**.

---
**🚀Version 1.5.0 Is Commming...🚀**

## Architecture

Four layers, deliberately decoupled:

| Layer | File(s) | Role |
|---|---|---|
| Application logic | `lottery/backend.py`, `core/*` | Pure Python, no Kivy/Android imports. Shared by Android and desktop. Testable standalone. |
| Web UI | `lottery/web/*` | All rendering, input, spin physics and the RPC client. |
| Android host | `lottery/shell.py`, `lottery/webbridge.py` | Kivy `App` + native `WebView` + hash-based RPC bridge. |
| Desktop host | `lottery/dev_server.py` | Serves `web/` over `http://127.0.0.1:8765/` and the same RPC on `POST /api`. |

The only public entry point into the logic is:

```python
Backend.handle(method, params) -> dict
```

`main.py` picks the host automatically: if `ANDROID_ARGUMENT` is set (by
`python-for-android`) it starts `ShellApp`, otherwise it starts
`dev_server.main()`.

---

## Directory layout

```
lottery/
├── backend.py          # shared RPC logic (no Kivy, no Android)
├── main.py             # entry point (Android -> shell, else dev_server)
├── shell.py            # Kivy App that hosts the WebView (Android)
├── webbridge.py        # WebView <-> Python RPC bridge (Android)
├── dev_server.py       # desktop preview HTTP server
├── buildozer.spec      # Android build configuration
├── requirements.txt    # desktop needs nothing extra
├── core/
│   ├── config.py       # GIFTS, POOCH, colors, paths
│   ├── database.py     # SQLite persistence layer
│   └── utils.py        # digits_only, normalize_phone
└── web/
    ├── index.html
    ├── app.js
    └── style.css
```

---

## Running the desktop preview

Requires **no third-party packages** — only the Python standard library.

```bash
cd lottery
python3 main.py
```

- Serves `web/` from `http://127.0.0.1:8765/`.
- Exposes the same RPC on `POST /api` (same JSON shape as the Android bridge).
- Uses `lottery.db` next to the source tree.
- Sends `Cache-Control: no-store` so edits in `web/` show up on refresh.
- Opens the page in your default browser; Ctrl+C to stop.

---

## Building the Android APK

`buildozer.spec` pins:

- **Requirements:** `python3, sqlite3, kivy==2.3.1, pyjnius, android`
- **Architectures:** `arm64-v8a`, `armeabi-v7a`
- **API:** `android.api = 33`, `android.minapi = 24`, NDK `25b`
- **p4a branch:** `develop`
- **Permissions:** `INTERNET` only

```bash
cd lottery
buildozer -v android debug
```

KivyMD / Pillow / materialyoucolor / libthorvg are **no longer required** —
the UI is HTML and Kivy only hosts the `WebView`. `sqlite3` is required.

`buildozer.spec` **intentionally excludes** `lottery.db` and `*.db` from the
package, and does not list `db` in `source.include_exts`, so a developer's
local test database never ships in the APK.

On Android the DB lives inside `App.user_data_dir` so it survives APK updates.

---

## The RPC bridge

The web UI uses one function:

```js
call(method, params) -> Promise<{ok, ...}>
```

How it is transported depends on the page URL (`location.protocol`):

### Desktop (`http:` / `https:`)

```js
fetch("/api", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({m: method, p: params || {}})
})
```

Requests are serialised (`chain = chain.then(...)`), so only one is in flight
at a time.

### Android (`file:`)

The page sets `location.hash = "rpc/<id>/<base64url(json)>"`. `WebBridge`
polls `WebView.getUrl()` five times a second, matches
`#rpc/(\d+)/([A-Za-z0-9_-]*)$`, decodes the base64url payload, calls
`backend.handle()`, and answers with:

```js
window.__rpcReply(id, JSON.stringify(result))
```

The page resolves the matching pending `Promise`. A `_last_id` guard means
each hash is served only once. An **8-second timeout** surfaces a friendly
error if the app thread is blocked.

Why this design:

- **No local HTTP server on Android** (no cleartext problem, no port
  conflicts).
- **No `@JavascriptInterface` Java subclass** (keeps the build simple).

The Android hardware back button flows through:

```
Kivy _on_key(27) -> WebBridge.back() -> window.__back() in the page
```

`window.__back()` decides what to do based on the current view, and calls the
`exit` RPC on the login screen, which asks `ShellApp` to stop.

---

## RPC methods

All methods take a single dict and return either
`{ "ok": true, ... }` or `{ "ok": false, "error": "..." }`.
`Backend.handle` wraps each call in a `threading.Lock`, catches
`sqlite3.Error` and any other exception, and turns them into a generic error
message.

| Method | Params | Returns |
|---|---|---|
| `config` | — | `gifts`, `pooch`, `prizeColors`, `poochColors` |
| `register` | `first`, `last`, `phone`, `invoice` | `name`, `invoice` |
| `spin` | `invoice` | `index`, `prize` |
| `exit` | — | `ok` |

- **`register`** trims and validates the names, normalises the phone via
  `normalize_phone` (Iranian `09xxxxxxxxx`, accepts `+98`, `0098`, `98…`
  prefixes and Persian/Arabic-Indic digits), strips non-digits from the
  invoice, and inserts the row if the invoice is new. If the invoice already
  belongs to another phone number it raises `ValueError`.
- **`spin`** picks `_rng.randrange(len(GIFTS))` with `random.SystemRandom`
  (unpredictable outcome), then `mark_as_played` performs an
  `UPDATE ... WHERE lottery_check = 0` and checks `cursor.rowcount == 1`,
  so a race between two spins resolves to exactly one winner.
- **`exit`** is only used from the login screen by the Android back button.
  `WebBridge` then schedules `ShellApp.stop()`.

---

## Database

SQLite, one table, one file. Schema:

```sql
CREATE TABLE lottery (
    factorID     INTEGER NOT NULL PRIMARY KEY,   -- invoice number
    username     TEXT,                           -- "First Last"
    first_name   TEXT,
    last_name    TEXT,
    phone        TEXT,
    lottery_check INTEGER NOT NULL DEFAULT 0,
    prize        TEXT NOT NULL DEFAULT 'Pooch',
    played_at    TEXT
);
```

`LotteryDatabase` migrates older tables on startup:

- Adds any missing columns in `EXTRA_COLUMNS`
  (`first_name`, `last_name`, `phone`, `played_at`).
- If `username` still has a `UNIQUE` constraint from an older schema, it
  rebuilds the table into the current shape.

`mark_as_played` writes `played_at = datetime('now', 'localtime')` at the
same time it flips `lottery_check` to `1`.

---

## Configuration

Everything user-visible lives in `core/config.py`:

- **`GIFTS`** — the 36 sector labels in clockwise order. `app.js` draws the
  wheel generically from `config.gifts`, so any length works; the spin
  code recomputes `SPIN.step = 360 / gifts.length` on each spin.
- **`POOCH`** — label and default value for the "no prize" outcome.
  Pooch sectors alternate between the two `POOCH_COLORS`.
- **`PRIZE_COLORS`** — one accent colour per real prize, used **only** on
  wheel sectors. The result screen uses the gold palette from `style.css`.
- **`DB_FILENAME`, `WEB_DIR`, `PROJECT_ROOT`** — resolved relative to
  `core/config.py`, so the same paths work on desktop and inside the APK.

---

## Design notes

- **No page scroll.** `html, body { overflow: hidden }`, and every view is a
  flex column that reflows by viewport height. `style.css` has dedicated
  rules for short portrait, short landscape, and very tight landscape.
- **Reduced motion.** `prefers-reduced-motion: reduce` shortens the spin,
  disables confetti, and disables the view transition. Read once on load.
- **Persian / Arabic-Indic digits.** Accepted in both `#phone` and
  `#invoice`, converted to ASCII on the fly by `toAsciiDigits` in `app.js`
  and by `_DIGIT_TABLE` in `core/utils.py`.
- **No system font scaling on Android.**
  `settings.setTextZoom(100)` ignores the user's Android font-size setting
  so the wheel layout cannot overflow.
- **WebView is debuggable.** `WebView.setWebContentsDebuggingEnabled(True)`
  is left on so `chrome://inspect` works when needed.
- **Wheel physics.** Constant angular deceleration
  `x(t) = v0·t − ½·f·t²` drives the wheel; a damped harmonic oscillator
  (`POINTER.stiffness`, `POINTER.damping`) drives the pointer, kicked by
  each peg crossing. The winning sector's final resting offset is jittered
  by up to `±0.38` of a sector so the pointer does not always stop dead
  centre.
- **View state is client-side only.** `state.cfg`, `state.name`,
  `state.invoice` live in `app.js`. A process restart returns to the login
  screen — nothing sensitive is stored on the device.
- **Cache busting on desktop only.** `dev_server.py` adds
  `Cache-Control: no-store`; on Android the assets are inside the APK, so
  it is unnecessary.

---

## Testing the logic without a device

Because `backend.py` and `core/*` import neither Kivy nor `android`, you can
exercise the RPC directly:

```python
from backend import Backend

b = Backend("/tmp/test-lottery.db")
print(b.handle("config", {}))
print(b.handle("register", {
    "first": "Sara", "last": "Ahmadi",
    "phone": "09123456789", "invoice": "12345",
}))
print(b.handle("spin", {"invoice": "12345"}))
b.close()
```

`spin` on an already-used invoice returns
`{"ok": False, "error": "This invoice has already been used."}` — no UI
involved.
