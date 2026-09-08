"""US state -> local timezone, for a caller's actual "today" and business hours.

One zone per state — a business-scheduling approximation, not a county-line-precise
lookup. A handful of states genuinely span two zones (FL panhandle, west TX, KY,
IN, MI); we use each state's majority zone, which is the right call for "is 9am a
valid slot" rather than a Prohibited-by-GPS-coordinate answer.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

STATE_TIMEZONES: dict[str, str] = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "HI": "Pacific/Honolulu", "ID": "America/Boise",
    "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis", "IA": "America/Chicago",
    "KS": "America/Chicago", "KY": "America/New_York", "LA": "America/Chicago",
    "ME": "America/New_York", "MD": "America/New_York", "MA": "America/New_York",
    "MI": "America/Detroit", "MN": "America/Chicago", "MS": "America/Chicago",
    "MO": "America/Chicago", "MT": "America/Denver", "NE": "America/Chicago",
    "NV": "America/Los_Angeles", "NH": "America/New_York", "NJ": "America/New_York",
    "NM": "America/Denver", "NY": "America/New_York", "NC": "America/New_York",
    "ND": "America/Chicago", "OH": "America/New_York", "OK": "America/Chicago",
    "OR": "America/Los_Angeles", "PA": "America/New_York", "RI": "America/New_York",
    "SC": "America/New_York", "SD": "America/Chicago", "TN": "America/Chicago",
    "TX": "America/Chicago", "UT": "America/Denver", "VT": "America/New_York",
    "VA": "America/New_York", "WA": "America/Los_Angeles", "WV": "America/New_York",
    "WI": "America/Chicago", "WY": "America/Denver", "DC": "America/New_York",
}

# Used when no state is known (e.g. a general RAG question before booking details
# are collected) — Eastern is the most common "business time" default for a US company.
DEFAULT_TIMEZONE = "America/New_York"


def timezone_for_state(state: str | None) -> ZoneInfo:
    name = STATE_TIMEZONES.get((state or "").upper(), DEFAULT_TIMEZONE)
    return ZoneInfo(name)


def local_now(state: str | None = None) -> datetime:
    return datetime.now(timezone_for_state(state))


# Two buckets, not four — morning and afternoon both close with "have a nice day";
# evening and night both close with the other line. Deterministic (real clock, not
# an LLM guessing what time it "feels like"); the cutoff hours are the only thing
# to tune if the wording or timing ever needs adjusting.
DAY_START_HOUR = 5
NIGHT_START_HOUR = 17


def period_and_closing_line(state: str | None = None) -> tuple[str, str, datetime]:
    now = local_now(state)
    is_day = DAY_START_HOUR <= now.hour < NIGHT_START_HOUR
    if is_day:
        return "day", "Have a nice day!", now
    return "night", "Have a great evening!", now
