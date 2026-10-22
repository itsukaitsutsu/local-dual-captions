"""Serve the bundled local-file player. No files are uploaded to this server."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser


def main():
    directory = Path(__file__).resolve().parents[1] / "tools"
    url = "http://127.0.0.1:8090/offline-test.html"
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    with ThreadingHTTPServer(("127.0.0.1", 8090), handler) as server:
        print(f"Open in Chrome: {url}\nChoose your downloaded Japanese media file.\nCtrl+C stops this local test-page server.", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
