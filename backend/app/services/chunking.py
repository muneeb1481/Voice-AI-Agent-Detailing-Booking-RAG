"""Token-ish chunking with overlap. Word-based so it needs no tokenizer dependency."""

DEFAULT_CHUNK_WORDS = 320
DEFAULT_OVERLAP_WORDS = 60


def chunk_text(
    text: str,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[str]:
    if overlap_words >= chunk_words:
        raise ValueError("overlap_words must be smaller than chunk_words")

    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    step = chunk_words - overlap_words
    for start in range(0, len(words), step):
        window = words[start : start + chunk_words]
        if not window:
            break
        chunks.append(" ".join(window))
        if start + chunk_words >= len(words):
            break
    return chunks


def extract_text(filename: str, content_type: str, raw: bytes) -> str:
    if filename.lower().endswith(".pdf") or content_type == "application/pdf":
        import io  # noqa: PLC0415

        from pypdf import PdfReader  # noqa: PLC0415

        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return raw.decode("utf-8", errors="replace")
