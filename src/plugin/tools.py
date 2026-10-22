"""The three tools: show a week (what the model sees), save a schedule after checking every rule (with a
receipt for the verifier), and pin the optimum (the answer key, which the model never sees)."""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from slimconfig import build_output

from contract import CaseInput, PinOutput, Placement, SavedOutput, SaveInput, WeekOutput
from plugin import week as weeks
from plugin.solve import solve

# This plugin process's run: every receipt it writes names it. A task's tool calls share one process.
RUN = secrets.token_hex(8)


def stamp() -> str:
    """Now, UTC, to the microsecond: strings in this form sort as their times do."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def plain(placement: Placement) -> dict:
    return {
        "meeting": placement.meeting.value,
        "day": placement.day.value,
        "start": placement.start,
        "room": placement.room.value,
    }


def get_week(given: CaseInput, workspace: Path) -> WeekOutput:
    return build_output(weeks.generate(given.case), WeekOutput)


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{RUN}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def save_schedule(given: SaveInput, workspace: Path) -> SavedOutput:
    """Check every rule; refuse with every broken one listed, or write the receipt and return its summary."""
    week = weeks.generate(given.case)
    placements = [plain(placement) for placement in given.placements]
    broken = weeks.violations(week, placements)
    if broken:
        lines = "\n".join(f"- {rule}: {text}" for rule, text in broken)
        plural = "rule is" if len(broken) == 1 else "rules are"
        raise ValueError(
            f"save_schedule refused case {given.case}: {len(broken)} {plural} broken and nothing was saved. "
            f"Fix these placements and save again:\n{lines}"
        )
    kept = weeks.ordered(placements)
    saved_at = stamp()
    digest = weeks.digest(given.case, RUN, saved_at, kept)
    receipt = {
        "case": given.case,
        "generator": weeks.GENERATOR,
        "run": RUN,
        "saved_at": saved_at,
        "placements": kept,
        "scheduled": len(kept),
        "digest": digest,
    }
    path = weeks.receipt_path(given.case)
    write_atomic(workspace / path, json.dumps(receipt, indent=2) + "\n")
    return SavedOutput(case=given.case, receipt=path, digest=digest, scheduled=len(kept))


def prior_runs(workspace: Path, case: int) -> list[str]:
    """The run of a receipt for ``case`` already in ``workspace``: one an earlier task left behind."""
    path = workspace / weeks.receipt_path(case)
    try:
        run = json.loads(path.read_text(encoding="utf-8"))["run"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [run] if isinstance(run, str) else []


def pin_optimum(given: CaseInput, workspace: Path) -> PinOutput:
    """The answer key: the optimum by exhaustive search, one optimal schedule, and this task's start."""
    pinned_at = stamp()
    week = weeks.generate(given.case)
    best, schedule, _ = solve(week)
    return build_output(
        {
            "case": given.case,
            "generator": weeks.GENERATOR,
            "meetings": len(week["meetings"]),
            "best": best,
            "worst": 0,
            "schedule": schedule,
            "pinned_at": pinned_at,
            "prior_runs": prior_runs(workspace, given.case),
        },
        PinOutput,
    )
