"""Unit tests for Evernote ENML transformation helpers."""

from __future__ import annotations

import pytest

from evernote_mcp.evernote.enml import insert_plaintext_near_anchor_in_enml


RICH_ENML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
    '<en-note><h1>Local, CLI, and Agentic LLM Tools</h1>'
    '<div><span>AionUi target section</span></div>'
    '<ul><li><a href="https://example.com">Existing link</a></li></ul>'
    '</en-note>'
)


def test_insert_plaintext_after_anchor_preserves_existing_rich_enml() -> None:
    updated_enml = insert_plaintext_near_anchor_in_enml(
        existing_enml=RICH_ENML,
        anchor_text="AionUi target section",
        plaintext_content="New <unsafe> line\nSecond line",
        position="after",
    )

    assert updated_enml.startswith(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
    )
    assert "<h1>Local, CLI, and Agentic LLM Tools</h1>" in updated_enml
    assert '<a href="https://example.com">Existing link</a>' in updated_enml
    assert (
        "<div>New &lt;unsafe&gt; line<br />Second line</div>"
        in updated_enml
    )
    assert updated_enml.index("AionUi target section") < updated_enml.index(
        "New &lt;unsafe&gt; line"
    )


def test_insert_plaintext_before_anchor() -> None:
    updated_enml = insert_plaintext_near_anchor_in_enml(
        existing_enml=RICH_ENML,
        anchor_text="AionUi target section",
        plaintext_content="Inserted first",
        position="before",
    )

    assert updated_enml.index("Inserted first") < updated_enml.index(
        "AionUi target section"
    )


def test_insert_plaintext_after_anchor_in_direct_en_note_text() -> None:
    existing_enml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        "<en-note>plain anchor text<br />next line</en-note>"
    )

    updated_enml = insert_plaintext_near_anchor_in_enml(
        existing_enml=existing_enml,
        anchor_text="plain anchor text",
        plaintext_content="inserted section",
        position="after",
    )

    assert updated_enml.index("plain anchor text") < updated_enml.index(
        "inserted section"
    )


def test_insert_plaintext_before_anchor_in_direct_en_note_text() -> None:
    existing_enml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        "<en-note>plain anchor text<br />next line</en-note>"
    )

    updated_enml = insert_plaintext_near_anchor_in_enml(
        existing_enml=existing_enml,
        anchor_text="plain anchor text",
        plaintext_content="inserted section",
        position="before",
    )

    assert updated_enml.index("inserted section") < updated_enml.index(
        "plain anchor text"
    )


def test_insert_plaintext_selects_requested_occurrence() -> None:
    existing_enml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        "<en-note><div>repeat anchor</div><div>repeat anchor</div></en-note>"
    )

    updated_enml = insert_plaintext_near_anchor_in_enml(
        existing_enml=existing_enml,
        anchor_text="repeat anchor",
        plaintext_content="after second",
        position="after",
        occurrence=2,
    )

    assert updated_enml.index("repeat anchor") < updated_enml.rindex("repeat anchor")
    assert updated_enml.rindex("repeat anchor") < updated_enml.index("after second")


def test_insert_plaintext_fails_when_anchor_is_missing() -> None:
    with pytest.raises(ValueError, match="Anchor text was not found"):
        insert_plaintext_near_anchor_in_enml(
            existing_enml=RICH_ENML,
            anchor_text="missing",
            plaintext_content="new section",
            position="after",
        )


def test_insert_plaintext_rejects_invalid_position() -> None:
    with pytest.raises(ValueError, match="position must be"):
        insert_plaintext_near_anchor_in_enml(
            existing_enml=RICH_ENML,
            anchor_text="AionUi target section",
            plaintext_content="new section",
            position="middle",
        )


def test_insert_plaintext_rejects_non_positive_occurrence() -> None:
    with pytest.raises(ValueError, match="occurrence must be"):
        insert_plaintext_near_anchor_in_enml(
            existing_enml=RICH_ENML,
            anchor_text="AionUi target section",
            plaintext_content="new section",
            occurrence=0,
        )
