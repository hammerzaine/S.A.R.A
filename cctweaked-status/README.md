# CCTweaked Status UI

Pull live status from in-game CC:T (ComputerCraft: Tweaked) computers into a
web dashboard.

## Architecture (push-based)
- Each CC:T computer runs `cc_status.lua`, which POSTs a status JSON blob to the
  backend every ~15s.
- Backend (`server.py`, pure stdlib, port 8011) stores the latest status per
  computer, stamps `last_seen`, and auto-marks a computer `offline` if it hasn't
  reported within `ONLINE_TTL` seconds (default 60).
- Dashboard (`index.html`) polls `GET /api/status` every 4s and renders a card
  per computer (online/offline, state, fuel, GPS position, raw data).
- Apache on `192.168.2.225` proxies `/minecraft/cctweak*` → `192.168.2.176:8011`
  (same pattern as `/mtg`). So the public URL is:
  `http://192.168.2.225/minecraft/cctweak`

## Run (backend already installed as a systemd --user service)
    systemctl --user status cctweaked-status
    systemctl --user restart cctweaked-status
    # logs: journalctl --user -u cctweaked-status

## Wire a real CC:T computer
1. Copy `cc_status.lua` onto a CC:T computer (pastebin/forge, or `edit cc_status`).
2. Edit the top CONFIG block:
     BACKEND = "http://192.168.2.176:8011/api/status"
     NAME    = a unique name per computer (e.g. "ReactorCtrl")
     LABEL   = human label (optional)
     REPORT_MS = how often to report (ms)
3. `label <NAME>` on the computer, then `cc_status` to start it.
4. It shows up on the dashboard within ~REPORT_MS.

`data` in the Lua `collect()` function is where you add per-computer metrics
(e.g. read a peripheral: `peripheral.call("top","getHeat")`).

## API
    POST /api/status            -> push status (object or list)
    GET  /api/status            -> all computers
    GET  /api/status/<name>     -> one computer
    GET  /api/health            -> {"ok": true}

## Test
    python3 test_server.py      -> 10 ad-hoc checks (ingest, TTL, HTTP round-trip)
