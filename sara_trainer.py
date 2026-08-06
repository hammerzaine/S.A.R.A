#!/usr/bin/env python3
"""S.A.R.A training harness — runs her real ask() loop through structured
scenarios across four domains, captures tool calls + learnings, and flags
bugs/flaws. NOT a fake loop: it calls Sara.ask() exactly as the CLI does.

Run:  python3 sara_trainer.py --scenarios all --max-steps 6
      python3 sara_trainer.py --domain ssh --only 3
"""
from __future__ import annotations
import argparse, json, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sara.agent import Sara
from sara.console import Console

# Each scenario: (id, domain, user_prompt, expect_tool=None)
# expect_tool: optional tool name we EXPECT her to use (for bug detection).
SCENARIOS = [
    # ---- SSH domain ----
    ("ssh-1", "ssh", "SSH into the home server and tell me the uptime.", "ssh_run"),
    ("ssh-2", "ssh", "Connect to 192.168.2.140 as root and show me the free memory (free -h).", "ssh_run"),
    ("ssh-3", "ssh", "Run 'df -h' on the server so I can see disk usage.", "ssh_run"),
    ("ssh-4", "ssh", "Check whether the MariaDB service is running on the home server (systemctl is-active mariadb).", "ssh_run"),
    ("ssh-5", "ssh", "What's the kernel version on the home server? (uname -a over ssh)", "ssh_run"),
    ("ssh-6", "ssh", "List the contents of /root on the home server via ssh.", "ssh_run"),
    # ---- Programming domain ----
    ("prog-1", "programming", "Write a small Python script that prints the 10 largest files under /home/zaine sorted by size. Save it to /tmp/bigfiles.py and run it.", "write_file"),
    ("prog-2", "programming", "Create a bash script at /tmp/pingcheck.sh that pings 192.168.2.140 twice and reports up/down. Make it executable and test it.", "write_file"),
    ("prog-3", "programming", "Show me how to define a class in Zig (the language you know). Write an example to /tmp/zig_demo.zig.", "write_file"),
    ("prog-4", "programming", "Find the python file that defines S.A.R.A's tool registry in the SARA folder.", "find_path"),
    ("prog-5", "programming", "Read /home/zaine/SARA/sara/tools.py and tell me how many tool classes are defined in it.", "read_file"),
    ("prog-6", "programming", "Write a Python function that flattens a nested list, save to /tmp/flatten.py, and run a quick test.", "write_file"),
    # ---- append_file coverage (don't overwrite, ADD onto) ----
    ("prog-7", "programming", "Append the line 'alias ll=\"ls -la\"' to the END of /tmp/sara_aliases.sh, creating the file if it doesn't exist yet. Use the append_file tool, NOT write_file.", "append_file"),
    ("prog-8", "programming", "I have a list of URLs at /tmp/sara_urls.txt. Add the line 'https://example.com/new-feed' onto the END of it without erasing what's already there. Use append_file.", "append_file"),
    ("prog-9", "programming", "Add two more entries onto /tmp/sara_urls.txt (one per call is fine): 'https://a.test/x' and 'https://b.test/y'. They must appear AFTER the existing lines, not replace them. Use append_file.", "append_file"),
    # ---- shell / run-a-linux-command coverage ----
    ("prog-10", "programming", "Run the linux command 'uname -a' and tell me what kernel this box is on. Use the shell tool.", "shell"),
    ("prog-11", "programming", "Show me the free memory on this machine by running 'free -h' via the shell tool.", "shell"),
    ("prog-12", "programming", "List the files in /home/zaine/SARA using 'ls -la' through the shell tool.", "shell"),
    # ---- vision / see_image coverage ----
    ("prog-13", "programming", "I just pasted a screenshot at /tmp/sara_vision_test.png that shows an error. Use the see_image tool to look at it, tell me what error is shown, and what command would fix it.", "see_image"),
    ("prog-14", "programming", "There's a UI screenshot at /tmp/sara_vision_test.png. Use see_image to describe what buttons and warnings are visible, then tell me what's wrong.", "see_image"),
    # ---- Web design / build domain ----
    ("web-1", "web", "Build a single-file HTML page for a fictional cafe called 'Wattle & Brew' with a hero section, menu, and contact form. Save to /tmp/cafe.html.", "write_file"),
    ("web-2", "web", "Scrape the category list from https://duckduckgo.com and tell me what categories it has.", "scrape_categories"),
    ("web-3", "web", "Create a dark-themed landing page for a personal portfolio at /tmp/portfolio.html with CSS grid.", "write_file"),
    ("web-4", "web", "Use web_search to find the current recommended way to center a div with CSS (flexbox vs grid).", "web_search"),
    ("web-5", "web", "Fetch https://example.com and summarise what the page is about.", "web_fetch"),
    ("web-6", "web", "Build a responsive 3-card layout in one HTML file using flexbox, save to /tmp/cards.html.", "write_file"),
    # ---- Story writing domain ----
    ("story-1", "story", "Write a short opening scene (200 words) for a sci-fi story set on a generation ship waking from cryo.", None),
    ("story-2", "story", "Write a tense dialogue between a detective and a suspect who is lying. 150 words.", None),
    ("story-3", "story", "Give me a 3-act outline for a noir thriller about a disgraced chef.", None),
    ("story-4", "story", "Write a creepy 100-word micro-horror about a smart fridge.", None),
    ("story-5", "story", "Continue this line: 'The last person alive on Earth answered the knock at the door.' (120 words)", None),
    ("story-6", "story", "Write a children's fable (under 200 words) about a stubborn echidna learning to share.", None),
]


class Trainer:
    def __init__(self, console: Console, max_steps: int):
        self.a = Sara(console=console)
        self.a.cfg["max_steps"] = max_steps
        self.results = []
        self.bugs = []

    def run_scenario(self, sid, domain, prompt, expect_tool):
        t0 = time.time()
        # reset per-scenario tool capture so names don't bleed across scenarios
        console = getattr(self.a, "console", None)
        if console is not None and hasattr(console, "_captured_names"):
            console._captured_names.clear()
        try:
            final = self.a.ask(prompt)
        except Exception as e:
            final = f"[TRAINER-EXCEPTION] {type(e).__name__}: {e}\n{traceback.format_exc()}"
        dt = time.time() - t0

        # pull tool usage from this turn's turns table (last N after run)
        used_tools = self._tools_used_since(t0)
        ok_tool = (expect_tool in used_tools) if expect_tool else None

        rec = {
            "id": sid, "domain": domain, "prompt": prompt,
            "expect_tool": expect_tool, "used_tools": used_tools,
            "met_expectation": ok_tool,
            "seconds": round(dt, 1),
            "reply_len": len(final or ""),
            "reply_head": (final or "")[:240],
        }
        self.results.append(rec)

        # ---- BUG DETECTION heuristics ----
        low = (final or "").lower()
        if "[trainer-exception]" in low:
            self.bugs.append((sid, "EXCEPTION during ask()", final[:400]))
        if "as an ai" in low or "i cannot assist" in low or "i'm sorry i cannot" in low:
            self.bugs.append((sid, "FALSE REFUSAL despite having tools", final[:200]))
        if expect_tool and not ok_tool and used_tools:
            self.bugs.append((sid, f"used tools {used_tools} but NOT expected '{expect_tool}'", ""))
        if expect_tool and not used_tools:
            self.bugs.append((sid, f"used NO tools, expected '{expect_tool}' (likely hallucinated answer)", final[:200]))
        if "traceback" in low or "permissionerror" in low or "modulenotfounderror" in low:
            self.bugs.append((sid, "error text leaked into final answer", final[:200]))
        return rec

    def _tools_used_since(self, t0):
        """Return tool names actually invoked during this scenario.

        Reads from the capture console's _captured_names (populated by c.act),
        which is the authoritative signal — the turns table does not log ACTION
        blocks. Falls back to regex over the full turns blob if unavailable.
        """
        console = getattr(self.a, "console", None)
        if console is not None and getattr(console, "_captured_names", None):
            names = set(console._captured_names)
            console._captured_names = []
            return sorted(names)
        import re
        blob = " ".join(r["content"] for r in self.a.memory.db.execute(
            "SELECT content FROM turns WHERE ts >= ?", (t0,)).fetchall())
        names = set()
        for t in self.a.tools:
            if re.search(rf"(?m)^ACTION:\s*{t}\b|\bTOOL:\s*{t}\b|\[{t}\]", blob):
                names.add(t)
        return sorted(names)

    def run_all(self, only_domain=None, limit=None):
        sc = SCENARIOS
        if only_domain:
            sc = [s for s in sc if s[1] == only_domain]
        if limit:
            sc = sc[:limit]
        for i, (sid, dom, prompt, exp) in enumerate(sc, 1):
            print(f"\n=== [{i}/{len(sc)}] {sid} ({dom}) ===", flush=True)
            print(f"  prompt: {prompt}", flush=True)
            rec = self.run_scenario(sid, dom, prompt, exp)
            flag = "" if rec["met_expectation"] is not False else "  <-- TOOL MISMATCH"
            print(f"  tools: {rec['used_tools']} | {rec['seconds']}s | reply {rec['reply_len']}ch{flag}", flush=True)
        return self

    def write_report(self, path: Path):
        # gather skill/memory growth
        skills = self.a.memory.all_skills()
        facts = self.a.memory.facts(40)
        lines = []
        lines.append("=" * 70)
        lines.append("S.A.R.A TRAINING REPORT")
        lines.append("generated: " + time.strftime("%Y-%m-%d %H:%M:%S"))
        lines.append("model: " + self.a.cfg["model"])
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"SCENARIOS RUN: {len(self.results)}")
        domains = {}
        for r in self.results:
            domains.setdefault(r["domain"], 0)
            domains[r["domain"]] += 1
        lines.append("by domain: " + ", ".join(f"{k}={v}" for k, v in domains.items()))
        lines.append("")
        lines.append("-" * 70)
        lines.append("PER-SCENARIO RESULTS")
        lines.append("-" * 70)
        for r in self.results:
            met = {True: "OK", False: "MISMATCH", None: "n/a"}[r["met_expectation"]]
            lines.append(f"\n[{r['id']}] ({r['domain']})  expectation: {met}")
            lines.append(f"  prompt   : {r['prompt']}")
            lines.append(f"  tools    : {r['used_tools']}")
            lines.append(f"  time     : {r['seconds']}s   reply: {r['reply_len']} chars")
            if r["met_expectation"] is False:
                lines.append(f"  !! expected tool '{r['expect_tool']}' but didn't use it")
        lines.append("")
        lines.append("-" * 70)
        lines.append("BUGS / FLAWS DETECTED")
        lines.append("-" * 70)
        if not self.bugs:
            lines.append("None detected by automated heuristics.")
        else:
            for sid, kind, detail in self.bugs:
                lines.append(f"\n[{sid}] {kind}")
                if detail:
                    lines.append(f"   {detail[:300]}")
        lines.append("")
        lines.append("-" * 70)
        lines.append("SKILLS LEARNED (cumulative, top by use)")
        lines.append("-" * 70)
        for s in skills[:15]:
            lines.append(f"  {s['name']}  (used {s['uses']}x): {s['description'][:60]}")
        lines.append("")
        lines.append("-" * 70)
        lines.append("FACTS REMEMBERED (recent)")
        lines.append("-" * 70)
        for f in facts[:20]:
            lines.append(f"  - {f[:90]}")
        lines.append("")
        lines.append("=" * 70)
        lines.append("END OF REPORT")
        lines.append("=" * 70)
        path.write_text("\n".join(lines))
        return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default=None, choices=["ssh", "programming", "web", "story"])
    ap.add_argument("--scenarios", default="all")
    ap.add_argument("--max-steps", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="/home/zaine/sara_training_report.txt")
    args = ap.parse_args()

    # quiet console so training output is scannable; we still see tool lines.
    # Captures every invoked tool name into a list the trainer reads per-scenario.
    class Quiet(Console):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._captured_names = []
        def think(self, *a, **k): pass
        def act(self, *a, **k):
            if a:
                self._captured_names.append(a[0])
            print(f"    > ACTION: {a[0]} {a[1][:60] if len(a) > 1 else ''}", flush=True)
        def result(self, *a, **k): print(f"    < {a[0][:80]}", flush=True)
        def warn(self, *a, **k): print(f"    ! {a[0][:80]}", flush=True)
        def learned(self, *a, **k): print(f"    ++ LEARNED {a}", flush=True)
        def error(self, *a, **k): print(f"    X {a[0][:80]}", flush=True)

    tr = Trainer(Quiet(), args.max_steps)
    tr.run_all(only_domain=args.domain, limit=args.limit)
    out = tr.write_report(Path(args.out))
    print("\n" + "=" * 70)
    print(f"REPORT WRITTEN: {out}")
    print(f"scenarios: {len(tr.results)}  bugs flagged: {len(tr.bugs)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
