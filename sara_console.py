"""S.A.R.A Console — Sara's visible inner life and all screen furniture.

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
    """S.A.R.A's console output handler."""

    def __init__(self, colour: bool = True):
        self.colour = colour

    def _c(self, text: str, colour: str = "") -> str:
        if not self.colour:
            return text
        return f"{colour}{text}{RESET}"

    def _p(self, text: str = ""):
        print(text)

    def splash(self, model: str, skills: int, facts: int, online: bool,
               commands: list[tuple[str, str]], version: str = "unknown",
               upgrade: dict | None = None, tools: int = 0) -> None:
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
                  + "   " + self._c("tools ", GREY) + self._c(str(tools), VIOLET)
                  + "   " + self._c("memories ", GREY)
                  + self._c(str(facts), VIOLET))
        pad = max(0, (inner - visible_len(status)) // 2)
        row(" " * pad + status)
        row()

        # Upgrade banner (inside the box, when one is available)
        if upgrade:
            up_text = self._c(f"⬆  upgrade available: v{upgrade.get('version', '?')}", AMBER)
            row(up_text)
            row()

        # Commands
        if commands:
            cmd_str = "   ".join(
                self._c(f"/{cmd}", CYAN) + self._c(f" — {desc}", GREY_D)
                for cmd, desc in commands
            )
            row(cmd_str)
            row()

        edge(BL, BR)
        self._p()

    def say(self, text: str):
        """S.A.R.A speaking."""
        self._p(self._c(text, CYAN))

    def you(self, text: str):
        """You speaking."""
        self._p(self._c(text, BLUE))

    def think(self, text: str):
        """Private reasoning."""
        self._p(self._c(text, GREY))

    def act(self, text: str):
        """Action being taken."""
        self._p(self._c(text, AMBER))

    def ok(self, text: str):
        """Tool succeeded."""
        self._p(self._c(text, GREEN))

    def err(self, text: str):
        """Tool failed / error."""
        self._p(self._c(text, RED))

    def grow(self, text: str):
        """Growth — new skill or remembered fact."""
        self._p(self._c(text, VIOLET))

    def data(self, text: str):
        """Data returned from a tool."""
        self._p(self._c(text, GOLD))
