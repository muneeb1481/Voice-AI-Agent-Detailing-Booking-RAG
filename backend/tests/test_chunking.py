from app.services.chunking import chunk_text


def test_chunks_overlap():
    text = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_text(text, chunk_words=100, overlap_words=20)
    assert len(chunks) > 1
    tail = chunks[0].split()[-20:]
    head = chunks[1].split()[:20]
    assert tail == head


def test_empty_text():
    assert chunk_text("") == []


def test_short_text_is_one_chunk():
    assert len(chunk_text("just a few words here")) == 1
