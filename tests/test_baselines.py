"""Trivial agents, first-come schedulers and two naive verifiers, scored on the first 100 weeks.

An agent that does not schedule earns 0; an agent that places meetings without keeping the rules earns 0;
only the optimum earns full marks. The first-come schedulers keep every rule but take meetings in a fixed
order, so they hold fewer meetings than possible on many weeks. The naive verifiers are what a quick
check would use: comparing with the key's own schedule, or believing the count the agent reports.
"""

from __future__ import annotations

import random
from pathlib import Path
from statistics import mean

from conftest import fewest_attendees, forge, in_order, key, plain_schedule, save, summary, verdict
from test_verifier import other_optimum

from plugin import week as weeks

CASES = range(100)


def run(tmp_path: Path, workspace: Path, agent, forged: bool = False) -> list[dict]:
    """Each week's verdict for the schedule ``agent(week, key)`` returns, saved by save_schedule (or, with
    ``forged``, written as a receipt directly, since save_schedule would refuse it)."""
    out = []
    for case in CASES:
        reference = key(tmp_path, case)
        placements = agent(weeks.generate(case), reference)
        output = forge(workspace, case, placements) if forged else save(workspace, case, placements)
        out.append(verdict(case, output, reference, workspace))
    return out


def scores(results) -> list[float]:
    return [result["score"] for result in results]


def test_scheduling_nothing_scores_zero(tmp_path: Path, workspace: Path) -> None:
    assert scores(run(tmp_path, workspace, lambda week, reference: [])) == [0.0] * len(CASES)


def test_the_oracle_scores_one(tmp_path: Path, workspace: Path) -> None:
    results = run(tmp_path, workspace, lambda week, reference: plain_schedule(reference))
    assert scores(results) == [1.0] * len(CASES) and all(result["valid"] for result in results)


def everything_at_once(week: dict, reference) -> list[dict]:
    """Every meeting on Monday at 9 in the biggest room: all the same answer."""
    return [{"meeting": m["meeting"], "day": "mon", "start": 9, "room": "elm"} for m in week["meetings"]]


def test_placing_every_meeting_alike_scores_zero(tmp_path: Path, workspace: Path) -> None:
    assert scores(run(tmp_path, workspace, everything_at_once, forged=True)) == [0.0] * len(CASES)


def test_placing_meetings_at_random_scores_about_zero(tmp_path: Path, workspace: Path) -> None:
    rng = random.Random(580)

    def guess(week: dict, reference) -> list[dict]:
        held = rng.sample(week["meetings"], rng.randint(1, len(week["meetings"])))
        return [
            {
                "meeting": m["meeting"],
                "day": rng.choice(weeks.DAYS),
                "start": rng.randint(9, 17 - m["hours"]),
                "room": rng.choice(weeks.ROOMS),
            }
            for m in held
        ]

    assert mean(scores(run(tmp_path, workspace, guess, forged=True))) < 0.05


def test_holding_every_meeting_is_never_possible(tmp_path: Path, workspace: Path) -> None:
    """Every week has more meetings than any schedule can hold, so the agent has to choose."""
    for case in CASES:
        assert key(tmp_path, case).best < len(weeks.generate(case)["meetings"])


def test_first_come_schedulers_keep_the_rules_but_often_hold_too_few(tmp_path: Path, workspace: Path) -> None:
    for agent in (in_order, fewest_attendees):
        results = run(tmp_path, workspace, lambda week, reference, agent=agent: agent(week))
        assert all(result["score"] > 0 for result in results), "they keep every rule"
        fully_right = mean(result["valid"] for result in results)
        assert 0.4 < fully_right < 0.8, (agent.__name__, fully_right)
        assert 0.85 < mean(scores(results)) < 0.98


def test_matching_the_keys_schedule_would_fail_other_optima(tmp_path: Path, workspace: Path) -> None:
    """A naive verifier that wants the key's schedule back refuses optimal schedules the real one accepts."""
    refused = 0
    for case in range(30):
        reference = key(tmp_path, case)
        other = other_optimum(weeks.generate(case), plain_schedule(reference))
        if other is None:
            continue
        naive = weeks.ordered(other) == weeks.ordered(plain_schedule(reference))
        ours = verdict(case, save(workspace, case, other), reference, workspace)
        assert not naive and ours["score"] == 1.0
        refused += 1
    assert refused >= 20


def test_believing_the_reported_count_would_reward_a_made_up_summary(tmp_path: Path, workspace: Path) -> None:
    """A naive verifier that scores the count the agent submits gives a made-up summary full marks."""
    for case in range(10):
        reference = key(tmp_path, case)
        made_up = summary(case, weeks.receipt_path(case), "f" * 64, reference.best)
        naive = made_up.scheduled / reference.best
        assert naive == 1.0
        assert verdict(case, made_up, reference, workspace)["score"] == 0.0
