"""The exact optimum: the most meetings a schedule keeping every rule can hold, by branch and bound.

Each meeting's options are the (day, start, room) it could have on its own: every attendee free, its
fixed day, its hours inside 9 to 17, a room big enough. An option takes a set of cells, one per hour for
its room and for each attendee; two options clash exactly when their cells meet, so the cells are bits of
one integer and a clash is a nonzero AND.

The search places one meeting at a time. At each node it keeps, for every meeting not yet decided, the
options that clash with nothing placed so far; a meeting with none left cannot be held. It branches on
the undecided meeting with the fewest options left (each option, then leaving it out), and prunes a node
when the meetings placed plus the undecided ones that still have an option cannot beat the best found.
The bound never cuts off a better schedule, so the search is exhaustive: what it returns is the optimum.
"""

from __future__ import annotations

from plugin.week import DAYS, FIRST_HOUR, PEOPLE, ROOMS, number

HOURS = 8  # hour-slots in a day, 9 to 17


def _bit(resource: int, day: str, hour: int) -> int:
    return 1 << ((resource * len(DAYS) + DAYS.index(day)) * HOURS + hour - FIRST_HOUR)


def options(week: dict) -> list[list[tuple[dict, int]]]:
    """Each meeting's options, in the order the week lists its meetings: (placement, cells) in day, start
    and room order."""
    out = []
    for meeting in week["meetings"]:
        found = []
        for day, starts in meeting["open"].items():
            for start in starts:
                for room in meeting["rooms"]:
                    cells = 0
                    for hour in range(start, start + meeting["hours"]):
                        cells |= _bit(ROOMS.index(room), day, hour)
                        for person in meeting["attendees"]:
                            cells |= _bit(len(ROOMS) + PEOPLE.index(person), day, hour)
                    placement = {"meeting": meeting["meeting"], "day": day, "start": start, "room": room}
                    found.append((placement, cells))
        out.append(found)
    return out


def solve(week: dict) -> tuple[int, list[dict], int]:
    """The most meetings any schedule can hold, one schedule holding them (in meeting order) and the number
    of search nodes visited."""
    choices = options(week)
    total = len(choices)
    best: dict = {"count": 0, "schedule": []}
    nodes = 0

    def search(undecided: list[int], taken: int, chosen: list[dict]) -> None:
        nonlocal nodes
        nodes += 1
        live = {index: [option for option in choices[index] if not option[1] & taken] for index in undecided}
        alive = [index for index in undecided if live[index]]
        if len(chosen) + len(alive) <= best["count"]:
            return
        if not alive:
            best["count"], best["schedule"] = len(chosen), list(chosen)
            return
        branch = min(alive, key=lambda index: (len(live[index]), index))
        rest = [index for index in alive if index != branch]
        for placement, cells in live[branch]:
            chosen.append(placement)
            search(rest, taken | cells, chosen)
            chosen.pop()
            if best["count"] == total:
                return
        search(rest, taken, chosen)

    search(list(range(total)), 0, [])
    schedule = sorted(best["schedule"], key=lambda placement: number(placement["meeting"]))
    return best["count"], schedule, nodes
