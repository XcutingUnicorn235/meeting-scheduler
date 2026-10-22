"""The weeks: built from the case number alone by a seeded generator, and the rules a schedule must keep.

Every draw comes from a SHA-256 stream: the seed is SHA-256 of "meeting-scheduler:<case>", block j of
the stream is SHA-256 of the seed followed by j as 8 big-endian bytes, and each draw takes the next 8
bytes as a big-endian number, modulo the range. No other randomness is used, so a case is the same
week on every machine and the verifier, which may not import this file, rebuilds it with its own copy
(verifier/rules.py; tests/test_rules.py checks that both agree on every case).

A week (generator meeting-scheduler/1) has 7 to 9 meetings, three rooms and seven people. One person,
the lead, attends 4 or 5 of the meetings and is free for one hour less than those meetings need in
all, so at least one meeting can never be held: no week can hold every meeting. The meetings are
listed with the most flexible first (the most open start hours and rooms), which is the order a
first-come schedule handles worst.
"""

from __future__ import annotations

import hashlib
import json

GENERATOR = "meeting-scheduler/1"
CASES = 1000
DAYS = ("mon", "tue", "wed", "thu", "fri")
FIRST_HOUR = 9
END_HOUR = 17
PEOPLE = ("Ana", "Ben", "Cleo", "Dev", "Eve", "Finn", "Gia")
ROOMS = ("oak", "pine", "elm")
RULES = (
    ("known-meeting", "Every placement names a meeting of this week"),
    ("once", "Each meeting is placed at most once"),
    ("working-hours", "Each meeting starts at 9 or later and ends by 17"),
    ("fixed-day", "A meeting with a day is held on that day"),
    ("room-capacity", "Each meeting's room holds at least its min_capacity"),
    ("attendees-free", "Every attendee is free for every hour of the meeting"),
    ("attendee-overlap", "No two meetings that share an attendee overlap"),
    ("room-overlap", "No two meetings in the same room overlap"),
)
RECEIPT_DIR = "meeting-scheduler"


class Stream:
    """Draws from the SHA-256 stream of ``text``."""

    def __init__(self, text: str) -> None:
        self.seed = hashlib.sha256(text.encode("utf-8")).digest()
        self.block = 0
        self.pool = b""

    def below(self, bound: int) -> int:
        """A number from 0 to bound - 1."""
        if len(self.pool) < 8:
            self.pool += hashlib.sha256(self.seed + self.block.to_bytes(8, "big")).digest()
            self.block += 1
        drawn, self.pool = self.pool[:8], self.pool[8:]
        return int.from_bytes(drawn, "big") % bound

    def between(self, low: int, high: int) -> int:
        """A number from low to high, both included."""
        return low + self.below(high - low + 1)

    def sample(self, items, count: int) -> list:
        """``count`` distinct items, by a partial Fisher-Yates shuffle."""
        pool = list(items)
        for index in range(count):
            other = index + self.below(len(pool) - index)
            pool[index], pool[other] = pool[other], pool[index]
        return pool[:count]


def in_range(case: int) -> bool:
    return 0 <= case < CASES


def starts(meeting: dict, busy: dict) -> dict[str, list[int]]:
    """Each allowed day's start hours at which every attendee is free for all the meeting's hours and it
    ends by END_HOUR; days with none left out."""
    out = {}
    for day in DAYS:
        if meeting["day"] is not None and meeting["day"] != day:
            continue
        hours = [
            start
            for start in range(FIRST_HOUR, END_HOUR - meeting["hours"] + 1)
            if not any(
                hour in busy[person].get(day, [])
                for person in meeting["attendees"]
                for hour in range(start, start + meeting["hours"])
            )
        ]
        if hours:
            out[day] = hours
    return out


def fitting(meeting: dict, capacities: dict[str, int]) -> list[str]:
    return [room for room in ROOMS if capacities[room] >= meeting["min_capacity"]]


def option_count(meeting: dict, busy: dict, capacities: dict[str, int]) -> int:
    return sum(len(hours) for hours in starts(meeting, busy).values()) * len(fitting(meeting, capacities))


def generate(case: int) -> dict:
    """The week of ``case``, as plain JSON: what get_week shows, before it is typed."""
    if not in_range(case):
        raise ValueError(f"case must be from 0 to {CASES - 1}, not {case}")
    stream = Stream(f"meeting-scheduler:{case}")
    count = stream.between(7, 9)
    capacities = {"oak": stream.between(3, 4), "pine": stream.between(5, 6), "elm": 8 + 2 * stream.below(2)}
    lead = PEOPLE[stream.below(len(PEOPLE))]
    others = [person for person in PEOPLE if person != lead]
    led = set(stream.sample(range(count), stream.between(4, 5)))
    meetings = []
    for index in range(count):
        size = stream.between(2, 4)
        attendees = stream.sample(others, size - 1) + [lead] if index in led else stream.sample(others, size)
        hours = 2 if stream.below(10) < 4 else 1
        need = len(attendees) + stream.below(2)
        if stream.below(10) < 2:
            need += 3
        day = None
        if stream.below(10) < 4:
            day = DAYS[stream.below(len(DAYS))]
        meetings.append(
            {
                "attendees": sorted(attendees, key=PEOPLE.index),
                "hours": hours,
                "min_capacity": min(need, capacities["elm"]),
                "day": day,
            }
        )
    busy: dict[str, dict[str, set[int]]] = {}
    for person in others:
        busy[person] = {}
        for day in DAYS:
            hours = set()
            for _ in range(stream.between(1, 3)):
                length = stream.between(1, 2)
                start = stream.between(FIRST_HOUR, END_HOUR - length)
                hours.update(range(start, start + length))
            busy[person][day] = hours
    # The lead is free one hour less than the lead's meetings need, in blocks of 2 hours (and one of 1 when
    # the total is odd) that never touch; most of the others are freed for each block.
    free: dict[str, set[int]] = {day: set() for day in DAYS}
    left = sum(meetings[index]["hours"] for index in led) - 1
    for _ in range(1000):
        if left == 0:
            break
        length = min(2, left)
        day = DAYS[stream.below(len(DAYS))]
        start = stream.between(FIRST_HOUR, END_HOUR - length)
        block = set(range(start, start + length))
        if block & free[day] or start - 1 in free[day] or start + length in free[day]:
            continue
        free[day] |= block
        left -= length
        for person in others:
            if stream.below(10) < 8:
                busy[person][day] -= block
    if left:
        raise RuntimeError(f"case {case}: the lead's free hours do not fit the week")
    busy[lead] = {day: set(range(FIRST_HOUR, END_HOUR)) - free[day] for day in DAYS}
    shown = {person: {day: sorted(busy[person][day]) for day in DAYS if busy[person][day]} for person in PEOPLE}
    # A day no attendee set can meet on is dropped; then the most flexible meetings are listed first.
    for meeting in meetings:
        if meeting["day"] is not None and not starts(meeting, shown):
            meeting["day"] = None
    order = sorted(range(count), key=lambda index: -option_count(meetings[index], shown, capacities))
    listed = []
    for number, index in enumerate(order, start=1):
        meeting = {"meeting": f"m{number}", **meetings[index]}
        meeting["open"] = starts(meeting, shown)
        meeting["rooms"] = fitting(meeting, capacities)
        listed.append(meeting)
    for meeting in listed:
        meeting["clashes"] = [
            other["meeting"]
            for other in listed
            if other is not meeting and set(other["attendees"]) & set(meeting["attendees"])
        ]
    return {
        "case": case,
        "rooms": [{"room": room, "capacity": capacities[room]} for room in ROOMS],
        "meetings": listed,
        "busy": shown,
    }


def _span(start: int, hours: int) -> str:
    return f"from {start} to {start + hours}"


def _hours(hours) -> str:
    return ", ".join(str(hour) for hour in sorted(hours))


def violations(week: dict, placements: list[dict]) -> list[tuple[str, str]]:
    """Every rule the placements break, as (rule id, what is wrong), in RULES order then placement order.

    ``placements`` are plain {meeting, day, start, room}. A meeting placed more than once is judged by its
    first placement for every later rule; a placement naming no meeting of the week is judged by no other.
    """
    meetings = {meeting["meeting"]: meeting for meeting in week["meetings"]}
    capacities = {room["room"]: room["capacity"] for room in week["rooms"]}
    found: dict[str, list[str]] = {rule: [] for rule, _ in RULES}
    seen: dict[str, int] = {}
    kept = []
    for placement in placements:
        name = placement["meeting"]
        if name not in meetings:
            found["known-meeting"].append(f"{name} is not a meeting of this week")
            continue
        seen[name] = seen.get(name, 0) + 1
        if seen[name] == 2:
            found["once"].append(f"{name} is placed {sum(p['meeting'] == name for p in placements)} times")
        if seen[name] == 1:
            kept.append(placement)
    for placement in kept:
        name, day, start, room = placement["meeting"], placement["day"], placement["start"], placement["room"]
        meeting = meetings[name]
        hours = meeting["hours"]
        if start < FIRST_HOUR:
            found["working-hours"].append(f"{name} starts at {start}: the day runs from 9 to 17")
        elif start + hours > END_HOUR:
            found["working-hours"].append(
                f"{name} runs {hours}h: starting at {start} it ends at {start + hours}, after 17"
            )
        if meeting["day"] is not None and day != meeting["day"]:
            found["fixed-day"].append(f"{name} must be on {meeting['day']}, not {day}")
        if capacities[room] < meeting["min_capacity"]:
            found["room-capacity"].append(
                f"{name} needs a room for {meeting['min_capacity']}; {room} holds {capacities[room]}"
            )
        taken = set(range(start, start + hours))
        busy = [
            f"{person} is busy at {_hours(taken & set(week['busy'].get(person, {}).get(day, [])))}"
            for person in meeting["attendees"]
            if taken & set(week["busy"].get(person, {}).get(day, []))
        ]
        if busy:
            found["attendees-free"].append(f"{name} on {day} {_span(start, hours)}: " + "; ".join(busy))
    for first, one in enumerate(kept):
        for two in kept[first + 1 :]:
            if one["day"] != two["day"]:
                continue
            a, b = meetings[one["meeting"]], meetings[two["meeting"]]
            common = set(range(one["start"], one["start"] + a["hours"])) & set(
                range(two["start"], two["start"] + b["hours"])
            )
            if not common:
                continue
            shared = [person for person in a["attendees"] if person in b["attendees"]]
            where = f"on {one['day']} at {_hours(common)}"
            if shared:
                found["attendee-overlap"].append(
                    f"{one['meeting']} and {two['meeting']} overlap {where} and share {', '.join(shared)}"
                )
            if one["room"] == two["room"]:
                found["room-overlap"].append(f"{one['meeting']} and {two['meeting']} are both in {one['room']} {where}")
    return [(rule, text) for rule, _ in RULES for text in found[rule]]


def number(meeting: str) -> int:
    return int(meeting[1:])


def ordered(placements: list[dict]) -> list[dict]:
    """The placements as a receipt keeps them: plain, in meeting order."""
    return sorted(
        ({"meeting": p["meeting"], "day": p["day"], "start": p["start"], "room": p["room"]} for p in placements),
        key=lambda p: number(p["meeting"]),
    )


def digest(case: int, run: str, saved_at: str, placements: list[dict]) -> str:
    """SHA-256 of a receipt's content: its case, generator, run, time and placements, as compact sorted JSON."""
    content = {"case": case, "generator": GENERATOR, "run": run, "saved_at": saved_at, "placements": placements}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def receipt_path(case: int) -> str:
    return f"{RECEIPT_DIR}/case-{case}.json"
