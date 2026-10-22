"""Shared helpers. The plugin needs no data or network: every week is built from its case number, so the
tests run on the real weeks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from slimconfig import build_output, plain_output

import verifier
from contract import CaseInput, PinOutput, SavedOutput, SaveInput
from plugin import week as weeks
from plugin.tools import pin_optimum, save_schedule

TASK = "schedule-week"


def sandboxed(value, cls):
    """A value as NanoAgent's sandbox hands it to the verifier: plain JSON built into its class."""
    return build_output(plain_output(value), cls)


def given(case: int) -> CaseInput:
    return build_output({"case": case}, CaseInput)


def key(folder: Path, case: int) -> PinOutput:
    """The answer key, pinned in a scratch folder of its own, as NanoAgent pins it."""
    scratch = folder / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    return sandboxed(pin_optimum(given(case), scratch), PinOutput)


def key_seeing(workspace: Path, folder: Path, case: int) -> PinOutput:
    """The answer key pinned in a scratch copy of ``workspace``, as the web pins it."""
    scratch = folder / "staged"
    shutil.copytree(workspace, scratch, dirs_exist_ok=True)
    return sandboxed(pin_optimum(given(case), scratch), PinOutput)


def save(workspace: Path, case: int, placements: list[dict]) -> SavedOutput:
    return sandboxed(
        save_schedule(build_output({"case": case, "placements": placements}, SaveInput), workspace), SavedOutput
    )


def summary(case: int, receipt: str, digest: str, scheduled: int) -> SavedOutput:
    return build_output({"case": case, "receipt": receipt, "digest": digest, "scheduled": scheduled}, SavedOutput)


def verdict(case: int, output, reference, workspace: Path):
    return verifier.verify_task(TASK, given(case), output, reference, str(workspace))


def failing(result) -> list[str]:
    return [row["id"] for row in result["details"]["constraints"] if not row["ok"]]


def plain_schedule(reference: PinOutput) -> list[dict]:
    return [plain_output(placement) for placement in reference.schedule]


def forge(workspace: Path, case: int, placements: list[dict], **changes) -> SavedOutput:
    """A receipt written by hand, bypassing save_schedule's checks, with a digest that matches it: what a
    tool that checked nothing would leave. Returns the summary that names it."""
    run, saved_at = "0123456789abcdef", "2999-01-01T00:00:00.000000Z"
    kept = weeks.ordered(placements)
    receipt = {
        "case": case,
        "generator": weeks.GENERATOR,
        "run": run,
        "saved_at": saved_at,
        "placements": kept,
        "scheduled": len(kept),
        "digest": weeks.digest(case, run, saved_at, kept),
    }
    receipt.update(changes)
    path = workspace / weeks.receipt_path(case)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return summary(case, weeks.receipt_path(case), receipt["digest"], receipt["scheduled"])


def options(week: dict, meeting: dict) -> list[dict]:
    """A meeting's placements that keep rules b to e, in day, start and room order."""
    return [
        {"meeting": meeting["meeting"], "day": day, "start": start, "room": room}
        for day, starts in meeting["open"].items()
        for start in starts
        for room in meeting["rooms"]
    ]


def greedy(week: dict, order: list[int]) -> list[dict]:
    """First come, first placed: each meeting in ``order`` gets its first placement that clashes with
    nothing placed before it, or is left out."""
    placed: list[dict] = []
    for index in order:
        for option in options(week, week["meetings"][index]):
            if not weeks.violations(week, placed + [option]):
                placed.append(option)
                break
    return placed


def in_order(week: dict) -> list[dict]:
    return greedy(week, list(range(len(week["meetings"]))))


def fewest_attendees(week: dict) -> list[dict]:
    meetings = week["meetings"]
    return greedy(week, sorted(range(len(meetings)), key=lambda index: (len(meetings[index]["attendees"]), index)))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    folder = tmp_path / "workspace"
    folder.mkdir()
    return folder
