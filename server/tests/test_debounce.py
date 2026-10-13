"""Debounced rewrites of the library files (debounce.py): batching and retries."""

from __future__ import annotations

import asyncio

from scanmylib.debounce import DebouncedBatch


def run_batch(action, scenario) -> None:
    async def main() -> None:
        batch = DebouncedBatch(action, delay=0.01, max_delay=0.02)
        batch.start()
        await scenario(batch)
        await batch.aclose()

    asyncio.run(main())


def test_changes_are_batched():
    calls = []

    async def action(keys, index):
        calls.append((sorted(keys), index))

    async def scenario(batch):
        batch.schedule("a")
        batch.schedule("b")
        batch.schedule("a")
        await asyncio.sleep(0.2)

    run_batch(action, scenario)
    assert calls == [(["a"], False), (["b"], False), ([], True)]


def test_failed_work_is_retried_without_holding_up_the_rest():
    calls = []
    failures = {"a": 2, "index": 1}  # e.g. a full disk: "a" fails twice, the index once

    async def action(keys, index):
        calls.append((sorted(keys), index))
        for name in [*keys, *(["index"] if index else [])]:
            if failures.get(name):
                failures[name] -= 1
                raise OSError(28, "No space left on device")

    async def scenario(batch):
        batch.schedule("a")
        batch.schedule("b")
        await asyncio.sleep(0.5)

    run_batch(action, scenario)
    assert calls == [
        (["a"], False), (["b"], False), ([], True),  # "b" is written although "a" failed
        (["a"], False), ([], True),  # retried later
        (["a"], False),
    ]


def test_flush_failure_is_retried_in_the_background():
    calls = []
    failures = [1]

    async def action(keys, index):
        calls.append((sorted(keys), index))
        if failures[0]:
            failures[0] -= 1
            raise OSError(28, "No space left on device")

    async def scenario(batch):
        batch.schedule("a")
        await batch.flush("a")  # e.g. GET /markdown: fails, the document stays pending
        await asyncio.sleep(0.3)

    run_batch(action, scenario)
    assert calls[:2] == [(["a"], False), ([], True)]
    assert (["a"], False) in calls[2:]
