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

from fastapi import Request


async def parse_tool_call(request: Request) -> tuple[dict, str | None]:
    """Returns (arguments, tool_call_id). tool_call_id is None for a flat/legacy
    body, signaling the caller wants the old unwrapped response and old-style
    HTTP error codes rather than a wrapped 200 with the error as text."""
    raw = await request.body()
    if not raw:
        return {}, None  # a no-argument tool call (e.g. list_services) with an empty body
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return {}, None
    message = body.get("message") if isinstance(body, dict) else None
    if isinstance(message, dict) and message.get("type") == "tool-calls":
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
            return arguments or {}, call.get("id")
    return body if isinstance(body, dict) else {}, None


def tool_response(result, tool_call_id: str | None):
    """Wrap `result` for a real Vapi call; pass it through unwrapped for the
    flat/legacy admin-and-test shape."""
    if tool_call_id is not None:
        return {"results": [{"toolCallId": tool_call_id, "result": result}]}
    return result
