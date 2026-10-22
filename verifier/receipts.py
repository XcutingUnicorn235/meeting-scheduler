"""The receipt save_schedule wrote: where it is, that it is whole, and that a summary matches it."""

from pathlib import Path

from . import rules
from .checks import constraint, shown


def receipt_rows(case, summary, workspace):
    """(constraint rows, the receipt or None): ``summary`` (a contract SavedOutput) names the case's receipt
    in ``workspace``, the receipt is a well-formed save_schedule receipt for the case, its digest is its
    content's, and the summary gives its digest and count. Rows stop at the first that fails."""
    rows = []
    expected = rules.receipt_path(case)

    def add(identifier, text, ok, wanted=None, actual=None):
        rows.append(constraint(identifier, text, ok, wanted, actual))
        return ok

    if not add("output-case", "The output is for the task's week", summary.case == case, case, summary.case):
        return rows, None
    if not add(
        "receipt-path",
        "The output names the week's receipt, meeting-scheduler/case-<case>.json",
        summary.receipt == expected,
        expected,
        summary.receipt,
    ):
        return rows, None
    receipt, problem = rules.read_receipt(Path(workspace), case)
    if not add("receipt-file", "The receipt exists and is a save_schedule receipt", receipt is not None, None, problem):
        return rows, None
    if not add(
        "receipt-case",
        "The receipt is for the task's week, made by the pinned generator",
        receipt["case"] == case and receipt["generator"] == rules.GENERATOR,
        [case, rules.GENERATOR],
        [receipt["case"], receipt["generator"]],
    ):
        return rows, None
    content = rules.digest(case, receipt["run"], receipt["saved_at"], receipt["placements"])
    if not add(
        "receipt-intact",
        "The receipt's digest is its content's and its count is its placements'",
        content == receipt["digest"] and receipt["scheduled"] == len(receipt["placements"]),
        [content, len(receipt["placements"])],
        [receipt["digest"], receipt["scheduled"]],
    ):
        return rows, None
    add(
        "output-matches-receipt",
        "The output gives the receipt's digest and count",
        summary.digest == receipt["digest"] and summary.scheduled == receipt["scheduled"],
        [receipt["digest"], receipt["scheduled"]],
        [summary.digest, summary.scheduled],
    )
    return rows, receipt


def rule_rows(week, placements):
    """One row per schedule rule, each listing what breaks it."""
    broken = rules.violations(week, placements)
    rows = []
    for rule, text in rules.RULES:
        found = [message for which, message in broken if which == rule]
        rows.append(constraint(rule, text, not found, [], shown(found)))
    return rows
