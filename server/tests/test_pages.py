"""A page's rules, on plain values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from scanmylib.domain.pages import (
    AttemptOutcome,
    conclude_failed_attempt,
    conclude_released_attempt,
    propose_page_keys,
    should_detect_orientation,
    summarize_ocr,
)
from scanmylib.domain.records import OcrSummary

OFFSET = timezone(timedelta(hours=2))
CAPTURED_AT = datetime(2026, 10, 12, 20, 15, 30, tzinfo=OFFSET)
PAGE_ID = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
FAILURE_MESSAGE = "OCR failed: HTTP 500 (processing_failed: simulated failure)"
ENGINE = "PaddleOCR-VL-1.6"
MARKDOWN = "## Chapter 1\n\nThe carpenter measures twice.\n"
MARKDOWN_CHARACTER_COUNT = 44
IMAGE_COUNT = 2
DURATION_SECONDS = 12.3456
FINISHED_AT = datetime(2026, 10, 12, 20, 15, 30, 123456, tzinfo=OFFSET)
RELEASED_ATTEMPT_COUNT = 2


@dataclass(frozen=True)
class FailedAttempt:
    previous_attempt_count: int
    is_retryable: bool
    expected_outcome: AttemptOutcome


@dataclass(frozen=True)
class ConcludedAttempt:
    attempt: FailedAttempt
    outcome: AttemptOutcome


class TestThePages:
    class TestTheProposePageKeysFunction:
        class TestWhenAPageIsCaptured:
            @pytest.fixture
            def keys(self) -> tuple[str, ...]:
                return propose_page_keys(CAPTURED_AT, PAGE_ID)

            def test_should_name_it_after_its_capture_time_then_a_longer_and_longer_prefix_of_its_id(
                self, keys: tuple[str, ...]
            ) -> None:
                assert keys == (
                    "20261012-201530_0a1b2c3d",
                    "20261012-201530_0a1b2c3d4e5f",
                    "20261012-201530_0a1b2c3d4e5f4a6b",
                    "20261012-201530_0a1b2c3d4e5f4a6b8c7d9e0f1a2b3c4d",
                )

    class TestTheConcludeFailedAttemptFunction:
        class TestWhenAnAttemptFails:
            @pytest.fixture(
                params=[
                    FailedAttempt(0, True, AttemptOutcome("queued", 1, None)),
                    FailedAttempt(2, True, AttemptOutcome("queued", 3, None)),
                    FailedAttempt(3, True, AttemptOutcome("error", 4, FAILURE_MESSAGE)),
                    FailedAttempt(0, False, AttemptOutcome("error", 1, FAILURE_MESSAGE)),
                ],
                ids=[
                    "a-first-failure-that-may-be-retried",
                    "the-last-retry-allowed",
                    "a-failure-past-the-retries",
                    "a-failure-that-retrying-cannot-help",
                ],
            )
            def concluded(self, request: pytest.FixtureRequest) -> ConcludedAttempt:
                attempt: FailedAttempt = request.param
                outcome = conclude_failed_attempt(
                    attempt.previous_attempt_count, FAILURE_MESSAGE, is_retryable=attempt.is_retryable
                )
                return ConcludedAttempt(attempt, outcome)

            def test_should_count_it_and_queue_the_page_again_only_while_retries_remain(
                self, concluded: ConcludedAttempt
            ) -> None:
                assert concluded.outcome == concluded.attempt.expected_outcome

    class TestTheConcludeReleasedAttemptFunction:
        class TestWhenTheSandboxCouldNotTakeThePage:
            @pytest.fixture
            def outcome(self) -> AttemptOutcome:
                return conclude_released_attempt(RELEASED_ATTEMPT_COUNT)

            def test_should_queue_the_page_again_without_counting_the_attempt(self, outcome: AttemptOutcome) -> None:
                assert outcome == AttemptOutcome("queued", RELEASED_ATTEMPT_COUNT, None)

    class TestTheSummarizeOcrFunction:
        class TestWhenAPageIsRead:
            @pytest.fixture
            def summary(self) -> OcrSummary:
                return summarize_ocr(
                    engine=ENGINE,
                    markdown=MARKDOWN,
                    image_count=IMAGE_COUNT,
                    duration_seconds=DURATION_SECONDS,
                    finished_at=FINISHED_AT,
                )

            def test_should_name_the_engine_in_lowercase_and_keep_its_model_name(self, summary: OcrSummary) -> None:
                assert (summary["engine"], summary["model"]) == ("paddleocr-vl-1.6", ENGINE)

            def test_should_round_its_duration_to_hundredths_of_a_second(self, summary: OcrSummary) -> None:
                assert summary["duration_s"] == pytest.approx(12.35)

            def test_should_date_it_to_the_second_in_its_offset(self, summary: OcrSummary) -> None:
                assert summary["at"] == "2026-10-12T20:15:30+02:00"

            def test_should_count_its_images_and_the_characters_of_its_markdown(self, summary: OcrSummary) -> None:
                assert (summary["images"], summary["chars"]) == (IMAGE_COUNT, MARKDOWN_CHARACTER_COUNT)

    class TestTheShouldDetectOrientationFunction:
        class TestWhenThePageIsAsScanned:
            @pytest.fixture
            def is_detected(self) -> bool:
                return should_detect_orientation(0)

            def test_should_let_the_sandbox_detect_its_orientation(self, is_detected: bool) -> None:
                assert is_detected is True

        class TestWhenTheUserTurnedIt:
            @pytest.fixture(params=[90, 180, 270], ids=["a-quarter-turn", "a-half-turn", "three-quarters-of-a-turn"])
            def is_detected(self, request: pytest.FixtureRequest) -> bool:
                return should_detect_orientation(request.param)

            def test_should_not_let_the_sandbox_detect_it_so_that_it_never_undoes_a_rotation_the_user_chose(
                self, is_detected: bool
            ) -> None:
                assert is_detected is False
