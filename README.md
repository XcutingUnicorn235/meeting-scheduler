# Meeting Scheduler

A `nanoagent.plugin/v0001` plugin. A model reads a team's week (meetings,
rooms and everyone's busy hours) and schedules as many of the meetings as the
rules allow. Not every meeting fits, so it has to choose which to leave out and
where to put the rest. A deterministic verifier rebuilds the week from its
number, re-checks every rule and compares the count with the optimum, found by
exhaustive search out of the model's sight.

## Tools

| Tool | Does | Code |
|---|---|---|
| `get_week` | Shows a week: its three rooms, its 7 to 9 meetings (attendees, hours, minimum room size, fixed day, the start hours open to every attendee, the rooms big enough, the meetings sharing an attendee) and everyone's busy hours | `src/plugin/tools.py`, `src/plugin/week.py` |
| `save_schedule` | Checks a schedule against every rule; refuses it with each broken rule listed and saves nothing, or writes a receipt to `meeting-scheduler/case-<case>.json` in the workspace and returns its summary | `src/plugin/tools.py`, `src/plugin/week.py` |
| `pin_optimum` | Finds the most meetings any schedule can hold, by branch and bound, with one such schedule; the task's reference, run out of the model's sight | `src/plugin/tools.py`, `src/plugin/solve.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `schedule-week` | Schedules as many of a week's meetings as possible | `agent`, with `get_week` and `save_schedule`; reference `pin_optimum` |

The input is a case number from 0 to 999. The agent reads the week, chooses
the placements `{meeting, day, start, room}`, saves them (and, if refused,
fixes the listed placements and saves again), and submits the summary
`save_schedule` returned: `{case, receipt, digest, scheduled}`. A whole task is
3 or 4 tool calls and `submit`, within the 6 model requests the deployment
allows.

The tools compute every rule (who is free when, which rooms are big enough,
which meetings share someone) and refuse any schedule that breaks one. What is
left to the model is the choice no single rule makes: which meetings to give
up and how to fit the rest around each other.

### The weeks

Every week is built from its case number alone. The seed is SHA-256 of
`meeting-scheduler:<case>`; block *j* of the stream is SHA-256 of the seed
followed by *j* as 8 big-endian bytes, and each draw takes the next 8 bytes as
a big-endian number modulo its range. Nothing else is random, so a case is the
same week on every machine. The generator's version, `meeting-scheduler/1`, is
pinned in the answer key, and `tests/test_week.py` pins the SHA-256 of weeks 0
to 9.

A week has 5 days of 8 hour-slots (9:00 to 17:00), three rooms (oak holds 3 or
4 people, pine 5 or 6, elm 8 or 10) and seven people. Each meeting has 2 to 4
attendees, runs 1 or 2 hours (2 in 40% of meetings), needs a room for at least
its attendees (more in some), and in 40% of meetings is fixed to one day (a
fixed day on which its attendees can never meet together is dropped). Each
person other than the lead is busy in 1 to 3 blocks of 1 or 2 hours a day.

One person, the lead, attends 4 or 5 of the meetings and is free for exactly
one hour less than those meetings need in all, in blocks of 2 hours (and one of
1) that never touch; most of the others are freed during those blocks. So no
schedule can hold every meeting: at the optimum 1 meeting is left out in 852
of the 1,000 weeks, 2 in 134, 3 in 13 and 4 in 1. The meetings are listed with
the most flexible first (the most open start hours times rooms): the order in
which taking meetings first come, first placed does worst.

### The rules

A placement is `{meeting, day, start, room}`. `save_schedule` and the verifier
check exactly these, each with an id:

| Id | Rule |
|---|---|
| `known-meeting` | Every placement names a meeting of this week |
| `once` | Each meeting is placed at most once (a meeting left out is not held) |
| `working-hours` | Each meeting starts at 9 or later and ends by 17 |
| `fixed-day` | A meeting with a day is held on that day |
| `room-capacity` | Each meeting's room holds at least its `min_capacity` |
| `attendees-free` | Every attendee is free for every hour of the meeting |
| `attendee-overlap` | No two meetings that share an attendee overlap |
| `room-overlap` | No two meetings in the same room overlap |

Two meetings overlap when they are on the same day and have an hour in common.
A refusal lists every broken rule with the meetings, hours, people and rooms
involved, for example `attendee-overlap: m6 and m7 overlap on fri at 14 and
share Cleo, Gia`.

### The answer key

`pin_optimum` runs a branch and bound over each meeting's options, the
(day, start, room) it could have on its own. An option takes one cell per hour
for its room and for each attendee, kept as bits of one integer, so two options
clash exactly when their cells meet. The search branches on the undecided
meeting with the fewest options left (each option, then leaving it out) and
prunes a node when the meetings placed plus the undecided ones that still have
an option cannot beat the best found; that bound never cuts off a better
schedule, so the result is the optimum. Over all 1,000 weeks it takes 1.9 ms on
average and 0.14 s at most (50,967 nodes), far inside the 180 s tool timeout.
`tests/test_solve.py` checks it against a slow search that tries every set of
meetings, on 40 weeks.

The key holds the case, the generator version, the number of meetings, `best`,
`worst` (0: holding no meeting keeps every rule), one optimal schedule, when it
was pinned, and the run of any receipt for the week already in the workspace.

### What the verifier checks

`verifier/schedule.py` builds a table of constraints, in order. Any failure
before `most-meetings` scores 0:

| Id | Constraint |
|---|---|
| `task-case`, `answer-key` | The task's case is from 0 to 999 and it has an answer key |
| `key-case`, `key-generator`, `key-meetings` | The key is for the task's week, from the pinned generator, and counts its meetings |
| `key-best`, `key-worst` | 1 ≤ best < meetings, and worst is 0 |
| `key-schedule` | The key's schedule holds best meetings and keeps every rule of the week rebuilt in the verifier |
| `key-pinned` | The key says when it was pinned and which earlier runs it found |
| `output-case`, `receipt-path` | The output is for the task's week and names its receipt |
| `receipt-file`, `receipt-case` | The receipt exists, is well formed, and is for the task's week and generator |
| `this-run` | The receipt was saved during this task: not by a run the key found in the workspace, and not before the key was pinned |
| `receipt-intact` | The receipt's digest is its content's and its count is its placements' |
| `output-matches-receipt` | The output gives the receipt's digest and count |
| the eight rules | Each rule above, re-checked on the week the verifier rebuilds from the case number |
| `within-best` | The schedule holds no more meetings than the key's best (more means the key is wrong) |
| `most-meetings` | The schedule holds the most meetings any schedule can |

The score is the meeting-suggestion formula (v − worst) / (best − worst) with
worst = 0: scheduled / best. The verdict is valid only at the best. Every
optimal schedule scores 1.0, whichever meetings it leaves out and wherever it
puts the others; the tests save optima other than the key's (different times,
and different meetings left out) and check they all score 1.0.

The verifier never trusts the tools. It rebuilds the week with its own copy of
the generator (`verifier/rules.py`, `hashlib` only), re-checks every rule on
the receipt's placements, and recomputes the receipt's digest.
`tests/test_rules.py` checks that both copies of the generator agree on all
1,000 weeks and both copies of the rules on 3,000 random schedules.

The tool checks (`verifier/week.py`, `verifier/save.py`, `verifier/pin.py`)
refuse a case out of range, a shown week that is not the generator's, a receipt
that does not hold exactly the saved placements or breaks a rule, and an answer
key that breaks any key constraint above.

### Baselines

Over all 1,000 weeks (`scheduled / best`, and the share scored valid):

| Agent | Mean score | Valid |
|---|---|---|
| Empty schedule | 0.000 | 0% |
| Every meeting on Monday at 9 in elm | 0.000 | 0% |
| Random placements | 0.004 | 0% |
| First come, in the listed order | 0.918 | 51.7% |
| First come, fewest attendees first | 0.933 | 59.3% |
| First come, fewest options first | 0.970 | 81.6% |
| The key's schedule | 1.000 | 100% |

Breaking any rule scores 0, so placing meetings without checking them earns
nothing. The first-come schedulers keep every rule but leave out one meeting
too many on 18% to 48% of the weeks. A verifier that compared the schedule with
the key's would refuse the other optima; one that believed the submitted count
would give a made-up summary full marks (`tests/test_baselines.py`).

### Limits

- Because an empty schedule is valid, worst is 0 and a schedule one meeting
  short still scores 0.67 to 0.88. Validity (the optimum) is the sharper
  measure; partial scores are close together.
- A run's receipt is told apart from an earlier task's by its run token and by
  time: it must be saved no earlier than the key was pinned, by the same
  machine's clock. On Windows with Python 3.12 that clock ticks every 16 ms,
  so a receipt saved within 16 ms before the pin would pass; a real earlier
  task is seconds or more before.
- The generator is synthetic: one person is deliberately overbooked so the
  week can never hold every meeting. Real calendars are messier.
- The optimum is found by exhaustive search; the verifier checks that the key
  holds together and that no submission beats it, but it does not repeat the
  search.

## Layout

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network, workspace writes), tools, the schedule-week task
├── contract.py      # typed inputs and outputs: CaseInput, WeekOutput, SaveInput, SavedOutput, PinOutput
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # empty: the plugin needs no environment variables
├── src/plugin/      # the MCP server (__main__.py), the tools (tools.py), the weeks and rules (week.py), the solver (solve.py)
├── tests/           # tools, generator, solver, rules agreement, verifier, baselines, server schemas
├── ui/              # outputs are drawn from their JSON Schema
├── product/         # the product page: product.yaml and icon.svg
└── verifier/        # deterministic checks: schedule.py (the task), week.py, save.py, pin.py (the tools), receipts.py, rules.py
```

`verifier/rules.py` restates the plugin's fixed rules (the generator, the
schedule rules, the receipt digest and path) because the verifier may not
import the plugin's own code; `tests/test_rules.py` checks that both copies
agree.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

Publishing checks every plugin rule: push the plugin to a public GitHub
repository and submit its URL on RUSH Lab's Marketplace.
