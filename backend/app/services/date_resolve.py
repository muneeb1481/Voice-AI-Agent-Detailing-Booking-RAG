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

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_NAMES = "|".join(_MONTHS)


def _resolve_month_day(text: str, today: date) -> date | None:
    """"12 September", "September 12", "Sept 12th" — an explicit calendar date
    the caller stated outright, not a relative phrase. Resolves to this year
    unless that date has already passed, in which case next year."""
    m = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MONTH_NAMES + r")\b", text
    )
    if m:
        day_num, month_name = int(m.group(1)), m.group(2)
    else:
        m = re.search(
            r"\b(" + _MONTH_NAMES + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", text
        )
        if not m:
            return None
        month_name, day_num = m.group(1), int(m.group(2))

    month = _MONTHS[month_name]
    year = today.year
    try:
        candidate = date(year, month, day_num)
    except ValueError:
        return None  # e.g. "February 30" — not a real date, don't guess
    if candidate < today:
        try:
            candidate = date(year + 1, month, day_num)
        except ValueError:
            return None
    return candidate


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

    month_day = _resolve_month_day(text, today)
    if month_day is not None:
        return month_day

    return None
