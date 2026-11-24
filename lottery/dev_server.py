"""Desktop preview: serves ./web and the same RPC API on http://127.0.0.1:8765"""
import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from backend import Backend
from core.config import DB_FILENAME, PROJECT_ROOT, WEB_DIR

PORT = 8765


class Handler(SimpleHTTPRequestHandler):

    backend = None

    def translate_path(self, path):
        if path.startswith("/assets/"):
            return str(PROJECT_ROOT / path.lstrip("/"))
        return super().translate_path(path)

    def do_POST(self):
        if self.path != "/api":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(size) or b"{}")
            result = self.backend.handle(data.get("m"), data.get("p"))
        except Exception:
            result = {"ok": False, "error": "Bad request."}
        body = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")     # always fresh while editing
        super().end_headers()

    def log_message(self, *_args):
        pass


def main(open_browser=True):
    Handler.backend = Backend(PROJECT_ROOT / DB_FILENAME)
    handler = partial(Handler, directory=str(WEB_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"A1 Lucky Spin dev server -> {url}   (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        Handler.backend.close()


if __name__ == "__main__":
    main()
