"""The plugin's fixed rules, restated here because the verifier may not import the plugin's own code.

The week generator, the schedule rules, the receipt digest and the receipt path must agree with
src/plugin/week.py; tests/test_rules.py checks that they do, on every case. The generator draws only
from SHA-256 streams (hashlib), so the verifier rebuilds each week from its case number alone.
"""

import hashlib
import json
import re

GENERATOR = "meeting-scheduler/1"
CASES = 1000
DAYS = ("mon", "tue", "wed", "thu", "fri")
FIRST_HOUR = 9
END_HOUR = 17
PEOPLE = ("Ana", "Ben", "Cleo", "Dev", "Eve", "Finn", "Gia")
ROOMS = ("oak", "pine", "elm")
MEETINGS = tuple(f"m{index}" for index in range(1, 10))
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
RUN = re.compile(r"^[0-9a-f]{16}$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Stream:
    """Draws from the SHA-256 stream of ``text``."""

    def __init__(self, text):
        self.seed = hashlib.sha256(text.encode("utf-8")).digest()
        self.block = 0
        self.pool = b""

    def below(self, bound):
        if len(self.pool) < 8:
            self.pool += hashlib.sha256(self.seed + self.block.to_bytes(8, "big")).digest()
            self.block += 1
        drawn, self.pool = self.pool[:8], self.pool[8:]
        return int.from_bytes(drawn, "big") % bound

    def between(self, low, high):
        return low + self.below(high - low + 1)

    def sample(self, items, count):
        pool = list(items)
        for index in range(count):
            other = index + self.below(len(pool) - index)
            pool[index], pool[other] = pool[other], pool[index]
        return pool[:count]


def in_range(case):
    return 0 <= case < CASES


def starts(meeting, busy):
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


def fitting(meeting, capacities):
    return [room for room in ROOMS if capacities[room] >= meeting["min_capacity"]]


def option_count(meeting, busy, capacities):
    return sum(len(hours) for hours in starts(meeting, busy).values()) * len(fitting(meeting, capacities))


def generate(case):
    """The week of ``case`` as plain JSON, exactly as get_week shows it."""
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
    busy = {}
    for person in others:
        busy[person] = {}
        for day in DAYS:
            hours = set()
            for _ in range(stream.between(1, 3)):
                length = stream.between(1, 2)
                start = stream.between(FIRST_HOUR, END_HOUR - length)
                hours.update(range(start, start + length))
            busy[person][day] = hours
    free = {day: set() for day in DAYS}
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
    busy[lead] = {day: set(range(FIRST_HOUR, END_HOUR)) - free[day] for day in DAYS}
    shown = {person: {day: sorted(busy[person][day]) for day in DAYS if busy[person][day]} for person in PEOPLE}
    for meeting in meetings:
        if meeting["day"] is not None and not starts(meeting, shown):
            meeting["day"] = None
    order = sorted(range(count), key=lambda index: -option_count(meetings[index], shown, capacities))
    listed = []
    for number_, index in enumerate(order, start=1):
        meeting = {"meeting": f"m{number_}", **meetings[index]}
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


def lead_crunch(week):
    """Whether some person is free for fewer hours than the meetings they attend need in all: then no
    schedule holds every meeting. Every generated week has one (its lead)."""
    for person in PEOPLE:
        needed = sum(meeting["hours"] for meeting in week["meetings"] if person in meeting["attendees"])
        busy = sum(len(hours) for hours in week["busy"].get(person, {}).values())
        if needed > len(DAYS) * (END_HOUR - FIRST_HOUR) - busy:
            return True
    return False


def _span(start, hours):
    return f"from {start} to {start + hours}"


def _hours(hours):
    return ", ".join(str(hour) for hour in sorted(hours))


def violations(week, placements):
    """Every rule the placements break, as (rule id, what is wrong), as src/plugin/week.py finds them."""
    meetings = {meeting["meeting"]: meeting for meeting in week["meetings"]}
    capacities = {room["room"]: room["capacity"] for room in week["rooms"]}
    found = {rule: [] for rule, _ in RULES}
    seen = {}
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


def number(meeting):
    return int(meeting[1:])


def ordered(placements):
    return sorted(
        ({"meeting": p["meeting"], "day": p["day"], "start": p["start"], "room": p["room"]} for p in placements),
        key=lambda p: number(p["meeting"]),
    )


def digest(case, run, saved_at, placements):
    content = {"case": case, "generator": GENERATOR, "run": run, "saved_at": saved_at, "placements": placements}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def receipt_path(case):
    return f"{RECEIPT_DIR}/case-{case}.json"


def plain_placement(placement):
    """A contract Placement as plain JSON."""
    return {
        "meeting": placement.meeting.value,
        "day": placement.day.value,
        "start": placement.start,
        "room": placement.room.value,
    }


def plain_week(week):
    """A contract WeekOutput as plain JSON, in the form generate gives."""
    return {
        "case": week.case,
        "rooms": [{"room": room.room.value, "capacity": room.capacity} for room in week.rooms],
        "meetings": [
            {
                "meeting": meeting.meeting.value,
                "attendees": [person.value for person in meeting.attendees],
                "hours": meeting.hours,
                "min_capacity": meeting.min_capacity,
                "day": None if meeting.day is None else meeting.day.value,
                "open": {day.value: list(hours) for day, hours in meeting.open.items()},
                "rooms": [room.value for room in meeting.rooms],
                "clashes": [other.value for other in meeting.clashes],
            }
            for meeting in week.meetings
        ],
        "busy": {
            person.value: {day.value: list(hours) for day, hours in days.items()} for person, days in week.busy.items()
        },
    }


RECEIPT_KEYS = ("case", "generator", "run", "saved_at", "placements", "scheduled", "digest")
PLACEMENT_KEYS = ("meeting", "day", "start", "room")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def receipt_problem(receipt):
    """What makes ``receipt`` (parsed JSON) not a receipt save_schedule writes, or None."""
    if not isinstance(receipt, dict) or sorted(receipt) != sorted(RECEIPT_KEYS):
        return "it must be a JSON object with exactly " + ", ".join(RECEIPT_KEYS)
    if not _whole(receipt["case"]) or not _whole(receipt["scheduled"]):
        return "its case and scheduled must be whole numbers"
    if not isinstance(receipt["generator"], str):
        return "its generator must be a string"
    if not isinstance(receipt["run"], str) or not RUN.match(receipt["run"]):
        return "its run must be 16 hex digits"
    if not isinstance(receipt["saved_at"], str) or not STAMP.match(receipt["saved_at"]):
        return "its saved_at must be a UTC time as YYYY-MM-DDTHH:MM:SS.ffffffZ"
    if not isinstance(receipt["digest"], str) or not SHA256.match(receipt["digest"]):
        return "its digest must be 64 hex digits"
    if not isinstance(receipt["placements"], list):
        return "its placements must be a list"
    for placement in receipt["placements"]:
        if not isinstance(placement, dict) or sorted(placement) != sorted(PLACEMENT_KEYS):
            return "each placement must be an object with exactly meeting, day, start and room"
        if placement["meeting"] not in MEETINGS or placement["day"] not in DAYS or placement["room"] not in ROOMS:
            return "each placement must name a meeting m1 to m9, a day mon to fri and a room oak, pine or elm"
        if not _whole(placement["start"]):
            return "each placement's start must be a whole hour"
    return None


def read_receipt(workspace, case):
    """(the receipt for ``case`` in ``workspace``, None) or (None, what is wrong with it)."""
    where = receipt_path(case)
    try:
        text = (workspace / where).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None, f"{where} is missing or unreadable"
    try:
        receipt = json.loads(text)
    except ValueError:
        return None, f"{where} is not JSON"
    problem = receipt_problem(receipt)
    if problem:
        return None, f"{where} is not a save_schedule receipt: {problem}"
    return receipt, None
