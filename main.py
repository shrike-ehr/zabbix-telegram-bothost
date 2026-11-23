#!/usr/bin/env python3
import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ["ZABBIX_WEBHOOK_SECRET"]
PORT = int(os.environ.get("PORT", "3000"))


def pick_mark(payload: dict) -> str:
    """Возвращает эмодзи по полям event_value / event_update_status."""
    update_status = str(payload.get("event_update_status", "")).strip()
    event_value = str(payload.get("event_value", "")).strip()

    if update_status == "1":
        return "🔵"          # UPDATE ACTION
    if event_value == "1":
        return "🔴"          # PROBLEM
    if event_value == "0":
        return "🟢"          # RESOLVED
    return "⚪"              # неизвестно / нет данных


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
        print(f"--> ПОЛУЧЕН POST: {self.path}", flush=True)
        print(f"--> Заголовки: {self.headers}", flush=True)
        
        path = self.path.split("?", 1)[0]
        m = re.match(r"^/zabbix/bot([^/]+)/sendMessage$", path)
        if not m:
            print("--> ОШИБКА: Неверный путь (regex не совпал)", flush=True)
            self._send(404, "not found")
            return
        if self.headers.get("X-Webhook-Secret", "") != SECRET:
            print("--> ОШИБКА: Неверный секрет", flush=True)
            self._send(403, "forbidden")
            return

        api_token = m.group(1)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            print("--> ОШИБКА: Невалидный JSON", flush=True)
            self._send(400, "bad json")
            return

        print(f"--> Тело запроса: {payload}", flush=True)
        
        mark = pick_mark(payload)
        text = payload.get("text", "")
        payload["text"] = f"{mark} {text}" if text else mark

        for key in ("api_token", "event_value", "event_update_status", "event_nseverity", "event_severity", "event_update_nseverity", "event_update_severity", "event_source", "event_tags", "tls_verify"):
            payload.pop(key, None)

        try:
            print("--> Отправляем в Telegram...", flush=True)
            send_telegram(api_token, payload)
            print("--> Telegram ответил успешно!", flush=True)
        except Exception as exc:
            print(f"--> ОШИБКА TELEGRAM: {exc}", flush=True)
            self._send(502, "telegram error")
            return
        self._send(200, "ok")

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()