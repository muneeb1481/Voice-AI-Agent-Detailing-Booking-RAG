"""Vehicle-category classification from freeform text.

Keyword match first: it's free, instant, and a vehicle body type is a closed,
well-known vocabulary, so a lookup covers the vast majority of real input. Only
when that comes back empty (an unlisted or unusual model) does this fall back to
one Groq call rather than silently leaving the category — and therefore the
large-vehicle surcharge — unset.
"""
import json
import re

import httpx

from app.config import get_settings

settings = get_settings()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

LARGE_CATEGORIES = {"suv", "truck", "van", "minivan"}
_ALL_CATEGORIES = {"sedan", "suv", "truck", "hatchback", "coupe", "van", "minivan"}

# Longer/more specific keys first within a category so "pickup truck" doesn't get
# swallowed by a shorter unrelated match; order across categories doesn't matter
# since every keyword is checked and the most specific one wins by keyword length.
_KEYWORDS: dict[str, list[str]] = {
    "truck": [
        "truck", "pickup", "f-150", "f150", "f-250", "f250", "silverado", "sierra",
        "ram 1500", "ram1500", "ram 2500", "ram 3500", "tacoma", "tundra", "colorado",
        "ranger", "titan", "frontier", "ridgeline", "gladiator", "canyon",
    ],
    "suv": [
        "suv", "crossover", "rav4", "cr-v", "crv", "explorer", "tahoe", "suburban",
        "expedition", "highlander", "4runner", "pilot", "pathfinder", "wrangler",
        "grand cherokee", "cherokee", "traverse", "equinox", "trailblazer", "blazer",
        "escape", "edge", "santa fe", "tucson", "telluride", "sorento", "outback",
        "forester", "ascent", "cx-5", "cx5", "cx-9", "cx9", "rogue", "murano",
        "armada", "yukon", "acadia", "bronco", "land cruiser", "sequoia",
    ],
    "minivan": [
        "minivan", "mini van", "odyssey", "sienna", "pacifica", "carnival",
        "sedona", "grand caravan",
    ],
    "van": ["van", "sprinter", "transit", "promaster", "express cargo"],
    "hatchback": [
        "hatchback", "golf", "civic hatchback", "corolla hatchback", "fit", "veloster",
        "mazda3 hatch", "impreza hatchback", "leaf", "bolt",
    ],
    "coupe": ["coupe", "mustang", "camaro", "challenger", "brz", "gt86", "86 "],
    "sedan": [
        "sedan", "corolla", "camry", "civic", "accord", "altima", "sentra", "maxima",
        "jetta", "passat", "elantra", "sonata", "impala", "malibu", "fusion",
        "3 series", "5 series", "c-class", "e-class", "a4", "a6", "model 3",
        "model s", "es350", "ilx", "tlx",
    ],
}


def classify_vehicle(text: str | None) -> str | None:
    """Return one of the category keys in _KEYWORDS, or None if nothing matched."""
    if not text:
        return None
    # Keep hyphens: several keywords (f-150, cr-v) are hyphenated themselves.
    normalized = f" {re.sub(r'[^a-z0-9\- ]', ' ', text.lower())} "

    best_category: str | None = None
    best_len = 0
    for category, keywords in _KEYWORDS.items():
        for kw in keywords:
            if f" {kw} " in normalized or normalized.strip().startswith(kw):
                if len(kw) > best_len:
                    best_category = category
                    best_len = len(kw)
    return best_category


def classify_vehicle_smart(text: str | None) -> str | None:
    """Keyword match first; only calls the LLM when that finds nothing."""
    category = classify_vehicle(text)
    if category is not None or not text or not settings.groq_key_list:
        return category
    return _classify_with_llm(text)


def _classify_with_llm(text: str) -> str | None:
    prompt = (
        "Classify this vehicle's body style into exactly one word from this list: "
        f"{', '.join(sorted(_ALL_CATEGORIES))}. "
        f'Vehicle: "{text}". Reply with only the single category word, nothing else.'
    )
    for key in settings.groq_key_list:
        try:
            resp = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.groq_model,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=10,
            )
            if resp.status_code == 429:
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip().lower()
            return content if content in _ALL_CATEGORIES else None
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError):
            continue
    return None


def is_large_vehicle(category: str | None) -> bool:
    return category in LARGE_CATEGORIES
