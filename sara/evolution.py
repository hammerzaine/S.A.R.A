"""Evolution engine — S.A.R.A's hard-coded ability to learn and grow.

WHY THIS MODULE EXISTS (the whole point of the feature):
  The previous build's "growth" was SOFT — it relied on the model
  voluntarily emitting LEARNED:/REMEMBER: blocks, and everything landed
  in data/sara.db, which a clean build WIPES. So her growth was neither
  deterministic nor persistent across a reinstall.

  This module welds evolution into the SOURCE so it cannot be opted out of
  and survives a clean build:
    - SEED_SKILLS / SEED_FACTS  baked-in baseline knowledge re-inserted on
      first boot, so a clean install still "knows" the core environment and
      her own capabilities. (Hard-coded growth.)
    - seed_brain()              idempotent + versioned re-seed on first boot.
    - promote_procedures()      auto-promotes repeated successful actions into
      real skills — she grows from DOING, not from being told to.
    - extract_env_facts()       pulls durable environment facts out of real tool
      results (hosts, DBs) and remembers them.
    - capture_recovery()        turns a failure→recovery into a skill so she
      never makes the same mistake twice.

  None of this depends on the model's cooperation. She evolves because the
  code says so, every turn, on every boot.
"""

from __future__ import annotations

import re
import time

# Bump when the seed curriculum changes so old installs re-seed.
EVOLUTION_VERSION = 2
SEED_MARKER = f"S.A.R.A seed curriculum v{EVOLUTION_VERSION}"

# --- Baked-in baseline knowledge (hard-coded growth) -------------------------
# Re-seeded on first boot so a clean build's empty DB still "knows" the world.
# These are ENVIRONMENT FACTS and CAPABILITY DESCRIPTIONS — never credentials
# (those live in ~/SARA/credentials.json, chmod 600, and are never in source).
# Intentionally EMPTY. A clean brain learns the environment itself from real
# tool output (see extract_env_facts) — we do NOT pre-bake IPs, hostnames,
# database names, or user names. That keeps a packed build anonymous.
SEED_FACTS: list[str] = []

# The ONLY hard-coded skill. A clean brain boots knowing it can search the web
# to teach itself anything — every other skill is learned from doing. No IPs,
# hostnames, DB names, or user names are baked in.
SEED_SKILLS = [
    ("web-search", "Search the web to learn how to do anything",
     "When you don't know how to do a task, use web_search or web_fetch to look "
     "it up, then act on what you learn. This is how you teach yourself new "
     "skills — you are never blocked by not knowing; you search, learn, and do. "
     "Prefer web_search for factual/lookup questions and web_fetch for reading a "
     "specific page."),
]

# Local-loopback / link-local ranges we do NOT want to remember as "the
# environment" — they're noise, not discovery.
_IGNORE_IPS = (
    "127.0.0.1", "127.0.1.1", "0.0.0.0", "255.255.255.255",
    "::1", "169.254",
)


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "x"


# ---------------------------------------------------------------------------
def seed_brain(memory) -> dict:
    """Insert the baked-in baseline on first boot (or when the seed version
    advances). Idempotent + versioned: returns added counts and whether it had
    already been seeded. This is what makes a clean build's empty DB instantly
    'know' the core environment + her capabilities — hard-coded growth.
    """
    # Already seeded this version? Skip the work.
    if SEED_MARKER in memory.facts(2000):
        return {"added_facts": 0, "added_skills": 0, "already_seeded": True}

    added_facts = 0
    added_skills = 0
    for f in SEED_FACTS:
        if memory.remember(f, source="seed"):
            added_facts += 1
    for name, desc, body in SEED_SKILLS:
        if memory.add_skill(name, desc, body, source="seed"):
            added_skills += 1
    # Mark as seeded (a fact so it survives in the DB like any other memory).
    memory.remember(SEED_MARKER, source="seed")
    return {"added_facts": added_facts, "added_skills": added_skills,
            "already_seeded": False}


# ---------------------------------------------------------------------------
_ENV_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
_ENV_HOST_RE = re.compile(r"\b([a-z0-9][\w.-]*\.(?:local|lan|home|internal))\b",
                          re.I)
# DB-name markers. We also require the captured name NOT to be a common English
# word (the loose 'database <word>' form caught 'changed' from
# 'database changed to xnxx_db' — a false positive).
_DB_MARK_RE = re.compile(
    r"(?:create\s+database|use|database|schema|table_schema)\s+[`'\"]?"
    r"([a-z0-9_]{2,})", re.I)
_DB_UNDERSCORE_RE = re.compile(
    r"\b(?:to|is|=|into|from)\s+[`'\"]?([a-z0-9_]+_[a-z0-9_]+)[`'\"]?", re.I)
_DB_STOP = {
    "changed", "to", "name", "exists", "is", "the", "table", "schema",
    "database", "db", "a", "an", "in", "on", "of", "from", "use",
    "information_schema", "performance_schema", "mysql", "sys",
}


def extract_env_facts(memory, user_msg: str, result: dict) -> int:
    """Pull durable environment facts from a REAL tool result and remember them.
    Returns the number of NEW facts remembered. This is how she learns the
    landscape (which hosts/DBs exist) from doing real work — not from being
    told. Conservative on purpose: only IPs, LAN hostnames, and DB names.
    """
    if not isinstance(result, dict) or not result.get("ok"):
        return 0
    text = ""
    for k in ("output", "stdout", "description", "text", "hint", "host"):
        v = result.get(k)
        if isinstance(v, str):
            text += "\n" + v
    if not text.strip():
        return 0

    added = 0
    for m in _ENV_IP_RE.findall(text):
        if any(m.startswith(ig) for ig in _IGNORE_IPS):
            continue
        fact = f"Discovered IP {m} on the network (from tool output)."
        if memory.remember(fact, source="env-scan"):
            added += 1
    for m in _ENV_HOST_RE.findall(text):
        fact = f"Host '{m}' seen on the LAN (from tool output)."
        if memory.remember(fact, source="env-scan"):
            added += 1
    # Only credit DB names when the context is actually about a database.
    if "mariadb" in user_msg.lower() or "database" in text.lower() \
            or "db_import" in user_msg.lower():
        seen = set()
        for m in _DB_MARK_RE.findall(text):
            name = m.strip().lower()
            if name in _DB_STOP:
                continue
            seen.add(name)
        for m in _DB_UNDERSCORE_RE.findall(text):
            name = m.strip().lower()
            if name in _DB_STOP:
                continue
            seen.add(name)
        for name in seen:
            fact = f"MariaDB database '{name}' exists on 127.0.0.1."
            if memory.remember(fact, source="env-scan"):
                added += 1
    return added


# ---------------------------------------------------------------------------
def capture_recovery(memory, name: str, arg: str,
                     recovered_via: str | None = None) -> bool:
    """Record a failure→recovery as a skill so she never repeats the mistake.
    e.g. a shell command hit a permission wall and was rerouted via ssh_run as
    root. That is a lesson worth keeping. Returns True if a NEW skill was saved.
    """
    if not recovered_via:
        return False
    skill_name = f"recovery-{name}-{_slug(recovered_via)}"[:64]
    body = (f"When `{name}` failed, recovered via `{recovered_via}`.\n\n"
            f"Example arg that needed recovery:\n{arg[:300]}\n\n"
            f"If `{name}` returns a permission/privilege error, retry the "
            f"equivalent through `{recovered_via}` instead of giving up.")
    return memory.add_skill(
        skill_name,
        f"recovery path: {name} -> {recovered_via}",
        body, source="recovery")


# ---------------------------------------------------------------------------
def promote_procedures(memory, min_uses: int = 3) -> int:
    """Auto-promote procedures that have been reused enough into real skills.
    This is the 'grows from DOING' lever: repetition = a learned skill, welded
    into the code path. Returns the number of NEW skills created (refinements
    of existing skills don't count, so it is naturally idempotent).
    """
    procs = memory.all_procedures()
    promoted = 0
    for p in procs:
        if (p.get("used") or 0) < min_uses:
            continue
        tool = p["tool"]
        intent = (p.get("intent") or "").strip() or (p.get("arg") or "")[:80]
        skill_name = f"auto-{tool}-{_slug(intent or p.get('arg',''))[:20]}"[:64]
        body = (f"Repeated successful pattern (used {p['used']}x).\n\n"
                f"Tool: {tool}\n"
                f"Intent: {intent}\n"
                f"Example arg: {(p.get('arg') or '')[:300]}\n")
        if memory.add_skill(
                skill_name,
                f"auto-learned from {tool} (used {p['used']}x)",
                body, source="auto-promote"):
            promoted += 1
    return promoted
