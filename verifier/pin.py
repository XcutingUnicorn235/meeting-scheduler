"""pin_optimum: the answer key must be for the task's week and hold together."""

from . import rules
from .checks import constraint, failed, result


def key_constraints(case, key):
    """The answer key's own checks: the case, the generator, the shape of the optimum, and its schedule
    keeping every rule of the week rebuilt here. That no schedule holds more rests on the exhaustive search;
    a submission holding more is refused by the task's within-best check."""
    if not rules.in_range(case):
        return [constraint("task-case", "The task's case is from 0 to 999", False, "0 to 999", case)]
    if key is None:
        return [constraint("answer-key", "The task has an answer key", False, "pinned", "missing")]
    week = rules.generate(case)
    meetings = len(week["meetings"])
    schedule = [rules.plain_placement(placement) for placement in key.schedule]
    broken = [f"{rule}: {text}" for rule, text in rules.violations(week, schedule)]
    return [
        constraint("key-case", "The answer key is for the task's week", key.case == case, case, key.case),
        constraint(
            "key-generator",
            "The answer key was made by the pinned generator",
            key.generator == rules.GENERATOR,
            rules.GENERATOR,
            key.generator,
        ),
        constraint(
            "key-meetings",
            "The answer key counts the week's meetings",
            key.meetings == meetings,
            meetings,
            key.meetings,
        ),
        constraint(
            "key-best",
            "The optimum holds at least one meeting and fewer than all of them",
            1 <= key.best < meetings,
            f"1 to {meetings - 1}",
            key.best,
        ),
        constraint("key-worst", "The worst schedule holds no meeting", key.worst == 0, 0, key.worst),
        constraint(
            "key-schedule",
            "The answer key's schedule holds best meetings and keeps every rule",
            len(schedule) == key.best and not broken,
            key.best,
            broken[:3] if broken else len(schedule),
        ),
        constraint(
            "key-pinned",
            "The answer key says when it was pinned and which earlier runs it found",
            bool(rules.STAMP.match(key.pinned_at)) and all(rules.RUN.match(run) for run in key.prior_runs),
        ),
    ]


def verify_input(value):
    if not rules.in_range(value.case):
        return result(False, f"case must be from 0 to {rules.CASES - 1}, not {value.case}")
    return result(True, "the case exists")


def verify_output(input_value, output_value, workspace):
    problems = failed(key_constraints(input_value.case, output_value))
    if problems:
        return result(False, problems[0]["constraint"] + ": it does not hold", constraints=problems)
    return result(True, f"answer key for case {input_value.case} is pinned: best {output_value.best}")
