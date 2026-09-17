from chunking import chunk_text, detect_content_type, token_count


def test_chunking_is_token_bounded_and_indexed():
    text = " ".join(f"word{i}" for i in range(1200))
    chunks = chunk_text(text, filename="notes.txt", chunk_tokens=100, overlap_tokens=20)
    assert len(chunks) > 1
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(token_count(chunk.text) <= 100 for chunk in chunks)
    assert all(chunk.content_type == "plain" for chunk in chunks)


def test_content_type_detection():
    assert detect_content_type("notes.md", "# Heading\ncontent") == "markdown"
    assert detect_content_type("page.html", "<p>Hello</p>") == "html"
    assert detect_content_type("notes.txt", "plain text") == "plain"


def test_markdown_heading_is_preserved():
    chunks = chunk_text("# Photosynthesis\nPlants convert light energy into chemical energy.\n\n# Respiration\nCells release energy.", filename="biology.md", chunk_tokens=50)
    assert chunks
    assert any("# Photosynthesis" in chunk.text for chunk in chunks)
    assert all(chunk.content_type == "markdown" for chunk in chunks)
