#!/usr/bin/env python3
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ["ZABBIX_WEBHOOK_SECRET"]
PORT = int(os.environ.get("PORT", "3000"))

def pick_mark(payload: dict) -> str:
    update_status = str(payload.get("event_update_status", "")).strip()
    event_value = str(payload.get("event_value", "")).strip()

    if update_status == "1":
        return "🔵"
    if event_value == "1":
        return "🔴"
    if event_value == "0":
        return "🟢"
    return "⚪"

def send_telegram(api_token: str, payload: dict) -> None:
    url = f"https://api.telegram.org/bot{api_token}/sendMessage"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str = "ok") -> None:
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/health":
            self._send(200, "ok")
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/zabbix":
            self._send(404, "not found")
            return

        if self.headers.get("X-Webhook-Secret", "") != SECRET:
            self._send(403, "forbidden")
            return

        # Забираем токен из заголовка (чтобы не пихать его в длинный URL)
        api_token = self.headers.get("X-Api-Token", "")
        if not api_token:
            self._send(400, "missing api_token header")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._send(400, "bad json")
            return

        # Маркировка
        mark = pick_mark(payload)
        text = payload.get("text", "")
        payload["text"] = f"{mark} {text}" if text else mark

        # Очистка
        for key in ("api_token", "event_value", "event_update_status", "event_nseverity", "event_severity", "event_update_nseverity", "event_update_severity", "event_source", "event_tags", "tls_verify"):
            payload.pop(key, None)

        try:
            send_telegram(api_token, payload)
        except Exception as exc:
            print("telegram error:", exc)
            self._send(502, "telegram error")
            return
        self._send(200, "ok")

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"listening on 0.0.0.0:{PORT}")
    server.serve_forever()