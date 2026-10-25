"""The printable text (ocr/scanmylib_ocr/printable_text.py): the escape of the characters a terminal does not show,
and the cut of an escaped text.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import re
import sys
import unittest
from typing import ClassVar

from scanmylib_ocr.printable_text import cut_escaped, escape_unprintable

CODE_POINT_COUNT = sys.maxunicode + 1
PRINTABLE_TEXT = "Example Book, by Zoë Doe"
TEXT_THAT_READS_AS_AN_ESCAPE = "\\x1b"
ESCAPE_PATTERN = re.compile(r"\\x([0-9a-f]{2})|\\u([0-9a-f]{4})|\\U([0-9a-f]{8})")
TERMINAL_CONTROLS = {
    "an escape, which starts a control sequence": ("\N{ESCAPE}", "\\x1b"),
    "a backslash, which would make an escape ambiguous": ("\\", "\\x5c"),
    "a tab": ("\t", "\\x09"),
    "a C1 control sequence introducer": ("\x9b", "\\x9b"),
    "a right-to-left override, which reorders what follows": ("\N{RIGHT-TO-LEFT OVERRIDE}", "\\u202e"),
    "a tag character, which renders as nothing": ("\U000e0001", "\\U000e0001"),
}
CUT_LIMIT_CHARACTERS = 6
CUT_ESCAPED_TEXTS = {
    "a cut inside an escape of a byte, which it drops whole": ("abc\\x1b", "abc"),
    "a cut inside an escape of four hexadecimal digits, which it drops whole": ("a\\u202e", "a"),
    "a cut inside an escape of eight hexadecimal digits, which it drops whole": ("a\\U000e0001", "a"),
    "a cut right after the backslash of an escape, which it drops": ("abcde\\x1b", "abcde"),
    "a cut right after an escape, which it keeps": ("ab\\x1bcd", "ab\\x1b"),
    "a cut in plain text, at the limit": ("abcdefgh", "abcdef"),
    "a text within the limit, kept whole": ("a\\x1b", "a\\x1b"),
}


def read_escapes(text: str) -> str:
    return ESCAPE_PATTERN.sub(lambda match: chr(int(next(group for group in match.groups() if group), 16)), text)


class TheEscapeUnprintableFunctionWhenGivenEveryCodePoint(unittest.TestCase):
    unprintable_outputs: ClassVar[list[str]]
    checked_code_point_count: ClassVar[int]
    original_text: ClassVar[str]
    read_back_text: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.unprintable_outputs = []
        cls.checked_code_point_count = 0
        for code_point in range(CODE_POINT_COUNT):
            escaped_character = escape_unprintable(chr(code_point))
            cls.checked_code_point_count += 1
            if not escaped_character.isprintable():
                cls.unprintable_outputs.append(f"U+{code_point:04X}: {escaped_character!r}")
        every_character = "".join(chr(code_point) for code_point in range(CODE_POINT_COUNT))
        cls.original_text = every_character + TEXT_THAT_READS_AS_AN_ESCAPE
        cls.read_back_text = read_escapes(escape_unprintable(cls.original_text))

    def test_should_write_only_printable_characters_so_that_no_control_sequence_reaches_a_terminal(self) -> None:
        self.assertEqual(self.checked_code_point_count, CODE_POINT_COUNT)
        self.assertEqual(self.unprintable_outputs, [])

    def test_should_be_undone_by_reading_each_escape_so_that_the_log_keeps_what_the_sandbox_printed(self) -> None:
        # assertEqual would diff a million characters on a failure.
        self.assertTrue(self.read_back_text == self.original_text, "the escaped text does not read back whole")


class TheEscapeUnprintableFunctionWhenGivenTerminalControls(unittest.TestCase):
    escaped_controls: ClassVar[dict[str, tuple[str, str]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.escaped_controls = {
            name: (escape_unprintable(control), expected_escape)
            for name, (control, expected_escape) in TERMINAL_CONTROLS.items()
        }

    def test_should_write_each_one_as_its_escape(self) -> None:
        self.assertEqual(len(self.escaped_controls), len(TERMINAL_CONTROLS))
        for name, (escaped_control, expected_escape) in self.escaped_controls.items():
            with self.subTest(name):
                self.assertEqual(escaped_control, expected_escape)


class TheEscapeUnprintableFunctionWhenGivenPrintableText(unittest.TestCase):
    def setUp(self) -> None:
        self.escaped_text = escape_unprintable(PRINTABLE_TEXT)

    def test_should_keep_it_as_it_is_so_that_the_log_reads_as_the_sandbox_printed_it(self) -> None:
        self.assertEqual(self.escaped_text, PRINTABLE_TEXT)


class TheCutEscapedFunctionWhenGivenEscapedTexts(unittest.TestCase):
    def setUp(self) -> None:
        self.cut_texts = {
            name: (cut_escaped(escaped_text, CUT_LIMIT_CHARACTERS), expected_cut_text)
            for name, (escaped_text, expected_cut_text) in CUT_ESCAPED_TEXTS.items()
        }

    def test_should_cut_each_one_within_the_limit_so_that_no_part_of_an_escape_reads_as_other_characters(self) -> None:
        self.assertEqual(len(self.cut_texts), len(CUT_ESCAPED_TEXTS))
        for name, (cut_text, expected_cut_text) in self.cut_texts.items():
            with self.subTest(name):
                self.assertEqual(cut_text, expected_cut_text)


if __name__ == "__main__":
    unittest.main()
