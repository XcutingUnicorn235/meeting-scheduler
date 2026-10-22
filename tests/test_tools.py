"""save_schedule: it refuses a schedule with every broken rule listed and writes nothing, or saves the
receipt the verifier reads; and pin_optimum notices a receipt an earlier task left."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest
from conftest import key, key_seeing, plain_schedule, save
from slimconfig import build_output

from contract import SaveInput
from plugin import tools
from plugin import week as weeks


def free_at(week: dict, meeting: dict, day: str, start: int) -> bool:
    """Whether every attendee is free for the meeting's hours from ``start`` on ``day`` (hours past 17
    count as free: no one is busy then)."""
    return not any(
        hour in week["busy"][person].get(day, [])
        for person in meeting["attendees"]
        for hour in range(start, start + meeting["hours"])
    )


def _first_common(a: dict, b: dict) -> tuple[str, int] | None:
    for day, starts in a["open"].items():
        for start in starts:
            if start in b["open"].get(day, []):
                return day, start
    return None


def _broken(week: dict) -> dict[str, list[dict]] | None:
    """For each rule, placements of ``week`` that break it and nothing else, or None when some rule
    cannot be broken alone in this week."""
    meetings = week["meetings"]
    capacity = {room["room"]: room["capacity"] for room in week["rooms"]}

    def at(meeting: dict, day: str, start: int, room: str) -> dict:
        return {"meeting": meeting["meeting"], "day": day, "start": start, "room": room}

    def first(found):
        return next(iter(found), None)

    short = first(m for m in meetings if m["hours"] == 1 and m["day"] is None)
    wrong_day = first(
        (m, day, start)
        for m in meetings
        if m["day"] is not None
        for day in weeks.DAYS
        if day != m["day"]
        for start in range(9, 18 - m["hours"])
        if free_at(week, m, day, start)
    )
    big = first(m for m in meetings if m["min_capacity"] > capacity["oak"])
    closed = first(
        (m, day, start)
        for m in meetings
        for day in weeks.DAYS
        if m["day"] in (None, day)
        for start in range(9, 18 - m["hours"])
        if start not in m["open"].get(day, [])
    )
    clashing = first(
        (a, b, _first_common(a, b), ra, rb)
        for a in meetings
        for b in meetings
        if b["meeting"] in a["clashes"] and _first_common(a, b)
        for ra in a["rooms"]
        for rb in b["rooms"]
        if ra != rb
    )
    apart = first(
        (a, b, _first_common(a, b), room)
        for a in meetings
        for b in meetings
        if a is not b and b["meeting"] not in a["clashes"] and _first_common(a, b)
        for room in a["rooms"]
        if room in b["rooms"]
    )
    if len(meetings) == 9 or None in (short, wrong_day, big, closed, clashing, apart):
        return None
    some = meetings[0]
    day0 = next(iter(some["open"]))
    big_day = next(iter(big["open"]))
    m, day, start = wrong_day
    n, closed_day, closed_start = closed
    a, b, (day_ab, start_ab), ra, rb = clashing
    c, d, (day_cd, start_cd), room = apart
    return {
        "known-meeting": [{"meeting": "m9", "day": "mon", "start": 9, "room": "elm"}],
        "once": [at(some, day0, some["open"][day0][0], some["rooms"][0])] * 2,
        "working-hours": [at(short, "mon", 8, short["rooms"][-1])],
        "fixed-day": [at(m, day, start, m["rooms"][-1])],
        "room-capacity": [at(big, big_day, big["open"][big_day][0], "oak")],
        "attendees-free": [at(n, closed_day, closed_start, n["rooms"][-1])],
        "attendee-overlap": [at(a, day_ab, start_ab, ra), at(b, day_ab, start_ab, rb)],
        "room-overlap": [at(c, day_cd, start_cd, room), at(d, day_cd, start_cd, room)],
    }


@cache
def broken_case() -> tuple[int, dict[str, list[dict]]]:
    """The first week with fewer than 9 meetings where every rule can be broken alone, and for each rule
    placements that break it and nothing else."""
    for case in range(weeks.CASES):
        found = _broken(weeks.generate(case))
        if found is not None:
            return case, found
    raise AssertionError("no week lets every rule be broken alone")


def save_input(case: int, placements: list[dict]) -> SaveInput:
    return build_output({"case": case, "placements": placements}, SaveInput)


def test_saves_a_receipt_and_returns_its_summary(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, 4)
    saved = tools.save_schedule(save_input(4, plain_schedule(reference)), workspace)
    assert saved.case == 4 and saved.scheduled == reference.best
    assert saved.receipt == "meeting-scheduler/case-4.json"
    receipt = json.loads((workspace / saved.receipt).read_text(encoding="utf-8"))
    assert receipt["run"] == tools.RUN and receipt["generator"] == weeks.GENERATOR
    assert receipt["placements"] == weeks.ordered(plain_schedule(reference))
    assert (
        receipt["digest"] == saved.digest == weeks.digest(4, receipt["run"], receipt["saved_at"], receipt["placements"])
    )
    assert str(workspace) not in json.dumps(saved.__dict__)
    assert [path.name for path in (workspace / "meeting-scheduler").iterdir()] == ["case-4.json"]


def test_an_empty_schedule_is_saved(workspace: Path) -> None:
    assert save(workspace, 4, []).scheduled == 0


@pytest.mark.parametrize(
    "rule",
    [
        "known-meeting",
        "once",
        "working-hours",
        "fixed-day",
        "room-capacity",
        "attendees-free",
        "attendee-overlap",
        "room-overlap",
    ],
)
def test_refuses_each_broken_rule_alone_and_writes_nothing(workspace: Path, rule: str) -> None:
    case, broken = broken_case()
    assert [found for found, _ in weeks.violations(weeks.generate(case), broken[rule])] == [rule]
    with pytest.raises(ValueError, match=f"refused case {case}") as error:
        tools.save_schedule(save_input(case, broken[rule]), workspace)
    assert f"- {rule}: " in str(error.value)
    assert not (workspace / "meeting-scheduler").exists()


def test_a_refusal_lists_every_broken_rule_precisely(workspace: Path) -> None:
    case, broken = broken_case()
    everything = [
        placement for rule in ("known-meeting", "attendees-free", "room-overlap") for placement in broken[rule]
    ]
    with pytest.raises(ValueError) as error:
        tools.save_schedule(save_input(case, everything), workspace)
    text = str(error.value)
    broken_rules = weeks.violations(weeks.generate(case), everything)
    assert f"{len(broken_rules)} rules are broken and nothing was saved" in text
    for rule, message in broken_rules:
        assert f"- {rule}: {message}" in text
    assert len({rule for rule, _ in broken_rules}) >= 3


def test_the_messages_name_the_hours_people_and_rooms() -> None:
    case, broken = broken_case()
    week = weeks.generate(case)
    texts = {rule: [text for _, text in weeks.violations(week, placements)] for rule, placements in broken.items()}
    short = broken["working-hours"][0]["meeting"]
    assert texts["working-hours"] == [f"{short} starts at 8: the day runs from 9 to 17"]
    late = [dict(broken["working-hours"][0], start=17)]
    assert weeks.violations(week, late) == [
        ("working-hours", f"{short} runs 1h: starting at 17 it ends at 18, after 17")
    ]
    two_hours = next(m for m in week["meetings"] if m["hours"] == 2)
    late = [{"meeting": two_hours["meeting"], "day": two_hours["day"] or "mon", "start": 16, "room": "elm"}]
    assert (
        "working-hours",
        f"{two_hours['meeting']} runs 2h: starting at 16 it ends at 18, after 17",
    ) in weeks.violations(week, late)
    assert texts["attendees-free"][0].split(":")[1].strip().split(" is busy at ")[0] in weeks.PEOPLE
    assert texts["room-capacity"][0].endswith(f"oak holds {week['rooms'][0]['capacity']}")
    assert " overlap on " in texts["attendee-overlap"][0] and " and share " in texts["attendee-overlap"][0]
    assert texts["once"][0].endswith("is placed 2 times")


def test_saving_again_replaces_the_receipt(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, 4)
    first = save(workspace, 4, plain_schedule(reference)[:1])
    second = save(workspace, 4, plain_schedule(reference))
    receipt = json.loads((workspace / second.receipt).read_text(encoding="utf-8"))
    assert receipt["digest"] == second.digest != first.digest
    assert receipt["scheduled"] == reference.best


def test_a_refused_save_leaves_the_last_receipt_alone(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, 4)
    saved = save(workspace, 4, plain_schedule(reference))
    before = (workspace / saved.receipt).read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        tools.save_schedule(save_input(4, plain_schedule(reference) * 2), workspace)
    assert (workspace / saved.receipt).read_text(encoding="utf-8") == before


def test_pin_optimum_lists_a_receipt_an_earlier_task_left(tmp_path: Path, workspace: Path) -> None:
    save(workspace, 4, [])
    pinned = key_seeing(workspace, tmp_path, 4)
    assert pinned.prior_runs == [tools.RUN]
    assert key_seeing(workspace, tmp_path / "other", 5).prior_runs == []
