"""save_schedule: the receipt it wrote must hold exactly the placements it was given, and they must keep
every rule of the week rebuilt here."""

from . import rules
from .checks import failed, result
from .receipts import receipt_rows, rule_rows


def verify_input(value):
    if not rules.in_range(value.case):
        return result(False, f"case must be from 0 to {rules.CASES - 1}, not {value.case}")
    return result(True, "the case exists")


def verify_output(input_value, output_value, workspace):
    rows, receipt = receipt_rows(input_value.case, output_value, workspace)
    problems = failed(rows)
    if problems:
        return result(False, problems[0]["constraint"] + ": it does not hold", constraints=problems)
    given = rules.ordered([rules.plain_placement(placement) for placement in input_value.placements])
    if receipt["placements"] != given:
        return result(False, "the receipt does not hold the placements save_schedule was given")
    problems = failed(rule_rows(rules.generate(input_value.case), receipt["placements"]))
    if problems:
        return result(False, problems[0]["constraint"] + ": it does not hold", constraints=problems)
    return result(True, f"case {input_value.case}: {receipt['scheduled']} meetings saved, every rule kept")
