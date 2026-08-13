"""Memory — conversation history, durable facts, and skill growth.

Three stores, one SQLite file:

  turns    every message, for conversational continuity
  facts    durable things she has learned ABOUT the user or the world
  skills   procedures she has taught herself, with a usage counter

The skills table is what makes growth *visible*: `/skills` shows what she knows
and how often each one has earned its keep.

HARD RULE learned from the previous build: never store an error/failure string
as an `assistant` turn. Assistant turns are replayed into the prompt as
context, and the model will parrot stale failures back at the user forever.
Failures go in as role='system'.
"""

from __future__ import annotations

import hashlib
import json
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
        # Guard: never let a failure masquerade as an assistant turn.
        if role == "assistant" and text.lstrip().startswith(
                BANNED_ASSISTANT_PREFIXES):
            role = "system"
        self.db.execute(
            "INSERT INTO turns (role, content, ts) VALUES (?,?,?)",
            (role, text, time.time()))
        self.db.commit()
        # Steady-state 2GB guard: evict oldest non-active turns as we go so
        # the history never balloons unbounded. Never touches the newest
        # KEEP_RECENT_TURNS (the live thread you're switching on).
        self._maybe_trim()

    def recent(self, n: int = 12) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM turns WHERE role IN ('user','assistant')"
            " ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [{"role": r["role"], "content": r["content"]}
                for r in reversed(rows)]

    def turn_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) c FROM turns").fetchone()["c"]

    # -- facts -------------------------------------------------------------
    def remember(self, fact: str, source: str = "conversation") -> bool:
        fact = fact.strip()
        if not fact:
            return False
        try:
            self.db.execute(
                "INSERT INTO facts (fact, source, ts) VALUES (?,?,?)",
                (fact, source, time.time()))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # already known

    def facts(self, n: int = 40) -> list[str]:
        rows = self.db.execute(
            "SELECT fact FROM facts ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [r["fact"] for r in rows]

    def fact_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"]

    def forget(self, needle: str) -> int:
        cur = self.db.execute("DELETE FROM facts WHERE fact LIKE ?",
                              (f"%{needle}%",))
        self.db.commit()
        return cur.rowcount

    # -- skills ------------------------------------------------------------
    def add_skill(self, name: str, description: str, body: str,
                  source: str = "self-taught") -> bool:
        """Store a new skill. Returns False if she already knew it."""
        name = name.strip().lower().replace(" ", "-")[:64]
        if not name or not body.strip():
            return False
        try:
            self.db.execute(
                "INSERT INTO skills (name, description, body, source, created)"
                " VALUES (?,?,?,?,?)",
                (name, description.strip(), body.strip(), source, time.time()))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            # Already exists — refresh the body so skills improve over time.
            self.db.execute(
                "UPDATE skills SET body=?, description=? WHERE name=?",
                (body.strip(), description.strip(), name))
            self.db.commit()
            return False

    def get_skill(self, name: str) -> dict | None:
        r = self.db.execute("SELECT * FROM skills WHERE name=?",
                            (name.strip().lower(),)).fetchone()
        return dict(r) if r else None

    # Words that carry no topical signal. Without this, "...website that I can
    # communicate with" matched a Zig skill on the single word "that".
    STOP = {
        "that", "this", "with", "what", "when", "where", "your", "yours",
        "have", "has", "had", "been", "being", "them", "they", "their",
        "there", "then", "than", "from", "into", "about", "would", "could",
        "should", "cant", "cannot", "dont", "doesnt", "isnt", "wont", "want",
        "need", "make", "made", "some", "any", "all", "just", "like", "know",
        "think", "tell", "show", "give", "take", "come", "over", "very",
        "much", "more", "most", "also", "even", "only", "same", "such",
        "here", "still", "back", "good", "well", "sure", "yeah", "okay",
        "you", "yours", "our", "ours", "the", "and", "for", "but", "not",
        "can", "cant", "use", "used", "get", "got", "how", "why", "who",
        "was", "are", "its", "it's", "one", "two", "out", "off", "now",
        "did", "does", "done", "will", "shall", "may", "might", "must",
    }

    def find_skills(self, query: str, limit: int = 3) -> list[dict]:
        """Cheap keyword relevance — good enough to surface a known procedure.

        Requires a real topical hit: stopwords are stripped, and a single weak
        match is rejected. A false positive is worse than no match, because she
        announces "I've done this before" and then talks nonsense.
        """
        words = {w.strip(".,!?;:'\"") for w in query.lower().split()
                 if len(w) > 2}
        words -= self.STOP
        if not words:
            return []
        rows = self.db.execute("SELECT * FROM skills").fetchall()
        scored = []
        for r in rows:
            hay = f"{r['name']} {r['description']} {r['body'][:400]}".lower()
            hits = {w for w in words if w in hay}
            if not hits:
                continue
            # Need either 2+ distinct topical words, or one strong hit that
            # appears in the skill's NAME (not just buried in the body).
            strong = any(w in r["name"].lower() for w in hits)
            if len(hits) < 2 and not strong:
                continue
            scored.append((len(hits) + (2 if strong else 0), dict(r)))
        scored.sort(key=lambda x: (-x[0], -x[1]["uses"]))
        return [s[1] for s in scored[:limit]]

    def use_skill(self, name: str) -> None:
        self.db.execute(
            "UPDATE skills SET uses = uses + 1, last_used = ? WHERE name = ?",
            (time.time(), name.strip().lower()))
        self.db.commit()

    def rename_skill(self, old: str, new: str) -> tuple[bool, str]:
        """Rename a skill, keeping its body and use-count.

        Returns (ok, message). Names are normalised the same way add_skill
        does it, so /rename and self-taught names can't drift apart.
        """
        old = old.strip().lower()
        new = new.strip().lower().replace(" ", "-")[:64]
        if not new:
            return False, "new name is empty"
        if not self.get_skill(old):
            return False, f"no skill called '{old}'"
        if old == new:
            return False, "that's already its name"
        if self.get_skill(new):
            return False, f"'{new}' is already taken"
        self.db.execute("UPDATE skills SET name=? WHERE name=?", (new, old))
        self.db.commit()
        return True, f"'{old}' is now '{new}'"

    def all_skills(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM skills ORDER BY uses DESC, created DESC").fetchall()
        return [dict(r) for r in rows]

    def skill_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) c FROM skills").fetchone()["c"]

    # -- procedures (HARD-CODED learning: HOW she solved things) ----------
    def record_procedure(self, intent: str, tool: str, arg: str,
                         outcome: str = "") -> bool:
        """Persist a successful action so S.A.R.A remembers HOW she solved a
        task and can reuse it next session. Deduped by a signature of
        (tool + normalised arg) — the same logical call across sessions
        collides, so repetition just bumps a use-counter (she gets *better*
        at a known procedure instead of spawning duplicates). Returns True
        if this is a brand-new procedure (genuine growth), False if already
        known.
        """
        tool = (tool or "").strip().lower()
        if not tool:
            return False
        norm = re.sub(r"\s+", " ", (arg or "").strip())
        if not norm:
            return False
        sig = f"{tool}::{norm[:300]}"
        signature = hashlib.sha1(sig.encode()).hexdigest()[:16]
        outcome = (outcome or "").strip()[:400]
        intent = (intent or "").strip()[:300]
        now = time.time()
        try:
            self.db.execute(
                "INSERT INTO procedures "
                "(signature, intent, tool, arg, outcome, created) "
                "VALUES (?,?,?,?,?,?)",
                (signature, intent, tool, norm[:400], outcome, now))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            # Already known — she's refining a skill she already has.
            self.db.execute(
                "UPDATE procedures SET used = used + 1, last_used = ? "
                "WHERE signature = ?", (now, signature))
            self.db.commit()
            return False

    def find_procedure(self, query: str, limit: int = 3) -> list[dict]:
        """Keyword recall of a past procedure, mirroring find_skills."""
        words = {w.strip(".,!?;:'\"") for w in query.lower().split()
                 if len(w) > 2}
        words -= self.STOP
        if not words:
            return []
        rows = self.db.execute("SELECT * FROM procedures").fetchall()
        scored = []
        for r in rows:
            hay = (f"{r['intent']} {r['tool']} {r['arg'][:200]} "
                   f"{r['outcome']}").lower()
            hits = {w for w in words if w in hay}
            if not hits:
                continue
            scored.append((len(hits), dict(r)))
        scored.sort(key=lambda x: (-x[0], -x[1]["used"]))
        return [s[1] for s in scored[:limit]]

    def use_procedure(self, signature: str) -> None:
        self.db.execute(
            "UPDATE procedures SET used = used + 1, last_used = ? "
            "WHERE signature = ?", (time.time(), signature))
        self.db.commit()

    def all_procedures(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM procedures ORDER BY used DESC, created DESC"
            ).fetchall()]

    def procedure_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) c FROM procedures"
                               ).fetchone()["c"]

    def stats(self) -> dict:
        return {
            "turns": self.turn_count(),
            "facts": self.fact_count(),
            "skills": self.skill_count(),
            "procedures": self.procedure_count(),
        }

    # -- task state (the spine of a cross-device handoff) -----------------
    # A tiny JSON ledger of the STANDING OBJECTIVE + what's done/next, so a
    # fresh client (or new day) can be told "I know where we are" without a
    # re-brief. Persisted next to the DB in data/task_state.json.
    def get_task_state(self) -> dict | None:
        p = self.path.parent / "task_state.json"
        if not p.exists():
            return None
        try:
            obj = json.loads(p.read_text())
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def set_task_state(self, state: dict | None) -> None:
        p = self.path.parent / "task_state.json"
        if state is None:
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
            return
        state = dict(state)
        state["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        p.write_text(json.dumps(state, indent=2))

    # -- 2GB trim guard ---------------------------------------------------
    # The user asked: once the conversation history reaches ~2GB, start
    # trimming the oldest completed conversations as we go. We evict the
    # OLDEST turns OUTSIDE the active recent window only — never the
    # in-flight thread you're switching on — so a handoff never loses its
    # context mid-task.
    MAX_DB_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
    KEEP_RECENT_TURNS = 200                # never evict these newest turns

    def _maybe_trim(self) -> int:
        """Trim oldest non-active turns if the DB exceeds the 2GB cap.

        Returns the number of turns removed (0 if nothing done).
        """
        try:
            size = self.path.stat().st_size
        except OSError:
            return 0
        if size < self.MAX_DB_BYTES:
            return 0
        # Count how many turns we can drop: everything older than the
        # KEEP_RECENT_TURNS newest, but only whole conversations at a time
        # would be ideal — we keep it simple and drop the oldest single
        # turns beyond the window. This is a steady-state guard.
        row = self.db.execute(
            "SELECT MIN(id) AS lo FROM ("
            "SELECT id FROM turns ORDER BY id DESC LIMIT ?)",
            (self.KEEP_RECENT_TURNS,)).fetchone()
        if not row or row["lo"] is None:
            return 0
        cutoff = row["lo"] - 1  # ids strictly below this are evictable
        if cutoff <= 0:
            return 0
        cur = self.db.execute("DELETE FROM turns WHERE id <= ?", (cutoff,))
        self.db.commit()
        return cur.rowcount

    def reset(self) -> dict:
        """Wipe EVERY store — turns, facts, skills, procedures.

        Used by /reset (factory reset). The DB file itself is kept (schema
        re-created on next connect) so the agent keeps working immediately;
        only the learned content is dropped. Returns the before/after counts.
        """
        before = self.stats()
        self.db.executescript(
            "DELETE FROM turns; "
            "DELETE FROM facts; "
            "DELETE FROM skills; "
            "DELETE FROM procedures; "
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('turns','facts','skills','procedures');"
        )
        self.db.commit()
        after = self.stats()
        return {"before": before, "after": after}
