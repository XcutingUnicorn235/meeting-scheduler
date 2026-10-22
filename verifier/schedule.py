"""schedule-week: the saved schedule, judged from the week rebuilt here and the pinned optimum.

Gates come first: the answer key, then the receipt (this run's, whole, matching the output), then every
schedule rule, re-checked on the week this module rebuilds from the case number; it never trusts
save_schedule's own check. Any failure scores 0. A schedule that keeps every rule scores scheduled / best,
the share of the most meetings any schedule can hold (the worst, holding none, is 0); it is valid only at
the best. Any schedule at the best scores 1.0, whichever meetings it leaves out and wherever it puts the
others.
"""

from . import rules
from .checks import constraint, failed, result
from .pin import key_constraints
from .receipts import receipt_rows, rule_rows


def this_run(receipt, reference):
    """The receipt was saved by this task: not by a run the answer key found in the workspace, and not
    before the answer key was pinned (which NanoAgent does before the agent starts)."""
    earlier = receipt["run"] in reference.prior_runs
    before = receipt["saved_at"] < reference.pinned_at
    problem = None
    if earlier:
        problem = f"run {receipt['run']} saved it before this task began: save this task's schedule"
    elif before:
        problem = f"saved at {receipt['saved_at']}, before this task's key was pinned at {reference.pinned_at}"
    return constraint(
        "this-run",
        "The receipt was saved during this task",
        problem is None,
        f"at or after {reference.pinned_at}",
        problem,
    )


def verify_task(arguments, output, reference, workspace):
    case = arguments.case
    gates = key_constraints(case, reference)
    broken = failed(gates)
    if broken:
        return result(False, broken[0]["constraint"] + ": it does not hold", score=0.0, constraints=gates)

    rows, receipt = receipt_rows(case, output, workspace)
    if receipt is not None:
        rows.insert(4, this_run(receipt, reference))
    gates += rows
    broken = failed(gates)
    if broken:
        return result(False, broken[0]["constraint"] + ": it does not hold", score=0.0, constraints=gates)

    week = rules.generate(case)
    placements = receipt["placements"]
    gates += rule_rows(week, placements)
    broken = failed(gates)
    if broken:
        return result(
            False,
            f"the schedule breaks a rule ({broken[0]['id']}): {broken[0]['actual'][0]}",
            score=0.0,
            constraints=gates,
        )

    scheduled, best = len(placements), reference.best
    held = {placement["meeting"] for placement in placements}
    left_out = [meeting["meeting"] for meeting in week["meetings"] if meeting["meeting"] not in held]
    optimum = [rules.plain_placement(placement) for placement in reference.schedule]
    within = scheduled <= best
    gates.append(
        constraint(
            "within-best",
            "The schedule holds no more meetings than the pinned optimum (more means the key is wrong)",
            within,
            f"at most {best}",
            scheduled,
        )
    )
    if not within:
        return result(
            False,
            "the schedule holds more meetings than the pinned optimum: the key is wrong",
            score=0.0,
            constraints=gates,
        )
    gates.append(
        constraint(
            "most-meetings", "The schedule holds the most meetings any schedule can", scheduled == best, best, scheduled
        )
    )
    meetings = len(week["meetings"])
    if scheduled == best:
        message = f"every rule kept; {scheduled} of {meetings} meetings held, the most possible"
    else:
        message = f"every rule kept; {scheduled} of {meetings} meetings held, {best} were possible"
    return result(
        scheduled == best,
        message,
        score=round(scheduled / best, 4),
        constraints=gates,
        scheduled=scheduled,
        best=best,
        meetings=meetings,
        left_out=left_out,
        optimum=optimum,
    )
