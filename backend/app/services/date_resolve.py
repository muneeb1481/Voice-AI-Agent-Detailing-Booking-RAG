"""Deterministic relative-date resolution — "Friday", "tomorrow", "next Monday".

A live call showed the agent computing the wrong absolute date for a simple
relative phrase (LLM mental date arithmetic is unreliable), then correctly
reporting "no slots" for a day that wasn't actually the one the caller meant.
This resolves the phrase server-side instead, so the LLM never has to do the
math itself — it just passes the phrase through and gets a real date back.
"""
import re
from datetime import date, timedelta

from app.services.timezones import local_now

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def resolve_relative_date(phrase: str, state: str | None) -> date | None:
    """Returns the resolved calendar date in the caller's local timezone, or
    None if the phrase isn't one of the recognized patterns — callers should
    fall back to asking the caller to clarify rather than guessing further."""
    if not phrase:
        return None
    text = phrase.strip().lower()
    today = local_now(state).date()

    if text in ("today", "this evening", "tonight"):
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text in ("day after tomorrow", "the day after tomorrow"):
        return today + timedelta(days=2)
    if text == "next week":
        return today + timedelta(days=7)

    # "next Friday" and plain "Friday" both mean the nearest upcoming Friday in
    # everyday speech — the "skip a week" reading of "next X" is genuinely
    # regionally ambiguous, so both patterns resolve the same way here.
    m = re.search(r"\b(next\s+|this\s+)?(" + "|".join(_WEEKDAYS) + r")\b", text)
    if m:
        target = _WEEKDAYS[m.group(2)]
        delta = (target - today.weekday()) % 7
        delta = 7 if delta == 0 else delta  # same weekday as today means next week's, not today
        return today + timedelta(days=delta)

    m = re.search(r"\bin\s+(\d+)\s+days?\b", text)
    if m:
        return today + timedelta(days=int(m.group(1)))

    return None
