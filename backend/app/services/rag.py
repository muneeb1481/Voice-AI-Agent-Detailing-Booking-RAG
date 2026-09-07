"""Retrieval + grounded answering.

Hard rule carried over from the patient project: the agent answers only from what
retrieval returned. Empty retrieval means "I don't know", never a guessed price.
"""
from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentChunk
from app.schemas import AskResponse, RetrievedChunk
from app.services.embeddings import cosine_similarity, get_embedder

settings = get_settings()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

NO_ANSWER = (
    "I don't have that in our current information. Let me take your number and have "
    "someone from the shop call you right back with an exact answer."
)


def _grounded_system_prompt() -> str:
    return f"""You are the phone assistant for {settings.brand_name}, a mobile car detailing
company that serves customers across the United States.

Rules, without exception:
- Answer ONLY from the CONTEXT below. Never invent a price, duration, or policy.
- If the CONTEXT does not contain the answer, say you don't have it and offer a callback.
- Keep answers under 40 words. You are being spoken aloud on a phone call.
- Never read out URLs, IDs, or formatting.
"""


def _ungrounded_system_prompt() -> str:
    # No matching document chunk was found. The model may still have a normal
    # conversation — greetings, "what do you do", small talk — but it must not
    # invent the one thing this whole system exists to protect: a specific price,
    # duration, or policy detail it was not actually given.
    return f"""You are the phone assistant for {settings.brand_name}, a mobile car detailing
company that serves customers across the United States.

Nothing in our documented pricing, services, or policies matched this question, so you have
no specific facts to draw on for it. Rules, without exception:
- You may have a brief, natural conversation: greetings, what the business generally does,
  clarifying what the caller needs, general small talk.
- Never state a specific price, dollar amount, exact duration, or specific policy detail —
  you were not given one for this question, so any number would be invented.
- If the caller is asking for a specific price, duration, or policy detail, say plainly that
  you don't have that exact information and offer to have someone call them back.
- Keep answers under 40 words. You are being spoken aloud on a phone call.
- Never read out URLs, IDs, or formatting.
"""


def ingest_document(db: Session, document: Document, chunks: list[str]) -> int:
    embedder = get_embedder()
    vectors = embedder.embed(chunks) if chunks else []
    for i, (content, vector) in enumerate(zip(chunks, vectors, strict=True)):
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=i,
                content=content,
                embedding=vector,
            )
        )
    document.chunk_count = len(chunks)
    return len(chunks)


def retrieve(db: Session, question: str, top_k: int = 4) -> list[RetrievedChunk]:
    embedder = get_embedder()
    query_vec = embedder.embed([question])[0]
    min_score = embedder.min_score

    if settings.uses_postgres:
        rows = db.execute(
            select(DocumentChunk, Document.title)
            .join(Document, Document.id == DocumentChunk.document_id)
            .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        ).all()
        scored = [(chunk, title, 1.0 - _distance(chunk, query_vec)) for chunk, title in rows]
    else:
        rows = db.execute(
            select(DocumentChunk, Document.title).join(
                Document, Document.id == DocumentChunk.document_id
            )
        ).all()
        scored = [
            (chunk, title, cosine_similarity(query_vec, chunk.embedding or []))
            for chunk, title in rows
        ]
        scored.sort(key=lambda r: r[2], reverse=True)
        scored = scored[:top_k]

    return [
        RetrievedChunk(
            document_id=chunk.document_id,
            document_title=title,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            score=round(score, 4),
        )
        for chunk, title, score in scored
        if score >= min_score
    ]


def _distance(chunk: DocumentChunk, query_vec: list[float]) -> float:
    return 1.0 - cosine_similarity(query_vec, list(chunk.embedding or []))


def answer(db: Session, question: str, top_k: int = 4) -> AskResponse:
    sources = retrieve(db, question, top_k)

    if sources:
        context = "\n\n---\n\n".join(f"[{s.document_title}] {s.content}" for s in sources)
        messages = [
            {"role": "system", "content": _grounded_system_prompt()},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
        ]
        text = _complete(messages, fallback=context.split("\n\n---\n\n")[0])
        return AskResponse(answer=text, grounded=True, sources=sources)

    # No matching chunk: still let the LLM respond naturally, just without a
    # license to invent the specific fact nothing backs up.
    messages = [
        {"role": "system", "content": _ungrounded_system_prompt()},
        {"role": "user", "content": question},
    ]
    text = _complete(messages, fallback=NO_ANSWER)
    return AskResponse(answer=text, grounded=False, sources=[])


def _complete(messages: list[dict], fallback: str) -> str:
    """LLM call behind one function so the provider swaps in one place."""
    if settings.groq_key_list:
        text = _complete_groq(messages)
        if text is not None:
            return text

    if settings.openai_api_key:
        from openai import OpenAI  # noqa: PLC0415

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.1, messages=messages
        )
        return (resp.choices[0].message.content or fallback).strip()

    # No LLM configured at all: fall back rather than fabricate.
    return fallback


def _complete_groq(messages: list[dict]) -> str | None:
    """Try each configured Groq key in turn; a 429 (rate limit) rotates to the next one."""
    last_error: Exception | None = None
    for key in settings.groq_key_list:
        try:
            resp = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.groq_model,
                    "temperature": 0.1,
                    "messages": messages,
                },
                timeout=20,
            )
            if resp.status_code == 429:
                continue  # this key is rate-limited, try the next one
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return (content or NO_ANSWER).strip()
        except httpx.HTTPError as exc:
            last_error = exc
            continue

    if last_error is not None:
        # All keys exhausted or erroring — fall through to whatever provider is next
        # rather than surfacing a 500 to the caller mid-call.
        return None
    return None
