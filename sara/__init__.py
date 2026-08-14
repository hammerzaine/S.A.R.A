"""S.A.R.A — Smart AI Resource Assistant.

A JARVIS-style conversational agent with visible reasoning, persistent memory,
web-backed self-teaching, and observable skill growth.

Design goals (why this exists, so future maintainers don't undo them):
  1. Transparency  — the user sees WHAT she is doing and WHY, live, always.
  2. Growth        — every solved problem can become a durable skill on disk.
  3. Honesty       — she never fabricates a result. Failure is reported plainly.
  4. Personality   — she reads as a person, not a command parser.
"""

__version__ = "0.2.2"
__all__ = ["Sara"]
