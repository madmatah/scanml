"""The escape of the characters a terminal does not show, and the cut of an escaped text.

A terminal acts on the control sequences in the text it prints, such as OSC 52, which writes the clipboard: the
sandbox's output reaches an operator's terminal only escaped.
"""

from __future__ import annotations

_ESCAPE_LENGTHS_CHARACTERS = {"x": 4, "u": 6, "U": 10}


def escape_unprintable(text: str) -> str:
    if text.isprintable() and "\\" not in text:
        return text
    return "".join(
        character if character.isprintable() and character != "\\" else _escape(character) for character in text
    )


def cut_escaped(escaped_text: str, limit_characters: int) -> str:
    """A part of an escape would read as other characters, so a cut drops an escape whole.

    Every backslash of an escaped text starts an escape, the backslash itself being escaped.
    """
    cut_text = escaped_text[:limit_characters]
    last_escape_start = cut_text.rfind("\\")
    if last_escape_start == -1:
        return cut_text
    escape_length_characters = _ESCAPE_LENGTHS_CHARACTERS.get(
        escaped_text[last_escape_start + 1 : last_escape_start + 2]
    )
    if escape_length_characters is None or last_escape_start + escape_length_characters > len(cut_text):
        return cut_text[:last_escape_start]
    return cut_text


def _escape(character: str) -> str:
    code_point = ord(character)
    if code_point <= 0xFF:
        return f"\\x{code_point:02x}"
    if code_point <= 0xFFFF:
        return f"\\u{code_point:04x}"
    return f"\\U{code_point:08x}"
