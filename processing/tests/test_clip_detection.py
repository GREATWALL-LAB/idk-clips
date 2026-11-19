from __future__ import annotations

from typing import Any

import pytest

from openclip_processing.clip_detection import (
    ClipSuggestion,
    DetectionOptions,
    build_prompt,
    chunk_segments,
    detect_clips,
    select_clips,
)
from openclip_processing.errors import AIProviderError, ClipDetectionError


def make_segments(count: int = 40, length: float = 5.0, gap: float = 0.5) -> list[dict[str, Any]]:
    segments = []
    t = 0.0
    for i in range(count):
        start, end = t, t + length
        words = [
            {"start": start + k, "end": start + k + 0.8, "text": f"w{i}_{k}"}
            for k in range(int(length))
        ]
        segments.append(
            {"id": i, "start": start, "end": end, "text": f"Sentence number {i}.", "words": words}
        )
        t = end + gap
    return segments


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate_json(self, system, user, schema, *, temperature=0.2, should_cancel=None):  # type: ignore[no-untyped-def]
        self.prompts.append(user)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def clip(start: int, end: int, score: int, title: str = "A title") -> dict[str, Any]:
    return {
        "start_segment": start,
        "end_segment": end,
        "title": title,
        "description": "d",
        "reason": "r",
        "score": score,
    }


def test_timestamps_come_from_real_segments_and_are_padded() -> None:
    segments = make_segments()
    provider = FakeProvider([{"clips": [clip(2, 6, 90)]}])
    [result] = detect_clips(segments, 220.0, DetectionOptions(clip_count=5), provider)
    # Segment 2 starts at 11.0 and segment 6 ends at 38.0; padding never crosses neighbours.
    assert result.start == pytest.approx(10.75)
    assert result.end == pytest.approx(38.45)
    assert result.first_segment == 2 and result.last_segment == 6
    assert "Sentence number 2." in result.text


def test_short_clips_are_extended_and_long_clips_trimmed_at_sentence_boundaries() -> None:
    segments = make_segments()
    options = DetectionOptions(clip_count=5, min_seconds=20, max_seconds=30)
    provider = FakeProvider([{"clips": [clip(3, 3, 80), clip(10, 30, 70)]}])
    short, long_ = sorted(detect_clips(segments, 220.0, options, provider), key=lambda c: c.start)
    assert 20 <= short.duration <= 31
    assert long_.duration <= 31
    assert long_.first_segment == 10


def test_invalid_and_hallucinated_segment_ids_are_ignored() -> None:
    segments = make_segments(10)
    provider = FakeProvider(
        [{"clips": [clip(99, 120, 99), {"start_segment": "x"}, "junk", clip(1, 4, 50)]}]
    )
    results = detect_clips(segments, 60.0, DetectionOptions(clip_count=5, min_seconds=10), provider)
    assert [r.first_segment for r in results] == [1]


def test_overlapping_suggestions_are_deduplicated_and_ranked() -> None:
    a = ClipSuggestion(10, 40, "a", "", "", 90, 0, 1, "")
    b = ClipSuggestion(12, 42, "b", "", "", 80, 0, 1, "")  # mostly overlaps a
    c = ClipSuggestion(60, 90, "c", "", "", 70, 2, 3, "")
    assert [s.title for s in select_clips([c, b, a], 5)] == ["a", "c"]
    assert [s.title for s in select_clips([c, b, a], 1)] == ["a"]


def test_fewer_clips_are_returned_instead_of_inventing_more() -> None:
    provider = FakeProvider([{"clips": [clip(1, 5, 60)]}])
    results = detect_clips(make_segments(), 220.0, DetectionOptions(clip_count=8), provider)
    assert len(results) == 1


def test_empty_transcript_and_no_suggestions_raise_clear_errors() -> None:
    with pytest.raises(ClipDetectionError, match="empty"):
        detect_clips([], 10.0, DetectionOptions(), FakeProvider([]))
    with pytest.raises(ClipDetectionError, match="did not suggest"):
        detect_clips(make_segments(), 220.0, DetectionOptions(), FakeProvider([{"clips": []}]))


def test_malformed_output_is_retried_once() -> None:
    provider = FakeProvider(
        [AIProviderError("The AI model did not return valid JSON."), {"clips": [clip(1, 5, 60)]}]
    )
    assert len(detect_clips(make_segments(), 220.0, DetectionOptions(), provider)) == 1
    failing = FakeProvider([AIProviderError("Ollama is not reachable.")])
    with pytest.raises(AIProviderError, match="not reachable"):
        detect_clips(make_segments(), 220.0, DetectionOptions(), failing)


def test_prompt_marks_transcript_as_data_and_chunks_long_transcripts() -> None:
    long_segments = make_segments(400)
    chunks = chunk_segments(long_segments, max_chars=2000)
    assert len(chunks) > 1
    assert chunks[1][0]["id"] < chunks[0][-1]["id"] + 1  # chunks overlap a little
    prompt = build_prompt(chunks[0], 4, DetectionOptions(language="en"))
    assert "[0] 0:00-0:05 Sentence number 0." in prompt
    assert "English" in prompt


def test_text_fields_are_trimmed() -> None:
    long_title = "word " * 100
    provider = FakeProvider([{"clips": [clip(1, 5, 500, title=long_title)]}])
    [result] = detect_clips(make_segments(), 220.0, DetectionOptions(), provider)
    assert len(result.title) <= 100
    assert result.score == 100  # clamped to 1..100


def test_short_clips_do_not_grow_into_the_next_suggestion() -> None:
    # Segment 3 alone is too short; segment 4 starts another suggestion, so the clip
    # must grow backwards instead of ending in the middle of the next topic.
    segments = make_segments()
    options = DetectionOptions(clip_count=5, min_seconds=15, max_seconds=60)
    provider = FakeProvider([{"clips": [clip(3, 3, 90, "First"), clip(4, 8, 80, "Second")]}])
    results = {r.title: r for r in detect_clips(segments, 220.0, options, provider)}
    assert set(results) == {"First", "Second"}
    assert results["First"].last_segment == 3
    assert results["First"].first_segment < 3
    # Neither clip contains the other's speech (padding may share the silent gap).
    assert results["First"].end <= segments[4]["start"]
    assert results["Second"].start >= segments[3]["end"]
