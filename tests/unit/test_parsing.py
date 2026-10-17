import pytest

from citedesk.ingestion.parsing import ParseError, parse

LONG_TEXT = "This sentence is here to give the page enough text to be accepted. " * 4


def test_markdown_sections_carry_their_heading_path() -> None:
    document = parse(
        f"# Handbook\n\n## Benefits\n\n### Leave\n\n{LONG_TEXT}\n\n## Expenses\n\n{LONG_TEXT}",
        "markdown",
        fallback_title="fallback",
    )
    assert document.title == "Handbook"
    assert [section.path for section in document.sections] == [
        "Benefits > Leave",
        "Expenses",
    ]


def test_plain_text_becomes_one_section_named_after_the_title() -> None:
    document = parse(LONG_TEXT, "text", fallback_title="Notes")
    assert document.title == "Notes"
    assert [section.path for section in document.sections] == ["Notes"]


def test_html_drops_scripts_and_menus_and_keeps_headings() -> None:
    html = f"""
    <html><head><title>Policy page</title><script>var secret = 1;</script></head>
    <body><nav>Home | About</nav>
    <h1>Policy</h1><h2>Passwords</h2><p>{LONG_TEXT}</p></body></html>
    """
    document = parse(html, "html", fallback_title="fallback")
    text = " ".join(section.text for section in document.sections)
    assert document.title == "Policy"  # the page heading wins over <title>
    assert document.sections[0].path == "Passwords"
    assert "secret" not in text
    assert "Home | About" not in text


def test_too_little_text_is_rejected_like_an_error_page() -> None:
    with pytest.raises(ParseError):
        parse("<html><body><h1>Access denied</h1></body></html>", "html", fallback_title="x")
