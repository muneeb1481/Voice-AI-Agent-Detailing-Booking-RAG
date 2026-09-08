"""One shared chat-completion client for every LLM call in the app.

Kimi (Moonshot) is the primary provider — cheaper/faster with reasoning_effort
turned down low. Groq is the secondary/fallback: tried only if Kimi isn't
configured, errors, or times out, rotating through every configured Groq key on
a 429. Callers never talk to a provider directly, so the priority order lives
in exactly one place.
"""
import json

import httpx

from app.config import get_settings

settings = get_settings()

KIMI_URL = "https://api.moonshot.ai/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def chat_completion(
    messages: list[dict],
    *,
    temperature: float = 0,
    json_mode: bool = False,
    timeout: float = 20,
) -> str | None:
    """Returns the completion text, or None if no provider is configured or every
    provider failed — callers decide what to do then (heuristic parse, a fixed
    fallback string, etc.), this function never fabricates a result."""
    if settings.kimi_api_key:
        text = _complete_kimi(messages, temperature, json_mode, timeout)
        if text is not None:
            return text

    if settings.groq_key_list:
        text = _complete_groq(messages, temperature, json_mode, timeout)
        if text is not None:
            return text

    return None


def _complete_kimi(
    messages: list[dict], temperature: float, json_mode: bool, timeout: float
) -> str | None:
    body = {
        "model": settings.kimi_model,
        "temperature": temperature,
        "messages": messages,
        "reasoning_effort": settings.kimi_reasoning_effort,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        resp = httpx.post(
            KIMI_URL,
            headers={"Authorization": f"Bearer {settings.kimi_api_key}"},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() if content else None
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError):
        return None  # fall through to Groq


def _complete_groq(
    messages: list[dict], temperature: float, json_mode: bool, timeout: float
) -> str | None:
    """Try each configured Groq key in turn; a 429 (rate limit) rotates to the next one."""
    body = {
        "model": settings.groq_model,
        "temperature": temperature,
        "messages": messages,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    for key in settings.groq_key_list:
        try:
            resp = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json=body,
                timeout=timeout,
            )
            if resp.status_code == 429:
                continue  # this key is rate-limited, try the next one
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return content.strip() if content else None
        except httpx.HTTPError:
            continue
    return None
