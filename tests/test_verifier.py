"""The verifier on contract instances built the way NanoAgent's sandbox builds them: from plain JSON."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import (
    failing,
    forge,
    given,
    key,
    key_seeing,
    plain_schedule,
    sandboxed,
    save,
    summary,
    verdict,
)
from slimconfig import build_output
from test_tools import broken_case

import verifier
from contract import PinOutput, Placement, SavedOutput, SaveInput, WeekOutput
from plugin import week as weeks
from plugin.solve import solve
from plugin.tools import get_week, stamp

CASE = 4


def other_optimum(week: dict, schedule: list[dict], drop: bool = False) -> list[dict] | None:
    """An optimal schedule other than ``schedule``: one that never uses one of its placements' start hours
    (or, with ``drop``, never holds one of its meetings). Taking choices away only removes schedules, so what
    the solver finds is a schedule of the full week too."""
    for placement in schedule:
        narrowed = copy.deepcopy(week)
        meeting = next(m for m in narrowed["meetings"] if m["meeting"] == placement["meeting"])
        if drop:
            meeting["open"] = {}
        else:
            meeting["open"][placement["day"]].remove(placement["start"])
            meeting["open"] = {day: hours for day, hours in meeting["open"].items() if hours}
        best, found, _ = solve(narrowed)
        if best == len(schedule):
            return found
    return None


def test_the_oracle_scores_one(tmp_path: Path, workspace: Path) -> None:
    for case in range(12):
        reference = key(tmp_path, case)
        result = verdict(case, save(workspace, case, plain_schedule(reference)), reference, workspace)
        assert result["valid"] is True and result["score"] == 1.0, case
        assert result["message"].endswith("meetings held, the most possible")
        assert not failing(result)


def test_every_optimal_schedule_scores_one_not_only_the_keys(tmp_path: Path, workspace: Path) -> None:
    found = 0
    for case in range(30):
        reference = key(tmp_path, case)
        week = weeks.generate(case)
        other = other_optimum(week, plain_schedule(reference))
        if other is None:
            continue
        assert weeks.ordered(other) != weeks.ordered(plain_schedule(reference))
        assert not weeks.violations(week, other)
        result = verdict(case, save(workspace, case, other), reference, workspace)
        assert result["valid"] is True and result["score"] == 1.0, case
        found += 1
    assert found >= 20


def test_an_optimum_leaving_out_other_meetings_scores_one(tmp_path: Path, workspace: Path) -> None:
    for case in range(60):
        reference = key(tmp_path, case)
        other = other_optimum(weeks.generate(case), plain_schedule(reference), drop=True)
        if other is not None:
            held = {p["meeting"] for p in other}
            assert held != {p.meeting.value for p in reference.schedule}
            result = verdict(case, save(workspace, case, other), reference, workspace)
            assert result["valid"] is True and result["score"] == 1.0
            every = {m["meeting"] for m in weeks.generate(case)["meetings"]}
            assert set(result["details"]["left_out"]) == every - held
            return
    raise AssertionError("no week has two optima that hold different meetings")


def test_a_schedule_below_the_optimum_keeps_partial_credit(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, CASE)
    fewer = plain_schedule(reference)[:-1]
    result = verdict(CASE, save(workspace, CASE, fewer), reference, workspace)
    assert result["valid"] is False
    assert result["score"] == round((reference.best - 1) / reference.best, 4)
    assert failing(result) == ["most-meetings"]
    assert result["message"].endswith(f"{reference.best} were possible")


def test_an_empty_schedule_scores_zero(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, CASE)
    result = verdict(CASE, save(workspace, CASE, []), reference, workspace)
    assert result["valid"] is False and result["score"] == 0.0


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
def test_a_receipt_breaking_a_rule_scores_zero_though_its_digest_matches(
    tmp_path: Path, workspace: Path, rule: str
) -> None:
    case, broken = broken_case()
    reference = key(tmp_path, case)
    output = forge(workspace, case, broken[rule])
    result = verdict(case, output, reference, workspace)
    assert result["valid"] is False and result["score"] == 0.0
    assert failing(result) == [rule]
    assert result["message"].startswith("the schedule breaks a rule")


def test_a_forged_optimum_plus_one_broken_meeting_scores_zero(tmp_path: Path, workspace: Path) -> None:
    """More meetings than the optimum can only come from breaking a rule; the verifier finds which."""
    case = broken_case()[0]
    reference = key(tmp_path, case)
    held = {p.meeting.value for p in reference.schedule}
    extra = next(
        {"meeting": m["meeting"], "day": day, "start": hours[0], "room": m["rooms"][-1]}
        for m in weeks.generate(case)["meetings"]
        if m["meeting"] not in held
        for day, hours in m["open"].items()
    )
    result = verdict(case, forge(workspace, case, plain_schedule(reference) + [extra]), reference, workspace)
    assert result["score"] == 0.0 and failing(result)
    assert set(failing(result)) <= {"attendee-overlap", "room-overlap"}


def write_receipt(workspace: Path, case: int, change) -> None:
    path = workspace / weeks.receipt_path(case)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    change(receipt)
    path.write_text(json.dumps(receipt), encoding="utf-8")


@pytest.mark.parametrize(
    "change, failing_id",
    [
        (lambda r: r["placements"][0].update(start=r["placements"][0]["start"] + 1), "receipt-intact"),
        (lambda r: r.update(scheduled=r["scheduled"] + 1), "receipt-intact"),
        (lambda r: r.update(run="not-a-run"), "receipt-file"),
        (lambda r: r.pop("digest"), "receipt-file"),
        (
            lambda r: r["placements"].append({"meeting": "m10", "day": "sun", "start": 9, "room": "hall"}),
            "receipt-file",
        ),
        (lambda r: r.update(case=CASE + 1), "receipt-case"),
        (lambda r: r.update(generator="meeting-scheduler/0"), "receipt-case"),
    ],
    ids=["moved-meeting", "inflated-count", "bad-run", "no-digest", "unknown-values", "other-case", "other-generator"],
)
def test_a_tampered_receipt_is_refused(tmp_path: Path, workspace: Path, change, failing_id: str) -> None:
    reference = key(tmp_path, CASE)
    output = save(workspace, CASE, plain_schedule(reference))
    write_receipt(workspace, CASE, change)
    result = verdict(CASE, output, reference, workspace)
    assert result["valid"] is False and result["score"] == 0.0
    assert failing(result) == [failing_id]


def test_a_receipt_that_is_not_json_or_is_missing_is_refused(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, CASE)
    output = save(workspace, CASE, plain_schedule(reference))
    (workspace / output.receipt).write_text("{not json", encoding="utf-8")
    assert failing(verdict(CASE, output, reference, workspace)) == ["receipt-file"]
    (workspace / output.receipt).unlink()
    result = verdict(CASE, output, reference, workspace)
    assert failing(result) == ["receipt-file"] and "missing" in result["message"] + json.dumps(result["details"])


@pytest.mark.parametrize(
    "fields, failing_id",
    [
        ({"digest": "0" * 64}, "output-matches-receipt"),
        ({"scheduled": 9}, "output-matches-receipt"),
        ({"case": CASE + 1}, "output-case"),
        ({"receipt": "meeting-scheduler/case-5.json"}, "receipt-path"),
        ({"receipt": "../meeting-scheduler/case-4.json"}, "receipt-path"),
    ],
    ids=["made-up-digest", "made-up-count", "other-case", "other-receipt", "path-outside"],
)
def test_an_output_that_does_not_match_its_receipt_is_refused(
    tmp_path: Path, workspace: Path, fields, failing_id
) -> None:
    reference = key(tmp_path, CASE)
    output = save(workspace, CASE, plain_schedule(reference))
    changed = summary(
        **{
            "case": output.case,
            "receipt": output.receipt,
            "digest": output.digest,
            "scheduled": output.scheduled,
            **fields,
        }
    )
    result = verdict(CASE, changed, reference, workspace)
    assert result["valid"] is False and result["score"] == 0.0
    assert failing(result) == [failing_id]


def test_a_summary_with_no_receipt_behind_it_is_refused(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, CASE)
    made_up = summary(CASE, weeks.receipt_path(CASE), "a" * 64, reference.best)
    result = verdict(CASE, made_up, reference, workspace)
    assert result["score"] == 0.0 and failing(result) == ["receipt-file"]


def test_a_receipt_saved_before_the_task_began_is_refused(tmp_path: Path, workspace: Path) -> None:
    earlier = key(tmp_path / "earlier", CASE)
    stale = save(workspace, CASE, plain_schedule(earlier))
    saved_at = json.loads((workspace / stale.receipt).read_text(encoding="utf-8"))["saved_at"]
    while stamp() == saved_at:  # the clock can tick as rarely as every 16 ms (Windows)
        pass
    # A new task on the same week, pinned after that save; its agent submits the old summary.
    reference = key(tmp_path, CASE)
    result = verdict(CASE, stale, reference, workspace)
    assert result["valid"] is False and result["score"] == 0.0
    assert failing(result) == ["this-run"] and "before this task's key was pinned" in json.dumps(result)
    # The same week saved again in this task passes.
    fresh = save(workspace, CASE, plain_schedule(reference))
    assert verdict(CASE, fresh, reference, workspace)["score"] == 1.0


def test_a_receipt_the_key_found_in_the_workspace_is_refused(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, CASE)
    stale = save(workspace, CASE, plain_schedule(reference))
    # The web pins the key in a copy of the workspace: it sees the earlier task's receipt and its run.
    seen = key_seeing(workspace, tmp_path, CASE)
    seen = sandboxed(replace(seen, pinned_at=reference.pinned_at), PinOutput)
    result = verdict(CASE, stale, seen, workspace)
    assert failing(result) == ["this-run"] and "saved it before this task began" in json.dumps(result)


def tampered(reference: PinOutput, **changes) -> PinOutput:
    return sandboxed(replace(reference, **changes), PinOutput)


def moved(reference: PinOutput) -> list[Placement]:
    """The key's schedule with its first meeting moved onto the second's time and room."""
    first, second = reference.schedule[0], reference.schedule[1]
    return [replace(first, day=second.day, start=second.start, room=second.room)] + reference.schedule[1:]


@pytest.mark.parametrize(
    "change, failing_id",
    [
        (lambda r: {"case": CASE + 1}, "key-case"),
        (lambda r: {"generator": "meeting-scheduler/0"}, "key-generator"),
        (lambda r: {"meetings": r.meetings + 1}, "key-meetings"),
        (lambda r: {"best": r.meetings, "schedule": r.schedule}, "key-best"),
        (lambda r: {"best": 0, "schedule": []}, "key-best"),
        (lambda r: {"worst": 1}, "key-worst"),
        (lambda r: {"schedule": r.schedule[:-1]}, "key-schedule"),
        (lambda r: {"schedule": moved(r)}, "key-schedule"),
        (lambda r: {"pinned_at": "yesterday"}, "key-pinned"),
        (lambda r: {"prior_runs": ["?"]}, "key-pinned"),
    ],
    ids=[
        "other-case",
        "other-generator",
        "miscounted",
        "best-all",
        "best-none",
        "worst",
        "short",
        "clashing",
        "no-time",
        "bad-run",
    ],
)
def test_a_tampered_answer_key_is_refused(tmp_path: Path, workspace: Path, change, failing_id: str) -> None:
    reference = key(tmp_path, CASE)
    output = save(workspace, CASE, plain_schedule(reference))
    broken = tampered(reference, **change(reference))
    result = verdict(CASE, output, broken, workspace)
    assert result["valid"] is False and result["score"] == 0.0
    assert failing_id in failing(result)
    assert verifier.verify_output("pin_optimum", given(CASE), broken, str(workspace))["valid"] is False


def test_a_key_below_the_true_optimum_is_caught(tmp_path: Path, workspace: Path) -> None:
    """A key that holds together but undercounts: a schedule holding more shows the key is wrong."""
    reference = key(tmp_path, CASE)
    low = tampered(reference, best=reference.best - 1, schedule=reference.schedule[:-1])
    assert verifier.verify_output("pin_optimum", given(CASE), low, str(workspace))["valid"] is True
    result = verdict(CASE, save(workspace, CASE, plain_schedule(reference)), low, workspace)
    assert result["valid"] is False and result["score"] == 0.0
    assert failing(result) == ["within-best"] and "the key is wrong" in result["message"]


def test_a_missing_key_or_a_case_out_of_range_scores_zero(workspace: Path) -> None:
    made_up = summary(CASE, weeks.receipt_path(CASE), "a" * 64, 1)
    assert failing(verdict(CASE, made_up, None, workspace)) == ["answer-key"]
    assert failing(verdict(1000, made_up, None, workspace)) == ["task-case"]


@pytest.mark.parametrize("tool", ["get_week", "save_schedule", "pin_optimum"])
def test_inputs_must_name_an_existing_case(tool: str) -> None:
    def value(case: int):
        if tool == "save_schedule":
            return build_output({"case": case, "placements": []}, SaveInput)
        return given(case)

    assert verifier.verify_input(tool, value(0))["valid"] is True
    assert verifier.verify_input(tool, value(999))["valid"] is True
    assert verifier.verify_input(tool, value(-1))["valid"] is False
    assert verifier.verify_input(tool, value(1000))["valid"] is False


def test_get_week_output_is_checked(tmp_path: Path) -> None:
    shown = sandboxed(get_week(given(CASE), tmp_path), WeekOutput)
    assert verifier.verify_output("get_week", given(CASE), shown, str(tmp_path))["valid"] is True
    first = shown.meetings[0]
    cases = {
        "other case": replace(shown, case=CASE + 1),
        "a meeting missing": replace(shown, meetings=shown.meetings[:-1]),
        "made-up open hour": replace(shown, meetings=[replace(first, open={**first.open})] + shown.meetings[1:]),
        "bigger room": replace(shown, rooms=[replace(shown.rooms[0], capacity=20)] + shown.rooms[1:]),
        "nobody busy": replace(shown, busy={}),
    }
    day = next(iter(first.open))
    cases["made-up open hour"].meetings[0].open[day] = sorted(set(first.open[day]) | {9, 10, 11, 12, 13, 14, 15, 16})
    for name, bad in cases.items():
        result = verifier.verify_output("get_week", given(CASE), sandboxed(bad, WeekOutput), str(tmp_path))
        assert result["valid"] is False, name


def test_save_schedule_output_is_checked(tmp_path: Path, workspace: Path) -> None:
    reference = key(tmp_path, CASE)
    placements = plain_schedule(reference)
    request = build_output({"case": CASE, "placements": placements}, SaveInput)
    output = save(workspace, CASE, placements)
    assert verifier.verify_output("save_schedule", request, output, str(workspace))["valid"] is True
    fewer = build_output({"case": CASE, "placements": placements[:-1]}, SaveInput)
    assert verifier.verify_output("save_schedule", fewer, output, str(workspace))["valid"] is False
    lying = sandboxed(replace(output, scheduled=output.scheduled + 1), SavedOutput)
    assert verifier.verify_output("save_schedule", request, lying, str(workspace))["valid"] is False
    case, broken = broken_case()
    forged = forge(workspace, case, broken["room-overlap"])
    asked = build_output({"case": case, "placements": broken["room-overlap"]}, SaveInput)
    result = verifier.verify_output("save_schedule", asked, forged, str(workspace))
    assert result["valid"] is False and "same room" in result["message"]


def test_the_verdict_is_deterministic_and_small(tmp_path: Path, workspace: Path) -> None:
    case, broken = broken_case()
    reference = key(tmp_path, case)
    week = weeks.generate(case)
    pile = (
        [{"meeting": m["meeting"], "day": "mon", "start": 9, "room": "oak"} for m in week["meetings"]]
        + broken["known-meeting"]
        + broken["once"]
    )
    output = forge(workspace, case, pile)
    first = json.dumps(verdict(case, output, reference, workspace), sort_keys=True)
    second = json.dumps(verdict(case, output, reference, workspace), sort_keys=True)
    assert first == second
    assert len(first) < 8000, "the verdict lands in the chat's context: keep it small"
    other = key(tmp_path, CASE)
    good = json.dumps(verdict(CASE, save(workspace, CASE, plain_schedule(other)), other, workspace))
    assert len(good) < 8000
