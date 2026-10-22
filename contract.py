"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    GET_WEEK = "get_week"
    SAVE_SCHEDULE = "save_schedule"
    PIN_OPTIMUM = "pin_optimum"


class Task(Enum):
    SCHEDULE_WEEK = "schedule-week"


class Day(Enum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"


class Room(Enum):
    OAK = "oak"
    PINE = "pine"
    ELM = "elm"


class Person(Enum):
    ANA = "Ana"
    BEN = "Ben"
    CLEO = "Cleo"
    DEV = "Dev"
    EVE = "Eve"
    FINN = "Finn"
    GIA = "Gia"


class Meeting(Enum):
    M1 = "m1"
    M2 = "m2"
    M3 = "m3"
    M4 = "m4"
    M5 = "m5"
    M6 = "m6"
    M7 = "m7"
    M8 = "m8"
    M9 = "m9"


CASE = "Which week to schedule, from 0 to 999; every number is a fixed week"
MEETING = "The meeting, m1 to m9"
START = "The hour it starts, from 9; it runs its hours and must end by 17"
RECEIPT = "The receipt save_schedule wrote, relative to the workspace: meeting-scheduler/case-<case>.json"
DIGEST = "SHA-256 of the saved schedule, as save_schedule gives it"
SCHEDULED = "How many meetings the saved schedule holds"


@dataclass
class CaseInput(Output):
    case: Annotated[int, CASE]


@dataclass
class RoomInfo(Output):
    room: Annotated[Room, "The room"]
    capacity: Annotated[int, "How many people it holds"]


@dataclass
class MeetingInfo(Output):
    meeting: Annotated[Meeting, MEETING]
    attendees: Annotated[list[Person], "Everyone who must attend"]
    hours: Annotated[int, "How long it runs: 1 or 2 whole hours"]
    min_capacity: Annotated[int, "The room must hold at least this many people"]
    day: Annotated[Day | None, "The day it must be held on, or null for any day"]
    open: Annotated[
        dict[Day, list[int]],
        "Each allowed day's start hours at which every attendee is free for all its hours and it ends by 17; "
        "a day not listed has none",
    ]
    rooms: Annotated[list[Room], "The rooms that hold at least min_capacity"]
    clashes: Annotated[list[Meeting], "The other meetings that share an attendee with it: none of them may overlap it"]


@dataclass
class WeekOutput(Output):
    case: Annotated[int, "The week's number, as asked"]
    rooms: Annotated[list[RoomInfo], "The three rooms, smallest first"]
    meetings: Annotated[list[MeetingInfo], "The week's 7 to 9 meetings, m1 first"]
    busy: Annotated[
        dict[Person, dict[Day, list[int]]],
        "Each person's busy hours by day: hour h is h:00 to h+1:00; a day not listed is free all day (9 to 17)",
    ]


@dataclass
class Placement(Output):
    meeting: Annotated[Meeting, MEETING]
    day: Annotated[Day, "The day it is held"]
    start: Annotated[int, START]
    room: Annotated[Room, "The room it is held in"]


@dataclass
class SaveInput(Output):
    case: Annotated[int, CASE]
    placements: Annotated[list[Placement], "The meetings held, each at most once; a meeting left out is not held"]


@dataclass
class SavedOutput(Output):
    case: Annotated[int, "The week's number"]
    receipt: Annotated[str, RECEIPT]
    digest: Annotated[str, DIGEST]
    scheduled: Annotated[int, SCHEDULED]


@dataclass
class PinOutput(Output):
    case: Annotated[int, "The week's number, as asked"]
    generator: Annotated[str, "The version of the generator that built the week"]
    meetings: Annotated[int, "How many meetings the week has"]
    best: Annotated[int, "The most meetings any schedule that keeps every rule can hold, found by exhaustive search"]
    worst: Annotated[int, "The fewest such a schedule can hold: 0, since holding no meeting keeps every rule"]
    schedule: Annotated[list[Placement], "One schedule holding best meetings, m1 first"]
    pinned_at: Annotated[str, "When the key was pinned, UTC, as YYYY-MM-DDTHH:MM:SS.ffffffZ"]
    prior_runs: Annotated[list[str], "The run of a receipt for this week already in the workspace when it was pinned"]


TOOLS = {
    Tool.GET_WEEK: (CaseInput, WeekOutput),
    Tool.SAVE_SCHEDULE: (SaveInput, SavedOutput),
    Tool.PIN_OPTIMUM: (CaseInput, PinOutput),
}
TASKS = {Task.SCHEDULE_WEEK: (CaseInput, SavedOutput)}
