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
