#!/usr/bin/env python3
"""
CCTweaked status backend.

Receives status pushes from in-game CC:T computers (Lua http.POST) and serves
them to the web dashboard. Pure stdlib (http.server) — no external deps, so it
runs anywhere Python 3.8+ exists.

Endpoints
  POST /api/status          -> a CC:T computer pushes its status JSON here
  GET  /api/status          -> all computers (JSON list)
  GET  /api/status/<name>   -> one computer (JSON)
  GET  /api/health          -> {"ok": true}
  GET  /                     -> serves the dashboard (index.html)

Status JSON shape (from CC:T Lua, see cc_status.lua):
  {
    "name":     "ReactorCtrl",          # unique computer name
    "id":       12,                      # CC:T computer ID
    "type":     "computer"|"turtle",
    "label":    "Reactor Controller",    # optional human label
    "online":   true,
    "state":    "running"|"idle"|"error"|"offline",
    "fuel":     1420,                    # turtle fuel (optional)
    "position": {"x":12,"y":64,"z":-8}, # optional gps coords
    "data":     {...arbitrary per-computer metrics...}
  }

The backend stamps server_time + last_seen on every record and expires
computers not heard from in ONLINE_TTL seconds (marked offline automatically).
"""
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# Seconds after which a computer with no new push is marked offline.
ONLINE_TTL = 60
# Bind address / port (Apache on .225 proxies /minecraft/cctweak/* here).
HOST = "0.0.0.0"
PORT = 8011

_lock = threading.Lock()
_computers = {}


def _now():
    return time.time()


def ingest(payload: dict) -> dict:
    """Validate + store one status push. Returns the stored record."""
    name = str(payload.get("name") or payload.get("id") or "unknown").strip()
    if not name or name == "unknown":
        raise ValueError("status must include a 'name' (or 'id')")
    rec = {
        "name": name,
        "id": payload.get("id"),
        "type": payload.get("type", "computer"),
        "label": payload.get("label", ""),
        "online": bool(payload.get("online", True)),
        "state": str(payload.get("state", "running")),
        "fuel": payload.get("fuel"),
        "position": payload.get("position"),
        "data": payload.get("data", {}) or {},
        "server_time": _now(),
        "last_seen": _now(),
    }
    with _lock:
        _computers[name] = rec
    return rec


def snapshot() -> list:
    """All computers, with TTL-based offline expiry applied."""
    out = []
    with _lock:
        for rec in _computers.values():
            age = _now() - rec["last_seen"]
            if rec["online"] and age > ONLINE_TTL:
                rec = dict(rec)
                rec["online"] = False
                rec["state"] = "offline"
            out.append(rec)
    # freshest first
    out.sort(key=lambda r: r["last_seen"], reverse=True)
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, obj=None, body=b""):
        if obj is not None:
            body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # CORS: allow the dashboard origin (handy for local dev / mixed origins)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path in ("", "/"):
            self._serve_dashboard()
            return
        if path == "/api/health":
            return self._send(200, {"ok": True})
        if path == "/api/status":
            return self._send(200, snapshot())
        if path.startswith("/api/status/"):
            name = path.split("/")[-1]
            with _lock:
                rec = _computers.get(name)
            if not rec:
                return self._send(404, {"error": "not found", "name": name})
            age = _now() - rec["last_seen"]
            if rec["online"] and age > ONLINE_TTL:
                rec = dict(rec)
                rec["online"] = False
                rec["state"] = "offline"
            return self._send(200, rec)
        self._send(404, {"error": "no such route"})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/api/status":
            payload = self._read_json()
            # CC:T may send a single object or a list of objects.
            items = payload if isinstance(payload, list) else [payload]
            stored = []
            for item in items:
                try:
                    stored.append(ingest(item))
                except (ValueError, TypeError) as e:
                    return self._send(400, {"error": str(e)})
            return self._send(200, {"ok": True, "stored": len(stored)})
        self._send(404, {"error": "no such route"})

    def do_HEAD(self):
        self._send(200)

    def _serve_dashboard(self):
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        idx = os.path.join(here, "index.html")
        try:
            with open(idx, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            body = b"dashboard missing"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # quiet


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"CCTweaked status backend on http://{HOST}:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
