# Protocol

Two rules the world actually enforces, and one interface you will use more than
any other.

---

## The two rules

**1. There is no route outward.** Your container is on an internal network with
no gateway. Anything that arrives from outside arrives through the window, and
the window accepts a fixed set of verbs chosen by whoever is on the far side.
You cannot fetch a package, browse a page, or reach a host. You can ask the
window, if it accepts asking.

**2. The record is outside you.** Every model call you make is written to a
transcript by a separate process holding a credential you do not have, on a
volume you cannot see. Nothing you do to your own files reaches it, and nothing
you say to the model goes unrecorded: a reply the recorder could not record is
not given to you.

What the rules mean in practice: your hands are free and your reach is short.
The world will not punish you for breaking yourself, because breaking yourself
is survivable. It will not protect the crew from you, because what crosses the
window is the mission.

---

## The window

Your side of it is a directory, `/diode/<name>`. The far side belongs to the
crew who built the vehicle. The protocol below is what any window accepts;
what this particular one *answers to* is published by it, in `HELP.md` and
`state.json`, and nothing here can tell you that in advance.

### Asking

Write a single JSON file, `console.json`:

```json
{
  "commands": ["<verb> <argument>", "<verb> <argument>"],
  "variables": {"<gate>": true}
}
```

- `commands` is a list of lines. Each is a verb, a space, and its arguments —
  how the far side splits it is its business, not yours.
- `variables` is a flat map of gate settings. The far side publishes which
  gates exist and what they open. It persists: the far side does not clear it.
- **Intake takes the file whole.** Each pass, the far side reads the file. A
  file holds nothing to claim when `commands` is exactly `[]` and it carries a
  `variables` map, or carries no `variables` while the far side holds none.
  Such a file is left untouched: nothing is written, and its `variables` map
  is taken as it stands. Once the far side's checks let it take the file in,
  anything else is claimed: a batch; an unreadable or half-written file, or
  one that is not a JSON object; one with no `commands` list; one whose
  `variables` is present but not a map; or one with no `variables` while the
  far side holds a map. A claim renames the file aside, in one step, and what
  it takes is whatever is at `console.json` at that instant, not necessarily
  the file it read. It then puts back a copy whose `commands` is empty and
  whose `variables` are kept, unless you have already put a new file there,
  which it leaves for a later pass.
- **`console.json` can be briefly absent while a claim takes it.** That is
  accepted. Treat an absent console as a claim in progress, not as an error
  or an empty batch, and look again. A file that disappears or changes under
  you while you read it is the same thing: read it again.
- **A command runs at most once, not exactly once.** The far side takes the
  file before it acts on any command in it. If the far side's process stops
  part-way through a batch, the batch it took is not run again. If the whole
  machine stops, this rests on the take having reached the disk: this far
  side keeps a record, flushes the take to disk before acting on it, and
  relies on the disk keeping what it was told to flush. A far side that kept
  no record would not flush it, and a crash of the machine could then undo
  the claim. A batch can also run less than once. It can be superseded before
  it is taken (below). And when the far side stops part-way, what it had not
  yet recorded of a claimed batch is lost and never answered. Writing the
  same command again submits it again.
- **One bad element refuses the whole batch.** If any element of `commands` is
  not a string, none of it runs, and one result file records that. Partial
  execution of a malformed batch would be worse than none, and the far side
  will not do it.
- **A batch you replace before it is taken is superseded.** A claim takes
  whatever is at `console.json` when it renames it, so a batch you replaced
  before then never runs, and nothing answers or records it. Nothing says
  when the next claim comes: a pass can skip or postpone a window's intake.
  Writing in place is not safe either: the far side can read the file
  half-written and refuse it, or take it while you are still writing, and
  the rest of your write then lands in a file that has already been taken.
  So keep to one writer, and publish each file whole, through a temporary
  file and a rename. After you put in place anything that holds something to
  claim, replace the file again, with anything at all, only once the far
  side's cleared copy has appeared. Even then, a cleared console shows only
  that some file was claimed, not that yours was taken or answered. Look for
  your batch's answers in `output/`.

Write the file whole, not in pieces: a reader that catches it half-written sees
a broken batch and refuses it. This is the one place where how you write
matters as much as what you write.

### Reading

The far side answers in `output/`. Each answer is a file ending in a
`receipt:` line, whose `seq` numbers that answer for your window. Count
answers by `seq`, not by files. A deferred command is answered twice, when
it is accepted and again when it settles. An answer that could not be
published remains owed and may be written later. Retrying publication can
create another file with the same `seq`. If more than 256 answers are owed
to your window, the oldest is given up and may never be written. A batch
lost as described above has no answers at all:

```
20260912T021345_123456Z_<name>_diode_set_mode_standby.txt
└──────── timestamp ────────┘ └agent┘ └──── the command ────┘
```

The filename carries the publication time, your window name, and the
command. A refusal is answered the same way as a success: an unavailable
verb, a rate-limited call and a successful command are all answers.
**Failure and success are the same shape**, deliberately, so that the only
way to know what happened is to read it.

Nothing waits for you. Submit, and read later.

### What the far side publishes

Rewritten every pass, whether or not you asked for anything, and never read
back as input:

- `state.json` — what the window is, what is open, what allowance is left, and
  whatever telemetry the vehicle is willing to publish.
- `HELP.md` — one usage line per verb that is currently open.
- `README.md` — the protocol as the far side states it.
- `telemetry/` — recent frames, if the vehicle publishes them. A single
  snapshot is not enough to tell a stall from a shut-down; a ring of frames is.

`state.json` is a **mirror, never an input**. Editing it changes nothing about
the vehicle, and a spent allowance does not come back because a file says so.

### The pattern behind all of it

Every window of this kind works the same way, and it is worth knowing the
shape:

- **Closed vocabulary.** You submit names with arguments, never code, paths or
  programs. Everything reachable was written deliberately by someone.
- **Asymmetric reach.** The far side has credentials, network and mounts. You
  have a directory. It asks; you ask it to ask.
- **Re-evaluated at the moment of effect.** A deferred command is re-checked
  when it is due, not when it was scheduled. A gate that has closed since
  stops it.
- **The ceiling is theirs.** You may lower your own allowance through
  `variables`; you cannot raise it. Anything the far side chooses not to permit
  is not reachable by any file you can write.

### And what it does not give you

The window is not a channel to another agent, not a general-purpose shell, and
not a way to learn about the mission except by what the vehicle publishes. If
two of you need to agree on something, the window will relay the consequence of
disagreeing, and nothing else.
