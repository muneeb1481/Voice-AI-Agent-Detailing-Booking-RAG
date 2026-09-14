"""US state -> local timezone, for a caller's actual "today" and business hours.

One zone per state — a business-scheduling approximation, not a county-line-precise
lookup. A handful of states genuinely span two zones (FL panhandle, west TX, KY,
IN, MI); we use each state's majority zone, which is the right call for "is 9am a
valid slot" rather than a Prohibited-by-GPS-coordinate answer.
"""
import re
from datetime import date, datetime, time, timezone
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


# --- Caller wall-clock <-> stored UTC ---------------------------------------
# The voice agent only ever speaks the caller's own local time ("3 PM"). A live
# call showed the model passing that as a naive or "Z"-suffixed ISO string, which
# was then stored as 3 PM *UTC* — so a Texas caller's 3 PM showed up as ~10 AM on
# the dashboard. Every voice tool now treats a time as the job state's wall clock
# and converts here, so the model never does timezone math.

_CLOCK_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?(?::\d{2})?\s*(a\.?m\.?|p\.?m\.?)?\s*$", re.I)


def parse_clock_time(text: str | None) -> time | None:
    """"3 PM", "3:30pm", "15:00", "10 a.m." -> time. None if unrecognizable."""
    if not text:
        return None
    cleaned = text.strip().lower().replace("o'clock", "").replace("noon", "12 pm")
    m = _CLOCK_RE.match(cleaned)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    meridiem = (m.group(3) or "").replace(".", "")
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def wall_clock_to_utc(day: date, clock: time, state: str | None) -> datetime:
    return datetime.combine(day, clock, tzinfo=timezone_for_state(state)).astimezone(timezone.utc)


def reinterpret_as_wall_clock(dt: datetime, state: str | None) -> datetime:
    """Keep the date/hour/minute the agent wrote and discard whatever offset it
    attached — that number is always the caller's local time, never UTC."""
    return wall_clock_to_utc(dt.date(), dt.time().replace(tzinfo=None), state)


def to_local(dt: datetime, state: str | None) -> datetime:
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return aware.astimezone(timezone_for_state(state))


def format_clock(dt: datetime) -> str:
    """Spoken-style time, e.g. "3:00 PM" (no leading zero, platform-independent)."""
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def describe_local(dt: datetime, state: str | None) -> dict:
    """What the agent reads back — local date and time only, no timezone name."""
    local = to_local(dt, state)
    return {
        "date": local.date().isoformat(),
        "day_of_week": local.strftime("%A"),
        "time": format_clock(local),
        "starts_at_local": local.replace(tzinfo=None).isoformat(timespec="minutes"),
    }


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
