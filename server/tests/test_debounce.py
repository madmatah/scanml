"""Debounced rewrites of the library files (debounce.py): batching and retries."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import NamedTuple

import pytest

from scanmylib.debounce import BatchAction, DebouncedBatch

THE_INDEX = "index"


class ActionRun(NamedTuple):
    keys: list[str]
    includes_the_index: bool


INDEX_ONLY = ActionRun(keys=[], includes_the_index=True)


class ActionFailingLikeAFullDisk:
    def __init__(self, failures_by_key: dict[str, int]) -> None:
        self.runs: list[ActionRun] = []
        self._failures_left = dict(failures_by_key)

    async def __call__(self, keys: set[str], includes_the_index: bool) -> None:
        self.runs.append(ActionRun(keys=sorted(keys), includes_the_index=includes_the_index))
        for key in [*keys, *([THE_INDEX] if includes_the_index else [])]:
            if self._failures_left.get(key):
                self._failures_left[key] -= 1
                raise OSError(28, "No space left on device")


def run_batch(action: BatchAction, drive: Callable[[DebouncedBatch], Awaitable[None]]) -> None:
    async def drive_a_started_batch() -> None:
        batch = DebouncedBatch(action, delay=0.01, max_delay=0.02)
        batch.start()
        await drive(batch)
        await batch.aclose()

    asyncio.run(drive_a_started_batch())


class TestTheDebouncedBatch:
    class TestTheScheduleMethod:
        class TestWhenKeysAreScheduledInABurst:
            @pytest.fixture(scope="class")
            @classmethod
            def action_runs(cls) -> list[ActionRun]:
                action = ActionFailingLikeAFullDisk(failures_by_key={})

                async def schedule_a_burst_then_wait(batch: DebouncedBatch) -> None:
                    batch.schedule("a")
                    batch.schedule("b")
                    batch.schedule("a")
                    await asyncio.sleep(0.2)

                run_batch(action, schedule_a_burst_then_wait)
                return list(action.runs)

            def test_should_rewrite_each_key_once_then_the_index_once(self, action_runs: list[ActionRun]) -> None:
                assert action_runs == [ActionRun(["a"], False), ActionRun(["b"], False), INDEX_ONLY]

        class TestWhenTheActionFailsForAKeyAndForTheIndex:
            @pytest.fixture(scope="class")
            @classmethod
            def action_runs(cls) -> list[ActionRun]:
                action = ActionFailingLikeAFullDisk(failures_by_key={"a": 2, THE_INDEX: 1})

                async def schedule_two_keys_then_wait(batch: DebouncedBatch) -> None:
                    batch.schedule("a")
                    batch.schedule("b")
                    await asyncio.sleep(0.5)

                run_batch(action, schedule_two_keys_then_wait)
                return list(action.runs)

            def test_should_still_rewrite_the_other_keys_and_the_index_in_the_same_run(
                self, action_runs: list[ActionRun]
            ) -> None:
                assert action_runs[:3] == [ActionRun(["a"], False), ActionRun(["b"], False), INDEX_ONLY]

            def test_should_retry_the_failed_work_later_until_it_succeeds(self, action_runs: list[ActionRun]) -> None:
                assert action_runs[3:] == [ActionRun(["a"], False), INDEX_ONLY, ActionRun(["a"], False)]

    class TestTheFlushMethod:
        class TestWhenTheActionFailsForTheFlushedKey:
            @pytest.fixture(scope="class")
            @classmethod
            def action_runs(cls) -> list[ActionRun]:
                action = ActionFailingLikeAFullDisk(failures_by_key={"a": 1})

                async def flush_the_key_as_a_read_of_its_markdown_does_then_wait(batch: DebouncedBatch) -> None:
                    batch.schedule("a")
                    await batch.flush("a")
                    await asyncio.sleep(0.3)

                run_batch(action, flush_the_key_as_a_read_of_its_markdown_does_then_wait)
                return list(action.runs)

            def test_should_still_rewrite_the_index(self, action_runs: list[ActionRun]) -> None:
                assert action_runs[:2] == [ActionRun(["a"], False), INDEX_ONLY]

            def test_should_retry_the_failed_key_in_the_background(self, action_runs: list[ActionRun]) -> None:
                assert ActionRun(["a"], False) in action_runs[2:]
