"""The generator and get_week: fixed weeks of the promised shape, whose open hours, rooms and clashes are
exactly what the busy hours and capacities give."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from conftest import given, key
from slimconfig import plain_output

from contract import Meeting, SaveInput
from plugin import week as weeks
from plugin.tools import get_week, pin_optimum, save_schedule
from verifier import rules

ALL = range(weeks.CASES)
# SHA-256 of the JSON of weeks 0 to 9: a changed generator changes every task, so it must bump GENERATOR.
PINNED_WEEKS = "fc62926445cb07700fee31bb4cf14c2f710fa948557aad3c36d5d6e8c9e70d38"


def weeks_digest() -> str:
    text = json.dumps([weeks.generate(case) for case in range(10)], sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_stream_is_sha256_of_the_case() -> None:
    stream = weeks.Stream("meeting-scheduler:7")
    assert stream.seed == hashlib.sha256(b"meeting-scheduler:7").digest()
    first = hashlib.sha256(stream.seed + (0).to_bytes(8, "big")).digest()
    assert stream.below(1000) == int.from_bytes(first[:8], "big") % 1000
    assert stream.below(1000) == int.from_bytes(first[8:16], "big") % 1000
    picked = weeks.Stream("x").sample(range(10), 10)
    assert sorted(picked) == list(range(10))


def test_weeks_are_fixed() -> None:
    assert weeks.generate(5) == weeks.generate(5)
    assert weeks.generate(5) != weeks.generate(6)
    assert weeks_digest() == PINNED_WEEKS


def test_every_week_has_the_promised_shape() -> None:
    for case in ALL:
        week = weeks.generate(case)
        meetings = week["meetings"]
        assert 7 <= len(meetings) <= 9
        assert [meeting["meeting"] for meeting in meetings] == [f"m{n}" for n in range(1, len(meetings) + 1)]
        capacity = {room["room"]: room["capacity"] for room in week["rooms"]}
        assert list(capacity) == list(weeks.ROOMS)
        assert capacity["oak"] in (3, 4) and capacity["pine"] in (5, 6) and capacity["elm"] in (8, 10)
        assert set(week["busy"]) == set(weeks.PEOPLE)
        for days in week["busy"].values():
            for hours in days.values():
                assert hours and hours == sorted(set(hours)) and all(9 <= hour <= 16 for hour in hours)
        for meeting in meetings:
            assert 2 <= len(meeting["attendees"]) <= 4
            assert meeting["attendees"] == sorted(meeting["attendees"], key=weeks.PEOPLE.index)
            assert meeting["hours"] in (1, 2)
            assert len(meeting["attendees"]) <= meeting["min_capacity"] <= capacity["elm"]


def busy_at(week: dict, person: str, day: str, hour: int) -> bool:
    return hour in week["busy"][person].get(day, [])


def test_open_hours_rooms_and_clashes_are_what_the_rules_give() -> None:
    for case in range(0, weeks.CASES, 7):
        week = weeks.generate(case)
        capacity = {room["room"]: room["capacity"] for room in week["rooms"]}
        for meeting in week["meetings"]:
            for day in weeks.DAYS:
                expected = [
                    start
                    for start in range(9, 18 - meeting["hours"])
                    if meeting["day"] in (None, day)
                    and not any(
                        busy_at(week, person, day, hour)
                        for person in meeting["attendees"]
                        for hour in range(start, start + meeting["hours"])
                    )
                ]
                assert meeting["open"].get(day, []) == expected
            assert meeting["rooms"] == [room for room in weeks.ROOMS if capacity[room] >= meeting["min_capacity"]]
            for other in week["meetings"]:
                shares = other is not meeting and bool(set(other["attendees"]) & set(meeting["attendees"]))
                assert (other["meeting"] in meeting["clashes"]) == shares


def test_a_fixed_day_always_has_an_open_hour() -> None:
    for case in ALL:
        for meeting in weeks.generate(case)["meetings"]:
            if meeting["day"] is not None:
                assert list(meeting["open"]) == [meeting["day"]]


def test_no_week_can_hold_every_meeting() -> None:
    """The lead attends 4 or 5 meetings and is free one hour less than they need in all."""
    for case in ALL:
        assert rules.lead_crunch(weeks.generate(case)), case


def test_the_most_flexible_meetings_are_listed_first() -> None:
    for case in range(0, weeks.CASES, 11):
        week = weeks.generate(case)
        capacity = {room["room"]: room["capacity"] for room in week["rooms"]}
        counts = [weeks.option_count(meeting, week["busy"], capacity) for meeting in week["meetings"]]
        assert counts == sorted(counts, reverse=True)


def test_get_week_shows_the_week_and_writes_nothing(tmp_path: Path) -> None:
    shown = plain_output(get_week(given(12), tmp_path))
    assert shown == weeks.generate(12)
    assert not list(tmp_path.iterdir())


def test_get_week_never_shows_the_answer(tmp_path: Path) -> None:
    shown = plain_output(get_week(given(3), tmp_path))
    assert set(shown) == {"case", "rooms", "meetings", "busy"}
    text = json.dumps(shown)
    for word in ("best", "optimum", "schedule", "lead", "seed"):
        assert word not in text
    assert key(tmp_path, 3).best < len(shown["meetings"])


def test_a_week_fits_comfortably_in_context() -> None:
    sizes = [len(json.dumps(weeks.generate(case))) for case in ALL]
    assert max(sizes) < 4000, "about 1,000 tokens at most"


@pytest.mark.parametrize("case", [-1, weeks.CASES])
def test_tools_refuse_a_case_out_of_range(tmp_path: Path, case: int) -> None:
    with pytest.raises(ValueError, match="case must be from 0"):
        get_week(given(case), tmp_path)
    with pytest.raises(ValueError, match="case must be from 0"):
        pin_optimum(given(case), tmp_path)
    with pytest.raises(ValueError, match="case must be from 0"):
        save_schedule(SaveInput(case=case, placements=[]), tmp_path)


def test_the_contract_names_every_meeting_a_week_can_have() -> None:
    assert [meeting.value for meeting in Meeting] == [f"m{n}" for n in range(1, 10)]
