
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import yt_dlp

PORT = int(os.environ.get("PORT", "10000"))
API_KEY = os.environ.get("API_KEY", "")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "")


def ydl_options():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
    }
    if COOKIE_FILE and os.path.isfile(COOKIE_FILE):
        opts["cookiefile"] = COOKIE_FILE
    return opts


def is_youtube_url(url):
    host = (urlparse(url).hostname or "").lower()
    return host in {
        "youtube.com", "www.youtube.com",
        "m.youtube.com", "music.youtube.com",
        "youtu.be", "www.youtube-nocookie.com",
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if API_KEY and self.headers.get("X-API-Key") != API_KEY:
            return self.send_json(401, {"error": "Invalid API key"})

        if parsed.path == "/health":
            return self.send_json(200, {"status": "ok"})

        if parsed.path == "/search":
            query = params.get("q", [""])[0].strip()
            if not query:
                return self.send_json(400, {"error": "Missing q parameter"})

            try:
                with yt_dlp.YoutubeDL(ydl_options()) as ydl:
                    result = ydl.extract_info(
                        f"ytsearch10:{query}", download=False
                    )
                entries = result.get("entries") or []
                songs = [
                    {
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "duration": item.get("duration"),
                        "thumbnail": item.get("thumbnail"),
                        "url": item.get("webpage_url"),
                    }
                    for item in entries if item
                ]
                return self.send_json(200, {"results": songs})
            except Exception as exc:
                return self.send_json(502, {"error": str(exc)})

        if parsed.path == "/stream":
            url = params.get("url", [""])[0].strip()
            if not url or not is_youtube_url(url):
                return self.send_json(
                    400, {"error": "Provide a valid YouTube URL"}
                )

            try:
                with yt_dlp.YoutubeDL(ydl_options()) as ydl:
                    info = ydl.extract_info(url, download=False)

                formats = info.get("formats") or []
                audio_formats = [
                    f for f in formats
                    if f.get("url") and f.get("acodec") != "none"
                    and f.get("vcodec") == "none"
                ]
                best = audio_formats[-1] if audio_formats else next(
                    (f for f in reversed(formats)
                     if f.get("url") and f.get("acodec") != "none"),
                    None,
                )

                if not best:
                    return self.send_json(
                        502, {"error": "No audio format found"}
                    )

                return self.send_json(200, {
                    "id": info.get("id"),
                    "title": info.get("title"),
                    "duration": info.get("duration"),
                    "thumbnail": info.get("thumbnail"),
                    "audio_url": best["url"],
                    "ext": best.get("ext"),
                    "protocol": best.get("protocol"),
                    "headers": best.get("http_headers", {}),
                    "note": "Audio URL is temporary and may expire."
                })
            except Exception as exc:
                return self.send_json(502, {"error": str(exc)})

        return self.send_json(404, {
            "error": "Not found",
            "endpoints": ["/health", "/search?q=query", "/stream?url=YouTube_URL"]
        })

    def log_message(self, fmt, *args):
        print(fmt % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"yt-dlp API listening on port {PORT}")
    server.serve_forever()
