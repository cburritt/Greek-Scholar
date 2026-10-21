# serves the frontend for local development and tells the browser not to cache anything,
# so a code change shows up on the next reload
# usage, from the repo root: python serve_frontend.py

import functools
import http.server
from pathlib import Path

PORT = 5500


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


handler = functools.partial(NoCacheHandler, directory=str(Path(__file__).parent / "frontend"))
with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as server:
    print(f"frontend at http://localhost:{PORT}")
    server.serve_forever()
