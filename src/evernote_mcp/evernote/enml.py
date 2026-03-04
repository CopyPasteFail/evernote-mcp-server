"""Helpers for generating and editing Evernote ENML content."""

from __future__ import annotations

import html

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
