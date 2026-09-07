"""Retrieval + grounded answering.

Hard rule carried over from the patient project: the agent answers only from what
retrieval returned. Empty retrieval means "I don't know", never a guessed price.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentChunk
from app.schemas import AskResponse, RetrievedChunk
from app.services.embeddings import cosine_similarity, get_embedder

settings = get_settings()

NO_ANSWER = (
    "I don't have that in our current information. Let me take your number and have "
    "someone from the shop call you right back with an exact answer."
)

SYSTEM_PROMPT = """You are the phone assistant for a mobile car detailing business.

Rules, without exception:
- Answer ONLY from the CONTEXT below. Never invent a price, duration, or policy.
- If the CONTEXT does not contain the answer, say you don't have it and offer a callback.
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
    if not sources:
        return AskResponse(answer=NO_ANSWER, grounded=False, sources=[])

    context = "\n\n---\n\n".join(f"[{s.document_title}] {s.content}" for s in sources)
    text = _complete(question, context)
    return AskResponse(answer=text, grounded=True, sources=sources)


def _complete(question: str, context: str) -> str:
    """LLM call behind one function so Kimi K2 / another model swaps in one place."""
    if not settings.openai_api_key:
        # Extractive fallback: return the top chunk verbatim rather than fabricate.
        return context.split("\n\n---\n\n")[0]

    from openai import OpenAI  # noqa: PLC0415

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
        ],
    )
    return (resp.choices[0].message.content or NO_ANSWER).strip()
