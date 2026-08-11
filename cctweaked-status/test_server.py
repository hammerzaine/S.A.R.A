#!/usr/bin/env python3
"""Ad-hoc unit checks for the CCTweaked status backend (no test framework)."""
import json, threading, time, urllib.request, urllib.parse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server

OK = True
def check(label, cond, detail=""):
    global OK
    if not cond: OK = False
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))

# 1) ingest single record
r = server.ingest({"name":"A","id":1,"type":"turtle","fuel":100,"state":"running"})
check("ingest single sets name", r["name"]=="A")
check("ingest stamps last_seen", isinstance(r["last_seen"], float) and r["last_seen"]>0)

# 2) GET snapshot via handler logic (call snapshot directly)
snap = server.snapshot()
check("snapshot returns 1 computer", len(snap)==1, f"got {len(snap)}")

# 3) offline expiry: push with old last_seen should go offline after TTL
server.ingest({"name":"B","online":True,"state":"running"})
with server._lock:
    server._computers["B"]["last_seen"] = time.time() - (server.ONLINE_TTL + 5)
expired = [c for c in server.snapshot() if c["name"]=="B"][0]
check("TTL marks stale computer offline", expired["online"] is False and expired["state"]=="offline")

# 4) name fallback to id
r2 = server.ingest({"id":42})
check("name falls back to id", r2["name"]=="42")

# 5) invalid payload rejected (no name/id)
try:
    server.ingest({})
    check("rejects empty payload", False)
except ValueError:
    check("rejects empty payload", True)

# 6) live HTTP round-trip on the real port
import subprocess
proc = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),"server.py")],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
try:
    # POST a status
    req = urllib.request.Request("http://127.0.0.1:8011/api/status",
            data=json.dumps({"name":"WebTest","type":"computer","state":"idle","data":{"k":1}}).encode(),
            headers={"Content-Type":"application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=5).read().decode()
    check("HTTP POST /api/status ok", '"ok": true' in resp or '"stored": 1' in resp, resp[:60])
    # GET all
    got = json.loads(urllib.request.urlopen("http://127.0.0.1:8011/api/status", timeout=5).read())
    names = [c["name"] for c in got]
    check("HTTP GET lists WebTest", "WebTest" in names, str(names))
    # GET one
    one = json.loads(urllib.request.urlopen("http://127.0.0.1:8011/api/status/WebTest", timeout=5).read())
    check("HTTP GET /api/status/WebTest", one["name"]=="WebTest")
    # health
    h = json.loads(urllib.request.urlopen("http://127.0.0.1:8011/api/health", timeout=5).read())
    check("HTTP GET /api/health", h.get("ok") is True)
finally:
    proc.terminate()
    proc.wait()

print()
print("RESULT:", "ALL CHECKS PASSED - CCTweaked status backend verified" if OK else "VERIFICATION FAILED")
sys.exit(0 if OK else 1)
