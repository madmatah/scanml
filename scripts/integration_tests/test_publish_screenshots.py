"""The publication of screenshots for a pull request (`.claude/skills/pull-request/scripts/publish_screenshots.py`),
against a bare origin that the script takes for a GitHub repository (screenshots_support.py).

Needs git. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_publish_screenshots.py'
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from screenshots_support import BRANCH, GITHUB_URL, OWNER, PUBLISH, REPOSITORY, Remote, Run, make_png

NUMBER = "12"
OTHER_NUMBER = "13"
LIGHT = make_png(shade=255)
DARK = make_png(shade=0)
#: Over the branch's 30 MB, after which the script asks for a cleanup.
HEAVY_HISTORY_BYTES = 31 * 1024 * 1024
#: The chunks that may carry what a picture does not show: text, a time, Exif data, a color profile, a private chunk.
HIDDEN_DATA_CHUNKS = [b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME", b"iCCP", b"prVt"]
#: What such a chunk may say: a key and a path.
HIDDEN_TEXT = b"Comment\x00/home/user"
#: A chunk type that is no four letters, but an escape sequence that a terminal would act on.
ESCAPE_CHUNK = b"\x1b[0m"
#: LIGHT cut in the middle of its last chunk, IEND, whose 12 bytes are its length, type and checksum.
TRUNCATED = LIGHT[:-6]


def build_link(commit: str, path: str) -> str:
    return f"https://github.com/{OWNER}/{REPOSITORY}/blob/{commit}/{path}?raw=true"


def make_remote(test_case: type[unittest.TestCase]) -> Remote:
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-screenshots-")
    test_case.addClassCleanup(directory.cleanup)
    return Remote(Path(os.path.realpath(directory.name)))


class WhenTheBranchDoesNotExistYet(unittest.TestCase):
    publication: ClassVar[Run]
    tip: ClassVar[str | None]
    parents: ClassVar[list[str]]
    files: ClassVar[dict[str, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        light = remote.write_picture("library-light.png", LIGHT)
        dark = remote.write_picture("library-dark.png", DARK)
        cls.publication = remote.run(PUBLISH, NUMBER, str(light), str(dark))
        cls.tip = remote.read_branch_tip()
        cls.parents = remote.read_parents(cls.tip) if cls.tip else []
        cls.files = remote.read_files(cls.tip) if cls.tip else {}

    def test_should_print_a_markdown_image_per_picture_linked_by_the_commit_that_adds_it(self) -> None:
        self.assertEqual(
            self.publication.stdout.splitlines(),
            [
                f"![library-light]({build_link(str(self.tip), f'pr-{NUMBER}/library-light.png')})",
                f"![library-dark]({build_link(str(self.tip), f'pr-{NUMBER}/library-dark.png')})",
            ],
        )

    def test_should_start_the_branch_with_a_commit_that_shares_no_history_with_the_code(self) -> None:
        self.assertEqual(self.parents, [])

    def test_should_put_the_pictures_in_the_folder_of_the_pull_request(self) -> None:
        self.assertEqual(self.files, {f"pr-{NUMBER}/library-light.png": LIGHT, f"pr-{NUMBER}/library-dark.png": DARK})


class WhenTheBranchHoldsTheScreenshotsOfAnotherPullRequest(unittest.TestCase):
    first_tip: ClassVar[str | None]
    parents: ClassVar[list[str]]
    files: ClassVar[dict[str, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        remote.run(PUBLISH, NUMBER, str(remote.write_picture("library-light.png", LIGHT)))
        cls.first_tip = remote.read_branch_tip()
        remote.run(PUBLISH, OTHER_NUMBER, str(remote.write_picture("library-dark.png", DARK)))
        tip = remote.read_branch_tip()
        cls.parents = remote.read_parents(tip) if tip else []
        cls.files = remote.read_files(tip) if tip else {}

    def test_should_add_a_commit_on_the_branch(self) -> None:
        self.assertEqual(self.parents, [self.first_tip])

    def test_should_keep_the_pictures_of_the_other_pull_request(self) -> None:
        self.assertEqual(
            self.files, {f"pr-{NUMBER}/library-light.png": LIGHT, f"pr-{OTHER_NUMBER}/library-dark.png": DARK}
        )


class WhenAPictureIsPublishedAgain(unittest.TestCase):
    first_link_picture: ClassVar[bytes]
    tip_picture: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))
        first_tip = remote.read_branch_tip()
        remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", DARK)))
        tip = remote.read_branch_tip()
        cls.first_link_picture = remote.read_blob(str(first_tip), f"pr-{NUMBER}/library.png")
        cls.tip_picture = remote.read_blob(str(tip), f"pr-{NUMBER}/library.png")

    def test_should_leave_the_first_link_on_the_first_picture_so_that_a_description_never_changes(self) -> None:
        self.assertEqual(self.first_link_picture, LIGHT)

    def test_should_hold_the_new_picture_at_the_tip_of_the_branch(self) -> None:
        self.assertEqual(self.tip_picture, DARK)


class WhenAPictureHoldsTheChunksOfAnImageBesidesItsPixels(unittest.TestCase):
    publication: ClassVar[Run]
    picture: ClassVar[bytes]
    files: ClassVar[dict[str, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        # sRGB with its rendering intent, gAMA of 1/2.2, pHYs of 3780 pixels per meter (96 per inch) on both axes.
        cls.picture = make_png(
            (b"sRGB", bytes([0])), (b"gAMA", (45455).to_bytes(4, "big")), (b"pHYs", bytes.fromhex("00000EC400000EC401"))
        )
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", cls.picture)))
        tip = remote.read_branch_tip()
        cls.files = remote.read_files(tip) if tip else {}

    def test_should_publish_it_as_it_is(self) -> None:
        self.assertEqual(self.files, {f"pr-{NUMBER}/library.png": self.picture})


class WhenAnotherPublicationPushesFirst(unittest.TestCase):
    publication: ClassVar[Run]
    other: ClassVar[str]
    parents: ClassVar[list[str]]
    files: ClassVar[dict[str, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        cls.other = remote.commit_on_origin({f"pr-{OTHER_NUMBER}/settings.png": DARK})
        # The first push finds the branch moved by the other publication, and is refused.
        hook = remote.origin / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\n"
            f'[ -f "{remote.directory}/raced" ] && exit 0\n'
            f'touch "{remote.directory}/raced"\n'
            "env -u GIT_QUARANTINE_PATH -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES "
            f"git update-ref {BRANCH} {cls.other}\n"
            "exit 1\n"
        )
        hook.chmod(0o755)
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))
        tip = remote.read_branch_tip()
        cls.parents = remote.read_parents(tip) if tip else []
        cls.files = remote.read_files(tip) if tip else {}

    def test_should_publish_on_a_later_attempt(self) -> None:
        self.assertEqual(self.publication.returncode, 0, self.publication.stderr)

    def test_should_build_on_the_other_publication(self) -> None:
        self.assertEqual(self.parents, [self.other])

    def test_should_keep_the_pictures_of_the_other_publication(self) -> None:
        self.assertEqual(self.files, {f"pr-{OTHER_NUMBER}/settings.png": DARK, f"pr-{NUMBER}/library.png": LIGHT})


class WhenTheBranchWeighsMoreThanItsLimit(unittest.TestCase):
    publication: ClassVar[Run]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        # Git counts the size of an object before compression, so zeros weigh as much as a picture would.
        heavy = remote.commit_on_origin({"pr-1/heavy.png": bytes(HEAVY_HISTORY_BYTES)})
        remote.run_origin_git("update-ref", BRANCH, heavy)
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))

    def test_should_still_publish(self) -> None:
        self.assertEqual(self.publication.returncode, 0, self.publication.stderr)

    def test_should_ask_for_a_cleanup(self) -> None:
        self.assertIn("weighs 31 MB: the maintainer cleans it with /clean-pr-screenshots", self.publication.stderr)


class WhenAPictureCannotBePublished(unittest.TestCase):
    publications: ClassVar[dict[str, Run]]
    tip: ClassVar[str | None]
    refusals: ClassVar[dict[str, str]] = {
        "not a PNG file": "is not a PNG file",
        **{f"a {chunk.decode()} chunk": f"holds the chunk {chunk.decode()}," for chunk in HIDDEN_DATA_CHUNKS},
        "a chunk type that is no word": "holds the chunk b'\\x1b[0m',",
        "a truncated PNG file": "is a truncated PNG file",
        "a name with a space": "name a picture with letters, digits",
        "a name that is not a .png": "name a picture with letters, digits",
        "two pictures of the same name": "two pictures are named library.png",
        "a picture above 10 MB": "above GitHub's 10485760 for an image",
        "a missing picture": "cannot read",
        "the number 0": "the number of a pull request is positive",
    }

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        valid = str(remote.write_picture("library.png", LIGHT))
        too_big = LIGHT + bytes(10 * 1024 * 1024)
        arguments = {
            "not a PNG file": [NUMBER, str(remote.write_picture("library-jpeg.png", b"\xff\xd8\xff\xe0"))],
            **{
                f"a {chunk.decode()} chunk": [
                    NUMBER,
                    str(remote.write_picture(f"library-{chunk.decode()}.png", make_png((chunk, HIDDEN_TEXT)))),
                ]
                for chunk in HIDDEN_DATA_CHUNKS
            },
            "a chunk type that is no word": [
                NUMBER,
                str(remote.write_picture("library-escape.png", make_png((ESCAPE_CHUNK, HIDDEN_TEXT)))),
            ],
            "a truncated PNG file": [NUMBER, str(remote.write_picture("library-cut.png", TRUNCATED))],
            "a name with a space": [NUMBER, str(remote.write_picture("library light.png", LIGHT))],
            "a name that is not a .png": [NUMBER, str(remote.write_picture("library.jpg", LIGHT))],
            "two pictures of the same name": [NUMBER, valid, str(remote.directory / "library.png")],
            "a picture above 10 MB": [NUMBER, str(remote.write_picture("library-big.png", too_big))],
            "a missing picture": [NUMBER, str(remote.directory / "missing.png")],
            "the number 0": ["0", valid],
        }
        (remote.directory / "library.png").write_bytes(DARK)
        cls.publications = {row: remote.run(PUBLISH, *row_arguments) for row, row_arguments in arguments.items()}
        cls.tip = remote.read_branch_tip()

    def test_should_refuse_each_picture_and_say_why(self) -> None:
        self.assertEqual(sorted(self.publications), sorted(self.refusals))
        for row, publication in self.publications.items():
            with self.subTest(row):
                self.assertNotEqual(publication.returncode, 0)
                self.assertIn(self.refusals[row], publication.stderr)

    def test_should_push_nothing(self) -> None:
        self.assertIsNone(self.tip)


class WhenEveryPushIsRefused(unittest.TestCase):
    publication: ClassVar[Run]
    tip: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        hook = remote.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'refused by a hook' >&2\nexit 1\n")
        hook.chmod(0o755)
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))
        cls.tip = remote.read_branch_tip()

    def test_should_give_up_with_the_last_error_of_git(self) -> None:
        self.assertIn("git push failed 3 times, the last with:", self.publication.stderr)
        self.assertIn("refused by a hook", self.publication.stderr)

    def test_should_push_nothing(self) -> None:
        self.assertIsNone(self.tip)


class WhenOriginCannotBeReached(unittest.TestCase):
    publication: ClassVar[Run]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        unreachable = remote.directory / "missing.git"
        remote.run_git("-C", str(remote.clone), "config", f"url.{unreachable}.insteadOf", GITHUB_URL)
        remote.run_git("-C", str(remote.clone), "config", "--unset", f"url.{remote.origin}.insteadOf")
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))

    def test_should_refuse_with_the_error_of_git(self) -> None:
        self.assertNotEqual(self.publication.returncode, 0)
        self.assertIn("error: git ls-remote:", self.publication.stderr)


class WhenOriginIsWrittenInAnotherForm(unittest.TestCase):
    publications: ClassVar[dict[str, str]]
    forms: ClassVar[list[str]] = [
        f"https://github.com/{OWNER}/{REPOSITORY}",
        f"https://github.com/{OWNER}/{REPOSITORY}.git",
        f"ssh://git@github.com/{OWNER}/{REPOSITORY}.git",
    ]

    @classmethod
    def setUpClass(cls) -> None:
        cls.publications = {}
        for form in cls.forms:
            remote = make_remote(cls)
            remote.run_git("-C", str(remote.clone), "remote", "set-url", "origin", form)
            remote.run_git("-C", str(remote.clone), "config", f"url.{remote.origin}.insteadOf", form)
            cls.publications[form] = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT))).stdout

    def test_should_link_the_pictures_on_the_same_repository(self) -> None:
        self.assertEqual(sorted(self.publications), sorted(self.forms))
        for form, printed in self.publications.items():
            with self.subTest(form):
                self.assertIn(f"https://github.com/{OWNER}/{REPOSITORY}/blob/", printed)


class WhenOriginPushesToAnotherRepository(unittest.TestCase):
    publication: ClassVar[Run]
    tip: ClassVar[str | None]
    fork_tip: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        fork_url = f"git@github.com:{OWNER}/fork.git"
        fork = remote.make_fork(fork_url)
        remote.run_git("-C", str(remote.clone), "config", "remote.origin.pushurl", fork_url)
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))
        cls.tip = remote.read_branch_tip()
        cls.fork_tip = remote.run_git("--git-dir", str(fork), "for-each-ref", BRANCH)

    def test_should_refuse_since_it_would_read_one_repository_and_write_another(self) -> None:
        self.assertIn("origin's URLs name several repositories", self.publication.stderr)

    def test_should_push_to_neither_repository(self) -> None:
        self.assertEqual((self.tip, self.fork_tip), (None, ""))


class WhenOriginHasSeveralUrlsOfOneRepository(unittest.TestCase):
    publication: ClassVar[Run]
    tip: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        # The same repository in another form and another case, as a push URL.
        push_url = f"https://github.com/{OWNER.upper()}/{REPOSITORY}"
        remote.run_git("-C", str(remote.clone), "config", "remote.origin.pushurl", push_url)
        remote.run_git("-C", str(remote.clone), "config", "--add", f"url.{remote.origin}.insteadOf", push_url)
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))
        cls.tip = remote.read_branch_tip()

    def test_should_publish(self) -> None:
        self.assertEqual(self.publication.returncode, 0, self.publication.stderr)
        self.assertIsNotNone(self.tip)


class WhenOriginHasSeveralUrlsOfDifferentRepositories(unittest.TestCase):
    publication: ClassVar[Run]
    tip: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        fork_url = f"git@github.com:{OWNER}/fork.git"
        remote.make_fork(fork_url)
        remote.run_git("-C", str(remote.clone), "config", "--add", "remote.origin.url", fork_url)
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))
        cls.tip = remote.read_branch_tip()

    def test_should_refuse_since_a_push_would_reach_both(self) -> None:
        self.assertIn("origin's URLs name several repositories", self.publication.stderr)

    def test_should_push_nothing(self) -> None:
        self.assertIsNone(self.tip)


class WhenOriginIsNotOnGitHub(unittest.TestCase):
    publication: ClassVar[Run]
    tip: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        remote.run_git("-C", str(remote.clone), "remote", "set-url", "origin", str(remote.origin))
        cls.publication = remote.run(PUBLISH, NUMBER, str(remote.write_picture("library.png", LIGHT)))
        cls.tip = remote.read_branch_tip()

    def test_should_refuse_since_it_could_not_link_the_pictures(self) -> None:
        self.assertIn("origin is not a GitHub repository", self.publication.stderr)

    def test_should_push_nothing(self) -> None:
        self.assertIsNone(self.tip)


if __name__ == "__main__":
    unittest.main()
