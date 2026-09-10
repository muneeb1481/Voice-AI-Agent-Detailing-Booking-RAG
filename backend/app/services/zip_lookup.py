"""ZIP code -> US state, from the standard 3-digit ZIP prefix ranges.

So a caller only has to give their ZIP code, never separately asked "and what
state are you in" — this is a best-effort range table (a handful of ZIP3
prefixes are genuinely split across state lines), never treated as more
certain than what the caller says: always read the derived state back to them
to confirm rather than silently trusting it.
"""

# (start_zip3, end_zip3, state_code) — standard USPS 3-digit prefix ranges.
_RANGES: list[tuple[int, int, str]] = [
    (350, 369, "AL"), (995, 999, "AK"), (850, 865, "AZ"),
    (716, 729, "AR"), (755, 755, "AR"), (757, 758, "AR"),
    (900, 961, "CA"), (800, 816, "CO"), (60, 69, "CT"),
    (197, 199, "DE"), (200, 200, "DC"), (202, 205, "DC"),
    (320, 339, "FL"), (341, 342, "FL"), (344, 344, "FL"), (346, 347, "FL"), (349, 349, "FL"),
    (300, 319, "GA"), (398, 399, "GA"),
    (967, 968, "HI"), (832, 838, "ID"),
    (600, 629, "IL"), (460, 479, "IN"), (500, 528, "IA"),
    (660, 679, "KS"), (400, 427, "KY"),
    (700, 701, "LA"), (703, 708, "LA"), (710, 714, "LA"),
    (39, 49, "ME"), (206, 219, "MD"),
    (10, 27, "MA"), (55, 55, "MA"),
    (480, 499, "MI"), (550, 567, "MN"), (386, 397, "MS"),
    (630, 658, "MO"), (590, 599, "MT"), (680, 693, "NE"),
    (889, 898, "NV"), (30, 38, "NH"), (70, 89, "NJ"),
    (870, 884, "NM"), (100, 149, "NY"),
    (270, 289, "NC"), (580, 588, "ND"),
    (430, 459, "OH"), (730, 741, "OK"), (743, 749, "OK"),
    (970, 979, "OR"), (150, 196, "PA"), (28, 29, "RI"),
    (290, 299, "SC"), (570, 577, "SD"), (370, 385, "TN"),
    (750, 799, "TX"), (733, 733, "TX"), (885, 885, "TX"),
    (840, 847, "UT"), (50, 59, "VT"), (220, 246, "VA"),
    (980, 994, "WA"), (247, 268, "WV"), (530, 549, "WI"),
    (820, 831, "WY"), (6, 9, "PR"),
]


def state_from_zip(zip_code: str | None) -> str | None:
    if not zip_code:
        return None
    digits = "".join(c for c in zip_code if c.isdigit())[:3]
    if len(digits) < 3:
        return None
    prefix = int(digits)
    for start, end, state in _RANGES:
        if start <= prefix <= end:
            return state
    return None
