"""US state validation.

Accepts either a 2-letter USPS code or a full state name (any case) and normalizes
to the 2-letter code. Rejects anything else with a message safe to read to a caller.
"""

STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_NAME_TO_CODE = {name.lower(): code for code, name in STATES.items()}


def normalize_state(value: str) -> str:
    """Return the 2-letter code for a state given as a code or a full name.

    Raises ValueError with a caller-safe message if it isn't a real US state.
    """
    cleaned = value.strip()
    upper = cleaned.upper()
    if upper in STATES:
        return upper

    lower = cleaned.lower()
    if lower in _NAME_TO_CODE:
        return _NAME_TO_CODE[lower]

    raise ValueError(
        f"'{value}' doesn't look like a valid US state. "
        "Please provide a US state name or its 2-letter abbreviation."
    )


def state_name(code: str) -> str:
    return STATES.get(code.upper(), code)


# Callers usually answer "where will the car be?" with a city, not a ZIP. A live
# call got stuck demanding a ZIP from a caller who kept saying "Dallas".
CITY_TO_STATE: dict[str, str] = {
    "new york city": "NY", "nyc": "NY", "brooklyn": "NY", "queens": "NY", "bronx": "NY",
    "buffalo": "NY", "rochester": "NY", "los angeles": "CA", "san diego": "CA",
    "san jose": "CA", "san francisco": "CA", "fresno": "CA", "sacramento": "CA",
    "long beach": "CA", "oakland": "CA", "bakersfield": "CA", "anaheim": "CA",
    "santa ana": "CA", "riverside": "CA", "stockton": "CA", "irvine": "CA",
    "chula vista": "CA", "fremont": "CA", "burlingame": "CA", "chicago": "IL",
    "houston": "TX", "san antonio": "TX", "dallas": "TX", "austin": "TX",
    "fort worth": "TX", "el paso": "TX", "arlington": "TX", "corpus christi": "TX",
    "plano": "TX", "laredo": "TX", "lubbock": "TX", "garland": "TX", "irving": "TX",
    "frisco": "TX", "mckinney": "TX", "phoenix": "AZ", "tucson": "AZ", "mesa": "AZ",
    "chandler": "AZ", "scottsdale": "AZ", "glendale": "AZ", "gilbert": "AZ",
    "philadelphia": "PA", "pittsburgh": "PA", "jacksonville": "FL", "miami": "FL",
    "tampa": "FL", "orlando": "FL", "st petersburg": "FL", "saint petersburg": "FL",
    "hialeah": "FL", "columbus": "OH", "cleveland": "OH", "cincinnati": "OH",
    "charlotte": "NC", "raleigh": "NC", "greensboro": "NC", "durham": "NC",
    "winston salem": "NC", "indianapolis": "IN", "fort wayne": "IN", "seattle": "WA",
    "spokane": "WA", "denver": "CO", "colorado springs": "CO", "aurora": "CO",
    "oklahoma city": "OK", "tulsa": "OK", "nashville": "TN", "memphis": "TN",
    "knoxville": "TN", "chattanooga": "TN", "washington dc": "DC", "boston": "MA",
    "las vegas": "NV", "north las vegas": "NV", "reno": "NV", "portland": "OR",
    "detroit": "MI", "louisville": "KY", "lexington": "KY", "baltimore": "MD",
    "bel air": "MD", "milwaukee": "WI", "madison": "WI", "albuquerque": "NM",
    "atlanta": "GA", "savannah": "GA", "omaha": "NE", "lincoln": "NE",
    "virginia beach": "VA", "norfolk": "VA", "chesapeake": "VA", "richmond": "VA",
    "minneapolis": "MN", "st paul": "MN", "saint paul": "MN", "new orleans": "LA",
    "baton rouge": "LA", "wichita": "KS", "kansas city": "MO", "st louis": "MO",
    "saint louis": "MO", "honolulu": "HI", "newark": "NJ", "jersey city": "NJ",
    "boise": "ID", "des moines": "IA", "salt lake city": "UT", "birmingham": "AL",
    "charleston": "SC", "providence": "RI", "hartford": "CT", "little rock": "AR",
    "jackson": "MS", "anchorage": "AK",
}

_PLACES_LONGEST_FIRST = sorted(CITY_TO_STATE, key=len, reverse=True)
_STATE_NAMES_LONGEST_FIRST = sorted(_NAME_TO_CODE, key=len, reverse=True)


def state_from_place(value: str | None) -> str | None:
    """Best-effort US state from how a caller names a place: a state code or name,
    "Dallas", "Dallas, TX", "I live in Baltimore". None when nothing recognizable —
    never raises, so a vague answer never fails a whole tool call."""
    import re  # noqa: PLC0415

    if not value or not str(value).strip():
        return None
    try:
        return normalize_state(str(value))
    except ValueError:
        pass
    text = " " + re.sub(r"[^a-z0-9, ]", " ", str(value).lower().replace(".", "")) + " "
    text = re.sub(r"\s+", " ", text)
    # Cities first: "Kansas City" must not match the state "Kansas".
    for place in _PLACES_LONGEST_FIRST:
        if re.search(rf"\b{re.escape(place)}\b", text):
            return CITY_TO_STATE[place]
    for name in _STATE_NAMES_LONGEST_FIRST:
        if re.search(rf"\b{re.escape(name)}\b", text):
            return _NAME_TO_CODE[name]
    # A 2-letter code only after a comma ("Plano, TX") — bare words like "in" or
    # "me" are too ambiguous to read as a state code.
    m = re.search(r",\s*([a-z]{2})\b", text)
    if m and m.group(1).upper() in STATES:
        return m.group(1).upper()
    return None
