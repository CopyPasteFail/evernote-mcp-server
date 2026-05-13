"""Helpers for generating and editing Evernote ENML content."""

from __future__ import annotations

import html
from xml.etree import ElementTree

ENML_PREFIX = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
)


def escape_plaintext_for_enml(plaintext_content: str) -> str:
    """Escape plaintext for safe insertion into ENML.

    Args:
        plaintext_content: Plain user-provided text.

    Returns:
        ENML-safe body fragment where newlines are preserved as `<br/>`.
    """

    escaped_content = html.escape(plaintext_content)
    return escaped_content.replace("\n", "<br/>")


def build_enml_document(body_fragment: str) -> str:
    """Wrap an ENML body fragment in a complete ENML document.

    Args:
        body_fragment: ENML-safe content to place inside `<en-note>`.

    Returns:
        Complete ENML document string.
    """

    return f"{ENML_PREFIX}<en-note>{body_fragment}</en-note>"


def append_plaintext_to_existing_enml(existing_enml: str, plaintext_content: str) -> str:
    """Append plaintext to an existing ENML note body.

    Args:
        existing_enml: Existing ENML document content from Evernote.
        plaintext_content: New plaintext content to append.

    Returns:
        Updated ENML string with appended content wrapped in `<div>`.

    Raises:
        ValueError: If existing content does not contain a closing `</en-note>` tag.
    """

    closing_tag = "</en-note>"
    if closing_tag not in existing_enml:
        raise ValueError("Existing note content is not valid ENML; missing </en-note>.")

    appended_fragment = f"<div>{escape_plaintext_for_enml(plaintext_content)}</div>{closing_tag}"
    return existing_enml.replace(closing_tag, appended_fragment)


def insert_plaintext_near_anchor_in_enml(
    existing_enml: str,
    anchor_text: str,
    plaintext_content: str,
    position: str = "after",
    occurrence: int = 1,
) -> str:
    """Insert plaintext before or after a top-level ENML block containing text.

    Args:
        existing_enml: Existing ENML document content from Evernote.
        anchor_text: Visible text to locate inside the note body.
        plaintext_content: Plain user-provided text to insert.
        position: Either `before` or `after` the matching top-level block.
        occurrence: One-based occurrence of the anchor-containing block to use.

    Returns:
        Updated ENML document with existing rich markup preserved.

    Raises:
        ValueError: If the ENML cannot be parsed, anchor text is missing, or
            options are invalid.
    """

    if position not in {"before", "after"}:
        raise ValueError("position must be either 'before' or 'after'.")
    if occurrence < 1:
        raise ValueError("occurrence must be a positive integer.")
    if not anchor_text:
        raise ValueError("anchor_text must not be empty.")

    en_note = _parse_en_note(existing_enml)
    _wrap_direct_en_note_text(en_note)
    insertion_index = _find_top_level_insertion_index(
        en_note=en_note,
        anchor_text=anchor_text,
        position=position,
        occurrence=occurrence,
    )
    en_note.insert(insertion_index, _build_plaintext_div(plaintext_content))
    return f"{ENML_PREFIX}{ElementTree.tostring(en_note, encoding='unicode')}"


def _parse_en_note(existing_enml: str) -> ElementTree.Element:
    """Extract and parse the `<en-note>` element from a full ENML document."""

    start_index = existing_enml.find("<en-note")
    end_index = existing_enml.rfind("</en-note>")
    if start_index == -1 or end_index == -1:
        raise ValueError("Existing note content is not valid ENML; missing <en-note>.")

    en_note_fragment = existing_enml[start_index : end_index + len("</en-note>")]
    try:
        en_note = ElementTree.fromstring(en_note_fragment)
    except ElementTree.ParseError as error:
        raise ValueError("Existing note content is not parseable ENML.") from error

    if en_note.tag != "en-note":
        raise ValueError("Existing note content is not valid ENML; root is not <en-note>.")
    return en_note


def _wrap_direct_en_note_text(en_note: ElementTree.Element) -> None:
    """Move direct body text into a block so it can be positioned safely."""

    if not en_note.text or not en_note.text.strip():
        return

    existing_children = list(en_note)
    body_div = ElementTree.Element("div")
    body_div.text = en_note.text
    en_note.text = None

    for child in existing_children:
        en_note.remove(child)
        body_div.append(child)

    en_note.insert(0, body_div)


def _find_top_level_insertion_index(
    en_note: ElementTree.Element,
    anchor_text: str,
    position: str,
    occurrence: int,
) -> int:
    """Find where a new top-level block belongs relative to anchor text."""

    matching_occurrences = 0
    children = list(en_note)
    for index, child in enumerate(children):
        visible_text = "".join(child.itertext())
        if anchor_text not in visible_text:
            continue

        matching_occurrences += 1
        if matching_occurrences != occurrence:
            continue

        if position == "before":
            return index
        return index + 1

    raise ValueError("Anchor text was not found in the note body.")


def _build_plaintext_div(plaintext_content: str) -> ElementTree.Element:
    """Build an ENML `<div>` preserving newlines as `<br/>` elements."""

    div = ElementTree.Element("div")
    lines = plaintext_content.split("\n")
    div.text = lines[0]
    for line in lines[1:]:
        line_break = ElementTree.SubElement(div, "br")
        line_break.tail = line
    return div
