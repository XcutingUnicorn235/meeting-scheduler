"""get_week: what the model is shown must be the case's week exactly as the generator builds it."""

from . import rules
from .checks import result


def verify_input(value):
    if not rules.in_range(value.case):
        return result(False, f"case must be from 0 to {rules.CASES - 1}, not {value.case}")
    return result(True, "the case exists")


def verify_output(input_value, output_value, workspace):
    if output_value.case != input_value.case:
        return result(False, f"showed case {output_value.case}, not the asked {input_value.case}")
    if rules.plain_week(output_value) != rules.generate(input_value.case):
        return result(False, f"the week shown is not case {input_value.case} as the generator builds it")
    return result(True, f"case {input_value.case}: the generator's week")
