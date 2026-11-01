"""The copy of screenshots without the chunks that may carry hidden data (`pr_screenshots.py strip`), into a directory
that it creates, and whose copies the publication then takes, against a bare origin that the script takes for a GitHub
repository (screenshots_support.py).

Needs git. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_strip_screenshots.py'
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from screenshots_support import HIDDEN_DATA_CHUNKS, HIDDEN_TEXT, PUBLISH, STRIP, Remote, Run, make_png

NUMBER = "12"
#: The chunks of an image besides its pixels: sRGB with its rendering intent, and gAMA of 1/2.2.
IMAGE_CHUNKS = [(b"sRGB", bytes([0])), (b"gAMA", (45455).to_bytes(4, "big"))]
#: A picture as a capture tool saves it: the chunks of its image, and others that may carry what it does not show.
CAPTURED = make_png(*IMAGE_CHUNKS[:1], *((chunk, HIDDEN_TEXT) for chunk in HIDDEN_DATA_CHUNKS), *IMAGE_CHUNKS[1:])
#: The same picture with the chunks of its image only, in their order.
STRIPPED = make_png(*IMAGE_CHUNKS)
#: A picture that holds the chunks of its image only.
PLAIN = make_png(shade=255)
#: A picture whose copy weighs more than LARGEST_FILE_BYTES: a pHYs chunk, which the copy keeps, of 4 KB.
HEAVY = make_png((b"pHYs", bytes(4096)))
#: What a file may weigh in the run whose second write fails: PLAIN's copy fits, HEAVY's does not.
LARGEST_FILE_BYTES = 1024


def make_remote(test_case: type[unittest.TestCase]) -> Remote:
    directory = tempfile.TemporaryDirectory(prefix="pr-screenshots-tests-")
    test_case.addClassCleanup(directory.cleanup)
    return Remote(Path(os.path.realpath(directory.name)))


def read_tree(directory: Path) -> dict[str, bytes]:
    """The files under `directory`, by their path relative to it."""
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


class WhenPicturesHoldChunksThatMayCarryHiddenData(unittest.TestCase):
    stripping: ClassVar[Run]
    copies: ClassVar[Path]
    copied: ClassVar[dict[str, bytes]]
    pictures_after: ClassVar[list[bytes]]
    publication: ClassVar[Run]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        pictures = [
            remote.write_picture("library-light.png", CAPTURED),
            remote.write_picture("library-dark.png", PLAIN),
        ]
        cls.copies = remote.directory / "pictures" / "stripped"
        cls.stripping = remote.run(STRIP, str(cls.copies), *map(str, pictures))
        cls.copied = read_tree(cls.copies)
        cls.pictures_after = [picture.read_bytes() for picture in pictures]
        cls.publication = remote.run(PUBLISH, NUMBER, *(str(cls.copies / name) for name in sorted(cls.copied)))

    def test_should_print_the_path_of_each_copy(self) -> None:
        self.assertEqual(
            self.stripping.stdout.splitlines(),
            [str(self.copies / "library-light.png"), str(self.copies / "library-dark.png")],
        )

    def test_should_keep_the_pixels_and_the_chunks_of_the_image_in_their_order(self) -> None:
        self.assertEqual(self.copied, {"library-light.png": STRIPPED, "library-dark.png": PLAIN})

    def test_should_drop_each_chunk_that_may_carry_hidden_data(self) -> None:
        for chunk in HIDDEN_DATA_CHUNKS:
            with self.subTest(chunk.decode()):
                self.assertNotIn(chunk, self.copied["library-light.png"])

    def test_should_leave_the_pictures_as_they_are(self) -> None:
        self.assertEqual(self.pictures_after, [CAPTURED, PLAIN])

    def test_should_make_copies_that_the_publication_takes(self) -> None:
        self.assertEqual(self.publication.returncode, 0, self.publication.stderr)


class WhenThePathsAreRelative(unittest.TestCase):
    stripping: ClassVar[Run]
    copied: ClassVar[dict[str, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        remote.write_picture("library.png", CAPTURED)
        # The script runs from the clone, a sibling of the directory of the pictures.
        cls.stripping = remote.run(STRIP, "../pictures/stripped", "../pictures/library.png")
        copies = remote.directory / "pictures" / "stripped"
        cls.copied = read_tree(copies)

    def test_should_print_the_path_of_the_copy_as_given(self) -> None:
        self.assertEqual(self.stripping.stdout.splitlines(), ["../pictures/stripped/library.png"])

    def test_should_write_the_copy_there(self) -> None:
        self.assertEqual(self.copied, {"library.png": STRIPPED})


class WhenTheDestinationExists(unittest.TestCase):
    strippings: ClassVar[dict[str, Run]]
    destinations: ClassVar[dict[str, Path]]
    directory_after: ClassVar[dict[str, bytes]]
    file_after: ClassVar[bytes]
    link_after: ClassVar[str]
    link_target_exists: ClassVar[bool]
    picture_after: ClassVar[bytes]
    rows: ClassVar[tuple[str, ...]] = ("a directory", "a file", "a dangling symbolic link")

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        picture = remote.write_picture("library.png", CAPTURED)
        directory = remote.directory / "stripped"
        directory.mkdir()
        (directory / "library.png").write_bytes(PLAIN)
        file = remote.directory / "stripped-file"
        file.write_bytes(PLAIN)
        link = remote.directory / "stripped-link"
        link.symlink_to(remote.directory / "nowhere")
        cls.destinations = {"a directory": directory, "a file": file, "a dangling symbolic link": link}
        cls.strippings = {
            row: remote.run(STRIP, str(destination), str(picture)) for row, destination in cls.destinations.items()
        }
        cls.directory_after = read_tree(directory)
        cls.file_after = file.read_bytes()
        cls.link_after = os.readlink(link)
        cls.link_target_exists = os.path.lexists(remote.directory / "nowhere")
        cls.picture_after = picture.read_bytes()

    def test_should_refuse_each_and_name_it(self) -> None:
        self.assertEqual(sorted(self.strippings), sorted(self.rows))
        for row, stripping in self.strippings.items():
            with self.subTest(row):
                self.assertNotEqual(stripping.returncode, 0)
                self.assertIn(f"{self.destinations[row]} already exists", stripping.stderr)

    def test_should_leave_the_directory_as_it_is(self) -> None:
        self.assertEqual(self.directory_after, {"library.png": PLAIN})

    def test_should_leave_the_file_as_it_is(self) -> None:
        self.assertEqual(self.file_after, PLAIN)

    def test_should_leave_the_link_as_it_is_and_create_nothing_where_it_points(self) -> None:
        target = self.destinations["a dangling symbolic link"].parent / "nowhere"
        self.assertEqual((self.link_after, self.link_target_exists), (str(target), False))

    def test_should_leave_the_picture_as_it_is(self) -> None:
        self.assertEqual(self.picture_after, CAPTURED)


class WhenTheDestinationsParentIsMissing(unittest.TestCase):
    stripping: ClassVar[Run]
    copies: ClassVar[Path]
    is_left_behind: ClassVar[bool]
    picture_after: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        picture = remote.write_picture("library.png", CAPTURED)
        cls.copies = remote.directory / "missing" / "stripped"
        cls.stripping = remote.run(STRIP, str(cls.copies), str(picture))
        cls.is_left_behind = os.path.lexists(cls.copies.parent)
        cls.picture_after = picture.read_bytes()

    def test_should_refuse_and_name_the_destination(self) -> None:
        self.assertNotEqual(self.stripping.returncode, 0)
        self.assertIn(f"cannot create {self.copies}", self.stripping.stderr)

    def test_should_create_nothing(self) -> None:
        self.assertFalse(self.is_left_behind)

    def test_should_leave_the_picture_as_it_is(self) -> None:
        self.assertEqual(self.picture_after, CAPTURED)


class WhenTwoPicturesHaveTheSameNameWhateverItsCase(unittest.TestCase):
    stripping: ClassVar[Run]
    pictures: ClassVar[list[Path]]
    is_left_behind: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        other = remote.directory / "other" / "Library.png"
        other.parent.mkdir()
        other.write_bytes(PLAIN)
        cls.pictures = [remote.write_picture("library.png", CAPTURED), other]
        copies = remote.directory / "stripped"
        cls.stripping = remote.run(STRIP, str(copies), *map(str, cls.pictures))
        cls.is_left_behind = os.path.lexists(copies)

    def test_should_refuse_and_name_both_pictures(self) -> None:
        self.assertNotEqual(self.stripping.returncode, 0)
        self.assertIn(f"{self.pictures[0]} and {self.pictures[1]} have the same name", self.stripping.stderr)

    def test_should_create_nothing(self) -> None:
        self.assertFalse(self.is_left_behind)


class WhenAPictureCannotBeRead(unittest.TestCase):
    strippings: ClassVar[dict[str, Run]]
    unreadable: ClassVar[dict[str, Path]]
    is_left_behind_by_row: ClassVar[dict[str, bool]]
    picture_after: ClassVar[bytes]
    refusals: ClassVar[dict[str, str]] = {
        "not a PNG file": "is not a PNG file",
        "a truncated PNG file": "is a truncated PNG file",
        "a missing picture": "cannot read",
    }

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        picture = remote.write_picture("library.png", CAPTURED)
        # Each refusal comes after a picture that could be copied, and no copy is written.
        cls.unreadable = {
            "not a PNG file": remote.write_picture("library-jpeg.png", b"\xff\xd8\xff\xe0"),
            "a truncated PNG file": remote.write_picture("library-cut.png", PLAIN[:-6]),
            "a missing picture": remote.directory / "missing.png",
        }
        cls.strippings = {}
        cls.is_left_behind_by_row = {}
        for row, unreadable in cls.unreadable.items():
            copies = remote.directory / f"stripped-{unreadable.stem}"
            cls.strippings[row] = remote.run(STRIP, str(copies), str(picture), str(unreadable))
            cls.is_left_behind_by_row[row] = os.path.lexists(copies)
        cls.picture_after = picture.read_bytes()

    def test_should_refuse_each_and_say_why_naming_the_picture(self) -> None:
        self.assertEqual(sorted(self.strippings), sorted(self.refusals))
        for row, stripping in self.strippings.items():
            with self.subTest(row):
                self.assertNotEqual(stripping.returncode, 0)
                self.assertIn(str(self.unreadable[row]), stripping.stderr)
                self.assertIn(self.refusals[row], stripping.stderr)

    def test_should_create_nothing(self) -> None:
        self.assertEqual(sorted(self.is_left_behind_by_row), sorted(self.refusals))
        for row, is_left_behind in self.is_left_behind_by_row.items():
            with self.subTest(row):
                self.assertFalse(is_left_behind)

    def test_should_leave_the_picture_as_it_is(self) -> None:
        self.assertEqual(self.picture_after, CAPTURED)


class WhenACopyCannotBeWritten(unittest.TestCase):
    stripping: ClassVar[Run]
    copies: ClassVar[Path]
    is_left_behind: ClassVar[bool]
    pictures_after: ClassVar[list[bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        pictures = [remote.write_picture("library-light.png", PLAIN), remote.write_picture("library-dark.png", HEAVY)]
        cls.copies = remote.directory / "stripped"
        # The first copy is written, and the second fails as on a full disk.
        cls.stripping = remote.run(STRIP, str(cls.copies), *map(str, pictures), max_file_bytes=LARGEST_FILE_BYTES)
        cls.is_left_behind = os.path.lexists(cls.copies)
        cls.pictures_after = [picture.read_bytes() for picture in pictures]

    def test_should_refuse_and_name_the_copy(self) -> None:
        self.assertNotEqual(self.stripping.returncode, 0)
        self.assertIn(f"cannot write {self.copies / 'library-dark.png'}", self.stripping.stderr)

    def test_should_remove_the_directory_with_the_copy_already_written(self) -> None:
        self.assertFalse(self.is_left_behind)

    def test_should_leave_the_pictures_as_they_are(self) -> None:
        self.assertEqual(self.pictures_after, [PLAIN, HEAVY])


if __name__ == "__main__":
    unittest.main()
