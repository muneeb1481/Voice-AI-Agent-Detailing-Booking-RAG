"""Freeform text -> structured job fields.

An admin pastes something like:
    alex
    +1234567890
    toyota corolla
    213 tn usa
    interior exterior
    $200

and this extracts name / phone / vehicle / state / zip / address / service / price.
Uses the same Groq LLM as the RAG completion when configured; falls back to a plain
regex/heuristic parser (no network, no key) so the feature still works offline.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.services.us_states import normalize_state

settings = get_settings()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_SYSTEM_PROMPT_TEMPLATE = """You extract structured job-intake data from a short, messy note an \
admin typed or pasted after taking a car-detailing job over the phone or in person.

The current date and time is {now}.

Return ONLY a JSON object with exactly these keys (use null for anything not present):
- customer_name (string)
- customer_phone (string, as written)
- vehicle (string, e.g. "Toyota Corolla" or "2019 Ford F-150")
- state (string, a US state name or 2-letter code if present)
- zip_code (string, a 5-digit ZIP if present)
- address (string, any other address text that isn't the state/zip)
- service_label (string, short description of the service requested, e.g. "Interior and exterior detail")
- price_cents (integer, the dollar amount in the text converted to cents, e.g. $200 -> 20000)
- starts_at (string, ISO 8601 datetime with timezone, ONLY if a date/time is mentioned in the
  note — resolve relative phrases like "tomorrow" or "next Tuesday 2pm" against the current
  date/time given above; null if no date/time is mentioned at all)
- notes (string, anything else worth keeping)

Do not invent a value that is not in the text. Return raw JSON, no markdown fences."""


def parse_job_text(text: str) -> dict:
    if settings.groq_key_list:
        result = _parse_with_groq(text)
        if result is not None:
            return _clean(result)
    return _clean(_parse_heuristic(text))


def _parse_with_groq(text: str) -> dict | None:
    now = datetime.now(timezone.utc).strftime("%A, %Y-%m-%d %H:%M UTC")
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(now=now)},
        {"role": "user", "content": text},
    ]
    for key in settings.groq_key_list:
        try:
            resp = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.groq_model,
                    "temperature": 0,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                },
                timeout=20,
            )
            if resp.status_code == 429:
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError):
            continue
    return None


_PHONE_RE = re.compile(r"(\+?\d[\d\-\s()]{6,}\d)")
_PRICE_RE = re.compile(r"\$\s?([\d,]+(?:\.\d{1,2})?)")
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def _parse_heuristic(text: str) -> dict:
    """No LLM configured: best-effort line-based extraction. Deliberately conservative
    — it's fine to leave a field null for the admin to see and fill in manually,
    it must never guess a name or price that isn't actually in the text."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    remaining = list(lines)

    phone = None
    for ln in list(remaining):
        m = _PHONE_RE.search(ln)
        if m:
            phone = m.group(1).strip()
            remaining.remove(ln)
            break

    price_cents = None
    for ln in list(remaining):
        m = _PRICE_RE.search(ln)
        if m:
            price_cents = round(float(m.group(1).replace(",", "")) * 100)
            remaining.remove(ln)
            break

    zip_code = None
    state = None
    for ln in list(remaining):
        zm = _ZIP_RE.search(ln)
        found_state = False
        for word in re.split(r"[,\s]+", ln):
            try:
                state = normalize_state(word)
                found_state = True
            except ValueError:
                continue
        if zm or found_state:
            zip_code = zm.group(1) if zm else zip_code
            remaining.remove(ln)

    name = remaining.pop(0) if remaining else None

    from app.services.vehicle import classify_vehicle  # noqa: PLC0415

    vehicle = None
    for ln in list(remaining):
        if classify_vehicle(ln):
            vehicle = ln
            remaining.remove(ln)
            break

    service_label = remaining.pop(0) if remaining else None
    notes = " ".join(remaining) if remaining else None

    return {
        "customer_name": name,
        "customer_phone": phone,
        "vehicle": vehicle,
        "state": state,
        "zip_code": zip_code,
        "address": None,
        "service_label": service_label,
        "price_cents": price_cents,
        # No LLM available to resolve relative dates ("tomorrow 2pm") reliably —
        # left for the admin to set in the preview rather than guessed.
        "starts_at": None,
        "notes": notes,
    }


def _clean(data: dict) -> dict:
    out = {
        "customer_name": data.get("customer_name") or None,
        "customer_phone": data.get("customer_phone") or None,
        "vehicle": data.get("vehicle") or None,
        "state": None,
        "zip_code": data.get("zip_code") or None,
        "address": data.get("address") or None,
        "service_label": data.get("service_label") or None,
        "price_cents": None,
        "starts_at": None,
        "notes": data.get("notes") or None,
    }

    raw_starts_at = data.get("starts_at")
    if raw_starts_at:
        try:
            out["starts_at"] = datetime.fromisoformat(str(raw_starts_at).replace("Z", "+00:00"))
        except ValueError:
            pass  # leave null rather than pass through an unparseable string
    raw_state = data.get("state")
    if raw_state:
        try:
            out["state"] = normalize_state(str(raw_state))
        except ValueError:
            out["address"] = f"{out['address']} {raw_state}".strip() if out["address"] else str(raw_state)

    price = data.get("price_cents")
    if isinstance(price, (int, float)):
        out["price_cents"] = int(price)

    return out
