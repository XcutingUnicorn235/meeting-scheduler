"""The exact solver: it agrees with an independent search, finds an optimum on every case, and is fast."""

from __future__ import annotations

import time
from itertools import combinations
from pathlib import Path

from conftest import given, options

from plugin import week as weeks
from plugin.solve import solve
from plugin.tools import pin_optimum


def fits(week: dict, chosen: list[dict], placed: list[dict]) -> bool:
    """Whether every meeting of ``chosen`` can be placed next to ``placed``: plain backtracking."""
    if not chosen:
        return True
    first, rest = chosen[0], chosen[1:]
    for option in options(week, first):
        if not weeks.violations(week, placed + [option]) and fits(week, rest, placed + [option]):
            return True
    return False


def most_by_subsets(week: dict) -> int:
    """The optimum the slow way: the largest set of meetings that can all be placed, trying every set."""
    meetings = week["meetings"]
    for size in range(len(meetings), -1, -1):
        for chosen in combinations(meetings, size):
            ordered = sorted(chosen, key=lambda meeting: sum(len(h) for h in meeting["open"].values()))
            if fits(week, ordered, []):
                return size
    return 0


def test_the_optimum_agrees_with_trying_every_set_of_meetings() -> None:
    for case in range(0, 1000, 25):
        week = weeks.generate(case)
        assert solve(week)[0] == most_by_subsets(week), case


def test_every_case_has_an_optimum_below_all_meetings_found_quickly() -> None:
    slowest = 0.0
    for case in range(weeks.CASES):
        week = weeks.generate(case)
        started = time.perf_counter()
        best, schedule, _ = solve(week)
        slowest = max(slowest, time.perf_counter() - started)
        assert 1 <= best < len(week["meetings"]), case
        assert len(schedule) == best and not weeks.violations(week, schedule), case
        assert [p["meeting"] for p in schedule] == sorted((p["meeting"] for p in schedule), key=weeks.number)
    assert slowest < 5.0, "the reference must finish far inside the 180 s tool timeout"


def test_the_solver_is_deterministic() -> None:
    assert solve(weeks.generate(42)) == solve(weeks.generate(42))


def test_pin_optimum_gives_the_key(tmp_path: Path) -> None:
    pinned = pin_optimum(given(9), tmp_path)
    week = weeks.generate(9)
    assert pinned.case == 9 and pinned.generator == weeks.GENERATOR
    assert pinned.meetings == len(week["meetings"]) and pinned.worst == 0
    assert pinned.best == solve(week)[0] == len(pinned.schedule)
    assert pinned.prior_runs == [] and pinned.pinned_at.endswith("Z")
    assert not list(tmp_path.iterdir()), "pinning writes nothing"
