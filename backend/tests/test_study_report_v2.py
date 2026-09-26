from study_report import (
    ACADEMIC_SECTIONS,
    build_report_plan,
    normalize_report_data,
    normalize_section_response,
    render_report_markdown,
    report_to_docx,
)


def test_report_plan_is_topic_adaptive():
    scientific = build_report_plan("Detailed notes on photosynthesis", "study")
    historical = build_report_plan("Detailed notes on the French Revolution", "study")

    assert scientific != historical
    assert "mechanism or how it works" in scientific
    assert "chronology and major events" in historical


def test_academic_report_plan_is_structured():
    plan = build_report_plan("My science project", "academic")
    assert plan == ACADEMIC_SECTIONS


def test_explicit_report_sections_are_preserved():
    plan = build_report_plan(
        "cell biology",
        "study",
        ["Core concept", "Mechanism", "Exam questions"],
    )
    assert plan == ["Core concept", "Mechanism", "Exam questions"]


def test_report_markdown_contains_toc_terms_and_references():
    data = normalize_report_data(
        {
            "title": "Cell Biology",
            "summary": "Cells contain DNA.",
            "sections": [
                {
                    "heading": "Core concept",
                    "content": "DNA stores genetic information in cells.",
                    "points": ["DNA is genetic material."],
                    "source_refs": ["biology.md"],
                }
            ],
            "key_terms": [
                {
                    "term": "DNA",
                    "definition": "Genetic material in cells.",
                    "source_refs": ["biology.md"],
                }
            ],
            "exam_takeaways": ["Know the role of DNA."],
            "exam_questions": [
                {"question": "What is DNA?", "answer": "Genetic material."}
            ],
        },
        plan=["Core concept"],
        allowed_sources=["biology.md"],
    )

    markdown = render_report_markdown(
        data,
        source_names=["biology.md"],
        web_sources=[
            {"title": "NCBI", "url": "https://example.test/ncbi"},
        ],
    )

    assert "## Table of Contents" in markdown
    assert "## Core concept" in markdown
    assert "## Key Terms" in markdown
    assert "## Exam-Oriented Takeaways" in markdown
    assert "## Practice Questions" in markdown
    assert "## References" in markdown
    assert "https://example.test/ncbi" in markdown


def test_report_section_normalization_keeps_allowed_sources():
    section = normalize_section_response(
        {
            "heading": "Mechanism",
            "content": "Photosynthesis uses light energy.",
            "points": ["Light-dependent reactions."],
            "source_refs": ["biology.md", "not-allowed.txt"],
        },
        "Mechanism",
        ["biology.md"],
    )

    assert section["heading"] == "Mechanism"
    assert section["source_refs"] == ["biology.md"]


def test_report_docx_export_returns_a_valid_zip():
    document = report_to_docx("# Test Report\n\n## Section\n\n- Point", "Test Report")
    assert document[:2] == b"PK"
    assert len(document) > 1000
