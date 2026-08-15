"""Memory — conversation history, durable facts, and skill growth.

Three stores, one SQLite file:

  turns    every message, for conversational continuity
  facts    durable things she has learned ABOUT the user or the world
  skills   procedures she has taught herself, with a usage counter

HARD RULE: never store an error/failure string as an `assistant` turn.
Assistant turns are replayed into the prompt as context, and the model will
parrot stale failures back at the user forever. Failures go in as role='system'.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    role    TEXT NOT NULL,
    content TEXT NOT NULL,
    ts      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fact    TEXT NOT NULL UNIQUE,
    source  TEXT,
    ts      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    body        TEXT NOT NULL,
    source      TEXT,
    uses        INTEGER DEFAULT 0,
    created     REAL NOT NULL,
    last_used   REAL
);
CREATE TABLE IF NOT EXISTS procedures (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL UNIQUE,
    intent    TEXT,
    tool      TEXT NOT NULL,
    arg       TEXT,
    outcome   TEXT,
    used      INTEGER DEFAULT 0,
    created   REAL NOT NULL,
    last_used REAL
);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);
"""

BANNED_ASSISTANT_PREFIXES = (
    "All providers failed",
    "[provider-failure]",
    "Traceback (most recent call last)",
)


class Memory:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # -- turns -------------------------------------------------------------
    def log(self, role: str, content: str) -> None:
        if not content:
            return
        text = str(content)
        if role == "assistant" and text.lstrip().startswith(
                BANNED_ASSISTANT_PREFIXES):
            role = "system"
        self.db.execute(
            "INSERT INTO turns (role, content, ts) VALUES (?,?,?)",
            (role, text, time.time()))
        self.db.commit()

    def recent(self, n: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?",
            (n,)).fetchall()
        return [{"role": r["role"], "content": r["content"]}
                for r in reversed(rows)]

    def turn_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM turns").fetchone()[0]

    # -- facts -------------------------------------------------------------
    def remember(self, fact: str) -> bool:
        fact = fact.strip()
        if not fact:
            return False
        try:
            self.db.execute(
                "INSERT INTO facts (fact, source, ts) VALUES (?,?,?)",
                (fact, "conversation", time.time()))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def list_facts(self) -> list[str]:
        return [r["fact"] for r in self.db.execute(
            "SELECT fact FROM facts ORDER BY ts DESC")]

    # -- skills ------------------------------------------------------------
    def add_skill(self, name: str, description: str, body: str) -> bool:
        name = name.strip()
        if not name:
            return False
        existing = self.db.execute(
            "SELECT id, body FROM skills WHERE name = ?", (name,)).fetchone()
        now = time.time()
        if existing:
            self.db.execute(
                "UPDATE skills SET body = ?, description = ?, last_used = ? "
                "WHERE id = ?",
                (body, description, now, existing["id"]))
            self.db.commit()
            return False
        self.db.execute(
            "INSERT INTO skills (name, description, body, source, uses, "
            "created, last_used) VALUES (?,?,?,?,0,?,?)",
            (name, description, body, "conversation", now, now))
        self.db.commit()
        return True

    def bump_skill(self, name: str) -> None:
        self.db.execute(
            "UPDATE skills SET uses = uses + 1, last_used = ? WHERE name = ?",
            (time.time(), name))

    def list_skills(self, limit: int = 0) -> list[dict]:
        rows = self.db.execute(
            "SELECT name, description, uses FROM skills "
            "ORDER BY uses DESC, created DESC").fetchall()
        out = [{"name": r["name"], "description": r["description"],
                "uses": r["uses"]} for r in rows]
        return out[:limit] if limit else out

    def find_skills(self, query: str) -> list[dict]:
        """Loose topical match — used to recall a prior procedure."""
        STOP = {"the", "a", "an", "and", "or", "to", "of", "that", "this",
                "with", "for", "you", "me", "i", "can", "is", "it", "in", "on"}
        toks = {t for t in re.findall(r"[a-z]{4,}", query.lower()) if t not in
                STOP}
        hits = []
        for s in self.list_skills():
            name = s["name"].lower()
            body = s["description"].lower()
            if any(t in name for t in toks):
                hits.append(s)
                continue
            # need >=2 distinct topical words in the body to count (avoids the
            # single-stopword false positive that plagued v3)
            if sum(1 for t in toks if t in body) >= 2:
                hits.append(s)
        return hits

    # -- procedures (auto-learned actions) ----------------------------------
    def add_procedure(self, signature: str, tool: str, arg: str,
                      outcome: str) -> bool:
        try:
            self.db.execute(
                "INSERT INTO procedures (signature, tool, arg, outcome, used, "
                "created, last_used) VALUES (?,?,?,?,1,?,?)",
                (signature, tool, arg[:2000], outcome[:500],
                 time.time(), time.time()))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            self.db.execute(
                "UPDATE procedures SET used = used + 1, last_used = ? "
                "WHERE signature = ?", (time.time(), signature))
            self.db.commit()
            return False

    def promote_procedures(self, min_uses: int = 3) -> int:
        """Auto-promote heavily-reused procedures into real skills."""
        promoted = 0
        rows = self.db.execute(
            "SELECT signature, tool, arg, outcome FROM procedures "
            "WHERE used >= ?", (min_uses,)).fetchall()
        for r in rows:
            name = f"auto:{r['tool']}"
            body = f"On {r['tool']} with arg like:\n{r['arg']}\n\n" \
                   f"Outcome: {r['outcome']}"
            if self.add_skill(name, f"repeated {r['tool']} action", body):
                promoted += 1
        return promoted

    # -- maintenance -------------------------------------------------------
    def stats(self) -> dict:
        return {
            "turns": self.turn_count(),
            "facts": self.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
            "skills": self.db.execute(
                "SELECT COUNT(*) FROM skills").fetchone()[0],
        }

    def reset(self) -> dict:
        before = self.stats()
        self.db.executescript(
            "DELETE FROM turns; DELETE FROM facts; DELETE FROM skills; "
            "DELETE FROM procedures;")
        self.db.commit()
        return {"before": before, "after": self.stats()}
