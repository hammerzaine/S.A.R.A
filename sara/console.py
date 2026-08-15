"""Console — S.A.R.A's visible inner life and all screen furniture.

Everything printed goes through here. Each kind of information owns a colour
and a glyph, consistently:

    cyan      S.A.R.A speaking (her actual answer)
    blue      you
    grey      her private reasoning
    amber     an action she is taking, printed BEFORE it runs
    green     a tool succeeded
    red       a tool failed / an error
    violet    growth — a new skill or remembered fact
    gold      data returned from a tool (ground truth)
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"

CYAN = "\033[38;5;51m"
CYAN_D = "\033[38;5;37m"
BLUE = "\033[38;5;75m"
GREY = "\033[38;5;245m"
GREY_D = "\033[38;5;240m"
AMBER = "\033[38;5;214m"
GREEN = "\033[38;5;77m"
RED = "\033[38;5;203m"
VIOLET = "\033[38;5;141m"
GOLD = "\033[38;5;179m"
WHITE = "\033[38;5;255m"

TL, TR, BL, BR = "╭", "╮", "╰", "╯"
H, V = "─", "│"


def term_width() -> int:
    return max(64, min(shutil.get_terminal_size((100, 24)).columns, 100))


def visible_len(s: str) -> int:
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            while i < len(s) and s[i] != "m":
                i += 1
            i += 1
        else:
            out += 1
            i += 1
    return out


class Console:
    def __init__(self, verbose: bool = True, colour: bool = True):
        self.verbose = verbose
        self.colour = colour and sys.stdout.isatty() and os.environ.get(
            "TERM", "") not in ("dumb", "")
        self._step = 0

    def _c(self, text, colour) -> str:
        return f"{colour}{text}{RESET}" if self.colour else str(text)

    def _p(self, text: str = "") -> None:
        print(text, flush=True)

    def _wrap(self, text: str, width: int, indent: str = "") -> list[str]:
        lines = []
        for para in str(text).split("\n"):
            if not para.strip():
                lines.append("")
                continue
            lines.extend(textwrap.wrap(para, width=width) or [""])
        return [indent + l for l in lines]

    def user_echo(self, text: str) -> None:
        w = term_width()
        self._p()
        self._p(self._c("  you ", BLUE + BOLD)
                + self._c(H * (w - 8), GREY_D))
        for l in self._wrap(text, w - 6, "  "):
            self._p(self._c(l, BLUE))

    def speak(self, text: str) -> None:
        w = term_width()
        self._p()
        self._p(self._c("  S.A.R.A ", CYAN + BOLD)
                + self._c(H * (w - 12), CYAN_D))
        for line in str(text).split("\n"):
            if not line.strip():
                self._p()
                continue
            if line.startswith("  ") and not line.startswith("   "):
                self._p(self._c("  " + line, GOLD))
            elif line.startswith("Contents of ") or line.endswith("match(es):"):
                self._p(self._c("  " + line, GOLD + BOLD))
            else:
                for l in self._wrap(line, w - 6, "  "):
                    self._p(self._c(l, CYAN))
        self._p()

    def think(self, text: str) -> None:
        if not self.verbose:
            return
        cleaned = str(text).replace("```", "").strip(" \n\t`")
        if len(cleaned) < 3:
            return
        for l in self._wrap(cleaned, term_width() - 8, "    "):
            self._p(self._c(l.replace("    ", "  · ", 1)
                            if l.strip() else l, GREY + ITALIC))

    def act(self, tool: str, detail: str = "") -> None:
        self._step += 1
        tag = self._c(f"  ▸ {tool}", AMBER + BOLD)
        self._p(tag + (" " + self._c(detail, AMBER + DIM) if detail else ""))

    def result(self, summary: str, ok: bool = True) -> None:
        glyph = "✓" if ok else "✗"
        colour = GREEN if ok else RED
        self._p(self._c(f"    {glyph} {summary}", colour))

    def learned(self, what: str, detail: str = "") -> None:
        self._p()
        self._p(self._c(f"  ✦ LEARNED  {what}", VIOLET + BOLD))
        if detail:
            for l in self._wrap(detail, term_width() - 14, "             "):
                self._p(self._c(l, VIOLET))
        self._p()

    def warn(self, text: str) -> None:
        self._p(self._c(f"  ! {text}", RED))

    def error(self, text: str) -> None:
        self._p()
        self._p(self._c(f"  ✗ {text}", RED + BOLD))
        self._p()

    def info(self, text: str) -> None:
        self._p(self._c(f"  {text}", GREY))

    def rule(self, label: str = "") -> None:
        w = 0
        try:
            w = term_width()
        except Exception:
            w = 80
        if label:
            self._p()
            self._p(self._c(f"  {label} ", VIOLET + BOLD)
                    + self._c(H * max(0, w - len(label) - 5), GREY_D))
        else:
            self._p(self._c("  " + H * (w - 4), GREY_D))

    def skill_table(self, skills: list[dict]) -> None:
        if not skills:
            self.info("nothing self-taught yet — give her a problem")
            return
        w = term_width()
        self.rule(f"{len(skills)} skill{'s' if len(skills) != 1 else ''}")
        self._p()
        for s in skills:
            uses = s.get("uses", 0)
            badge = self._c(f"{uses}×", GOLD if uses else GREY_D)
            head = self._c(f"  {s['name']}", VIOLET + BOLD)
            dots = self._c(
                " " + "·" * max(1, w - visible_len(head)
                                - visible_len(badge) - 5) + " ", GREY_D)
            self._p(head + dots + badge)
            desc = (s.get("description") or "").strip()
            if desc.lower() == s["name"].lower() or not desc:
                body = (s.get("body") or "").strip().split("\n")[0]
                desc = body or "no description recorded"
            for l in self._wrap(desc, w - 8, "      "):
                self._p(self._c(l, GREY))
            self._p()

    def fact_list(self, facts: list[str]) -> None:
        if not facts:
            self.info("no durable facts yet")
            return
        self.rule(f"{len(facts)} thing{'s' if len(facts) != 1 else ''}"
                  f" she remembers")
        self._p()
        for f in facts:
            for i, l in enumerate(self._wrap(f, term_width() - 8, "     ")):
                self._p(self._c(l.replace("     ", "  ▪  ", 1) if i == 0
                                else l, GOLD if i == 0 else GREY))
        self._p()

    def splash(self, model: str, skills: int, facts: int, online: bool,
               commands: list[tuple[str, str]], version: str = "unknown",
               upgrade: dict | None = None) -> None:
        w = term_width()
        inner = w - 4

        def edge(l, r, colour=CYAN_D):
            self._p(self._c(l + H * (w - 2) + r, colour))

        def row(content: str = "", pad_colour=CYAN_D):
            vis = visible_len(content)
            body = content + " " * max(0, inner - vis)
            self._p(self._c(V, pad_colour) + " " + body + " "
                    + self._c(V, pad_colour))

        self._p()
        edge(TL, TR)
        row()

        # Wordmark
        title = "S . A . R . A"
        sub = "Smart AI Resource Assistant"
        row(self._c(title.center(inner), CYAN + BOLD))
        row(self._c(sub.center(inner), GREY))
        row(self._c(self._c(f"v{version}", GREY_D).center(inner), GREY_D))
        row()

        # Status strip
        dot = self._c("●", GREEN if online else RED)
        state = self._c("online" if online else "offline",
                        GREEN if online else RED)
        status = (f"{dot} {state}   "
                  + self._c("model ", GREY) + self._c(model, WHITE) + "   "
                  + self._c("skills ", GREY) + self._c(str(skills), VIOLET)
                  + "   " + self._c("memories ", GREY)
                  + self._c(str(facts), VIOLET))
        pad = max(0, (inner - visible_len(status)) // 2)
        row(" " * pad + status)
        row()

        # Upgrade banner (inside the box, when one is available)
        if upgrade and upgrade.get("available"):
            latest = upgrade.get("latest")
            tag = latest[:8] if isinstance(latest, str) and latest else ""
            row(self._c("◆ UPGRADE AVAILABLE", AMBER + BOLD))
            row(self._c(
                f"  a newer version is available — type /upgrade to pull it"
                f"{('  (' + tag + ')') if tag else ''}", AMBER + DIM))
            row()

        # Commands
        row(self._c("COMMANDS", AMBER + BOLD))
        row(self._c(H * (inner - 1), GREY_D))
        col_w = inner // 2
        pairs = [(c, d) for c, d in commands]
        for i in range(0, len(pairs), 2):
            chunk = pairs[i:i + 2]
            line = ""
            for cmd, desc in chunk:
                room = col_w - 12
                d = desc if len(desc) <= room else desc[:max(0, room - 1)] + "…"
                cell = self._c(f"{cmd:<10}", CYAN) + self._c(d, GREY)
                cell += " " * max(0, col_w - visible_len(cell))
                line += cell
            row(line)
        row()
        edge(BL, BR)
        self._p()

    def model_menu(self, models: list[dict]) -> None:
        if not models:
            self.info("no models found on any endpoint")
            return
        w = term_width()
        self.rule(f"{len(models)} available models")
        self._p()
        for i, m in enumerate(models, 1):
            name = m["name"]
            src = m["source"]
            if m.get("active"):
                head = self._c(f"  {i:>2}. {name}", GOLD + BOLD)
                src_colour = GOLD
            else:
                head = self._c(f"  {i:>2}. {name}", WHITE)
                src_colour = GREY_D
            badge = self._c(src, src_colour)
            # dot-fill between name and source, like skill_table
            fill = " " + "·" * max(1, w - visible_len(head)
                                    - visible_len(badge) - 5) + " "
            self._p(head + self._c(fill, GREY_D) + badge)
        self._p()
        self.info(f"switch: /model <n>  (or /model <name> — "
                  f"'{self._c('local', GREY_D)}' = ~/models/*.gguf via GPU server)")
        self._p()

    def prompt(self) -> str:
        if not self.colour:
            return "\n  you > "
        return (f"\n  \001{BLUE}{BOLD}\002you\001{RESET}\002 "
                f"\001{GREY_D}\002›\001{RESET}\002 ")

    class Spinner:
        FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

        def __init__(self, console, label):
            self.c, self.label, self.i = console, label, 0
            self.active = console.colour

        def __enter__(self):
            return self

        def tick(self):
            if not self.active:
                return
            f = self.FRAMES[self.i % len(self.FRAMES)]
            self.i += 1
            sys.stdout.write(f"\r{GREY}  {f} {self.label}…{RESET}")
            sys.stdout.flush()

        def __exit__(self, *a):
            if self.active:
                sys.stdout.write("\r" + " " * (len(self.label) + 8) + "\r")
                sys.stdout.flush()

    def thinking(self, label: str = "thinking"):
        return Console.Spinner(self, label)
