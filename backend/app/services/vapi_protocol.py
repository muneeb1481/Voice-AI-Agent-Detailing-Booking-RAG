"""Vapi's real custom-tool request/response contract.

A live phone call POSTs a tool call wrapped as:
    {"message": {"type": "tool-calls", "toolCallList": [
        {"id": "...", "function": {"name": "...", "arguments": {...}}}
    ]}}
and expects the response back wrapped as:
    {"results": [{"toolCallId": "...", "result": <anything>}]}

Every endpoint in this app was originally built and tested against a FLAT
body (the arguments alone, e.g. {"phone": "..."}) — which is what the admin
dashboard's own Agent Test page sends, and what the test suite sends. That
flat shape is not what a real Vapi call ever sends, so real calls never
actually worked: our endpoints couldn't parse the request, and even where
they degraded gracefully, the raw unwrapped response was silently unusable
to Vapi's harness.

This module lets every tool endpoint support BOTH shapes: a real wrapped
call is unwrapped for parsing and the response re-wrapped to match; the
existing flat admin/test shape keeps working exactly as before (unwrapped
response, real HTTPException status codes) so nothing already depended on
that behavior breaks.
"""
import json
import logging
import traceback
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

logger = logging.getLogger("app.vapi")


async def parse_tool_call(request: Request) -> tuple[dict, str | None]:
    """Returns (arguments, tool_call_id). tool_call_id is None for a flat/legacy
    body, signaling the caller wants the old unwrapped response and old-style
    HTTP error codes rather than a wrapped 200 with the error as text."""
    args, tool_call_id, _verified_number = await parse_tool_call_full(request)
    return args, tool_call_id


async def parse_tool_call_full(request: Request) -> tuple[dict, str | None, str | None]:
    """Same as parse_tool_call, plus the caller's VERIFIED phone number when Vapi's
    request includes one (a real phone call carries call.customer.number alongside
    the tool call) — None for a flat/legacy body or a call type with no caller ID
    (e.g. a web test call). Callers that must never trust an LLM-supplied phone
    number (lookup_appointments) should prefer this over the parsed arguments."""
    raw = await request.body()
    if not raw:
        return {}, None, None  # a no-argument tool call (e.g. list_services) with an empty body
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return {}, None, None
    if not isinstance(body, dict):
        return {}, None, None

    message = body.get("message")
    if isinstance(message, dict) and message.get("type") == "tool-calls":
        verified_number = _extract_customer_number(message) or _extract_customer_number(body)
        calls = message.get("toolCallList") or message.get("toolCalls") or []
        if calls:
            call = calls[0]
            fn = call.get("function", {}) or {}
            arguments = fn.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            return arguments or {}, call.get("id"), verified_number
    return body, None, None


def _extract_customer_number(obj: dict) -> str | None:
    for path in (
        ("customer", "number"),
        ("call", "customer", "number"),
    ):
        cur = obj
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        if isinstance(cur, str) and cur.strip():
            return cur
    return None


def tool_response(result, tool_call_id: str | None):
    """Wrap `result` for a real Vapi call; pass it through unwrapped for the
    flat/legacy admin-and-test shape."""
    if tool_call_id is not None:
        return {"results": [{"toolCallId": tool_call_id, "result": result}]}
    return result


class SafeToolRoute(APIRoute):
    """A live call twice showed Vapi's log recording "No result returned" for a
    tool call — Vapi's own generic error for a response it couldn't parse,
    which happens on anything but a clean 200 with a proper body. Whatever the
    underlying cause (a DB hiccup, a cold connection, anything else), an
    UNHANDLED exception escaping a tool endpoint as a raw 500 is exactly what
    produces that unparseable response and leaves the LLM with nothing to
    react to except guessing.

    This wraps every route on the vapi router so that can never happen again:
    an unhandled exception is logged (with the real traceback, so it's
    visible in Render's own logs for diagnosing what actually failed, without
    needing to reproduce it live) and converted into a normal, parseable
    response instead of an opaque 500 — a wrapped `results` entry for a real
    Vapi call, or a real HTTP 500 for the flat/legacy admin-test shape
    (unchanged from before this existed)."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            try:
                return await original(request)
            except HTTPException:
                # A deliberate raise (bad tool secret, flat-mode validation error,
                # a domain error in flat/legacy mode) — never mask these, they're
                # not the unexpected-crash case this route exists to catch.
                raise
            except Exception as exc:  # noqa: BLE001 — this route's entire purpose
                logger.error(
                    "Unhandled exception on %s %s: %s\n%s",
                    request.method,
                    request.url.path,
                    exc,
                    traceback.format_exc(),
                )
                tool_call_id = None
                try:
                    body = json.loads(await request.body())
                    message = body.get("message") if isinstance(body, dict) else None
                    if isinstance(message, dict) and message.get("type") == "tool-calls":
                        calls = message.get("toolCallList") or message.get("toolCalls") or []
                        if calls:
                            tool_call_id = calls[0].get("id")
                except Exception:  # noqa: BLE001 — best-effort only
                    pass

                error_text = (
                    "There was a brief technical issue on our end processing that — "
                    "please try again, or offer to have someone call the customer back."
                )
                if tool_call_id is not None:
                    return JSONResponse(
                        status_code=200,
                        content={"results": [{"toolCallId": tool_call_id, "result": error_text}]},
                    )
                return JSONResponse(status_code=500, content={"detail": error_text})

        return safe_handler
