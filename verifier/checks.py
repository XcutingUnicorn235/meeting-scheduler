"""Checks shared by the verifiers. Pure functions of their arguments."""

# The most messages one constraint row shows; the verdict lands in the chat's context.
SHOWN = 5


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def constraint(identifier, text, ok, expected=None, actual=None):
    return {"id": identifier, "constraint": text, "ok": ok, "expected": expected, "actual": actual}


def failed(constraints):
    return [item for item in constraints if not item["ok"]]


def shown(messages):
    """At most SHOWN messages, and how many more there are."""
    if len(messages) <= SHOWN:
        return list(messages)
    return list(messages[:SHOWN]) + [f"and {len(messages) - SHOWN} more"]
