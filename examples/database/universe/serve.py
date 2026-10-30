"""Serves a folder on 127.0.0.1 telling the browser never to keep a copy (prototypes change often)."""
import functools, http.server, sys

class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

port, folder = int(sys.argv[1]), sys.argv[2]
http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(NoCache, directory=folder)).serve_forever()
