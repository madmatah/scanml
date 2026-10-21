---
paths:
  - "server/tests/**"
  - "server/scanmylib/devtools/**"
  - "server/scanmylib/web/tests/**"
  - "ocr/tests/**"
  - "ocr/bench/**"
  - "android/app/src/test/**"
  - "android/app/src/testDebug/**"
  - "scripts/tests/**"
  - "scripts/integration_tests/**"
  - "scripts/lib/parallel_tests.py"
  - "scripts/e2e_test.py"
  - "scripts/verify-sandbox.sh"
  - "server/pyproject.toml"
  - "android/app/build.gradle.kts"
---

# Tests

Tests are the specification of the business rules: to learn how a part of the system behaves, read its tests.

## Structure

Every test file follows one structure, so that a rule reads the same way everywhere, and its arrangement, its act and
its assertions sit in known places. Its words are those of a framework that nests groups of tests and runs hooks around
them: a group, a test, a hook that runs before each test of its group, and a hook that runs once before all of them.
The section of each test framework below gives its own words for them, and how it stands in for what it lacks.

- **Level 1 names the component the file tests,** in domain vocabulary, as the file is named: `The ordering`, in the
  tests of `ordering`. A file tests one component; a file of integration or scenario tests may hold several subjects,
  one level-1 group each.
- **Level 2 names the operation whose rule the tests state:** the function, the method or the constant under test, such
  as `The roman_to_int() function`. Level 2 is there even when the file tests a single function.
  - When the act is a sequence of calls, level 2 names the last one, whose rule the tests state, and the earlier calls
    are arrangement.
  - When no operation of the component owns the rule, such as a page that the OCR loop finishes or a phone whose
    pairing is revoked, or when the rule spans several of its operations, level 2 is the situation:
    `When the page is rescanned`.
- **Above the unit level, level 1 names the subject,** such as `A document scanned twice`, and level 2 the situation.
- **Situations are nested groups named `When …`,** nested at most three deep under level 2, so that the sentence they
  make stays readable.
- **Hooks arrange and act; each test only asserts.** Teardown aside, a group holds its arrangement and its act in a
  single hook. A test may read what the act produced, and project it with a pure query (a map, a filter, a computation
  that calls nothing under test and changes nothing), but never calls what its group tests, except to assert a refusal
  or inside a property run, below. An assertion lives in a test only, never in a hook or in a helper: a helper
  computes, and the test asserts. A constant under test needs no hook: its test reads it.
- **What the act produces is named for what it is:** `layout`, `page_number`, `hint`, never `result`, `input` or `data`,
  and declared in its group.
- **One expectation per test;** a few tightly related ones are allowed, such as the two bounds of a range. One
  comparison over an ordered sequence or a composite record is one expectation, and stays one when the order or the
  combination is the rule.
- **A costly act runs once,** in a hook that runs once for its group, when its tests only read what it produced: a
  server on a real socket, a git repository, an image build by the docker stand-in, thousands of iterations. The act
  captures, as plain copies, every value its tests read, and nothing under it changes what it produced. CI can run tests
  several times slower than a contributor's machine, so where the framework times out a hook, the hook's timeout is at
  least twice the act's duration on CI.
- **A sequence of steps nests:** each `When …` group continues from the state its parent left.
  - A cheap sequence continues in hooks that run before each test, each level adding one step.
  - A costly sequence runs whole in one hook that runs once, which captures a copy at each step, and its nested groups
    hold no hook and read those captures; where the section of its test framework has each group replay the sequence
    instead, as [unittest](#unittest) does for the tests of the scripts, each group's hook that runs once takes its own
    step after its parent's.
  - A chain never mixes the two: a hook that runs once builds only on the ancestors' hooks that run once, since it runs
    before an ancestor's hook that runs before each test: it builds on what an earlier test left, or on nothing, and the
    ancestor's hook then rebuilds that state under every test.
- **A value read in the middle of a sequence is captured where it happens,** before the next step changes it, so that a
  test compares two moments and not the final state with itself.
- **A comparison runs both acts in the same hook,** each product named for what it is (`numbered_layout`,
  `unnumbered_layout`), as distinct objects.
- **A refusal names its reason.** When the refusal is thrown, the hook keeps the act as a function, and the test asserts
  that calling it fails with the expected error and its message or pattern, so that a failure for another reason fails
  the test. When it is returned as a value, such as an HTTP status and its detail, the act captures it like any
  product, and the test asserts its type, its value or its message.
- **A property keeps its whole run inside one test:** its generators, its act and its expectation stay in one property
  run, under a `When given any …` group that names the generated domain. A property is the run of a property-based
  testing library, which none of the project's test frameworks has yet: a loop over inputs in a test is not one.
- **A check over a collection** gathers the mismatches and asserts that there are none, next to an expectation on the
  count of what it checked, so that an empty collection fails.
- **Tables:**
  - a parameterized test only for a simple table of data that no act produces, such as the entries of a constant,
    inside a `When …` group, each row named so that it states its own rule;
  - a table whose rows each need an act is a parameterized group, with the act in its hook, since a parameterized test
    would call the unit in the test; when every row needs an act against one costly arrangement, such as a running api
    or a server, a single hook runs every row against it and keeps each product under its named row, and each test
    checks them as a collection, its mismatches named for their rows, next to an expectation on their count;
  - a table of subjects is a parameterized group at level 2;
  - a table built from production data covers a new entry by itself, where a hand-written list would not.
- **Shared data that nothing changes** lives in the narrowest group that holds every test reading it, or at the file's
  top level when that group is the file's only level 1. An object that an act mutates or writes into is built in each
  hook that runs before a test. An aliasing test, whose output is its input, keeps passing the same object.
- **Teardown** lives in the group whose hook set up what it releases. The file's top level holds only imports, constant
  data, helpers that build or compute, and the hooks that a framework's section below puts there for a costly act;
  everything a test runs happens in its hooks and its test.
- **A benchmark keeps the form its tool measures,** since the tool measures what runs inside its measured call: this
  structure does not apply to `ocr/bench/`.

## Writing a test

- **A test name is a sentence that states one rule**, in domain vocabulary, starts with `should`, after any prefix the
  framework requires, and keeps the reason the rule has when its groups do not give it. With the names of its groups,
  it reads as one sentence: `The ordering > The roman_to_int() function > When the numeral is not canonical > should
  return None, so that a stray word never numbers a page`, whose Python form is
  `test_should_return_none_so_that_a_stray_word_never_numbers_a_page`. A name is `` `should hint the next page` `` in
  Kotlin, and `'should keep the selection in reading order'` in JavaScript.
- **One rule per test.** Neither a test nor its hooks branch, and every expectation can fail: an expectation on a value
  that the test built itself checks nothing. Inputs are named values, not unexplained literals.
- **Every test asserts:** the gate fails a test that runs no assertion, wherever the test framework can tell, so that a
  test whose act never reaches its expectation does not pass. Where it cannot, review checks it.
- **No test is committed focused or skipped,** nor marked as an expected failure (`xfail`, `expectedFailure`, `todo`): a
  skip or a mark takes a test out of the gate's verdict without a word, and a focus takes the others out wherever a
  runner honors it. A conditional skip that the section of the test framework allows, with its reason, is the only
  exception.
- **A bug fix starts with a test** that reproduces the bug.
- **Floating point:** compare with a tolerance, unless bit-exactness is the rule under test.
- **No test depends on timing, the wall clock or the order of the tests,** and randomness is seeded, or reports its
  seed, so that a failure replays. A coroutine runs on a test dispatcher that a hook advances, and a clock is a port
  that a hook sets.
- **A deleted test, or a loosened expectation, states its reason** in the change, and so does a dropped refusal message
  or a weaker assertion.
- **The fixtures name no real document** and hold no personal data: invented titles, authors and pages, as
  `repository.md` > No real document names says.

## Levels

- **Unit tests of the api:** `server/tests/`, with pytest, in the api's test image, without network and on a read-only
  filesystem. The HTTP API runs through FastAPI's test client, against the fake OCR sandbox on a real Unix socket.
- **Unit tests of the web UI:** `server/scanmylib/web/tests/`, with `node --test`, on the modules of the UI that hold no
  DOM, and on its translation catalog.
- **Unit tests of the OCR sandbox:** `ocr/tests/`, with `unittest`, in the sandbox's image, without network or models;
  the tests that need an engine's environment skip without it.
- **Unit tests of the app:** `android/app/src/test/`, with JUnit on the JVM: view models, the upload queue and the
  client of the PC, against fakes and a mock web server.
- **Screenshot tests of the app:** `android/app/src/testDebug/`, with JUnit, Robolectric and Roborazzi on the JVM, on
  the debug variant: each draws a screen from its state, with invented data, in the light or the dark theme, or one of
  their high-contrast variants, records it as a PNG under `android/app/build/outputs/roborazzi/`, and asserts what the
  screen shows. A change to a screen draws that screen in one. A test that needs Android's framework to compose, such as
  the theme's choice of colors or what a tap on a screen does, lives there too, without a picture. The pictures stay out
  of the code's history: they show the screens to whoever checks a change, and a pull request publishes those of a
  visible change (`.claude/skills/pull-request/SKILL.md` > Show a visible change).
- **Unit tests of the scripts:** `scripts/tests/`, with `unittest` and the host's `python3`, on the modules of
  `scripts/lib/`, on `scripts/release.py` and on the workflows of `.github/workflows/`, against throwaway repositories
  where git is needed.
- **Integration tests of the scripts:** `scripts/integration_tests/`, with `unittest` and the host's `python3`, which
  run the scripts themselves, such as `deploy.sh`, `dev.sh`, `build-apk.sh`, `prod.sh`, `check.sh` and the scripts of
  the skills (`.claude/skills/*/scripts/`), against throwaway repositories and a docker stand-in
  (`scripts/integration_tests/docker_shim.py`) that never reaches the Docker daemon. Each one runs a script whole, with
  the processes it starts, and they have an area of their own in the gate, `integration`, which a commit runs only when
  it changes a script they run (`CLAUDE.md` > Workflow, "Commits").
- **End to end:** `scripts/e2e_test.py`, which acts like the phone against a running stack, the development stack by
  default.
- **Isolation of the sandbox:** `scripts/verify-sandbox.sh`, against the running `ocr` service.
- **Benchmarks:** `ocr/bench/`, on the real engine and the GPU, outside the gate.
- **A test that needs a real adapter** outside the test's own process and files, such as the GPU, the network, a running
  stack or the Docker daemon, has a level of its own, apart from the unit tests, so that the unit tests stay fast and
  need no outside resource.

## Test support

- **A fake lives next to the port it stands in for,** in the tests of the unit that declares the port, and refuses what
  the real adapter refuses, so that the code under test behaves the same on it as on the real adapter.
- **Only tests import test support.** The fake OCR sandbox (`server/scanmylib/devtools/fake_ocr.py`) is the exception:
  it ships in the api's image, since the development stack runs it as `ocr-fake`, and it refuses the production project
  and a socket that a real sandbox serves. Every other piece of test support lives in a test directory.
- **A test that runs git in a repository of its own drops the `GIT_` variables it inherits:** `git rebase --exec`, which
  checks each commit of a branch, exports `GIT_DIR` when it runs in a worktree, and the test's git would then work on
  the repository under rebase instead of its own. The unit tests of the scripts build their git environment with
  `scripts/tests/git_environment.py`, the integration tests a whole environment of their own, and `scripts/check.sh`
  drops those variables before any area runs.

## pytest

The api's tests, in `server/tests/`, run on pytest.

- **Its words:** a group is a class whose name starts with `Test`, nested in its parent's (`TestTheOrdering` >
  `TestTheRomanToIntFunction` > `TestWhenTheNumeralIsNotCanonical`), since pytest collects only the classes with that
  prefix; a test is a method named `test_should_…`; a hook is a fixture defined in its group, and the hook that runs
  once is a fixture of `scope="class"` written as a `@classmethod` under `@pytest.fixture`, since pytest 9.1 deprecates
  the form of an instance method with a `PytestRemovedIn10Warning`, on which the gate fails. The fixtures of
  `server/tests/conftest.py`, such as `settings`, `fake_ocr` and `socket_dir`, are shared arrangement: test support that
  a group's fixtures request, and that acts on nothing under test.
- **What the act produces is a fixture named for it,** which the tests, and the fixtures of the nested groups, request
  as an argument. A fixture never sets an attribute on `self` or `cls`: pytest gives each test a new instance of its
  class, and runs a fixture of an outer class, or of class scope, on another one, which the tests never see; and an
  attribute set on `cls` reaches no test of a nested class, which is not a subclass, and outlives the teardown of the
  fixture. An act whose tests read its effect through another fixture, such as a fake it writes to, is `autouse=True`. A
  fixture returns one value, so the products of one act, such as the two sides of a comparison or the captures of a
  costly sequence, are the fields of a frozen dataclass or a `NamedTuple` that it returns, each named for what it is.
- **A sequence nests through the fixtures:** a nested group's fixture requests its parent's product, and returns the
  next state under a name of its own.
- **A fixture of `scope="class"` lives until the end of the innermost class of the first test that requests it,** and
  the classes nested in that class share its value; otherwise it runs again in each class whose test next requests it.
  Which test comes first depends on the order and on the selection of the tests, such as `-k` or a test's node id, so a
  costly act whose captures nested or sibling groups read is a fixture of `scope="module"`, at the file's top level,
  which runs once per file, one for each such act: the only hooks there. A fixture of a wider scope runs before the
  narrower ones, whatever their group, and pytest refuses one that requests a narrower one.
- **A refusal:** the fixture returns the act as a function, and the test calls it as the only statement of
  `with pytest.raises(ReadingOrderRefused, match="…"):`, whose pattern is searched in the message. Ruff refuses a broad
  exception, such as `ValueError` or `OSError`, without `match` (PT011), a block of several statements (PT012) and an
  assertion in an `except` (PT017); the `match` of the project's own exceptions is left to review. A coroutine runs
  through `asyncio.run`, inside the block for a refusal.
- **Teardown follows the `yield` of its fixture,** in a `with` around the `yield`, or in a function the fixture gives
  `request.addfinalizer` before it acts: pytest skips what follows the `yield` of a fixture that raised before it.
- **Tables:** `@pytest.mark.parametrize`, with `ids` that name each row, for a table of data; a parameterized group is a
  fixture with `params` and `ids`, whose act reads `request.param`. A parameterized group whose act is costly takes
  `scope="class"`, or `scope="module"` at the file's top level when nested or sibling groups read it, so that its act
  runs once per row, not once per test: pytest runs the tests of a row together. The single hook that runs every row of
  a table against one costly arrangement is a fixture of `scope="class"` or `scope="module"` that builds its own
  arrangement, since pytest refuses one that requests the function-scoped fixtures of `conftest.py`.
- **A test that asserts nothing passes:** pytest has no check for it, and a test that returns a value only warns, so
  review checks it. No lint sees an assertion in a fixture, nor a skip.
- **No timeout:** pytest times out no test and no fixture.
- **No skip:** everything the api's tests need is in their image.

For example:

```python
class TestTheOrdering:
    class TestTheRomanToIntFunction:
        class TestWhenTheNumeralIsCanonical:
            @pytest.fixture
            def number(self) -> int | None:
                return roman_to_int("xiv")

            def test_should_read_its_value(self, number: int | None) -> None:
                assert number == 14

        class TestWhenTheNumeralIsNotCanonical:
            @pytest.fixture
            def number(self) -> int | None:
                return roman_to_int("iiii")

            def test_should_return_none_so_that_a_stray_word_never_numbers_a_page(self, number: int | None) -> None:
                assert number is None
```

## unittest

The tests of the OCR sandbox, in `ocr/tests/`, and of the scripts, in `scripts/tests/` and `scripts/integration_tests/`,
run on `unittest`: the gate runs
them with the standard library only, the `python3` of the sandbox's image and the host's.

- **Its words:** the loader collects only the `TestCase` classes at a module's top level, never one nested in another
  class, so groups do not nest. Level 1 is the module, named after the component, which its docstring names, and each
  `TestCase` class names level 2 and its situations at once: `TheReleaseCodeFunctionWhenTheMinorVersionChanges`. A test
  is a method named `test_should_…`, the hook before each test `setUp`, and the hook that runs once the class method
  `setUpClass`.
- **What the act produces is an attribute** that `setUp` sets on `self`, or `setUpClass` on `cls`, named for what it is.
- **A sequence nests by inheritance:** a parent situation's arrangement and act live in the hook of a base `TestCase`
  that holds no test, of which the loader runs nothing, named as the situation's class with a leading underscore
  (`_TheXWhenA`). The parent situation's own tests sit in a class of the situation's name that extends it and adds no
  step (`TheXWhenA`), and each child, named for both situations (`TheXWhenAWhenB`), extends it too, its hook calling
  its parent's first, `super().setUp()` or `super().setUpClass()`, then taking its own step. A `TestCase` that holds
  tests is never a base, since the loader runs its tests again in every subclass. The hook is:
  - `setUp` for a cheap sequence;
  - `setUpClass` for a costly sequence in the tests of the scripts: each class replays its whole chain once, in the one
    process the gate runs it in, where `setUpModule` would run the sequence in every process that takes a test of its
    module; and each step is written once, as [JUnit](#junit)'s step functions are.
- **`setUpClass` runs once per class, an inherited one included,** and calls its parent's only through
  `super().setUpClass()`. So a costly act whose tests sit in one class runs in that class's `setUpClass`. A costly
  sequence of the OCR sandbox's tests, which run in one process, runs whole in `setUpModule`, the only hook at a file's
  top level, which keeps its captures on the base `TestCase` the classes of its situations extend, as one declared
  `ClassVar` holding a frozen dataclass or a `NamedTuple` of them, and those classes hold no hook.
- **Teardown is registered with `addCleanup`, `addClassCleanup` or `unittest.addModuleCleanup`, as soon as the hook
  holds what it releases:** `tearDown`, `tearDownClass` and `tearDownModule` do not run when their hook fails, and the
  act runs in the hook.
- **A refusal:** `setUp` keeps the act as a function, and the test asserts
  `self.assertRaisesRegex(StackRefused, "…", self.act)`, whose pattern is searched in the message.
- **Tables:** a table of data is one test that asserts each row in a `self.subTest(…)` named for it; for rows that each
  need an act, `setUp` runs it for every row and keeps each product under its row, and the test asserts them as a check
  over a collection, each in its `subTest`.
- **A test that asserts nothing passes:** `unittest` counts no assertion, and a test that returns a value only warns, so
  review checks it. No lint sees an assertion in `setUp`, nor a skip.
- **No timeout:** `unittest` times out no test and no hook.
- **The gate runs the tests of the scripts in parallel** (`scripts/lib/parallel_tests.py`), in one process per core,
  since they spend their time starting processes: a class whose `setUpClass` is not unittest's, an inherited one
  included, whole in one of them, so that its setup runs once, and every other test in any of them. So a test of the
  scripts takes no resource of the whole machine that another one could take at the same time, such as a fixed port or a
  path outside its temporary directory: it takes a port the system gives it, and works in its own directory.
- **The skips allowed** are conditional, with `skipUnless`, `skipIf` or `self.skipTest` and their reason, and only
  these:
  - the engine's environment is missing, such as Pillow outside the worker's environment, since the sandbox's tests also
    run without it;
  - the tests run as root, which reads or writes where a test expects it cannot;
  - no real docker CLI is there to resolve a configuration;
  - the temporary directory lies in the home directory, which the scripts refuse;
  - port 8770 is taken, by a running development stack.
- **In the tests of the scripts, a class with a `setUpClass` skips with a class decorator,** `skipIf` or `skipUnless`,
  never from its hook: their gate counts the tests of each share, and the tests of a class whose `setUpClass` raised
  `SkipTest` as tests that unittest did not report, and fails.

For example:

```python
class TheReleaseCodeFunctionWhenTheMinorVersionChanges(unittest.TestCase):
    def setUp(self) -> None:
        self.code = version.release_code((1, 3, 0))
        self.previous_code = version.release_code((1, 2, 99))

    def test_should_be_above_every_patch_of_the_previous_minor_version_so_that_phones_install_it(self) -> None:
        self.assertGreater(self.code, self.previous_code)
```

## node:test

The web UI's tests, in `server/scanmylib/web/tests/`, run on Node's own runner, `node --test`, with
`node:assert/strict`.

- **Its words:** `describe`, `it`, `beforeEach` and `before`, imported from `node:test`, with `afterEach` and `after`
  for teardown. For the first test of a nested group, the parent's `before` runs, then the group's `before`, then the
  parent's `beforeEach`, then the group's: a `before` runs ahead of its ancestors' `beforeEach`.
- **What the act produces lives in a `let`** declared in its `describe`.
- **A refusal:** the hook keeps the act as a function, `act = () => …`, and the test asserts
  `assert.throws(act, { name: '…', message: /…/ })`; an asynchronous one, `await assert.rejects(act(), { … })`. The
  error is described as an object: a string in its place is the assertion's own failure message, and checks nothing.
- **Biome refuses what the structure forbids,** at error: `noMisplacedAssertion` (an assertion outside an `it` or a
  `test`, in a hook or a helper), `noFocusedTests`, `noSkippedTests`, `noDuplicateTestHooks` and
  `noExcessiveNestedTestSuites`. It knows them by name, so none of what escapes it is written: the `only`, `skip` and
  `todo` options, whatever their value, `describe.todo` and `it.todo`, `t.skip()` and `t.todo()`, and a bare
  `assert(…)`, written `assert.ok(…)`.
- **A test that asserts nothing passes:** only a `t.plan()` in each test would fail it, so review checks it.
- **No timeout:** a test or a hook runs without a limit unless it sets one.
- **No DOM and no skip:** the tests run in Node, on the modules of the UI that hold no DOM.

For example:

```js
describe('The reading order', () => {
  describe('The moveBlock() function', () => {
    describe('When the pages were selected in click order', () => {
      const pages = ['a', 'b', 'c', 'd', 'e', 'f'];
      const clickedPages = ['e', 'b'];
      const firstPosition = 0;
      let order;
      beforeEach(() => {
        order = moveBlock(pages, clickedPages, firstPosition);
      });

      it('should move them in reading order', () => {
        assert.deepEqual(order, ['b', 'e', 'a', 'c', 'd', 'f']);
      });
    });
  });
});
```

## JUnit

The app's tests, in `android/app/src/test/` and `android/app/src/testDebug/`, run on JUnit 4, on the JVM, with
kotlinx-coroutines-test.

- **Its words:** a group is a class nested in its parent's, without `inner`, under `@RunWith(Enclosed::class)`, which
  runs the public nested classes of a class, skips the abstract ones, and never runs a test of the class itself: a class
  holds either groups or tests. Level 1 is the class named after the file, `PageNumberingTest`, and the groups are named
  `TheHintForMethod` or `WhenThePagesAreConsecutive`. A test is a `@Test` function named `` `should …` ``, the hook
  before each test `@Before`, the hook that runs once `@BeforeClass` on a `@JvmStatic` function of the
  `companion object` of a class that holds tests, and teardown `@After` and `@AfterClass`.
- **A class under `@RunWith(Enclosed::class)` holds no companion object, and no other public nested class or object
  than its groups:** Kotlin compiles a companion object to a nested class, and Enclosed would run a public one as a
  group.
- **A sequence does not nest,** since a nested class runs on its own, without its parent's `@Before`: its situations are
  sibling groups, each named for its whole chain of at most three situations (`WhenAPageIsQueued`,
  `WhenAPageIsQueuedAndTheNetworkDrops`). Each step is written once, as a private function of the file that takes the
  state the step before left and takes that one step, and each group's `@Before` arranges, then calls the steps of its
  chain in order, its own last.
- **A costly act runs in the `@BeforeClass` of the one class whose tests read it,** since a class under Enclosed holds
  no companion object for a `@BeforeClass` of its own: the situations of a costly sequence are then the tests of that
  one class, each name saying its step.
- **What the act produces is a `lateinit var`** declared in its class, or in its companion object for the act of a
  `@BeforeClass`, which throws when a test reads it before a hook set it. A non-null type that `lateinit` refuses, a
  primitive or a value class, takes a `var` delegated to `Delegates.notNull()`, which throws the same way and keeps the
  type non-null, as `assertEquals` with a tolerance needs; and a product that may be null is held inside a non-null
  value in a `lateinit var`, such as a list or a data class of the act's products, so that a test that expects `null`
  still fails when no hook ran.
- **A refusal:** the hook keeps the act as a function, and the test asserts
  `assertThrows(PairingRefused::class.java) { act() }` and the message of the exception it returns. A suspending act
  cannot run in `assertThrows`, whose block is not inline: the test reads `runCatching { act() }.exceptionOrNull()`
  inside `runTest`.
- **A suspending act runs in `runTest`, in its hook,** on a test dispatcher: its body times out after 60 seconds, and
  JUnit 4 times out no hook.
- **Tables:** a parameterized group is a nested class under `@RunWith(Parameterized::class)`, or
  `@RunWith(ParameterizedRobolectricTestRunner::class)` for a screenshot test, whose `@Before` runs the act for its row,
  each row named by `@Parameters(name = …)`, or by `@ParameterizedRobolectricTestRunner.Parameters(name = …)` for that
  runner.
- **A screenshot test** is a group under `@RunWith(ParameterizedRobolectricTestRunner::class)`, whose rows are the
  themes, light and dark, and their high-contrast variants for a screen that shows every kind of color (the library),
  with `@GraphicsMode(GraphicsMode.Mode.NATIVE)` and `@Config(sdk = [36], qualifiers = …)`, the qualifiers naming a
  generic screen, such as `RobolectricDeviceQualifiers.MediumPhone`. Its `@Before` draws the screen in its row's theme,
  `ScanMyLibTheme(dark = …)`, or `ScanMyLibTheme(dark = …, contrast = Contrast.HIGH)`, through the rule of
  `createComposeRule` (`androidx.compose.ui.test.junit4.v2`), and records it with
  `captureRoboImage("build/outputs/roborazzi/<screen>-<situation>-<theme>.png")`, or, when a dialog is open in a window
  of its own, `captureScreenRoboImage(…)` once `waitForIdle()` has drawn it; its tests assert what the screen shows.
  Robolectric runs offline, on the image of Android that Gradle resolves and verifies (`robolectricAndroidAll` in
  `android/app/build.gradle.kts`).
- **A test without a picture** in `android/app/src/testDebug/` is a group under
  `@RunWith(RobolectricTestRunner::class)`, with `@Config(sdk = [36])`, and the qualifiers of a generic screen when it
  lays a screen out, so that its layout, and what a tap reaches, match a phone's. Its qualifiers also give the phone's
  configuration that its situation needs, such as `night` for a dark phone.
- **A test that asserts nothing passes:** JUnit counts no assertion, so review checks it. ktlint checks no rule of the
  tests.
- **No skip:** no `@Ignore` and no `Assume`, since the app's tests need nothing that the JVM lacks.

For example:

```kotlin
@RunWith(Enclosed::class)
class PageNumberingTest {
    @RunWith(Enclosed::class)
    class TheHintForMethod {
        class WhenThePagesAreConsecutive {
            private lateinit var hints: List<Int?>

            @Before
            fun hintFourPages() {
                hints = List(4, PageNumbering(firstPage = 13, consecutive = true)::hintFor)
            }

            @Test
            fun `should number the pages on from the first one`() {
                assertEquals(listOf(13, 14, 15, 16), hints)
            }
        }
    }
}
```
