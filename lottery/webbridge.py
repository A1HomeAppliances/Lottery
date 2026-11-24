"""
Android: full-screen WebView on top of the Kivy surface, plus a tiny RPC bridge.

No Java subclass / JavascriptInterface is needed:

  page -> app :  location.hash = "rpc/<id>/<base64url(json)>"
                 Python polls WebView.getUrl() (5x per second), runs
                 backend.handle() and answers with evaluateJavascript().
  app -> page :  window.__rpcReply(id, jsonString)   /   window.__back()

Pages are loaded from file:// (no local HTTP server, so no cleartext problem).
"""
import base64
import json
import logging
import re

from kivy.clock import Clock

from android.runnable import run_on_ui_thread
from jnius import autoclass

log = logging.getLogger("a1.webbridge")

PythonActivity = autoclass("org.kivy.android.PythonActivity")
WebView = autoclass("android.webkit.WebView")
WebViewClient = autoclass("android.webkit.WebViewClient")
LayoutParams = autoclass("android.view.ViewGroup$LayoutParams")
Color = autoclass("android.graphics.Color")
BuildVersion = autoclass("android.os.Build$VERSION")

_RPC = re.compile(r"#rpc/(\d+)/([A-Za-z0-9_-]*)$")


def decode_request(payload):
    padded = payload + "=" * (-len(payload) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    return data.get("m"), data.get("p") or {}


class WebBridge:

    def __init__(self, backend, on_exit):
        self.backend = backend
        self.on_exit = on_exit
        self._view = None
        self._active = False
        self._url = ""
        self._last_id = None
        self._poll = None

    # ---- public (Kivy thread) -----------------------------------------

    def open(self, url):
        if self._active:
            return
        self._active = True
        self._create(url)
        self._poll = Clock.schedule_interval(self._tick, 0.2)

    def back(self):
        """Android back button -> let the page decide what to do."""
        if self._view is not None:
            self._eval(self._view, "window.__back && window.__back()")

    def close(self):
        self._active = False
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        view, self._view = self._view, None
        if view is not None:
            self._destroy(view)

    def refocus(self):
        """بعد از resume شدن اپ، دوباره تمام‌صفحه را اعمال می‌کند."""
        if self._view is not None:
            self._reapply_fullscreen()

    # ---- polling -------------------------------------------------------

    def _tick(self, _dt):
        if not self._active:
            return False
        view = self._view
        if view is None:                 # still being created on the UI thread
            return True
        self._read_url(view)
        match = _RPC.search(self._url or "")
        if match and match.group(1) != self._last_id:
            self._last_id = match.group(1)
            self._serve(int(match.group(1)), match.group(2))
        return True

    def _serve(self, request_id, payload):
        try:
            method, params = decode_request(payload)
            result = self.backend.handle(method, params)
        except Exception:
            log.exception("bad request")
            method, result = None, {"ok": False, "error": "Bad request."}
        script = "window.__rpcReply(%d, %s)" % (
            request_id, json.dumps(json.dumps(result)))
        self._eval(self._view, script)
        if method == "exit":
            Clock.schedule_once(lambda _dt: self.on_exit(), 0.2)

    # ---- Android UI thread --------------------------------------------

    @run_on_ui_thread
    def _create(self, url):
        activity = PythonActivity.mActivity
        self._apply_fullscreen(activity)

        view = WebView(activity)

        settings = view.getSettings()
        settings.setJavaScriptEnabled(True)
        settings.setDomStorageEnabled(True)
        settings.setAllowFileAccess(True)       # file:// pages
        settings.setTextZoom(100)               # ignore system font scaling
        settings.setBuiltInZoomControls(False)

        view.setBackgroundColor(Color.parseColor("#0B0D12"))
        view.setOverScrollMode(2)               # OVER_SCROLL_NEVER
        view.setFocusable(True)                 # keyboard / text fields
        view.setFocusableInTouchMode(True)
        view.setWebViewClient(WebViewClient())  # keep navigation in-app
        try:
            view.setFitsSystemWindows(False)
        except Exception:
            pass
        WebView.setWebContentsDebuggingEnabled(True)   # chrome://inspect

        view.loadUrl(url)
        activity.addContentView(view, LayoutParams(-1, -1))
        view.requestFocus()
        self._view = view

    # ---- fullscreen helpers -------------------------------------------

    # ماسک‌ها برای سیستم‌یوآی قدیمی (API < 30)
    _UI_FULLSCREEN          = 0x00000004
    _UI_HIDE_NAVIGATION     = 0x00000200
    _UI_LAYOUT_FULLSCREEN   = 0x00000400
    _UI_LAYOUT_HIDE_NAV     = 0x00000002
    _UI_LAYOUT_STABLE       = 0x00000100
    _UI_IMMERSIVE_STICKY    = 0x00001000

    def _apply_fullscreen(self, activity):
        """نوار وضعیت و نوار ناوبری را در حالت immersive sticky پنهان می‌کند.
        باید فقط از روی UI thread صدا زده شود."""
        try:
            window = activity.getWindow()
            decor = window.getDecorView()

            if BuildVersion.SDK_INT >= 30:
                # مسیر مدرن (Android 11+)
                try:
                    window.setDecorFitsSystemWindows(False)
                except Exception:
                    pass
                controller = window.getInsetsController()
                if controller is not None:
                    controller.hide(0x7)            # statusBars | navigationBars | captionBar
                    controller.setSystemBarsBehavior(1)  # BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            else:
                # مسیر قدیمی
                decor.setSystemUiVisibility(
                    self._UI_FULLSCREEN
                    | self._UI_HIDE_NAVIGATION
                    | self._UI_LAYOUT_FULLSCREEN
                    | self._UI_LAYOUT_HIDE_NAV
                    | self._UI_LAYOUT_STABLE
                    | self._UI_IMMERSIVE_STICKY
                )
        except Exception:
            log.exception("failed to enable immersive fullscreen")

    @run_on_ui_thread
    def _reapply_fullscreen(self):
        try:
            self._apply_fullscreen(PythonActivity.mActivity)
        except Exception:
            log.exception("fullscreen reapply failed")

    @run_on_ui_thread
    def _read_url(self, view):
        self._url = view.getUrl()

    @run_on_ui_thread
    def _eval(self, view, script):
        if view is not None:
            view.evaluateJavascript(script, None)

    @run_on_ui_thread
    def _destroy(self, view):
        parent = view.getParent()
        if parent is not None:
            parent.removeView(view)
        view.destroy()
