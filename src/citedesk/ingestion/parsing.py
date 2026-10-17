"""Turn raw files and web pages into titled sections of clean text."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

ContentType = Literal["markdown", "text", "html"]

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class ParseError(ValueError):
    """The content cannot be used, for example an error page or an empty file."""


@dataclass(frozen=True)
class Section:
    path: str  # headings joined with " > ", e.g. "Benefits > Parental leave"
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    sections: tuple[Section, ...]


def parse(
    content: str,
    content_type: ContentType,
    *,
    fallback_title: str,
    min_chars: int = 100,
) -> ParsedDocument:
    """Parse content into sections.

    Raises `ParseError` when there is too little text; this catches error pages,
    login pages and empty uploads before they reach the index.
    """
    page_title = ""
    if content_type == "html":
        converter = _HtmlToMarkdown()
        converter.feed(content)
        converter.close()
        content, page_title = converter.markdown(), converter.page_title

    document = _parse_markdown(content, page_title or fallback_title)
    total_chars = sum(len(section.text) for section in document.sections)
    if total_chars < min_chars:
        raise ParseError(f"Only {total_chars} characters of text found; minimum is {min_chars}.")
    return document


def _parse_markdown(markdown: str, fallback_title: str) -> ParsedDocument:
    """Split markdown (or plain text) into sections at each heading."""
    sections: list[Section] = []
    headings: list[tuple[int, str]] = []  # (level, title) of the current heading path
    body: list[str] = []
    title = ""

    def close_section() -> None:
        text = "\n".join(body).strip()
        if text:
            path = " > ".join(name for _, name in headings) or title or fallback_title
            sections.append(Section(path=path, text=text))
        body.clear()

    for line in markdown.splitlines():
        match = _HEADING.match(line.strip())
        if match is None:
            body.append(line)
            continue
        close_section()
        level, name = len(match.group(1)), match.group(2).strip()
        if level == 1 and not title:
            title = name  # the document's own title is not part of its section paths
            continue
        while headings and headings[-1][0] >= level:
            headings.pop()
        headings.append((level, name))
    close_section()

    return ParsedDocument(title=title or fallback_title, sections=tuple(sections))


class _HtmlToMarkdown(HTMLParser):
    """Keeps headings and paragraph text, drops scripts, menus and page chrome."""

    _SKIPPED = frozenset({"script", "style", "nav", "header", "footer", "noscript", "svg"})
    _BLOCKS = frozenset(
        {"p", "li", "div", "br", "tr", "pre", "blockquote", "section", "article", "ul", "ol"}
    )
    _HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title = ""
        self._lines: list[str] = []
        self._buffer: list[str] = []
        self._skip_depth = 0
        self._heading_level = 0
        self._in_title = False

    def markdown(self) -> str:
        self._flush()
        return "\n".join(self._lines)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIPPED:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._HEADINGS:
            self._flush()
            self._heading_level = int(tag[1])
        elif tag in self._BLOCKS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in self._HEADINGS:
            self._flush()
            self._heading_level = 0
        elif tag in self._BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page_title += data.strip()
        elif self._skip_depth == 0:
            self._buffer.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._buffer).split())
        self._buffer.clear()
        if not text:
            return
        self._lines.append(f"{'#' * self._heading_level} {text}" if self._heading_level else text)
        self._lines.append("")
