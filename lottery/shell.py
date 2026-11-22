"""Android entry point: a blank Kivy window whose only job is to host the WebView."""
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.widget import Widget

from backend import Backend
from core.config import APP_TITLE, DB_FILENAME, WEB_DIR
from webbridge import WebBridge


class ShellApp(App):

    title = APP_TITLE

    def build(self):
        Window.clearcolor = (11 / 255, 13 / 255, 18 / 255, 1)   # #0B0D12

        # user_data_dir survives app updates (the app folder does not).
        folder = Path(self.user_data_dir)
        folder.mkdir(parents=True, exist_ok=True)
        self.backend = Backend(folder / DB_FILENAME)
        self.web = WebBridge(self.backend, on_exit=self.stop)

        Window.bind(on_keyboard=self._on_key)
        return Widget()

    def on_start(self):
        url = (WEB_DIR / "index.html").resolve().as_uri()
        Clock.schedule_once(lambda _dt: self.web.open(url), 0.2)

    def _on_key(self, _window, key, *_args):
        if key == 27:                       # Android back button
            self.web.back()
            return True
        return False

    def on_pause(self):
        return True

    def on_stop(self):
        self.web.close()
        self.backend.close()
