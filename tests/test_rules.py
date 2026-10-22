"""The verifier restates the plugin's rules; they must agree, on every case and on any placements."""

from __future__ import annotations

import random

import plugin.week as week_module
import verifier.rules as rules_module
from contract import Day, Meeting, Person, Room

CONSTANTS = ("GENERATOR", "CASES", "DAYS", "FIRST_HOUR", "END_HOUR", "PEOPLE", "ROOMS", "RULES", "RECEIPT_DIR")


def test_constants_agree_with_each_other_and_the_contract() -> None:
    for name in CONSTANTS:
        assert vars(week_module)[name] == vars(rules_module)[name], name
    assert rules_module.DAYS == tuple(day.value for day in Day)
    assert rules_module.ROOMS == tuple(room.value for room in Room)
    assert rules_module.PEOPLE == tuple(person.value for person in Person)
    assert rules_module.MEETINGS == tuple(meeting.value for meeting in Meeting)


def test_the_streams_agree() -> None:
    for text in ("meeting-scheduler:0", "meeting-scheduler:999", ""):
        a, b = week_module.Stream(text), rules_module.Stream(text)
        assert [a.below(bound) for bound in range(1, 60)] == [b.below(bound) for bound in range(1, 60)]
        assert a.sample(range(9), 5) == b.sample(range(9), 5)


def test_the_generators_agree_on_every_case() -> None:
    for case in range(week_module.CASES):
        assert week_module.generate(case) == rules_module.generate(case), case


def random_placements(rng: random.Random, count: int) -> list[dict]:
    return [
        {
            "meeting": f"m{rng.randint(1, 9)}",
            "day": rng.choice(week_module.DAYS),
            "start": rng.randint(7, 17),
            "room": rng.choice(week_module.ROOMS),
        }
        for _ in range(count)
    ]


def test_the_rule_checks_agree_on_random_placements() -> None:
    rng = random.Random(580)
    for _ in range(3000):
        week = week_module.generate(rng.randrange(week_module.CASES))
        placements = random_placements(rng, rng.randint(0, 10))
        assert week_module.violations(week, placements) == rules_module.violations(week, placements)


def test_the_receipt_digest_order_and_path_agree() -> None:
    rng = random.Random(7)
    for case in range(0, 1000, 37):
        placements = random_placements(rng, 6)
        assert week_module.ordered(placements) == rules_module.ordered(placements)
        kept = week_module.ordered(placements)
        assert week_module.digest(case, "ab" * 8, "2026-10-21T00:00:00.000000Z", kept) == rules_module.digest(
            case, "ab" * 8, "2026-10-21T00:00:00.000000Z", kept
        )
        assert week_module.receipt_path(case) == rules_module.receipt_path(case)
