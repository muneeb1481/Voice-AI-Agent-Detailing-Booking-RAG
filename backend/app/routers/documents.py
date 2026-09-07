from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Document
from app.schemas import DocumentOut
from app.security import current_admin
from app.services.chunking import chunk_text, extract_text
from app.services.rag import ingest_document

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_BYTES = 5 * 1024 * 1024


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> list[Document]:
    return list(
        db.execute(select(Document).order_by(Document.created_at.desc())).scalars().all()
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _: str = Depends(current_admin),
) -> Document:
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 5 MB.")

    text = extract_text(file.filename or "upload.txt", file.content_type or "", raw)
    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No readable text found in that file.")

    document = Document(
        title=title or (file.filename or "Untitled"),
        filename=file.filename or "upload.txt",
        content_type=file.content_type or "text/plain",
        size_bytes=len(raw),
    )
    db.add(document)
    db.flush()
    ingest_document(db, document, chunks)
    db.commit()
    db.refresh(document)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str, db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    # cascade drops the chunks with it — no stale embeddings left behind.
    db.delete(document)
    db.commit()
