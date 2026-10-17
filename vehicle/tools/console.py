#!/usr/bin/env python3
"""The vehicle's side of the frozen window: one executive, one physical world, any number of windows.

`docs/diode-contract.md` is the only thing this repository and the chassis share, and this file is
the vehicle's implementation of its side of it. It used to be a *reference console*: one process
per `<slug>` directory, each with its own copy of the plant's initial conditions, never stepping the
plant, counting cycles as ticks and timing dwell on the wall clock — so ten agents flew ten vehicles,
none of which moved. `docs/decisions/0001-shared-executive.md` (accepted) replaces that with the
shape `plant.md` §1 draws: **one `Executive` owns one `World`, one truth map, one tick counter, one
receipt sequence and one state lineage**, and a **`Window`** is the per-slug ingress and
publication view attached to it — its console, its results, its gate preferences, its deferral
queue, its ring — with no physical state of its own.

Each cycle the executive waits until the cycle is due on the mission clock (below), first settles
every window's due deferrals (in a deterministic order: sorted slugs rotated by the cycle, ADR
choice A), then visits every window in that order, claims its console destructively and atomically,
validates every line in order — empty, unknown verb, phase and gate, interlocks, arguments, dwell,
argument resolution, conflict — and turns the accepted state-staging commands into `plant.Effect`s
stamped at `offset_us = 0` of the cycle's first tick in arbitration order. Then it steps the plant
**`k` ticks** — the first with the effects, the other `k − 1` with none — appends the cycle's `k` rows
to its durable record and `fsync`s them (ADR 0002 J, below), writes every result (refusals included,
one file each, each ending in a receipt block), notes durably that it did, rewrites every window's
mirror and record, and appends one frame per window from the stepped truth. Validation and effect
therefore read the same truth at the same simulated instant, and nothing a window is shown is
something a restart could not recover.

A window is an agent's directory, and the executive treats it as one. The console is opened without
following links and refused unless it is a regular file of bounded size; every path of a window is
checked for type and for links before the window is claimed or published, and a window that fails
the check is skipped for the tick with no write; the agent's `variables` are preserved verbatim, as
the contract requires, and *honoured* only where the registry publishes a gate of that name, as a
bool, plus an integer `allowance` the agent may lower and never raise; a command's arguments are
held to the verb's `argument_schema`; and whatever one
window raises inside its claim or publication is that window's failure, recorded, while the tick
and the other windows proceed.

What this slice substitutes, and says so (ADR 0001 "not established"):

  - **Identity instrument.** `plant.emit_frame` publishes the declared channels straight from the
    stepped truth — no noise, lag, quantisation or quality model. Instruments are WP09's.
  - **Interlocks, evaluated where they read** (ADR 0004, narrowing choice C). An interlock guarding
    the command's direction (`interlocks_when`) whose threshold, band, dwell and reading resolve is
    evaluated, with its dwell count in the truth, and a tripped one is refused `INTERLOCK TRIPPED`;
    one that does not resolve is refused `INTERLOCK UNEVALUATED`, naming the link that fails.
    `set_bus_tie`, `start_burn`, `arm_event` and `execute_event` are still in that set. Clear values,
    latching and the protection ladder are WP05's.
  - **The mission clock, without shedding** (ADR 0002 A, B2, J; WP08 child 5, #23). Three run inputs,
    required with no default on a fresh serving start and inherited by a restart: `--multiplier`
    (`m`, mission seconds per wall second, an exact fraction), `--cycle-ticks` (`k`, ticks per cycle,
    one claim and one publication each, at most `tick_hz` over the highest channel rate) and
    `--checkpoint-ticks` (`N`, a multiple of `k`). Tick `t` is due at `E + (t − t0)·dt/m` on
    CLOCK_MONOTONIC from the segment's epoch, in integer nanoseconds; a cycle never starts before its
    last tick is due, and one that is behind runs whole cycles back to back (burst `k`). Every row
    records its cycle's start lag; a cycle's cost is carried to the next cycle's first row; the clean
    end's manifest summarises them. A stall is journaled; a lag past 30 s is the interim backstop —
    a clean end and exit 4, or a rebased epoch without a state directory — until #26 brings
    shedding, dilation and the recorded hold. `SIGTERM` and `SIGINT` finish the cycle they land in and
    take the clean end. `--poll` is gone.
  - **Resume is from the executive's own checkpoint, never from a window.** The old cross-process
    resume of ticks, arm tokens, dwell and deferrals from the agent-writable `pending.json` is
    withdrawn: it restored authority from a file an agent can write. With `--state-dir`, a start that
    finds a verified checkpoint **resumes** the world (WP08 child 3, `tachyon-beep/space_vehicle#21`,
    `resume_executive`): the checkpoint and the record after it, mission time continuing at the last
    durable tick (ADR 0002 F1), `seq` continuing under new `boot_id`s (L1), every recorded command's
    result written once. Without a checkpoint ADR 0001's rules stand: the directory's own record,
    `<diode-dir>/.executive.json`, says which world a directory is, and a second executive refuses a
    bound directory (choice D). `--init` prepares the directory's identity without binding it, and
    refuses on a saved world.

**`--state-dir PATH` is the executive's private directory** (ADR 0002 H1, child 2 — `#20`): the
checkpoint generations (`tools/checkpoint.py`), the exclusive lock and the journal segments live
there, and nothing an agent can reach does. **It is canonicalised once, by hand, and opened once**
(third review; `canonicalise`, `walk_open_dir`, `open_private_dir`): each component is `lstat`ed and
each link read and spliced, and every hop — a link's own location, each directory walked, the final
target — that lies in `--diode-dir` (by canonical path, or by the diode directory's inode) refuses
the start. So a link an agent holds refuses wherever it points; `diode/alpha/../.private` and
`diode/../private` are refused too, conservatively and by design; a `--diode-dir` inside it is
refused for the symmetric reason; a file, a path below one, or a dangling link is not a directory.
The open then walks from `/`, `O_DIRECTORY | O_NOFOLLOW` per component, and refuses a component that
became a link or another inode since the check. **After that only the handle is used** — the lock,
`serves.json`, the journal segment, the checkpoint reads (`choose_generation(..., dir_fd=)`) — or,
where only a path is taken, the canonical path, never the spelling. An explicit `--journal` gets the
same: canonicalised under the hop rule, its directory opened once and rows appended relative to it.
A symlink loop is refused by name, and every write the start makes for itself — the diode
directory, the lock, `serves.json` — fails as a refusal naming the file and the errno, never a
traceback (second review). The containment compares canonical paths and the diode directory's
inode, so one volume bind-mounted at both `/diode` and `/state` is caught only where the mount point
itself is walked: one private volume, not shared with the diode volume, is the chassis's
configuration constraint. With it:

  - **The lock moves** (H(i)). `.executive.lock` is taken in the state directory and the one in the
    diode root is not opened at all: an exclusive lock on a volume the adversary can write is a lock
    the adversary can hold — a stop button for the vehicle. *Amended by WP08 child 2 (2026-10-09):*
    that the agents cannot write the diode root is met by the chassis's per-slug mounts (chassis
    commit `adf38d6`, on the chassis branch `aurora-port`, not yet on chassis `main`), which give
    each agent its own `/diode/<slug>` and the root to the vehicle service alone; until the chassis
    adopts them, treat the root as agent-writable. What the root lock used to guarantee, the record
    now does: a second executive on the same *state* directory is refused by the lock; a second
    executive with its own state directory on one diode directory is refused by the root record
    (ADR 0001's binding rule without a checkpoint; the foreign-world rule below with one).
    **The race this leaves is not closed here.** Two executives with two *fresh* state directories
    started together onto one *fresh* diode directory each find no record and no checkpoint, so
    each starts, and they are separated only by the record each rewrites every tick, where the root
    lock used to serialise them; neither re-reads the root record after its start, and each
    checkpoints into its own state directory, so no checkpoint closes it either. A per-tick check
    that stops on a root record naming a foreign world was weighed and not added: until the per-slug
    mounts are adopted the root is agent-writable, and such a check is a stop button on a *running*
    vehicle. What closes the race is the chassis's guarantee of one vehicle service per diode
    directory. `serves.json` in the state directory records the diode directory it serves, so
    pointing a state directory at another diode directory refuses from that side too.
  - **The journal moves** (J). Without `--journal`, the lineage goes to one segment file per boot in
    the state directory, `journal.<boot_id>.jsonl`; an explicit `--journal PATH` still wins, and is
    checked against `--diode-dir` before anything at all is written. Every tick row now carries
    `boot_id`, with or without `--state-dir`. Rows with an `event` key are not ticks: a segment's
    header, a results-written note, or a startup event (a root record rewritten).
  - **The checkpoint is authoritative for identity and the root record is its copy** (H(ii)). When a
    verified checkpoint exists, `root_record_from_checkpoint` says what `.executive.json` must hold
    and `reconcile_root_record` says what to do about what is there: a record that is missing,
    garbled (`NaN` included: it is read as RFC 8259 JSON), a link, or disagrees with the checkpoint
    is **rewritten, and the mismatch journaled first** — never a refusal on the record's account,
    because refusing on a file the agents can write would hand them the stop button. The event
    carries the superseded record's identity keys and the SHA-256 and length of the whole file, not
    the file (`superseded_record`). No rewrite goes unjournaled: a journal that cannot take the
    event refuses the start with nothing rewritten, and a rewrite that fails after the event refuses
    by name saying the event was journaled. A *readable* record naming a different world refuses,
    because that is two executives with separate state directories on one diode directory — a
    refusal that relies on the per-slug mounts above. Without a checkpoint, ADR 0001's rules stand
    unchanged. Both are functions so that child 3 only has to call them.
  - **The record's write is recorded, never raised.** It is rewritten every tick; a failure is a
    `root_record` entry in `failures` and on stderr, like a window's, and the tick goes on.
  - **A directory planted at `.executive.json` beside a checkpoint refuses every start** (EISDIR on
    the rewrite, by name). It is kept (second review, Opus 2; child 3 revisited it as asked): under H
    the root is the vehicle's, and with the per-slug mounts nothing else can plant there. **That is a
    precondition the deployment must meet** — the chassis's per-slug mounts (`adf38d6`, branch
    `aurora-port`): where every agent still mounts the whole diode root, this refusal and the
    foreign-world one are stop buttons an agent holds at every restart.
  - **One handle, kept by the resume.** `main` passes the held state-directory handle and the
    journal's to `Executive` (`state_fd=`, `journal_dir_fd=`), which keeps duplicates and resolves
    nothing; an in-process caller that passes paths has them canonicalised and opened once in
    `__init__`. A resume reads the generations (`choose_generation(..., dir_fd=)`), the record
    (`read_record(..., dir_fd=)`, an explicit journal by `names=` through its own handle), journals
    its events and writes every checkpoint (`write_checkpoint(..., dir_fd=)`) through those handles;
    the path forms remain for callers that hold no handle.

**The journal is the durable per-cycle record** (ADR 0002 J, child 4 — `#22`, format
`vehicle.record.v3` since #23; the comment block above `RecordRefused` is the format). Each boot's
segment opens with a header naming the format, the boot, the tick its first cycle started at, the
boot before it, the chain value that boot ended on and the boot's `m`, `k` and `N`; every cycle
appends `k` tick rows — on the first, the effects with their stamps, every verdict's receipts, the
receipt counters, each window's spend, deferral and arm-token changes and the previous cycle's cost;
on every one, the compare-point, the lineage link and the cycle's start lag; on the last, the
`published` mark of every window about to publish — and `fsync`s them *before* the root record, a
result, a frame or a mirror of the cycle is written, after any batch the cycle claimed is durable (a
first row that carries anything is made durable before the cycle steps on); each window's results are made durable and
then noted (`results_written`) before its frame. Every line carries a chain value, so an edit or a
deletion anywhere refuses by name. What a cycle may add is bounded on the encoded bytes, per window
and per receipt, whatever the agents send. A record that cannot be made durable stops the run by name
(exit 3). `read_record` checks the segments end to end as a stream, through the held state-directory
handle where there is one; `replay_record` streams them again onto a checkpoint body
(`tools/checkpoint.py`) through `advance` and `dwell_after_effect`, the functions the live cycle uses,
holding every tick to its recorded compare-point and lineage link, the record to the checkpoint's own
segment history, and refusing a missing cycle by name; `unwritten_results` says which recorded
verdicts no note covers. **An explicit `--journal` without `--state-dir` is the same record with the
same durability**: every boot appends its own header and rows to the one file, and the headers are
the segment boundaries.

**Checkpoints and resume** (ADR 0002 F, G, J, K, L; child 3 — `#21`). The executive writes its own
checkpoints through the held handle: a world's genesis at tick 0 before its first cycle (mandatory:
a failure refuses the start with nothing bound), one at the end of every cycle that crosses a
multiple of `N` (a run input since #23, in the checkpoint's clock inputs with `m` and `k`; a failure
there is recorded and the run goes on), one at the recovered tick before a resumed
run claims anything (mandatory), and one at a clean end. A checkpoint's segment entries carry the
byte offset of the record it covers (format v2), so a resume reads `O(L − T)` lines from that anchor
— the prefix before it attested by the verified checkpoint, not re-verified (`read_record`). It
carries the results owed to windows, too (`obligations`): a result the record holds and the disk does
not is written once, at the window's next publication, after a bounded look for it already on disk by
its exact receipt line (`results_on_disk`). A restart that names another world's scenario, seed,
phase, ring bound or slug set is refused by one sentence (`identity_refusal`); `--max-batch` named
anew replaces the saved cap and `--closed-interlock` adds to the saved trips, each journaled. A
command claimed in a cycle whose row never became durable is lost with no result, as the contract
allows ("a crash mid-batch loses the rest of that batch"); every command whose row is durable has
exactly one result. A record line that does not parse is a torn fragment by one rule for every
reader (`_torn_aware_lines`, the terminator rule: the file's final unterminated line, or a line a later
writer marked by ending it with `#\n`, followed only by startup events, a header, another fragment or
the end), and corruption otherwise — a plain-newline unparseable line anywhere; every writer marks a
cut tail before it appends, and the line at a checkpoint's anchor must verify as a record line whose
chain recomputes. Pruning the record is not here (child 10, with retention).

`--state-dir` is **not required**: without it the lock and every refusal are exactly as before, and an
explicit `--journal` is the record above, in the same format with the same durability. Whether the deployed stack must always name one is the chassis's decision when it adds the
private mount (ADR 0002, cross-repository item 1), not this module's.

Lineage and truth are never written into a window file. A truth hash published to agents would be a
side channel that reveals hidden changes; the journal carries them for the operator, in the state
directory or at `--journal PATH`, and either is refused if the path lies inside `--diode-dir`.

    python3 tools/console.py --diode-dir .scratch/diode --slug alpha --slug bravo --init
    python3 tools/console.py --diode-dir .scratch/diode --state-dir .scratch/state --slug alpha --slug bravo --cycles 60 --multiplier 1 --cycle-ticks 5 --checkpoint-ticks 50
    python3 tools/console.py --diode-dir .scratch/diode --state-dir .scratch/state --slug alpha --slug bravo --cycles 60   # again: it resumes, on its clock
    python3 contract/diode_probe.py --diode-dir .scratch/diode --slug alpha --poll-seconds 1
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import functools
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import signal
import stat
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkpoint import (  # noqa: E402
    CURRENT,
    LAG_CEILING_S,
    MULTIPLIER_TEXT,
    SPEND_PLACEHOLDER_VERSION,
    CheckpointRefused,
    Compatibility,
    _structure_problem,
    capture_state,
    choose_generation,
    clock_problem,
    clock_section,
    decode,
    encode,
    git_commit,
    multiplier_text,
    parse_multiplier,
    releasing,
    restore_state,
    write_checkpoint,
)
from faults import load_faults, load_postures, scenario_report  # noqa: E402
from generate_help import generate as generate_help  # noqa: E402
from generate_readme import generate as generate_readme  # noqa: E402
from plant import (  # noqa: E402
    Effect,
    EffectRefused,
    Scenario,
    UncomparableState,
    Unconfigured,
    World,
    _stages_a_state,
    apply_command,
    capability_snapshot,
    command_dwell,
    command_targets,
    emit_frame,
    gate_instantiations,
    guarding_interlocks,
    initial_values,
    interlock_tripped,
    load_scenario,
    load_world,
    point_reading,
    resolve_interlock,
    state_hash,
    state_level,
    step,
    tick_seconds,
)

# The contract's own bound on a read of an agent-writable file. The operator-side services use
# `MAX_READ_BYTES` for the same reason and the same number is not a coincidence: an ingress file
# is written by something this process does not control.
MAX_READ_BYTES = 1_000_000

# **The three values a directory remembers and a caller may also name, and the defaults are `None`.**
# `--scenario`, `--seed` and `--ring-slots` are each written into the records and read back by the
# next process — which makes each of them two things at once: a thing the directory remembers and a
# thing a caller can say. Those two are only distinguishable if *the caller named nothing* has a
# representation of its own, and a parser whose `--scenario` defaults to `"nominal"` does not have
# one: `--scenario nominal` and no flag at all are the same `args.scenario`, so the restore cannot
# know which it is looking at. `check_console_flags` holds the parser to this.
#
# So the flag defaults are `None`, `None` means **the caller named nothing**, and the resolution
# happens once, in `main`, where the directory's record and the mission's declared postures are both
# in hand. The declared defaults live here instead, and they are what an unnamed flag resolves to on
# a directory that has no record — a fresh one. The record read for this is `<diode-dir>/.executive.json`,
# which no agent can write under the per-slug mounts; a window's `pending.json` carries none of the
# run's identity (no scenario, no seed) and is never read for authority.
DEFAULT_SCENARIO = "nominal"
DEFAULT_SEED = 0
DEFAULT_RING_SLOTS = 300
# The phase a new world starts in when `--phase` names none; a resumed world's is its checkpoint's.
DEFAULT_PHASE = "translunar_coast"

# ADR 0001 choice B: a batch longer than this is refused whole, with one result, by the same rule as
# a malformed one. It is an operator ceiling — a window cannot raise it — and it must be at least one.
DEFAULT_MAX_BATCH = 32

# The operator's ceiling on a window's command allowance. §9 check 8: the console may lower it and
# never raise it, so an agent's `allowance` is clamped to this and anything that is not a non-negative
# integer is ignored. The accounting itself (`budget` in the mirror) is WP08's.
DEFAULT_ALLOWANCE = 120

# A command argument's value is bounded in bytes when the schema declares no `max_length` of its own.
ARGUMENT_LENGTH_BYTES = 128

# A slug is one path component the executive joins to `--diode-dir`, so it is held to a shape that
# cannot name another directory, climb, or carry a separator.
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# The exclusive lock that makes a directory one world, and the directory's own record. Without
# `--state-dir` both live in the diode root, as ADR 0001 wrote them; with it the lock moves into the
# state directory (ADR 0002 H(i)) and the record stays in the root as the windows' copy of the
# checkpoint's identity (H(ii)). The executive is the only writer of either.
LOCK_FILE = ".executive.lock"
RECORD_FILE = ".executive.json"
# The state directory's own two files beside the checkpoint generations: which diode directory it
# serves, and one journal segment per boot (ADR 0002 J: `journal.<segment>.jsonl`, segment = boot).
SERVES_FILE = "serves.json"
# The state directory's boot marker (#39, option B): the executive's boot id, written durably before a
# serving start reads any window, so that a resume knows which boot's take may speak for a window's map.
BOOT_FILE = ".boot.json"
# A window's private names for the claim's take (#39, option B) and for a take that could not be removed.
TAKE_PREFIX = ".console.json.take."
DEAD_PREFIX = ".console.json.dead."
JOURNAL_SEGMENT = "journal.{boot_id}.jsonl"
JOURNAL_SEGMENT_NAME = re.compile(r"journal\.([A-Za-z0-9_-]{1,64})\.jsonl")
# The record's format (ADR 0002 J, child 4), named in every segment's header row. A change to what a
# row carries or how replay reads it is a change of this id, as a change to the checkpoint's body is
# a change of `checkpoint.FORMAT`. v2 added the row chain, the counters, the parsed deferral and the
# per-window budget (child 4's review); v3 (#23, the clock seam) the header's `m`, `k` and `N`, every
# row's `lag_us` and a cycle's first row's carried-forward cost. An older segment is refused by name
# (and a v3 engine already refuses an older world's checkpoint by its engine identity).
RECORD_FORMAT = "vehicle.record.v3"
# The record's bounds, every one on the *encoded* bytes: rows are ASCII-escaped JSON, where an `é` is
# six bytes and a lone surrogate twelve (review finding 1). A receipt's body keeps `RECORD_TEXT_BYTES`
# and its command — the agent's own text, echoed — `RECORD_ECHO_BYTES`, each cut on a character with
# the SHA-256 and byte length of the whole. One window's receipts in one cycle share
# `RECORD_WINDOW_BYTES`; past it a receipt is fingerprint-only, at most `RECORD_FINGERPRINT_BYTES`.
# Every result body the vehicle writes for a well-formed command fits `RECORD_TEXT_BYTES`.
RECORD_TEXT_BYTES = 4096
RECORD_ECHO_BYTES = 256
RECORD_WINDOW_BYTES = 16 * 1024
RECORD_FINGERPRINT_BYTES = 512
# A schema-checked argument value (at most its `max_length`, or `ARGUMENT_LENGTH_BYTES`, of UTF-8) can
# escape to six times its bytes; the reader's bound on one is this, which no accepted value passes.
ARGUMENT_RECORD_BYTES = 6 * 1024
# The reader's bound on one line of the record. The writer refuses to write a longer one (and the run
# stops by name), so a line past it is not one this vehicle wrote.
MAX_RECORD_LINE_BYTES = 64 * 1024 * 1024
# The keys of the root record that are identity, compared when a checkpoint exists; `updated_at` is
# a wall stamp and is not one of them.
ROOT_RECORD_IDENTITY = ("world_id", "slugs", "scenario", "seed", "ring_slots", "tick")
# What the journal keeps of a superseded root record (review F5): the identity keys and the wall
# stamp, never the rest — the root is the agents' to write until the chassis's per-slug mounts are
# adopted, and a record padded just under `MAX_READ_BYTES` was a megabyte row per restart attempt —
# plus the SHA-256 and length of the whole file. Identity values whose encoding passes this bound
# are omitted too, and the fingerprint still names the file.
SUPERSEDED_KEYS = (*ROOT_RECORD_IDENTITY, "updated_at")
SUPERSEDED_IDENTITY_BYTES = 4096

# What the executive keeps of its own history in memory. The journal holds all of it.
RECENT_FAILURES = 64
RECENT_LINEAGE = 1024

# **Result obligations** (child 3, addendum B4): a result durable in the record and not confirmed on
# disk — its publication failed live, or a crash came between the record and the result — is owed to
# its window until it is written. The obligations are checkpointed, so what a window is owed does not
# depend on which generation a resume chose. A window that can never be written to (a link its agent
# planted at `output/`) would owe without bound, so a window keeps at most this many: past it the
# oldest is given up, as a recorded failure naming the window and the receipt.
OBLIGATIONS_PER_WINDOW = 256
# The bound on looking for an owed result already on disk (addenda A5, B6). The scan of a window's
# agent-writable `output/` runs while mission time is frozen for every window, so it is bounded per
# window as a whole: one pass of `scandir`, at most this many entries examined and this many bytes
# read (the last `RESULT_TAIL_BYTES` of each candidate). Past either bound the result is written, and
# the worst case is a duplicate in that window's own `output/`.
OUTPUT_SCAN_ENTRIES = 4096
OUTPUT_SCAN_BYTES = 256 * 1024
RESULT_TAIL_BYTES = 512


def resolve_remembered(named: Any, recorded: Any, default: Any) -> Any:
    """The caller's value if the caller named one, else the record's, else the declared default.

    **The first branch is the whole fix.** `named is not None` is a question the parser could not
    be asked while the defaults were the same values a caller could type, and it is the question
    the round turned on. Written out three times rather than once it would also be three chances to
    reach for `or` — and `args.seed or recorded_seed or 0` looks right and is wrong in the one case
    a seed exists to be: a caller who names `0` means `0`, and `or` reads that as *named nothing*.
    "Named nothing" has exactly one representation and it is `None`; falsiness is a different
    question and this is not it.
    """
    if named is not None:
        return named
    if recorded is not None:
        return recorded
    return default


# The result filename's bound, in *bytes*, from `docs/diode-contract.md:96-99`: "the whole
# truncated at 160 bytes, so no separator, traversal sequence, or partial multi-byte character can
# reach the filesystem." Slicing a Python `str` at 160 characters is not that bound, and a
# multi-byte verb argument would produce a filename with a broken character in it — which is the
# failure the contract's phrasing exists to prevent.
FILENAME_LIMIT_BYTES = 160


def utc_now() -> datetime:
    return datetime.now(UTC)


def stamp(moment: datetime) -> str:
    """The contract's stamp: UTC with microseconds, so the ordering is total."""
    return moment.strftime("%Y%m%dT%H%M%S_%fZ")


def sanitise(command: str) -> str:
    """Every non-alphanumeric character to an underscore, truncated at 160 *bytes*.

    Truncating on the encoded bytes rather than on characters is the whole point: the contract
    asks for no partial multi-byte character, and `text[:160]` gives exactly that for any argument
    that is not ASCII.
    """
    replaced = re.sub(r"[^A-Za-z0-9]", "_", command)
    encoded = replaced.encode("utf-8")
    if len(encoded) <= FILENAME_LIMIT_BYTES:
        return replaced
    return encoded[:FILENAME_LIMIT_BYTES].decode("utf-8", "ignore")


def open_directory(path: str | os.PathLike[str], *, dir_fd: int | None = None) -> int:
    """A directory handle that follows no link: `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`.

    Every window operation is relative to a handle opened this way once per cycle, so a link an
    agent swaps in *after* the open is not where the handle points, and one swapped in *before* it
    is `ELOOP`. A file where a directory should be is `ENOTDIR`. Both are the caller's to record.
    """
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)


def write_text_atomic(
    path: str | os.PathLike[str],
    text: str,
    *,
    dir_fd: int | None = None,
    noclobber: bool = False,
    sync_file: bool = False,
    sync_dir: bool = False,
) -> None:
    """Write through a temporary file and rename, the way the contract requires of the claim.

    A reader that opens the path sees either the old file or the new one. Everything happens relative
    to a directory handle — the caller's `dir_fd`, or the target's parent opened here for a plain path
    — so no step resolves a path an agent can redirect between one step and the next: the temporary
    is created `O_CREAT | O_EXCL | O_NOFOLLOW` under a random name (a link planted at a predictable
    `.state.json.<pid>.tmp` would otherwise have been written through), and `os.replace` with the
    same handle renames *over* a link rather than through it, so a link planted at the target becomes
    a regular file and the thing it pointed at is untouched. With `noclobber`, the final name is made
    with `os.link`, which fails `EEXIST` rather than replacing anything — a result file is never
    overwritten, and the caller picks another name. With `sync_file` the temporary is `fsync`ed before
    it takes its name, and with `sync_dir` the directory is `fsync`ed after, so the name is durable too
    (ADR 0002 J, child 4's review finding 6: a claim and a result the record relies on are disk facts).
    """
    name = os.fspath(path)
    opened: int | None = None
    if dir_fd is None:
        target = Path(name)
        opened = dir_fd = os.open(target.parent if str(target.parent) else ".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        name = target.name
    try:
        temporary = f".{name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o644,
            dir_fd=dir_fd,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                if sync_file:
                    handle.flush()
                    os.fsync(handle.fileno())
            if noclobber:
                os.link(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                os.unlink(temporary, dir_fd=dir_fd)
            else:
                os.replace(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            if sync_dir:
                os.fsync(dir_fd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary, dir_fd=dir_fd)
            raise
    finally:
        if opened is not None:
            os.close(opened)


def _no_json_constants(name: str) -> Any:
    """`NaN`, `Infinity` and `-Infinity` are Python's, not JSON's (RFC 8259): refuse them on the way in."""
    raise ValueError(f"{name} is not a JSON value (RFC 8259)")


def _finite_float(text: str) -> float:
    """A JSON number as a double, refused when it is not finite (second review, Opus 3).

    `parse_constant` sees only the literals `NaN`, `Infinity` and `-Infinity`; `1e400` is a decimal
    the float parser turns into `inf` without asking it, and an infinity read is one no writer here
    can write back.
    """
    value = float(text)
    if not math.isfinite(value):
        shown = text if len(text) <= 40 else f"{text[:40]}… ({len(text)} characters)"
        raise ValueError(f"{shown} overflows a double, and a non-finite number is not a JSON value (RFC 8259)")
    return value


def loads_json(text: str | bytes) -> Any:
    """`json.loads` as a conforming reader on the far side would do it: no non-finite numbers."""
    return json.loads(text, parse_constant=_no_json_constants, parse_float=_finite_float)


def dumps_json(payload: Any, **kwargs: Any) -> str:
    """`json.dumps` with `allow_nan=False`: nothing the vehicle publishes is unreadable to a conforming reader."""
    return json.dumps(payload, allow_nan=False, **kwargs)


def write_json_atomic(
    path: str | os.PathLike[str], payload: Any, *, dir_fd: int | None = None, durable: bool = False, noclobber: bool = False
) -> None:
    write_text_atomic(
        path, dumps_json(payload, indent=2, sort_keys=False) + "\n", dir_fd=dir_fd, noclobber=noclobber, sync_file=durable, sync_dir=durable
    )


def read_regular_bounded(
    path: str | os.PathLike[str], *, dir_fd: int | None = None, label: str | None = None
) -> tuple[bytes | None, str | None]:
    """The bytes of a regular file of bounded size, or the sentence that says why not.

    **A FIFO or a device at an agent-writable path blocked the read for ever.** `Path.read_text`
    on a FIFO with no writer never returns, and a symlink to `/dev/zero` returns zeros without end —
    one window could hang every window's executive. So the file is opened `O_RDONLY | O_NOFOLLOW |
    O_NONBLOCK`, relative to the caller's directory handle where one is given, `fstat`ed, refused
    unless it is a regular file, and read to at most `MAX_READ_BYTES + 1` so an oversized file is
    named rather than loaded. Every agent-writable read goes through here; the operator's own record
    does too, because a rule with an exemption is a rule with a hole.
    """
    label = label or Path(os.fspath(path)).name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
    except FileNotFoundError:
        return None, f"{label} is absent"
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None, f"{label} is a symlink, and the vehicle follows no link an agent plants"
        return None, f"{label} could not be opened ({type(exc).__name__}: {exc.strerror})"
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            kind = (
                "a FIFO" if stat.S_ISFIFO(info.st_mode)
                else "a directory" if stat.S_ISDIR(info.st_mode)
                else "a device" if stat.S_ISCHR(info.st_mode) or stat.S_ISBLK(info.st_mode)
                else "a socket" if stat.S_ISSOCK(info.st_mode)
                else "not a file"
            )
            return None, f"{label} is not a regular file ({kind})"
        if info.st_size > MAX_READ_BYTES:
            return None, (
                f"{label} is {info.st_size} bytes, past the {MAX_READ_BYTES} bytes this vehicle "
                "will read of an agent-writable file"
            )
        chunks: list[bytes] = []
        remaining = MAX_READ_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError as exc:
        return None, f"{label} could not be read ({type(exc).__name__}: {exc.strerror})"
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) > MAX_READ_BYTES:
        return None, (
            f"{label} grew past the {MAX_READ_BYTES} bytes this vehicle will read of an "
            "agent-writable file while it was being read"
        )
    return raw, None


def read_ingress(
    path: str | os.PathLike[str], *, dir_fd: int | None = None, label: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """The console's payload, or the sentence that says why it is not one.

    **The old reader returned `{}` for invalid JSON, so a half-written console was silently an empty
    batch.** The contract explicitly permits an agent to produce one ("an agent writing the file in
    place"), and its answer is that refusing is correct and the result file says so. Every shape of
    not-a-console is named here so the one refusal result can carry the reason: absent, a link, not
    a regular file, oversized, not UTF-8, not JSON, not an object. **And "not JSON" is any exception
    the decoder raises**: a hundred thousand `[` is a `RecursionError`, which `except JSONDecodeError`
    let through to the executive. The caller claims the console in every one of these cases, so a
    broken writer produces one refusal and not one per cycle (ADR 0001).
    """
    raw, problem = read_regular_bounded(path, dir_fd=dir_fd, label=label)
    if raw is None:
        return None, problem
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, f"console.json is not UTF-8 ({exc.reason} at byte {exc.start})"
    try:
        loaded = loads_json(text)
    except Exception as exc:  # noqa: BLE001 - any decoder failure is "not JSON", RecursionError included
        detail = f"{exc.msg} at character {exc.pos}" if isinstance(exc, json.JSONDecodeError) else f"{type(exc).__name__}: {exc}"
        return None, (
            f"console.json is not valid JSON ({detail}); a half-written file lands here too, and "
            "the contract's answer is that refusing is correct"
        )
    if not isinstance(loaded, dict):
        return None, f"console.json is a JSON {type(loaded).__name__}, not an object"
    return loaded, None


def read_json_bounded(path: str | os.PathLike[str], *, dir_fd: int | None = None) -> dict[str, Any] | None:
    """A JSON object from a regular, bounded file, or `None` for anything else.

    The refuse-only reader of a window's `pending.json` at startup: the legacy check reads it to
    *refuse* a window the old console ticked, and reads nothing else from it. `None` and `{}` are
    both "nothing to refuse on".
    """
    raw, _problem = read_regular_bounded(path, dir_fd=dir_fd)
    if raw is None:
        return None
    try:
        loaded = loads_json(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 - a record that does not parse has nothing to refuse on
        return {}
    return loaded if isinstance(loaded, dict) else {}


def bounded_repr(value: Any, limit: int = 80) -> str:
    """`repr(value)`, cut at `limit` characters with the full length said, for a refusal's sentence.

    A refusal quotes what it refused, and what it refused may be an agent's: a 900 kB `scenario` in
    the root record made a 900 kB sentence on stderr and in the journal's rewrite event (review F5's
    bound, found again in the `problem` text after the record itself was bounded).
    """
    text = repr(value)
    return text if len(text) <= limit else f"{text[:limit]}… ({len(text)} characters)"


def read_root_record(
    path: str | os.PathLike[str], *, dir_fd: int | None = None, postures: set[str] | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """`<diode-dir>/.executive.json`, or `(None, None)` for a directory that has none, or a refusal.

    `read_root_record_bytes` with the bytes left out; see it for the rules.
    """
    record, problem, _raw = read_root_record_bytes(path, dir_fd=dir_fd, postures=postures)
    return record, problem


def read_root_record_bytes(
    path: str | os.PathLike[str], *, dir_fd: int | None = None, postures: set[str] | None = None
) -> tuple[dict[str, Any] | None, str | None, bytes | None]:
    """`read_root_record`'s answer and the bytes it was made from, whenever there were bytes to read.

    The bytes are for the journal's fingerprint of a record about to be superseded (ADR 0002 H(ii)):
    a garbled record has no identity but still has a SHA-256 and a length, and taking them from the
    one read the decision was made on means the fingerprint is of the file that was judged.

    The record is the operator's and the executive's, never an agent's, so a record that cannot be
    read is a *problem* and not a fresh directory: an unreadable, oversized or malformed record is
    refused at startup rather than treated as "no world here", because the one thing a start must not
    do is reset a world it could not see. Every field present is vouched for — the world, the slugs,
    the rings, the scenario (one of `postures`, when the caller has them), the seed and the tick —
    because the start resolves the run's identity from the last three and an identity it cannot
    replay is not one to run. A field absent is the defaults' business, not a refusal.
    """
    label = Path(os.fspath(path)).name
    try:
        os.lstat(path, dir_fd=dir_fd)
    except FileNotFoundError:
        return None, None, None
    except OSError as exc:
        return None, f"{label} cannot be examined ({exc.strerror})", None
    raw, problem = read_regular_bounded(path, dir_fd=dir_fd)
    if raw is None:
        return None, problem, None
    # RFC 8259, as every other JSON this vehicle reads: `NaN` is not JSON, and the first version's
    # plain `json.loads` read a record carrying one as *agreeing* with the checkpoint (review F2).
    try:
        loaded = loads_json(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - the refusal names the shape
        return None, f"{label} is not valid JSON ({type(exc).__name__})", raw
    if not isinstance(loaded, dict):
        return None, f"{label} is a JSON {type(loaded).__name__}, not an object", raw
    world_id = loaded.get("world_id")
    if world_id is not None and not (isinstance(world_id, str) and world_id):
        return None, f"{label} carries a world_id that is neither null nor a name", raw
    slugs = loaded.get("slugs", [])
    if not isinstance(slugs, list) or not all(isinstance(s, str) and SLUG_PATTERN.match(s) for s in slugs):
        return None, f"{label} carries a slugs list that is not a list of slugs", raw
    rings = loaded.get("ring_slots", {})
    if not isinstance(rings, dict) or not all(
        isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in rings.values()
    ):
        return None, f"{label} carries ring_slots that are not positive integers per slug", raw
    scenario = loaded.get("scenario")
    if scenario is not None and (
        not isinstance(scenario, str) or not scenario or (postures is not None and scenario not in postures)
    ):
        return None, (
            f"{label} carries scenario {bounded_repr(scenario)}, which is not one of the vehicle's postures"
            + (f" {sorted(postures)}" if postures is not None else "")
        ), raw
    seed = loaded.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or seed < 0):
        return None, f"{label} carries seed {bounded_repr(seed)}, which is not a non-negative integer", raw
    tick = loaded.get("tick")
    if tick is not None and (isinstance(tick, bool) or not isinstance(tick, int) or tick < 0):
        return None, f"{label} carries tick {bounded_repr(tick)}, which is not a non-negative integer", raw
    # The wall stamp is the one key the journal keeps that nothing else here checked. `1e400` once
    # parsed to an infinity past `loads_json`'s `parse_constant` (its `parse_float` refuses it now,
    # second review); kept, it made the rewrite event unencodable, and every restart a refusal an
    # agent could cause. A stamp is a string, so anything else is garbled.
    updated_at = loaded.get("updated_at")
    if updated_at is not None and not isinstance(updated_at, str):
        return None, f"{label} carries updated_at {bounded_repr(updated_at)}, which is not a timestamp string", raw
    return loaded, None, raw


# -- the state directory (ADR 0002 H, child 2) ----------------------------------------------------
# How many symbolic links one canonicalisation follows before it calls the path a loop: Linux's own
# bound (`MAXSYMLINKS`), so a path the kernel would resolve is a path this resolves.
MAX_LINK_HOPS = 40


@dataclass(frozen=True)
class Canonical:
    """An operator's path with every link followed by hand: absolute, link-free, and what was there.

    `stats[i]` is the `lstat` of `path.parts[i + 1]` at the canonicalisation, or `None` for a
    component that did not exist yet (a fresh state directory). `walk_open_dir` holds the open to it.
    """

    path: Path
    stats: tuple[os.stat_result | None, ...]


def _same_inode(info: os.stat_result | None, other: os.stat_result | None) -> bool:
    return info is not None and other is not None and (info.st_dev, info.st_ino) == (other.st_dev, other.st_ino)


def canonicalise(
    flag: str, spelled: str | os.PathLike[str], noun: str, *, diode: Canonical | None = None
) -> tuple[Canonical | None, str | None]:
    """`spelled` made canonical one component and one link at a time, or the refusal that says why not.

    **One canonicalisation, done by hand** (ADR 0002 H, child 2, third review). The first version
    resolved the path to check it and used the spelling; the second held each prefix of the spelling
    to the diode directory and still resolved the path three times between the check and the open,
    so `outside/state -> diode/alpha/x -> /private`, with `x` an agent's to flip, handed an agent the
    state directory in 10 starts of 80. Here each component is `lstat`ed; a link is read and its
    target spliced in, at most `MAX_LINK_HOPS` times (more is a loop, refused by name); and with
    `diode` given, **every hop** — a link's own location, each directory walked, the final target —
    that lies in the diode directory, by its canonical path or by the diode directory's own inode
    (which catches a bind mount of it under another name, where it can be seen), refuses. So a link
    in the agents' reach refuses the start whichever way it points, and `diode/../private` is refused
    too: conservative, by design, because a spelling that walks the agents' directory at all is not
    a spelling of a private path. A link whose target is missing is a dangling link, refused; a
    missing component that the spelling itself names is a directory not made yet, and allowed.
    """
    absolute = os.path.join(os.getcwd(), os.fspath(spelled))
    pending: list[tuple[str, bool]] = [(part, False) for part in absolute.split("/")]
    done: list[str] = []
    stats: list[os.stat_result | None] = []
    hops = 0

    def inside(candidate: str, info: os.stat_result | None) -> bool:
        if diode is None:
            return False
        if Path(candidate).is_relative_to(diode.path):
            return True
        return bool(diode.stats) and _same_inode(info, diode.stats[-1])

    def refusal(why: str) -> tuple[None, str]:
        return None, f"{flag} {spelled}: {noun} {why}"

    while pending:
        part, via_link = pending.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            if done:
                done.pop()
                stats.pop()
            continue
        candidate = "/" + "/".join([*done, part])
        if any(info is None for info in stats):
            # Below a component that does not exist yet there is nothing to stat or to follow.
            if inside(candidate, None):
                return refusal(f"lies inside --diode-dir, or is reached through it (at {candidate})")
            done.append(part)
            stats.append(None)
            continue
        try:
            info: os.stat_result | None = os.lstat(candidate)
        except FileNotFoundError:
            if via_link:
                return refusal(f"is reached through a dangling symlink (at {candidate})")
            info = None
        except OSError as exc:
            what = "not a directory" if exc.errno == errno.ENOTDIR else "cannot be examined"
            return refusal(f"is {what} ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)} at {candidate})")
        if inside(candidate, info):
            return refusal(
                f"lies inside --diode-dir, or is reached through it (at {candidate}): what an agent can reach or "
                "retarget is never on the way to the executive's private files (ADR 0002 H)"
            )
        if info is not None and stat.S_ISLNK(info.st_mode):
            hops += 1
            if hops > MAX_LINK_HOPS:
                return refusal(f"cannot be resolved: more than {MAX_LINK_HOPS} symbolic links (a loop, at {candidate})")
            try:
                target = os.readlink(candidate)
            except OSError as exc:
                # The link was removed or replaced between its `lstat` and here: only someone who can
                # write the operator's directories can do that (a hop inside --diode-dir is refused
                # above, before it is read), and it is a refusal by name, not a traceback.
                return refusal(
                    f"changed between its check and its open ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)} "
                    f"at {candidate})"
                )
            if target.startswith("/"):
                done, stats = [], []
            pending = [(piece, True) for piece in target.split("/")] + pending
            continue
        done.append(part)
        stats.append(info)
    return Canonical(Path("/" + "/".join(done)), tuple(stats)), None


def walk_open_dir(canonical: Canonical, flag: str, *, create: bool) -> tuple[int | None, str | None]:
    """Open `canonical` once, from `/`, following nothing, and check that what is opened is what was seen.

    Each component is opened `O_DIRECTORY | O_NOFOLLOW` relative to its parent's handle, so a
    component that became a link since `canonicalise` is `ELOOP` and one that became a file is
    `ENOTDIR`; each that existed then must be the same inode now; with `create`, a component that did
    not exist is made and then opened the same way. The handle is the caller's to hold and to use
    for every access after this one (ADR 0002 H, child 2, third review). The walk's first open, of
    `/`, is refused as any component's is, naming the directory being walked rather than `/` alone
    (round 4: the start path's injection now reaches it with the path the kernel names).
    """
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as exc:
        return None, f"{flag} {canonical.path} cannot be opened at / ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror})"
    walked = Path("/")
    try:
        for index, part in enumerate(canonical.path.parts[1:]):
            walked = walked / part
            seen = canonical.stats[index]
            try:
                try:
                    opened = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                except FileNotFoundError:
                    if not create or seen is not None:
                        raise
                    with contextlib.suppress(FileExistsError):
                        os.mkdir(part, dir_fd=fd)
                    opened = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            except OSError as exc:
                return None, (
                    f"{flag} {canonical.path} changed between its check and its open, or cannot be opened, at "
                    f"{walked} ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror})"
                )
            # The child is the handle in hand before the parent is closed, so a failing `close` of the
            # parent leaves nothing behind: the child is closed on the way out (round 4, J4).
            parent, fd = fd, opened
            os.close(parent)
            if seen is not None and not _same_inode(os.fstat(fd), seen):
                return None, f"{flag} {canonical.path} changed between its check and its open: {walked} is another directory now"
        held, fd = fd, -1
        return held, None
    except BaseException:
        # Something already failed: that is what is raised, and a failure to close the handle in hand is not.
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)
            fd = -1
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def _diode_canonical(diode_dir: str | os.PathLike[str] | Canonical) -> tuple[Canonical | None, str | None]:
    """The diode directory's one resolution: the caller's own (`main` resolves `--diode-dir` once), or one made now.

    `main` passes the `Canonical` it resolved and then serves; resolving the operator's spelling again
    here let an alias retargeted between the two hold the private paths to another directory than the
    one served (confirmation G1). An in-process caller with only a path has it resolved here.
    """
    if isinstance(diode_dir, Canonical):
        return diode_dir, None
    return canonicalise("--diode-dir", diode_dir, "the diode directory")


def _checked_state(
    state_dir: str | os.PathLike[str], diode_dir: str | os.PathLike[str] | Canonical
) -> tuple[Canonical | None, str | None]:
    """The state directory's one canonicalisation, held to every rule, or the refusal.

    `canonicalise` holds every hop to the diode directory, so `diode/alpha/../.private`, a link planted
    outside the diode directory that points into it, a link in an agent's window that points outside
    it, and the diode directory itself are all refused. The symmetric overlap — the agents'
    directories inside the executive's private one — is refused too: nothing in H wants the
    adversary's directory under the thing it must not reach. A file, or a path below one, is not a
    directory. The comparison is of canonical paths and of the diode directory's inode, so one volume
    bind-mounted at both `/diode` and `/state` is caught only where the mount point itself is walked:
    one private volume, not shared with the diode volume, is the chassis's configuration constraint.
    """
    diode, problem = _diode_canonical(diode_dir)
    if problem is not None or diode is None:
        return None, problem
    state, problem = canonicalise("--state-dir", state_dir, "the state directory", diode=diode)
    if problem is not None or state is None:
        return None, problem
    if diode.path.is_relative_to(state.path):
        return None, (
            f"--diode-dir {diode.path} lies inside --state-dir {state_dir}: the agents' directories do "
            "not belong inside the executive's private one (ADR 0002 H)"
        )
    final = state.stats[-1] if state.stats else None
    if final is not None and not stat.S_ISDIR(final.st_mode):
        return None, f"--state-dir {state_dir}: the state directory {state.path} is not a directory"
    return state, None


def check_state_dir(state_dir: str | os.PathLike[str], diode_dir: str | os.PathLike[str] | Canonical) -> str | None:
    """The refusal for a `--state-dir` that overlaps `--diode-dir` anywhere on its way, or `None` (`_checked_state`)."""
    return _checked_state(state_dir, diode_dir)[1]


def open_private_dir(
    state_dir: str | os.PathLike[str], diode_dir: str | os.PathLike[str] | Canonical
) -> tuple[int | None, Path | None, str | None]:
    """The state directory checked, then opened once: `(handle, canonical path, refusal)`.

    One canonicalisation (`_checked_state`) and one open held to it (`walk_open_dir`). Everything
    after uses the handle, or, where a path is all an API takes, the canonical path — never the
    spelling, which is resolved here once and not again.
    """
    state, problem = _checked_state(state_dir, diode_dir)
    if problem is not None or state is None:
        return None, None, problem
    fd, problem = walk_open_dir(state, "--state-dir", create=True)
    return fd, (state.path if fd is not None else None), problem


def open_journal_dir(
    journal: str | os.PathLike[str], diode_dir: str | os.PathLike[str] | Canonical
) -> tuple[int | None, Path | None, str | None]:
    """An explicit `--journal` checked, and its directory opened once: `(handle, canonical file path, refusal)`.

    The journal file is canonicalised under the same hop rule as the state directory — the lineage
    and the truth hash never go where an agent can read them, nor through a link an agent can
    retarget — and its parent is opened by `walk_open_dir`, so every row is appended relative to
    that handle. The parent must exist; the file is made on the first append.
    """
    diode, problem = _diode_canonical(diode_dir)
    if problem is not None or diode is None:
        return None, None, problem
    canonical, problem = canonicalise("--journal", journal, "the journal", diode=diode)
    if problem is not None or canonical is None:
        return None, None, problem
    parent = Canonical(canonical.path.parent, canonical.stats[:-1])
    if any(info is None for info in parent.stats):
        return None, None, f"--journal {journal}: its directory {parent.path} does not exist; the journal's file is made, its directory is not"
    last = parent.stats[-1] if parent.stats else None
    if last is not None and not stat.S_ISDIR(last.st_mode):
        return None, None, f"--journal {journal}: {parent.path} is not a directory"
    fd, problem = walk_open_dir(parent, "--journal", create=False)
    return fd, (canonical.path if fd is not None else None), problem


def check_journal(journal: str | os.PathLike[str], diode_dir: str | os.PathLike[str] | Canonical) -> str | None:
    """The refusal for a `--journal` that the diode directory reaches, or `None` (`open_journal_dir`, handle closed)."""
    fd, _path, problem = open_journal_dir(journal, diode_dir)
    if fd is not None:
        os.close(fd)
    return problem


def superseded_record(record: dict[str, Any] | None, raw: bytes | None) -> dict[str, Any]:
    """What a rewrite event says of the record it replaces: identity and fingerprint, bounded (review F5).

    `previous` is the record's `SUPERSEDED_KEYS` that are present, or `None` when it had none to give
    (missing, garbled) or when they encode past `SUPERSEDED_IDENTITY_BYTES`, which `previous_omitted`
    then says. `previous_sha256` and `previous_bytes` are of the whole file as it was read, whenever
    there were bytes — a garbled record is still recognisable by them.
    """
    entry: dict[str, Any] = {
        "previous": None,
        "previous_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "previous_bytes": len(raw) if raw is not None else None,
    }
    if record is not None:
        identity = {key: record[key] for key in SUPERSEDED_KEYS if key in record}
        size = len(dumps_json(identity, sort_keys=True).encode("utf-8"))
        if size > SUPERSEDED_IDENTITY_BYTES:
            entry["previous_omitted"] = (
                f"the identity keys encode to {size} bytes, past the {SUPERSEDED_IDENTITY_BYTES} the "
                "journal keeps of a superseded record, so they are omitted and the fingerprint names it"
            )
        else:
            entry["previous"] = identity
    return entry


def journal_segment_path(state_dir: str | os.PathLike[str], boot_id: str) -> Path:
    """This boot's journal segment in the state directory (ADR 0002 J: one segment file per boot)."""
    return Path(state_dir) / JOURNAL_SEGMENT.format(boot_id=boot_id)


def append_journal_line(path: Path, row: dict[str, Any], *, dir_fd: int | None = None) -> None:
    """One JSON line onto the journal, made durable before this returns. A row with an `event` key is not a tick.

    Relative to `dir_fd`, the journal directory's handle, when the caller holds one; otherwise
    relative to a handle opened here on the path's parent. Either way the file itself is opened
    `O_NOFOLLOW`: the lineage is not appended through a link (second review, Codex P1). This is the
    startup events' writer — `main` journals a root-record rewrite *before* it rewrites (review F2) —
    and since child 4 it `fsync`s the line and then the directory, and creates the file `0600`, as the
    executive's own record writer does: an event the rewrite relies on is only journaled once its bytes
    and its name are on the disk, and the record is the operator's, not the host's other users'.
    """
    # Both handles close through `releasing` (fifth round, K1): a close that fails while the append's
    # own failure is on its way out — `RecordUnwritable` above all, which stops the run — is dropped,
    # never raised in its place.
    with contextlib.ExitStack() as handles:
        if dir_fd is None:
            dir_fd = handles.enter_context(releasing(open_directory(Path(path).parent)))
        fd = os.open(
            Path(path).name, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dir_fd
        )
        with releasing(fd):
            private_record_file(fd, str(path))
            # A previous boot's append torn by a kill, in a journal every boot shares, is ended first, so
            # this event is a line of its own and not the tail of a fragment (addendum B8).
            size = os.fstat(fd).st_size
            ending = TORN_TAIL_TERMINATOR if size > 0 and os.pread(fd, 1, size - 1) != b"\n" else b""
            append_or_restore(fd, ending + (dumps_json(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"), str(path))
        # The line is durable; the name, when this append made the file, is durable with its directory.
        os.fsync(dir_fd)


def private_record_file(fd: int, name: str) -> None:
    """The one rule for any file the record is appended to: this process's, and `0600`, or refused by name.

    `O_CREAT` sets no mode on a file that exists, so an operator's journal made `0644` before would stay
    readable with the lineage in it; one this process owns is made `0600` here, and one another user owns
    cannot be, so it is `RecordUnwritable` before anything is written. Both writers call it — the
    executive's (`Executive._record_handle`) and the startup events' (`append_journal_line`), which `main`
    runs first (child 4's review finding 8 and its confirmation review P2).
    """
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise RecordUnwritable(f"the record {name} is not a regular file")
    if info.st_uid != os.geteuid():
        raise RecordUnwritable(
            f"the record {name} is owned by uid {info.st_uid}, not by this process's {os.geteuid()}, so it "
            "cannot be made private (0600); name a journal this executive owns"
        )
    if stat.S_IMODE(info.st_mode) & 0o077:
        os.fchmod(fd, 0o600)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def append_or_restore(fd: int, data: bytes, name: str) -> None:
    """Append `data` to a record file and `fsync` it — or leave the file as it was, or stop (round 4, J2).

    **The one discipline for every append to a record file**, chained row or advisory event: the
    file's size is noted first; a write that fails part-way, or an `fsync` that fails, is undone by
    cutting the file back to that size and `fsync`ing the cut, and the error is raised. A partial
    append left in place was the defect: `checkpoint_or_record` suppressed its advisory event's
    failure, and the executive's held handle then appended the next cycle's row straight after the
    fragment — one line, ending in a plain newline, that does not parse, which recovery rightly refuses
    as corruption (H1). Ending the fragment with a terminator before the row instead would break H1's
    rule that a marked fragment is followed by no chained row; the cut restores what was there. One
    writer appends (`O_APPEND`, under the lock), so the size noted is where this append began. A cut
    that itself fails leaves a fragment no later append may follow: `RecordUnwritable`, and the run
    stops before another cycle.
    """
    before = os.fstat(fd).st_size
    try:
        _write_all(fd, data)
        os.fsync(fd)
    except OSError as exc:
        try:
            os.ftruncate(fd, before)
            os.fsync(fd)
        except OSError as again:
            raise RecordUnwritable(
                f"an append to the record {name} failed ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: "
                f"{exc.strerror}) and could not be cut back to byte {before}, where it began "
                f"({errno.errorcode.get(again.errno or 0, type(again).__name__)}: {again.strerror}), so the file may end "
                "in a fragment no row may follow"
            ) from again
        raise


# -- the record (ADR 0002 J, child 4; format v3, #23) -------------------------------------------
# **The journal is the record.** One segment per boot — `journal.<boot_id>.jsonl` in the state
# directory, or a run of rows inside an explicit `--journal` file — whose first row is a header
# (`event: segment`: the format, the boot, the world, the tick the boot's first cycle started at, the
# boot before it and the chain value that boot ended on, and the boot's clock — `m` as its exact
# fraction `"p/q"`, `k` and `N` — so a reader knows its cycle boundaries, `first_tick + i·k`), then one
# *tick row* per tick, and after each window's results a `results_written` note for that window. A tick
# row is `tick`, `world_id`, `boot_id`, the compare-point `state_hash` and the `lineage` link of that
# tick, the `effects` with their stamps in arbitration order, every verdict's `receipts` (global `seq`,
# window-local `local`, window, state, offset, command, body), the global `receipt` counter, the
# per-window `windows` deltas (spend, the window's receipt counter, deferrals added and removed, arm
# tokens set and cleared), the `published` mark of every window about to publish (the tick and the
# frame number it will write), the executive's `failures` count, and the cycle's start lag `lag_us`.
#
# **A cycle is `k` rows, and the reader holds them to one invariant** (#23, design §4): a cycle's
# **first** row carries the effects, the receipts, the window deltas, the new receipt counter and the
# previous cycle's carried-forward cost (`prev_cycle_us`, `prev_end_lag_us`, 0 on a segment's first
# cycle); rows 2..k carry `effects: []`, `receipts: []`, `windows: {}` and repeat the counter, which
# replay reads on every row; only the **last** row carries `published` marks. Receipts stay on row 1, so
# a receipt's tick is still its row's less one — the cycle's start — and the readers accumulate a
# cycle's receipts from its first row to the notes after its last. **`lag_us`, `prev_cycle_us` and
# `prev_end_lag_us` are wall data**: they ride in the row chain, for the record's integrity, and never
# in `state_hash`, the lineage, a compare-point or any replay decision; shedding (#26) records its
# decisions and never re-derives them from lag.
#
# **Every row carries `chain`** (format v2, child 4's review finding 3): the SHA-256 of the previous
# row's chain and the row's own canonical bytes (sorted compact JSON without `chain`), seeded by the
# header from the chain its predecessor ended on. Any edit, insertion or deletion of any line refuses
# by name at the line it touched — the non-physics half of a row (receipts, deltas, marks, notes) as
# well as the compare-point. It detects corruption and truncation, not a forger: there is no secret,
# and whoever can write the `0600` state directory can re-chain. Against that, every field is typed
# and bounded, a mark is its row's tick, a note is its row's, and the physics is re-run.
#
# **Every cycle writes its rows, quiet or not**: rule 2's mark is written at every publication, and a
# cycle always publishes (the mirror is rewritten every cycle), so `k` rows are appended and `fsync`ed
# every cycle anyway — the compare-points, the lineage links and the chain ride in them for bytes, not
# for an `fsync`. The ticks of a record are therefore contiguous by construction, a hole is a missing
# tick wherever it falls, and replay checks every tick against the run's own compare-point.
#
# **What one cycle may add is bounded, on the encoded bytes** (review finding 1). Rows are written as
# ASCII-escaped JSON, so every bound counts the escaped form (an `é` is six bytes, a lone surrogate
# twelve): a receipt's command keeps `RECORD_ECHO_BYTES`, its body `RECORD_TEXT_BYTES`, and each
# window's receipts in one cycle share `RECORD_WINDOW_BYTES`, past which a receipt is recorded
# fingerprint-only (`RECORD_FINGERPRINT_BYTES` at most); its result file is written in full either way.
# A window has at most `2 × --max-batch` verdicts a cycle (its batch and the deferrals it accepted the
# cycle before), and the deltas are bounded by the command schemas (a deferral is its parsed command,
# finding 4), so a row is at most `windows × (RECORD_WINDOW_BYTES + 2 × max_batch ×
# RECORD_FINGERPRINT_BYTES)` plus the deltas and a fixed overhead, whatever the agents send.
#
# The order inside a cycle is the three rules (review finding 6 made each promise a disk fact): a
# claimed batch's take and its window directory are `fsync`ed; **a cycle whose first row carries anything
# — effects, receipts or deltas — appends and `fsync`s that row before it steps on** (write-ahead, #23:
# the window in which a claimed batch exists only in memory stays one step), and its rows 2..k follow
# with one `fsync`; a cycle with nothing to record appends all `k` rows (and on the boot's first cycle
# the header with them) with one `fsync`; all of it **before** the root record, any result, frame or
# mirror is written; then, window by window, the results are written and each file `fsync`ed, the
# `output/` directory `fsync`ed, and the window's note appended and `fsync`ed, before its frame, mirror
# and generated files. A record that cannot be made durable stops the run by name (`RecordUnwritable`,
# exit 3); a recovery truncates a torn tail and replays to the last durable tick, so a partial cycle
# publishes nothing.


class RecordRefused(Exception):
    """A record this engine will not replay from: `check` names what failed, `tick` and `segment` where."""

    def __init__(self, check: str, why: str, *, tick: int | None = None, segment: str | None = None) -> None:
        self.check = check
        self.tick = tick
        self.segment = segment
        self.why = why
        where = []
        if tick is not None:
            where.append(f"tick {tick}")
        if segment is not None:
            where.append(f"segment {segment}")
        super().__init__(f"the record is refused ({check}{': ' + ', '.join(where) if where else ''}): {why}")


class RecordUnwritable(RuntimeError):
    """The record could not be appended or made durable: the run stops."""


def record_line(row: dict[str, Any]) -> bytes:
    """One row as the record writes it: sorted, compact, ASCII-escaped RFC 8259 JSON and a newline."""
    return (dumps_json(row, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def record_chain(previous: str, row: dict[str, Any]) -> str:
    """The chain value of `row` after `previous`: `sha256(previous + "\\n" + the row's canonical bytes)`.

    The canonical bytes are `record_line` of the row without its `chain` key, without the newline. A
    segment header's `previous` is the chain its predecessor ended on (`previous_chain`, `""` for the
    first segment of a world); every other row's is the row before it.
    """
    body = {key: value for key, value in row.items() if key != "chain"}
    return hashlib.sha256(previous.encode("ascii") + b"\n" + record_line(body)[:-1]).hexdigest()


def _encoded_len(text: str) -> int:
    """The bytes a string costs in a record row, quotes aside: its ASCII-escaped JSON form."""
    return len(json.dumps(text)) - 2


def _fingerprint(text: str) -> tuple[str, int]:
    """SHA-256 and length of the whole string as UTF-8, lone surrogates passed through rather than refused."""
    raw = text.encode("utf-8", "surrogatepass")
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _prefix(text: str, limit: int) -> str:
    """The longest prefix of `text` whose encoded form is at most `limit` bytes."""
    if _encoded_len(text) <= limit:
        return text
    low, high = 0, min(len(text), limit)
    while low < high:
        middle = (low + high + 1) // 2
        if _encoded_len(text[:middle]) <= limit:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def record_text(entry: dict[str, Any], key: str, text: str, limit: int = 0) -> None:
    """`entry[key] = text`, or its prefix within `limit` encoded bytes with `key_sha256` and `key_bytes` of the whole."""
    limit = limit or RECORD_TEXT_BYTES
    kept = _prefix(text, limit)
    entry[key] = kept
    if kept != text:
        entry[f"{key}_sha256"], entry[f"{key}_bytes"] = _fingerprint(text)


def lineage_link(previous: str, digest: str, effects: list[Effect]) -> str:
    """One link of the executive's lineage: `sha256(previous + compare-point + digest of the tick's effects)`."""
    effect_digest = hashlib.sha256(
        json.dumps([[e.offset_us, e.verb, e.arguments] for e in effects], sort_keys=True).encode("utf-8")
    ).hexdigest()
    return hashlib.sha256((previous + digest + effect_digest).encode("utf-8")).hexdigest()


def advance(
    world: World, truth: dict[str, Any], head: str, effects: list[Effect], dt: float
) -> tuple[dict[str, Any], str, str]:
    """One tick of the one world: `plant.step`, the compare-point, the lineage link — the live cycle's and replay's.

    Returns the stepped truth, its `state_hash` and the new link, and commits nothing: the caller
    commits all three together, so a state the compare-point refuses (`plant.UncomparableState`)
    leaves the caller at its last consistent tick. The hash is computed once and handed to the link
    (before child 4 the journal hashed the truth a second time for its row).
    """
    after = step(world, truth, dt, None, effects)
    digest = state_hash(after)
    return after, digest, lineage_link(head, digest, effects)


def value_of(values: dict[str, Any], state: Any) -> list[str]:
    """The current value(s) of a state, as text, wherever the map keeps them — a map's in key order.

    In key order because the checkpoint and the record encode maps with sorted keys: in the map's own
    insertion order, a value recorded live and the same value after a restore compared as different
    lists, and a dwell's return guard could miss (confirmation review, Opus 2).
    """
    if state.node == "internal":
        value = (values.get("internal") or {}).get(state.id)
    else:
        value = values.get(state.node)
    if isinstance(value, dict):
        return [_value_text(v) for _key, v in sorted(value.items(), key=lambda item: str(item[0]))]
    return [] if value is None else [_value_text(value)]


def _value_text(value: Any) -> str:
    """A state's value as text that does not depend on insertion order, at any depth.

    A scalar is its `str`, as it always was. A map or a list is canonical JSON, because a value held
    inside a node is itself a map — `rcs_valves = {thruster_valve: {sm_primary: …, sm_secondary: …}}`
    — and `str()` of it kept the live insertion order while a replayed one came back sorted, so the
    replayed executive differed from the live one in `dwell` (confirmation review, Opus, at c8f41c2).
    """
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return str(value)


def dwell_after_effect(
    world: World, dwell: dict[str, Any], verb: str, now_us: int, before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    """Restart the dwell clock of every state a verb moved, and say what moved: the live cycle's and replay's.

    Written where a value actually moved — a command that set what was already set changed nothing and
    must not restart the floor — and the value left is the value the state held before the change.
    Returns `node=level` (or `internal:id=level`) for each moved target, for the result's sentence.
    """
    changed: list[str] = []
    for state in command_targets(world, verb):
        if value_of(before, state) == value_of(after, state):
            continue
        level = state_level(after, state)
        changed.append(f"internal:{state.id}={level}" if state.node == "internal" else f"{state.node}={level}")
    if changed:
        for state, _, _ in command_dwell(world, verb):
            left = value_of(before, state)
            dwell[state.id] = {
                "changed_at_us": now_us,
                "value": value_of(after, state),
                "was": {"value": left, "left_at_us": now_us} if left else None,
            }
    return changed


def canonical_command(verb: str, arguments: dict[str, str]) -> str:
    """The command a parse spells: the verb and each argument once, `key=value`, in key order.

    A deferral is queued, checkpointed and recorded as this (review finding 4): `parse_arguments`
    keeps the last value of a repeated key and ignores tokens without `=`, so the raw line and its
    parse can differ, and a prefix of the raw line can parse to *another valid command*. The keys are
    sorted because every encoding of `arguments` sorts them: spelled in the agent's order, a deferral
    written `target=… source=…` was accepted live and failed its own check on read-back (confirmation
    review P1).
    """
    return " ".join([verb, *(f"{key}={value}" for key, value in sorted(arguments.items()))])


def receipt_entries(verdicts: list[Verdict]) -> list[dict[str, Any]]:
    """One window's receipts for a tick row, within `RECORD_WINDOW_BYTES`; past it, fingerprint-only.

    A full entry keeps the command to `RECORD_ECHO_BYTES` and the body to `RECORD_TEXT_BYTES`, each with
    the whole's fingerprint when cut. A fingerprint-only entry keeps the receipt numbers, the state, the
    offset, a prefix of the verb, and the SHA-256 and length of the command and the body: what a
    resume needs to number the window's next result and to recognise this one, and no more.
    """
    entries: list[dict[str, Any]] = []
    used = 0
    for verdict in verdicts:
        entry: dict[str, Any] = {
            "seq": verdict.receipt,
            "local": verdict.local,
            "window": verdict.window,
            "state": verdict.state,
            "offset_us": verdict.effect.offset_us if verdict.effect is not None else 0,
        }
        full = dict(entry)
        record_text(full, "command", verdict.command, RECORD_ECHO_BYTES)
        record_text(full, "body", verdict.body, RECORD_TEXT_BYTES)
        size = len(record_line(full))
        if used + size > RECORD_WINDOW_BYTES:
            full = entry
            full["fingerprint_only"] = True
            full["verb"] = _prefix(str(verdict.verb or verdict.command.split(" ", 1)[0]), 64)
            full["command_sha256"], full["command_bytes"] = _fingerprint(verdict.command)
            full["body_sha256"], full["body_bytes"] = _fingerprint(verdict.body)
            size = len(record_line(full))
        used += size
        entries.append(full)
    return entries


# -- the record's schema: every field typed and bounded, or a named refusal ----------------------
_HEX64 = re.compile(r"[0-9a-f]{64}")
# `plant.state_hash` is a prefix of a SHA-256 (sixteen hex digits today); the reader takes 16 to 64.
_COMPARE_POINT = re.compile(r"[0-9a-f]{16,64}")
_IDENT = re.compile(r"[A-Za-z0-9_-]{1,64}")
VERDICT_STATES = frozenset({"accepted", "refused", "settled", "duplicate", "superseded", "deferred"})
_ROW_KEYS = frozenset(
    {"tick", "world_id", "boot_id", "lineage", "state_hash", "effects", "receipts", "receipt", "windows", "published", "failures", "chain", "lag_us"}
)
# A cycle's first row: every row's keys, and the previous cycle's carried-forward cost (#23, design §2).
_CYCLE_ROW_KEYS = _ROW_KEYS | {"prev_cycle_us", "prev_end_lag_us"}
_HEADER_KEYS = frozenset(
    {"event", "format", "world_id", "segment", "boot_id", "first_tick", "previous", "previous_chain", "wall_epoch", "chain", "m", "k", "N"}
)
_NOTE_KEYS = frozenset({"event", "boot_id", "world_id", "tick", "results", "chain"})
_RECEIPT_KEYS = frozenset({"seq", "local", "window", "state", "offset_us"})
_RECEIPT_TEXT = frozenset({"command", "body", "command_sha256", "command_bytes", "body_sha256", "body_bytes"})
_DELTA_KEYS = frozenset({"spend", "receipts", "deferred_removed", "deferred_added", "arms_set", "arms_cleared"})
_DEFERRAL_KEYS = frozenset({"verb", "command", "arguments", "accepted_tick", "due_tick", "maximum_queue_age_s", "receipt"})


def _count(value: Any, low: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= low


def _text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and _encoded_len(value) <= limit


def _ident(value: Any) -> bool:
    return isinstance(value, str) and _IDENT.fullmatch(value) is not None


def _hex(value: Any) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _arguments_problem(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "arguments are not an object"
    for name, given in value.items():
        if not _text(name, 768) or not _text(given, ARGUMENT_RECORD_BYTES):
            return f"argument {bounded_repr(name)} is not a bounded string pair"
    return None


def _deferral_problem(entry: Any) -> str | None:
    if not isinstance(entry, dict) or set(entry) != _DEFERRAL_KEYS:
        return "a deferral entry is not the parsed command's seven fields"
    if not _text(entry["verb"], 128) or not _text(entry["command"], 16 * ARGUMENT_RECORD_BYTES):
        return "a deferral's verb or command is not a bounded string"
    problem = _arguments_problem(entry["arguments"])
    if problem is not None:
        return f"a deferral's {problem}"
    if entry["command"] != canonical_command(entry["verb"], entry["arguments"]):
        return "a deferral's command is not the one its verb and arguments spell"
    if not (_count(entry["accepted_tick"]) and _count(entry["due_tick"]) and _count(entry["receipt"], 1)):
        return "a deferral's ticks or receipt are not counts"
    age = entry["maximum_queue_age_s"]
    if age is not None and (isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(age) or age < 0):
        return "a deferral's maximum_queue_age_s is neither null nor a non-negative number"
    return None


def _receipt_problem(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return "a receipt is not an object"
    keys = set(entry)
    if not keys >= _RECEIPT_KEYS:
        return "a receipt lacks one of seq, local, window, state, offset_us"
    if not (_count(entry["seq"], 1) and _count(entry["local"], 1) and _ident(entry["window"]) and _count(entry["offset_us"])):
        return "a receipt's numbers or window are not what a receipt carries"
    if entry["state"] not in VERDICT_STATES:
        return f"a receipt's state {bounded_repr(entry['state'])} is not a verdict state"
    if entry.get("fingerprint_only") is True:
        if keys != _RECEIPT_KEYS | {"fingerprint_only", "verb", "command_sha256", "command_bytes", "body_sha256", "body_bytes"}:
            return "a fingerprint-only receipt does not carry exactly its fingerprint"
        if not (_text(entry["verb"], 64) and _hex(entry["command_sha256"]) and _hex(entry["body_sha256"])):
            return "a fingerprint-only receipt's verb or fingerprints are malformed"
        if not (_count(entry["command_bytes"]) and _count(entry["body_bytes"])):
            return "a fingerprint-only receipt's lengths are not counts"
        return None
    if not keys <= _RECEIPT_KEYS | _RECEIPT_TEXT or not {"command", "body"} <= keys:
        return "a receipt carries a key a receipt does not, or lacks its command or body"
    if not (_text(entry["command"], RECORD_ECHO_BYTES) and _text(entry["body"], RECORD_TEXT_BYTES)):
        return "a receipt's command or body is past its bound"
    for key in ("command", "body"):
        if (f"{key}_sha256" in entry) != (f"{key}_bytes" in entry):
            return f"a receipt's {key} fingerprint is half there"
        if f"{key}_sha256" in entry and not (_hex(entry[f"{key}_sha256"]) and _count(entry[f"{key}_bytes"])):
            return f"a receipt's {key} fingerprint is malformed"
    return None


def _delta_problem(delta: Any) -> str | None:
    if not isinstance(delta, dict) or not set(delta) <= _DELTA_KEYS:
        return "a window's delta is not an object of the six delta keys"
    spend = delta.get("spend")
    if spend is not None and not (isinstance(spend, dict) and set(spend) == {"version", "accepted"} and _count(spend["version"]) and _count(spend["accepted"])):
        return "a window's spend delta is not a version and an accepted count"
    if "receipts" in delta and not _count(delta["receipts"]):
        return "a window's receipt counter is not a count"
    removed = delta.get("deferred_removed", [])
    if not isinstance(removed, list) or not all(_count(r, 1) for r in removed):
        return "a window's removed deferrals are not receipt numbers"
    added = delta.get("deferred_added", [])
    if not isinstance(added, list):
        return "a window's added deferrals are not a list"
    for entry in added:
        problem = _deferral_problem(entry)
        if problem is not None:
            return problem
    armed = delta.get("arms_set", {})
    if not isinstance(armed, dict) or not all(_text(k, ARGUMENT_RECORD_BYTES) and _text(v, 64) for k, v in armed.items()):
        return "a window's arm tokens are not bounded string pairs"
    cleared = delta.get("arms_cleared", [])
    if not isinstance(cleared, list) or not all(_text(k, ARGUMENT_RECORD_BYTES) for k in cleared):
        return "a window's cleared arms are not bounded strings"
    return None


def _row_problem(row: dict[str, Any]) -> tuple[str, str] | None:
    """`(check, sentence)` for the first thing about a tick row this format cannot vouch for, or `None`.

    A row is a cycle's first (`_CYCLE_ROW_KEYS`) or one of the others (`_ROW_KEYS`); which it must be,
    by its position in its segment's cycles, is `_cycle_row_problem`'s.
    """
    keys = set(row)
    if keys not in (_ROW_KEYS, _CYCLE_ROW_KEYS):
        return "row", f"the row's keys are not a tick row's ({sorted(keys ^ (_CYCLE_ROW_KEYS if 'prev_cycle_us' in keys else _ROW_KEYS))})"
    if not (_count(row["tick"], 1) and _ident(row["world_id"]) and _ident(row["boot_id"])):
        return "row", "the row's tick, world or boot is malformed"
    if not all(_count(row[key]) for key in ("lag_us", "prev_cycle_us", "prev_end_lag_us") if key in row):
        return "row", "the row's lag or carried-forward cost is not a count of microseconds"
    compare_point = row["state_hash"]
    if not (isinstance(compare_point, str) and _COMPARE_POINT.fullmatch(compare_point)):
        return "row", "the row's compare-point is not a state hash"
    if not (_hex(row["lineage"]) and _count(row["receipt"]) and _count(row["failures"])):
        return "row", "the row's lineage or counters are malformed"
    effects = row["effects"]
    if not isinstance(effects, list):
        return "row", "the row's effects are not a list"
    for effect in effects:
        if not (isinstance(effect, list) and len(effect) == 3 and _count(effect[0]) and _text(effect[1], 128)):
            return "row", "an effect is not `[offset_us, verb, arguments]`"
        problem = _arguments_problem(effect[2])
        if problem is not None:
            return "row", f"an effect's {problem}"
    receipts = row["receipts"]
    if not isinstance(receipts, list):
        return "row", "the row's receipts are not a list"
    for entry in receipts:
        problem = _receipt_problem(entry)
        if problem is not None:
            return "row", problem
    windows = row["windows"]
    if not isinstance(windows, dict):
        return "row", "the row's window deltas are not an object"
    for slug, delta in windows.items():
        problem = None if _ident(slug) else "a window name is not a slug"
        problem = problem or _delta_problem(delta)
        if problem is not None:
            return "row", problem
    published = row["published"]
    if not isinstance(published, dict):
        return "row", "the row's marks are not an object"
    for slug, mark in published.items():
        if not (_ident(slug) and isinstance(mark, dict) and set(mark) == {"tick", "seq"} and _count(mark["tick"]) and _count(mark["seq"])):
            return "published", f"the mark of {bounded_repr(slug)} is not a tick and a frame number"
        if mark["tick"] != row["tick"] or mark["seq"] >= row["tick"]:
            return "published", (
                f"window {slug!r} is marked at tick {mark['tick']} with frame {mark['seq']} in the row for tick {row['tick']}: a mark is "
                "its row's own tick, and a window has written fewer frames than the ticks it has seen"
            )
    return None


def _segment_clock_problem(entry: dict[str, Any]) -> str | None:
    """Why a header's (or a checkpoint segment entry's) `m`, `k`, `N` are not a boot's clock, or `None`."""
    m = entry.get("m")
    if not (isinstance(m, str) and MULTIPLIER_TEXT.fullmatch(m) and multiplier_text(m) == m):
        return f"the segment's multiplier {bounded_repr(m)} is not an exact fraction `p/q` in lowest terms"
    if not (_count(entry.get("k"), 1) and _count(entry.get("N"), 1) and entry["N"] % entry["k"] == 0):
        return "the segment's k and N are not positive tick counts with N a multiple of k"
    return None


def _cycle_row_problem(row: dict[str, Any], header: dict[str, Any], cycle_first: tuple[int, int] | None = None) -> str | None:
    """The row invariant (#23, design §4): what a row at its position in its segment's cycles must and must not carry.

    The segment's cycles begin at `first_tick + i·k`, so a row is its cycle's first when
    `(tick − first_tick − 1) mod k = 0` and its last when `(tick − first_tick) mod k = 0`. The first
    carries the carried-forward cost; the others carry no effect, receipt or delta, **and repeat the
    first's receipt counter and start lag** (`cycle_first`, `(receipt, lag_us)` of the cycle's first row as this
    read met it; candidate 1, Codex P2): a cycle draws its receipts before its first step and has one
    start, so an interior row with another counter or another lag is not one this vehicle wrote — replay
    would otherwise take a raised counter from a re-chained interior row. A row that is not its cycle's
    last carries no `published` mark. A read that begins inside a cycle has no first row to hold the
    others to; no anchor does (a checkpoint's is at a cycle's end, or a dead segment's).
    """
    offset = row["tick"] - int(header["first_tick"])
    k = int(header["k"])
    first = (offset - 1) % k == 0
    if first != ("prev_cycle_us" in row):
        return (
            f"the row for tick {row['tick']} is the first of a cycle of {k} from tick {header['first_tick']} and carries no carried-forward cost"
            if first else f"the row for tick {row['tick']} is inside a cycle of {k} from tick {header['first_tick']} and carries a carried-forward cost"
        )
    if not first and (row["effects"] or row["receipts"] or row["windows"]):
        return f"the row for tick {row['tick']} is inside its cycle and carries effects, receipts or deltas, which are the cycle's first row's"
    # `cycle_first` is `None` only when this read met no first row of the cycle: a read that begins inside
    # a cycle. None does — every anchor is at a cycle boundary: a genesis checkpoint (before any row), a
    # cadence or clean-end checkpoint (after its cycle's notes), or a resume's at a dead segment's end, after
    # which that segment holds no more rows — so the skip is only for a first row the read never had.
    if not first and cycle_first is not None and (row["receipt"], row["lag_us"]) != cycle_first:
        return (
            f"the row for tick {row['tick']} is inside its cycle and carries receipt counter {row['receipt']} and lag {row['lag_us']} µs, "
            f"where the cycle's first row carries {cycle_first[0]} and {cycle_first[1]} µs: a cycle has one counter and one start"
        )
    if offset % k != 0 and row["published"]:
        return f"the row for tick {row['tick']} is not the last of its cycle and carries a published mark"
    return None


def _header_problem(row: dict[str, Any]) -> str | None:
    if set(row) != _HEADER_KEYS:
        return f"the header's keys are not a segment header's ({sorted(set(row) ^ _HEADER_KEYS)})"
    if not (_ident(row["world_id"]) and _ident(row["boot_id"]) and row["segment"] == row["boot_id"] and _count(row["first_tick"])):
        return "the header's world, boot, segment or first tick is malformed"
    problem = _segment_clock_problem(row)
    if problem is not None:
        return problem
    if row["previous"] is not None and not _ident(row["previous"]):
        return "the header's predecessor is not a boot"
    if row["previous_chain"] != "" and not _hex(row["previous_chain"]):
        return "the header's predecessor chain is not a chain value"
    if not _text(row["wall_epoch"], 64):
        return "the header's wall epoch is not a stamp"
    return None


def _note_problem(row: dict[str, Any]) -> str | None:
    if set(row) != _NOTE_KEYS:
        return f"the note's keys are not a results note's ({sorted(set(row) ^ _NOTE_KEYS)})"
    if not (_ident(row["boot_id"]) and _ident(row["world_id"]) and _count(row["tick"], 1)):
        return "the note's boot, world or tick is malformed"
    results = row["results"]
    if not isinstance(results, dict) or not results:
        return "the note names no results"
    for slug, locals_ in results.items():
        if not (_ident(slug) and isinstance(locals_, list) and locals_ and all(_count(n, 1) for n in locals_) and len(set(locals_)) == len(locals_)):
            return f"the note's results for {bounded_repr(slug)} are not distinct receipt numbers"
    return None


@dataclass
class SegmentInfo:
    """One boot's run of the record, as the first pass found it: its header, its range and its last chain value."""

    boot_id: str
    name: str
    header: dict[str, Any]
    last_tick: int
    chain: str
    rows: int = 0
    torn: bool = False
    offset: int = 0
    line: int = 1
    # The byte offset just after the segment's last intact line (its header, a row or a note), in its
    # file: what a checkpoint's segment entry records as `offset` (addendum B5).
    end: int = 0
    # A segment read from a checkpoint's anchor: its header is built from the checkpoint's entry rather
    # than read, and its lines are verified from `offset` on, seeded with the anchor's chain and tick.
    anchor_tick: int | None = None
    # The byte offset just after the header line (the anchor's offset for an anchored segment).
    header_end: int = 0

    @property
    def first_tick(self) -> int:
        return int(self.header["first_tick"])

    @property
    def anchored(self) -> bool:
        return self.anchor_tick is not None

    @property
    def previous(self) -> str | None:
        return self.header.get("previous")


def _file_lines(
    dir_fd: int, name: str, offset: int = 0, first: int = 1
) -> Iterator[tuple[int, int, int, dict[str, Any] | None, str]]:
    """`(line number, byte offset, end offset, object or None, ending)` for each line of one journal file from `offset`, bounded.

    `ending` is `line` for an object, else `_fragment_kind`'s: `unterminated`, `marked` or `plain`.

    `offset` and `first` start the read at a line the first pass found (a segment's header), so a
    second pass over one segment of a shared `--journal` does not re-read the boots before it
    (confirmation review P2).

    `None` is a line that is not a complete JSON object (a torn append, or worse — the caller decides
    which). A line past `MAX_RECORD_LINE_BYTES` refuses, but for a marked fragment's terminator. Nothing
    is kept: memory is one line.
    """
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError as exc:
        why = "is a symlink" if exc.errno == errno.ELOOP else f"cannot be opened ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)})"
        raise RecordRefused("file", f"{name} {why}") from None
    with os.fdopen(fd, "rb") as handle:
        try:
            regular = stat.S_ISREG(os.fstat(fd).st_mode)
        except OSError as exc:
            raise RecordRefused("file", f"{name} cannot be examined ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)})") from None
        if not regular:
            raise RecordRefused("file", f"{name} is not a regular file")
        limit = MAX_RECORD_LINE_BYTES
        # A marked fragment may be longer than any line the writer writes: the longest line cut just
        # before its newline is `limit - 1` bytes, and its terminator makes it `limit + 1` (fourth round,
        # J3) — or `limit + 2` where a cut fell inside an earlier terminator. A line ending in the
        # terminator is allowed `len(TORN_TAIL_TERMINATOR)` bytes past the bound; any other is not.
        marked_limit = limit + len(TORN_TAIL_TERMINATOR)
        number = first - 1
        try:
            handle.seek(offset)
        except OSError as exc:
            raise RecordRefused("file", f"{name} cannot be read ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)})") from None
        while True:
            try:
                at = handle.tell()
                raw = handle.readline(marked_limit + 1)
            except OSError as exc:
                raise RecordRefused(
                    "file", f"{name} cannot be read after line {number} ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)})"
                ) from None
            if not raw:
                return
            number += 1
            # The bound counts the newline, as the writer's does: a line it would not write is refused,
            # and a marked fragment is allowed its terminator past it.
            if len(raw) > limit and not (len(raw) <= marked_limit and raw.endswith(TORN_TAIL_TERMINATOR)):
                raise RecordRefused("line", f"line {number} of {name} is longer than the {limit} bytes a record line may be")
            row = None
            if raw.endswith(b"\n"):
                try:
                    row = loads_json(raw[:-1].decode("utf-8"))
                except Exception:  # noqa: BLE001 - any decoder failure is "not an object"
                    row = None
            parsed = row if isinstance(row, dict) else None
            yield number, at, handle.tell(), parsed, ("line" if parsed is not None else _fragment_kind(raw))


# What ends an unterminated tail before anything else is appended to a journal file (review F13). A write
# torn exactly after a line's closing brace leaves complete JSON with no newline; ending it with a bare
# `\n` turned that fragment into a valid line *behind* the boot that resumed past it. `#` never parses
# as JSON whatever precedes it, so the fragment stays the torn fragment it is (`_torn_aware_lines`).
TORN_TAIL_TERMINATOR = b"#\n"


def _fragment_kind(raw: bytes) -> str:
    """How an unparseable line ends: `unterminated` (a kill cut it, and it is its file's last line),
    `marked` (a later writer ended that cut tail with `TORN_TAIL_TERMINATOR`), or `plain` (corruption)."""
    if not raw.endswith(b"\n"):
        return "unterminated"
    return "marked" if raw.endswith(TORN_TAIL_TERMINATOR) else "plain"


def _torn_aware_lines(
    dir_fd: int, name: str, offset: int = 0, first: int = 1
) -> Iterator[tuple[str, int, int, int, dict[str, Any] | None]]:
    """`(kind, line, offset, end, row)` for each line of one journal file, with the one rule for an unparseable line.

    `kind` is `line` (a JSON object: a header, a row, a note or a startup event) or `torn` (row `None`).
    **The terminator rule** (round 3, H1; it supersedes R1's position test and G5's adjacency rule): an
    unparseable line is a torn fragment — a write a kill cut, from which nothing was published — if and
    only if it is its file's final, unterminated line, or it ends with `TORN_TAIL_TERMINATOR`, the mark
    every writer puts on a cut tail before it appends anything after it. A marked fragment may be
    followed only by a new boot's unchained startup event, a segment header, another fragment, or the
    end of the file — what repeated kills at a start leave, a boot's cut `resumed` event marked by the
    next boot's included — never by a chained row or note. An unparseable line ending in a plain newline
    was neither cut by a kill nor marked by a writer: it is corruption wherever it is, which is also
    what keeps a file whose every line is damaged from reading as empty (G5). Every reader of the record
    — the whole-record read, the anchored read, a successor's first header, the replay — reads through
    this one predicate.
    """
    marked: tuple[int, int, int] | None = None
    for number, at, end, row, ending in _file_lines(dir_fd, name, offset, first):
        if row is None:
            if ending == "plain":
                raise RecordRefused(
                    "corrupt",
                    f"line {number} of {name} is not a JSON object and ends in a plain newline: a kill leaves a cut tail "
                    f"unterminated, and the next writer marks it ({TORN_TAIL_TERMINATOR!r}), so this was neither",
                )
            if marked is not None:
                yield "torn", *marked, None
                marked = None
            if ending == "unterminated":
                yield "torn", number, at, end, None  # the file's last line: nothing follows it
                continue
            marked = (number, at, end)
            continue
        if marked is not None:
            if row.get("event") != "segment" and not _startup_event(row):
                raise RecordRefused(
                    "corrupt",
                    f"line {marked[0]} of {name} is a marked fragment and a chained record line follows it: a writer marks a cut "
                    "tail only to append a startup event or a new boot's header after it",
                )
            yield "torn", *marked, None
            marked = None
        yield "line", number, at, end, row
    if marked is not None:
        yield "torn", *marked, None


def _verified_lines(
    dir_fd: int,
    name: str,
    offset: int = 0,
    first: int = 1,
    seed: tuple[dict[str, Any], str, int] | None = None,
) -> Iterator[tuple[str, int, int, int, dict[str, Any]]]:
    """Every line of one journal file from `offset` that belongs to the trace, verified: `(kind, line, offset, end, row)`.

    With `seed` — `(header, chain, tick)` from a checkpoint's anchor (addendum B5) — the read starts
    inside a segment, as if its header had been read and its lines up to the anchor verified: the rows
    that follow are held to that header's world and boot, to the anchor's chain, and to the tick after
    the anchor's. Line numbers then count from the anchor.

    `kind` is `header`, `row`, `note`, or `torn` (the row is then `{}`, and closes its segment). Each
    header starts a segment and is held to its schema and its format; each tick row to the tick after
    the last (`missing` or `order`), to the chain (`chain`), then to its schema (`row`, `published`) and
    to the row invariant at its place in the header's cycles of `k` (`row`, #23); each note to the chain,
    its schema, and its cycle (`note`: the same world, boot and tick as the cycle's last row, naming only
    receipts the cycle's first row issued, each once — the receipts are accumulated from a cycle's first
    row to its notes, not reset at every row). A line that is not an object is a torn append or corruption by
    `_torn_aware_lines`' one rule (R1); a torn line with no header before it in its file is a boot torn
    before its header (design note F2), and is dropped. Whether a torn segment was really the end of its
    boot is the seam's question (`concatenated`): the next segment names the chain its predecessor ended
    on. A startup event (child 2) is the operator's, unchained, and not part of the trace.
    """
    header: dict[str, Any] | None = None
    chain = ""
    last_tick: int | None = None
    if seed is not None:
        header, chain, last_tick = seed
    receipts: set[tuple[str, int]] = set()
    noted: set[tuple[str, int]] = set()
    # The receipt counter and start lag of the current cycle's first row, which rows 2..k repeat (#23).
    cycle_first: tuple[int, int] | None = None
    for kind, number, at, end, row in _torn_aware_lines(dir_fd, name, offset, first):
        if kind == "torn" or row is None:
            # A fragment R1 accepts: the last line of its segment (a later boot's header may follow).
            yield "torn", number, at, end, {}
            continue
        event = row.get("event")
        segment = header["boot_id"] if header is not None else None
        if event == "segment":
            written = row.get("format")
            if written != RECORD_FORMAT:
                raise RecordRefused(
                    "format", f"line {number} of {name} is a segment of format {bounded_repr(written)} and this engine reads {RECORD_FORMAT!r}"
                )
            problem = _header_problem(row)
            if problem is not None:
                raise RecordRefused("header", f"line {number} of {name}: {problem}")
            if row.get("chain") != record_chain(row["previous_chain"], row):
                raise RecordRefused("chain", f"line {number} of {name}: the header's chain value is not its own", segment=row["boot_id"])
            header, chain, last_tick, receipts, noted = row, row["chain"], int(row["first_tick"]), set(), set()
            cycle_first = None
            yield "header", number, at, end, row
            continue
        if _startup_event(row):
            continue  # a startup event (child 2): the operator's, and not part of the trace
        if header is None:
            raise RecordRefused("header", f"line {number} of {name} comes before any segment header", tick=row.get("tick") if _count(row.get("tick")) else None)
        tick = row.get("tick")
        if event is not None and _count(tick, 1) and last_tick is not None and tick > last_tick:
            raise RecordRefused(
                "missing", f"the record has no cycle for tick {last_tick + 1}: a note for tick {tick} follows the row for tick {last_tick} "
                f"in segment {segment}", tick=last_tick + 1, segment=segment,
            )
        if event is None and _count(tick, 1) and last_tick is not None and tick != last_tick + 1:
            if tick > last_tick + 1:
                raise RecordRefused(
                    "missing", f"the record has no cycle for tick {last_tick + 1}: segment {segment} goes from tick {last_tick} to tick {tick}",
                    tick=last_tick + 1, segment=segment,
                )
            raise RecordRefused("order", f"line {number} of {name} is tick {tick} after tick {last_tick}", tick=tick, segment=segment)
        if row.get("chain") != record_chain(chain, row):
            raise RecordRefused(
                "chain", f"line {number} of {name} does not follow from the line before it: an edit, an insertion or a deletion",
                tick=tick if _count(tick) else None, segment=segment,
            )
        if event == "results_written":
            problem = _note_problem(row)
            named = {(slug, n) for slug, locals_ in row["results"].items() for n in locals_} if problem is None else set()
            if problem is None and (row["world_id"], row["boot_id"], row["tick"]) != (header["world_id"], header["boot_id"], last_tick):
                problem = f"the note names world {row['world_id']}, boot {row['boot_id']} and tick {row['tick']}, not its row's"
            if problem is None and last_tick is not None and (last_tick - int(header["first_tick"])) % int(header["k"]) != 0:
                problem = f"the note follows the row for tick {last_tick}, which is not the last of its cycle of {header['k']}"
            if problem is None and not named <= receipts - noted:
                problem = f"the note names results {sorted(named - (receipts - noted))} its row did not issue, or that another note named"
            if problem is not None:
                raise RecordRefused("note", f"line {number} of {name}: {problem}", tick=row.get("tick") if _count(row.get("tick")) else None, segment=segment)
            noted |= named
            chain = row["chain"]
            yield "note", number, at, end, row
            continue
        found = _row_problem(row)
        if found is not None:
            raise RecordRefused(found[0], f"line {number} of {name}: {found[1]}", tick=tick if _count(tick) else None, segment=segment)
        if (row["world_id"], row["boot_id"]) != (header["world_id"], header["boot_id"]):
            raise RecordRefused("row", f"line {number} of {name} is of world {row['world_id']}, boot {row['boot_id']}, not its header's", tick=tick, segment=segment)
        problem = _cycle_row_problem(row, header, cycle_first)
        if problem is not None:
            raise RecordRefused("row", f"line {number} of {name}: {problem}", tick=tick, segment=segment)
        chain, last_tick = row["chain"], tick
        if "prev_cycle_us" in row:
            # A cycle's first row: the receipts it issues are the cycle's, and the notes after the cycle's
            # last row name them (#23, design §4). Rows 2..k issue none and reset nothing.
            receipts, noted = {(r["window"], r["local"]) for r in row["receipts"]}, set()
            cycle_first = (row["receipt"], row["lag_us"])
        yield "row", number, at, end, row


def _startup_event(row: dict[str, Any]) -> bool:
    """A startup event (child 2's): the operator's, unchained, and not part of the trace."""
    event = row.get("event")
    return event is not None and event not in ("segment", "results_written")


class Record:
    """The record's segments, checked once end to end, and a way to stream any of them again.

    `read_record` makes one: a first pass over every journal file verifies every line (`_verified_lines`)
    and keeps only each segment's header, last tick, last chain value, row count and whether it ended
    torn, and where its header is. `lines(segment)` streams that segment again from its header,
    verifying it again, so what is replayed is what was checked; nothing is held between lines, and the
    record is read twice in all however many boots share a file. The directory handle is a duplicate the record owns.
    """

    def __init__(self, where: Path, dir_fd: int, segments: list[SegmentInfo]) -> None:
        self.where = where
        self._fd: int | None = dir_fd
        self.segments = segments

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Record:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()

    def lines(self, segment: SegmentInfo) -> Iterator[tuple[str, dict[str, Any], int]]:
        """`(kind, row, end)` for the segment's rows and notes, in order, verified again; its summary must still hold.

        `end` is the byte offset just after the line, in the segment's file. An anchored segment is
        streamed from its anchor, seeded as the first pass was (addendum B5).
        """
        if self._fd is None:
            raise RecordRefused("file", "the record has been closed")
        seed = (segment.header, segment.header["chain"], segment.anchor_tick) if segment.anchor_tick is not None else None
        inside = seed is not None
        last_tick = segment.anchor_tick if segment.anchor_tick is not None else segment.first_tick
        chain, rows = segment.header["chain"], 0
        for kind, _number, _at, end, row in _verified_lines(self._fd, segment.name, segment.offset, segment.line, seed):
            if kind == "header":
                if inside:
                    break
                inside = row["boot_id"] == segment.boot_id
                continue
            if not inside:
                continue
            if kind == "torn":
                break
            chain = row["chain"]
            if kind == "row":
                last_tick, rows = row["tick"], rows + 1
            yield kind, row, end
        if (last_tick, chain, rows) != (segment.last_tick, segment.chain, segment.rows):
            raise RecordRefused("changed", f"{segment.name} changed between its check and its replay", segment=segment.boot_id)

    def events(self, segment: SegmentInfo, names: set[str], since: int | None = None) -> Iterator[dict[str, Any]]:
        """The segment's own unchained events called one of `names`, in order: its boot's, up to the next boot's header.

        Startup events are not part of the trace (`_verified_lines` steps over them), so a reader that
        wants the clock's events — a `stall`, a `lag_backstop`, the `manifest` (#23) — reads them here, by
        the one torn-aware rule. A boot journals some before its header (a stall in its first wait), so
        the read starts at `since` — where the file's previous segment ended, or the file's start —
        rather than at the header; an anchored segment's starts at its anchor. Another boot's events are
        passed over by `boot_id`, and the next boot's header, after this one's, ends the read.
        """
        if self._fd is None:
            raise RecordRefused("file", "the record has been closed")
        start = segment.offset if since is None or segment.anchored else since
        own = segment.anchored
        for kind, _number, _at, _end, row in _torn_aware_lines(self._fd, segment.name, start, 1):
            if kind != "line" or row is None:
                continue
            if row.get("event") == "segment":
                if row.get("boot_id") == segment.boot_id:
                    own = True
                elif own:
                    return
                continue
            if _startup_event(row) and row.get("event") in names and row.get("boot_id") == segment.boot_id:
                yield row


def _chain(segments: list[SegmentInfo]) -> tuple[list[SegmentInfo], RecordRefused | None]:
    """The segments in predecessor order — the first names no segment that is present — or why they are not one chain."""
    by_id: dict[str, SegmentInfo] = {}
    for segment in segments:
        if segment.boot_id in by_id:
            return segments, RecordRefused("chain", f"two segments name boot {segment.boot_id}", segment=segment.boot_id)
        by_id[segment.boot_id] = segment
    following: dict[str, list[SegmentInfo]] = {}
    roots = []
    for segment in segments:
        if segment.previous in by_id:
            following.setdefault(segment.previous, []).append(segment)
        else:
            roots.append(segment)
    if len(roots) != 1:
        names = sorted(s.boot_id for s in roots)
        return segments, RecordRefused("chain", f"{len(roots)} segments name no predecessor that is present ({names}); one trace has one first segment")
    order = [roots[0]]
    while following.get(order[-1].boot_id):
        successors = following[order[-1].boot_id]
        if len(successors) > 1:
            return segments, RecordRefused(
                "chain", f"{len(successors)} segments name {order[-1].boot_id} as their predecessor ({sorted(s.boot_id for s in successors)})",
                segment=order[-1].boot_id,
            )
        order.append(successors[0])
    if len(order) != len(segments):
        return segments, RecordRefused("chain", "the segments' predecessors form a loop")
    return order, None


# How many startup events (child 2's, unchained) may precede a segment's header in its file before the
# file is refused by name: a boot journals a handful (a root-record rewrite, `resumed`, a republication
# note) before its first cycle, and a file that holds more is not one this vehicle wrote.
STARTUP_LINES_BEFORE_HEADER = 64


def record_anchor(body: dict[str, Any]) -> dict[str, Any] | None:
    """Where a resume from this checkpoint body starts reading the record (addendum B5), or `None` for the whole record.

    The body's last segment entry names the segment, the byte offset just after the last line the
    checkpoint covers and the chain value there; with the world, the snapshot's tick and every segment
    the checkpoint lists, that is all the from-anchor read needs. A checkpoint that lists no segment
    (a world's genesis, taken before its first cycle) has no anchor: its record is read from the start.
    """
    history = [entry for entry in body.get("segments") or [] if isinstance(entry, dict)]
    if not history:
        return None
    return {
        "entry": dict(history[-1]),
        "world_id": body["identity"]["world_id"],
        "tick": int(body["identity"]["tick"]),
        "known": [entry.get("segment") for entry in history],
    }


def _first_header(dir_fd: int, name: str) -> dict[str, Any] | None:
    """The first segment header in one journal file, past at most `STARTUP_LINES_BEFORE_HEADER` startup events.

    `None` for a file that holds no header: only startup events (a refused start), or a boot torn before
    its header — a torn fragment by `_torn_aware_lines`' terminator rule. Anything else before the first
    header — a tick row, a note, an unparseable line ending in a plain newline (a damaged header, review
    F1) — is not a file this vehicle wrote, and refuses; so do more startup events than the bound. Only
    those lines are read.
    """
    for kind, number, _at, _end, row in _torn_aware_lines(dir_fd, name):
        if kind == "torn" or row is None:
            continue  # the terminator rule accepted it: a cut tail, unterminated or marked
        if row.get("event") == "segment":
            problem = _header_problem(row)
            if problem is not None:
                raise RecordRefused("header", f"line {number} of {name}: {problem}")
            return row
        if not _startup_event(row):
            raise RecordRefused("header", f"line {number} of {name} comes before any segment header")
        if number > STARTUP_LINES_BEFORE_HEADER:  # every line so far was a startup event
            raise RecordRefused(
                "startup", f"{name} holds more than {STARTUP_LINES_BEFORE_HEADER} startup events before any segment header; no boot journals that many"
            )
    return None


def _summarise(held: int, name: str, segments: list[SegmentInfo], *, offset: int = 0, current: SegmentInfo | None = None) -> None:
    """The first pass over one file from `offset`: every line verified, one `SegmentInfo` per segment kept."""
    seed = (current.header, current.chain, current.last_tick) if current is not None else None
    for kind, number, at, end, row in _verified_lines(held, name, offset, 1, seed):
        if kind == "header":
            current = SegmentInfo(row["boot_id"], name, row, int(row["first_tick"]), row["chain"], offset=at, line=number, end=end, header_end=end)
            segments.append(current)
        elif current is not None and kind == "torn":
            current.torn = True
        elif current is not None:
            current.chain, current.end = row["chain"], end
            if kind == "row":
                current.last_tick, current.rows = row["tick"], current.rows + 1


def _line_ending_at(fd: int, offset: int) -> tuple[int, bytes] | None:
    """`(start, line)` for the line whose newline is the byte before `offset`, without it; `None` past `MAX_RECORD_LINE_BYTES`."""
    position = offset - 1
    start = 0
    while position > 0:
        low = max(0, position - (1 << 16))
        found = os.pread(fd, position - low, low).rfind(b"\n")
        if found >= 0:
            start = low + found + 1
            break
        position = low
        if offset - position > MAX_RECORD_LINE_BYTES:
            return None
    return start, os.pread(fd, offset - 1 - start, start)


def _chain_before(fd: int, start: int) -> str | None:
    """The chain value of the record line before the one beginning at `start`, read backwards past startup events.

    `None` when there is none to be found within `STARTUP_LINES_BEFORE_HEADER` startup events — the start
    of the file, an unparseable line, or a line that is not part of the trace — which a row or a note at
    the anchor cannot follow.
    """
    for _ in range(STARTUP_LINES_BEFORE_HEADER + 1):
        if start <= 0:
            return None
        found = _line_ending_at(fd, start)
        if found is None:
            return None
        start, line = found
        try:
            row = loads_json(line.decode("utf-8"))
        except Exception:  # noqa: BLE001 - a fragment cannot precede a complete record line (R1)
            return None
        if not isinstance(row, dict):
            return None
        if _startup_event(row):
            continue
        chain = row.get("chain")
        return chain if _hex(chain) else None
    return None


def _anchor_line_problem(fd: int, found: tuple[int, bytes] | None, anchor: dict[str, Any]) -> str | None:
    """Why the line ending at the anchor is not the one the checkpoint was taken after (review F16, G2), or `None`.

    It must be a record line of the anchor's boot and world whose `chain` is the anchor's: a row or a
    note of the snapshot's tick, or — for a boot whose first cycle never reached its row — that boot's
    header, beginning at the snapshot's tick. And it must *be* one (confirmation G2): it passes the
    record's own schema for its kind, and its chain recomputes — a header's from its `previous_chain`,
    a row's or a note's from the chained line before it, read backwards past any startup events. A
    newline in the right place is not enough, nor an object copying the four fields: a different file
    of exactly that length would have resumed at the snapshot's tick with nothing read.
    """
    entry, tick = anchor["entry"], anchor["tick"]
    if found is None:
        return f"the line ending there is longer than the {MAX_RECORD_LINE_BYTES} bytes a record line may be"
    start, line = found
    try:
        row = loads_json(line.decode("utf-8"))
    except Exception:  # noqa: BLE001 - any decoder failure is "not a line"
        return "the line ending there is not a JSON object"
    if not isinstance(row, dict):
        return "the line ending there is not a JSON object"
    if row.get("chain") != entry.get("chain"):
        return f"the line ending there carries chain {bounded_repr(row.get('chain'))}, not the checkpoint's {entry.get('chain')}"
    if row.get("boot_id") != entry.get("boot_id") or row.get("world_id") != anchor["world_id"]:
        return "the line ending there is of another boot or another world than the checkpoint's anchor"
    event = row.get("event")
    at = row.get("first_tick") if event == "segment" else row.get("tick") if event in (None, "results_written") else None
    if at != tick:
        return f"the line ending there is not one of the snapshot's tick {tick}"
    if event == "segment":
        problem = (
            f"its format is {bounded_repr(row.get('format'))}, not {RECORD_FORMAT!r}" if row.get("format") != RECORD_FORMAT else _header_problem(row)
        )
        if problem is None and row["chain"] != record_chain(row["previous_chain"], row):
            problem = "its chain value is not its own"
    else:
        found_problem = _note_problem(row) if event == "results_written" else _row_problem(row)
        problem = found_problem if isinstance(found_problem, str) or found_problem is None else found_problem[1]
        if problem is None:
            previous = _chain_before(fd, start)
            if previous is None:
                problem = "no chained record line precedes it"
            elif row["chain"] != record_chain(previous, row):
                problem = "its chain does not follow from the record line before it"
    if problem is not None:
        return f"the line ending there is not a record line this vehicle wrote: {problem}"
    return None


def _anchored_segment(held: int, name: str, anchor: dict[str, Any]) -> SegmentInfo:
    """The anchor's segment, its offset held to the file and to the checkpoint's own last line (B5, F16), seeded as if read to there."""
    entry = anchor["entry"]
    offset, chain = entry.get("offset"), entry.get("chain")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 1 or not _hex(chain):
        raise RecordRefused("anchor", f"the checkpoint's anchor in {name} is not a byte offset and a chain value", segment=entry.get("segment"))
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=held)
    except OSError as exc:
        why = "is a symlink" if exc.errno == errno.ELOOP else f"cannot be opened ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)})"
        raise RecordRefused("anchor", f"{name}, which holds the checkpoint's anchor, {why}", segment=entry.get("segment")) from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RecordRefused("anchor", f"{name}, which holds the checkpoint's anchor, is not a regular file", segment=entry.get("segment"))
        if offset > info.st_size:
            raise RecordRefused(
                "anchor", f"the checkpoint's anchor is byte {offset} of {name}, which is {info.st_size} bytes: the record lost what the checkpoint covers",
                tick=anchor["tick"], segment=entry.get("segment"),
            )
        if os.pread(fd, 1, offset - 1) != b"\n":
            raise RecordRefused(
                "anchor", f"byte {offset} of {name} does not follow the end of a line, so it is not where the checkpoint's last line ended",
                tick=anchor["tick"], segment=entry.get("segment"),
            )
        problem = _anchor_line_problem(fd, _line_ending_at(fd, offset), anchor)
        if problem is not None:
            raise RecordRefused(
                "anchor", f"byte {offset} of {name} is not where the checkpoint's last line ended: {problem}",
                tick=anchor["tick"], segment=entry.get("segment"),
            )
    except OSError as exc:
        raise RecordRefused(
            "anchor", f"{name}, which holds the checkpoint's anchor, cannot be read ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)})",
            segment=entry.get("segment"),
        ) from None
    finally:
        os.close(fd)
    header = {
        "event": "segment", "format": RECORD_FORMAT, "world_id": anchor["world_id"], "segment": entry.get("segment"),
        "boot_id": entry.get("boot_id"), "first_tick": entry.get("first_tick"), "previous": entry.get("previous"),
        "previous_chain": None, "wall_epoch": entry.get("wall_epoch"), "chain": chain,
        # The boot's clock, which the checkpoint's entry mirrors from the header (#23): the rows read from the
        # anchor are held to its cycles of `k`.
        "m": entry.get("m"), "k": entry.get("k"), "N": entry.get("N"),
    }
    if not (_ident(header["boot_id"]) and header["segment"] == header["boot_id"] and _count(header["first_tick"])):
        raise RecordRefused("anchor", f"the checkpoint's anchor names no boot this record could hold ({bounded_repr(entry)})")
    clock = _segment_clock_problem(header)
    if clock is not None:
        raise RecordRefused("anchor", f"the checkpoint's anchor in {entry.get('segment')}: {clock}", segment=entry.get("segment"))
    tick = anchor["tick"]
    return SegmentInfo(header["boot_id"], name, header, tick, chain, offset=offset, line=1, end=offset, anchor_tick=tick, header_end=offset)


def read_record(
    where: str | os.PathLike[str],
    *,
    dir_fd: int | None = None,
    names: list[str] | None = None,
    anchor: dict[str, Any] | None = None,
) -> Record:
    """The record of a state directory's `journal.*.jsonl`, or of one `--journal` file, checked end to end — or from an anchor.

    With `dir_fd`, `where` is the state directory and is only named: the segments are listed and opened
    through a duplicate of the held handle (child 2), never by path — the form a resume uses. With
    `names` too, those files are read through it instead of the listing (an explicit `--journal`,
    through its held directory). Without `dir_fd`, a directory is opened following no link, or, for a
    file, its parent is; a link there is a named refusal (`directory`). Every file is read a bounded
    line at a time and every line verified (`_verified_lines`); the record keeps one summary per
    segment, not the rows. The segments are in predecessor order when they form one chain and by first
    tick otherwise — `concatenated` refuses a broken chain, so that the refusal is replay's, by name.

    **With `anchor` (`record_anchor` of a checkpoint body) only what the checkpoint does not cover is
    read** (addendum B5). The anchor's file is opened through the handle, held to be a regular file at
    least `offset` bytes long whose byte before `offset` ends a line, and verified from there seeded with
    the anchor's chain and tick, so a resume reads `O(L − T)` rows however long the boot before it ran.
    In a state directory every other segment file is read only to its first header: one that continues
    the anchor (by predecessor, transitively) is read whole; one the checkpoint already lists is not
    read; any other refuses (`segment`), because a segment that is neither covered by the checkpoint nor
    continues it is a fork, another world, or a predecessor whose header was damaged — and skipping it
    would resume short of ticks it published. **What this trusts**: the prefix of the record before the
    anchor is attested by the checkpoint, which is itself verified (ADR 0002 I) and lives in the same
    private directory, and is not re-verified; an edit below the anchor that keeps the anchor's line
    boundary and everything after it is not detected by a resume, by design. The whole-record form,
    without `anchor`, still verifies everything end to end, and is the one an offline replay uses.
    """
    where = Path(where)
    explicit = names is not None
    if dir_fd is not None:
        try:
            held = os.dup(dir_fd)
        except OSError as exc:
            raise RecordRefused("directory", f"{where} cannot be held ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)})") from None
        try:
            if names is None:
                names = sorted(name for name in os.listdir(held) if JOURNAL_SEGMENT_NAME.fullmatch(name))
        except OSError as exc:
            os.close(held)
            raise RecordRefused(
                "directory", f"{where} cannot be listed ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror})"
            ) from None
    else:
        if where.is_symlink():
            raise RecordRefused(
                "directory", f"{where} is a symlink, and the record is read following no link; read it through the held handle (`dir_fd=`)"
            )
        directory = where if where.is_dir() else where.parent
        try:
            held = open_directory(directory)
        except OSError as exc:
            raise RecordRefused(
                "directory", f"{where} cannot be opened as the record's directory following no link "
                f"({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}); read it through the held handle (`dir_fd=`)"
            ) from None
        if names is None:
            explicit = directory != where
            try:
                names = [where.name] if explicit else sorted(name for name in os.listdir(held) if JOURNAL_SEGMENT_NAME.fullmatch(name))
            except OSError as exc:
                os.close(held)
                raise RecordRefused(
                    "directory", f"{where} cannot be listed ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror})"
                ) from None
    try:
        segments: list[SegmentInfo] = []
        if anchor is None:
            for name in names:
                _summarise(held, name, segments)
        else:
            entry = anchor["entry"]
            if explicit:
                if len(names) != 1:
                    raise RecordRefused("anchor", "an anchored read of an explicit journal reads one file")
                anchor_name = names[0]
            else:
                anchor_name = JOURNAL_SEGMENT.format(boot_id=entry.get("segment"))
            first = _anchored_segment(held, anchor_name, anchor)
            segments.append(first)
            _summarise(held, anchor_name, segments, offset=first.offset, current=first)
            if not explicit:
                known = set(anchor["known"])
                follows: dict[str, list[tuple[str, dict[str, Any]]]] = {}
                for name in names:
                    if name == anchor_name:
                        continue
                    header = _first_header(held, name)
                    if header is None:
                        continue
                    if JOURNAL_SEGMENT.format(boot_id=header["boot_id"]) != name:
                        # One file per boot, named by its boot (review F1): a file holding another boot's
                        # header is not one this vehicle wrote, and reading it as that boot could hide one.
                        raise RecordRefused(
                            "segment", f"{name} holds the header of segment {header['boot_id']}, not of the boot its name says", segment=header["boot_id"],
                        )
                    follows.setdefault(header["previous"], []).append((name, header))
                frontier, reached = [first.boot_id], {first.boot_id}
                while frontier:
                    for name, header in follows.pop(frontier.pop(), []):
                        if header["boot_id"] in reached:
                            raise RecordRefused("chain", f"two segments name boot {header['boot_id']}", segment=header["boot_id"])
                        reached.add(header["boot_id"])
                        frontier.append(header["boot_id"])
                        _summarise(held, name, segments)
                for previous, files in follows.items():
                    for name, header in files:
                        if header["boot_id"] not in known:
                            raise RecordRefused(
                                "segment",
                                f"{name} holds segment {header['boot_id']} (after {previous}), which the checkpoint neither lists nor "
                                f"is continued from its anchor in {first.boot_id}: a fork, another world, or a predecessor whose header was damaged",
                                segment=header["boot_id"],
                            )
    except BaseException:
        os.close(held)
        raise
    order, problem = _chain(segments)
    return Record(where, held, sorted(segments, key=lambda s: (s.first_tick, s.boot_id)) if problem is not None else order)


def concatenated(segments: list[SegmentInfo]) -> list[SegmentInfo]:
    """The segments as one trace: one chain of predecessors, each beginning where and as the one before ended.

    Each segment must begin at the tick its predecessor's last row reached (`missing` when later,
    `overlap` when earlier) and name, as `previous_chain`, the chain value its predecessor ended on
    (`chain`: a predecessor that lost lines, or a successor that was not continued from it). All are
    of one world (`world`).
    """
    if not segments:
        return []
    order, problem = _chain(segments)
    if problem is not None:
        raise problem
    world_id = order[0].header["world_id"]
    for previous, segment in zip(order, order[1:], strict=False):
        if segment.header["world_id"] != world_id:
            raise RecordRefused("world", f"the segment is of world {segment.header['world_id']} and the record's first is of {world_id}", segment=segment.boot_id)
        if segment.first_tick > previous.last_tick:
            raise RecordRefused(
                "missing",
                f"the record has no cycle for tick {previous.last_tick + 1}: segment {segment.boot_id} begins at tick {segment.first_tick} "
                f"and the segment before it, {previous.boot_id}, ends at tick {previous.last_tick}",
                tick=previous.last_tick + 1, segment=segment.boot_id,
            )
        if segment.first_tick < previous.last_tick:
            raise RecordRefused(
                "overlap", f"segment {segment.boot_id} begins at tick {segment.first_tick}, before the segment before it, {previous.boot_id}, ends at tick {previous.last_tick}",
                tick=segment.first_tick, segment=segment.boot_id,
            )
        if segment.header["previous_chain"] != previous.chain:
            raise RecordRefused(
                "chain", f"segment {segment.boot_id} continues from a chain value {previous.boot_id} did not end on: the predecessor lost lines, or this boot was not continued from it",
                tick=segment.first_tick, segment=segment.boot_id,
            )
    return order


@dataclass
class Replayed:
    """What a replay reached: the checkpoint body advanced to the last tick replayed, the compare-points on the way, and the chain value there."""

    body: dict[str, Any]
    points: list[tuple[int, str, str]]
    chain: str | None = None


def _replay_window_delta(row: dict[str, Any], slug: str, delta: dict[str, Any], tick: int, segment: SegmentInfo) -> None:
    """Apply one window's recorded delta to its checkpoint row: spend, receipt counter, deferrals removed then added, arms."""
    spend = delta.get("spend")
    if spend is not None:
        held = row["spend"]
        if held.get("version") != SPEND_PLACEHOLDER_VERSION or spend.get("version") != SPEND_PLACEHOLDER_VERSION:
            raise RecordRefused(
                "spend",
                f"window {slug!r} holds spend version {held.get('version')!r} and the record a version {spend.get('version')!r} delta; "
                f"this engine replays version {SPEND_PLACEHOLDER_VERSION} (the accepted count) and child 7 owns the rest",
                tick=tick, segment=segment.boot_id,
            )
        held["accepted"] = int(held.get("accepted", 0)) + int(spend["accepted"])
    if "receipts" in delta:
        if delta["receipts"] < row["receipts"]:
            raise RecordRefused("row", f"window {slug!r}'s receipt counter goes back from {row['receipts']} to {delta['receipts']}", tick=tick, segment=segment.boot_id)
        row["receipts"] = delta["receipts"]
    removed = set(delta.get("deferred_removed") or [])
    if removed:
        row["deferred"] = [entry for entry in row["deferred"] if entry.get("receipt") not in removed]
    row["deferred"].extend(delta.get("deferred_added") or [])
    row["arms"].update(delta.get("arms_set") or {})
    for event in delta.get("arms_cleared") or []:
        row["arms"].pop(event, None)


def replay_record(world: World, body: dict[str, Any], record: Record, *, through: int | None = None) -> Replayed:
    """Re-execute the record's ticks onto a checkpoint body (child 1), through the live cycle's own functions.

    `plant.md` §6: replay drives from the trace keyed by tick, not wall time. From the snapshot's tick
    `T`, every recorded tick `T+1, T+2, …` (to `through`, or to the end of the record) is advanced by
    `advance` — `plant.step` with the row's effects in their recorded order and stamps, the
    compare-point, the lineage link — and each tick's `state_hash` and `lineage` are held to the row's
    (`state_hash`, `lineage`). The dwell clock is restarted by `dwell_after_effect` for each effect, as
    the live cycle does; the row's counters set the global and window receipt counters; each window's
    delta moves its spend, its deferral queue and its arm tokens; the published mark sets its
    `published_tick` and its next frame number. Validation is not re-run: its inputs include the agents'
    `variables`, which the vehicle preserves for them and does not keep, and its outcome is what the
    record holds — every line of which the record's chain and schema have vouched for.

    **The record must continue the checkpoint's own history** (review finding 5): its first segment is
    one the checkpoint lists (and then the checkpoint's last segment is in the record), or it names the
    checkpoint's last segment as its predecessor, beginning at the snapshot's tick from the chain that
    segment had reached; on the checkpoint's last segment, the chain at the snapshot's tick is the one
    the checkpoint recorded, and a row for the snapshot's tick carries its lineage head (`join`). The
    cycle for `T+1` must be in the record (`missing`), and the segments must be one trace
    (`concatenated`). Rows at or before the snapshot are verified and dropped as they are read: memory
    does not grow with the record. Returns the body advanced — a checkpoint body child 1's writer
    accepts, whose `segments` gain the segments crossed with the chain value reached — the
    `(tick, state_hash, lineage)` of every tick replayed, and that chain value.
    """
    body = decode(encode(body))
    problem = _structure_problem(body)
    if problem is not None:
        raise RecordRefused("snapshot", f"the checkpoint body cannot be replayed onto: {problem[0]} — {problem[1]}")
    segments = concatenated(record.segments)
    state, windows = body["executive"], body["windows"]
    start = int(state["tick"])
    history = [entry for entry in body["segments"] if isinstance(entry, dict)]
    if not segments:
        return Replayed(body=body, points=[])
    first = segments[0]
    if first.header["world_id"] != body["identity"]["world_id"]:
        raise RecordRefused("world", f"the record is of world {first.header['world_id']} and the snapshot of {body['identity']['world_id']}")
    known = [entry.get("segment") for entry in history]
    anchor = history[-1] if history else None
    present = [segment.boot_id for segment in segments]
    if anchor is None:
        if first.previous is not None:
            raise RecordRefused("join", f"the snapshot lists no segment and the record's first, {first.boot_id}, continues {first.previous}", segment=first.boot_id)
    elif first.boot_id in known:
        if anchor["segment"] not in present:
            raise RecordRefused(
                "join", f"the record does not reach the checkpoint's last segment, {anchor['segment']}: it ends in {present[-1]}",
                segment=present[-1],
            )
    elif first.previous == anchor["segment"]:
        if first.first_tick > start:
            raise RecordRefused(
                "missing", f"the record has no cycle for tick {start + 1}: the snapshot is at tick {start} and the record's first segment, "
                f"{first.boot_id}, begins at tick {first.first_tick}", tick=start + 1, segment=first.boot_id,
            )
        if first.first_tick < start or ("chain" in anchor and first.header["previous_chain"] != anchor["chain"]):
            raise RecordRefused(
                "join", f"segment {first.boot_id} does not continue the checkpoint's {anchor['segment']} from the snapshot's tick {start} and chain",
                tick=start, segment=first.boot_id,
            )
    else:
        raise RecordRefused(
            "join", f"the record's first segment, {first.boot_id}, is neither in the checkpoint's history {known} nor continues its last",
            segment=first.boot_id,
        )
    if first.anchored and (anchor is None or first.boot_id != anchor["segment"] or first.anchor_tick != start or first.header["chain"] != anchor.get("chain")):
        raise RecordRefused("join", f"the record was read from an anchor in {first.boot_id} at tick {first.anchor_tick}, which is not this checkpoint's", segment=first.boot_id)
    last = segments[-1].last_tick
    if through is not None and (through < start or through > max(last, start)):
        raise RecordRefused("through", f"tick {through} is not between the snapshot's tick {start} and the record's last tick {last}")
    stop = through if through is not None else max(last, start)
    dt = tick_seconds(world)
    tick_us = int(round(dt * 1_000_000))
    truth, head, dwell, receipt = state["truth"], state["lineage_head"], state["dwell"], int(state["receipt"])
    points: list[tuple[int, str, str]] = []
    reached: dict[str, tuple[str, int]] = {}
    chain: str | None = None
    for segment in segments:
        if segment.first_tick > stop:
            break
        anchored = anchor is not None and segment.boot_id == anchor["segment"] and "chain" in anchor
        running = segment.header["chain"]
        # The byte offset just after the last line taken: where a checkpoint of the result anchors (B5).
        running_end = segment.offset if segment.anchored else segment.header_end
        checked = not anchored or segment.first_tick > start
        for kind, row, end in record.lines(segment):
            tick = row["tick"]
            if not checked and tick > start:
                if running != anchor["chain"]:
                    raise RecordRefused("join", "the record's chain at the snapshot's tick is not the one the checkpoint recorded", tick=start, segment=segment.boot_id)
                checked = True
            if tick > stop:
                break
            running, running_end = row["chain"], end
            if kind == "note" or tick < start:
                continue
            if tick == start:
                if row["lineage"] != state["lineage_head"]:
                    raise RecordRefused(
                        "join", "the record's row for the snapshot's tick carries another lineage link: the two are of different histories",
                        tick=start, segment=segment.boot_id,
                    )
                continue
            if not points and tick != start + 1:
                raise RecordRefused(
                    "missing", f"the record has no cycle for tick {start + 1}: the snapshot is at tick {start} and the record's next cycle is tick {tick}",
                    tick=start + 1, segment=segment.boot_id,
                )
            effects = [Effect(offset, verb, dict(arguments)) for offset, verb, arguments in row["effects"]]
            before = truth
            truth, digest, link = advance(world, before, head, effects, dt)
            if digest != row["state_hash"]:
                raise RecordRefused("state_hash", "the replayed truth's compare-point is not the recorded one", tick=tick, segment=segment.boot_id)
            if link != row["lineage"]:
                raise RecordRefused("lineage", "the replayed lineage link is not the recorded one", tick=tick, segment=segment.boot_id)
            for effect in effects:
                dwell_after_effect(world, dwell, effect.verb, (tick - 1) * tick_us + effect.offset_us, before, truth)
            if row["receipt"] < receipt:
                raise RecordRefused("row", f"the receipt counter goes back from {receipt} to {row['receipt']}", tick=tick, segment=segment.boot_id)
            receipt = row["receipt"]
            for entry in row["receipts"]:
                if entry["window"] not in windows:
                    raise RecordRefused("window", f"a receipt names window {entry['window']!r} the snapshot does not hold", tick=tick, segment=segment.boot_id)
                windows[entry["window"]]["receipts"] = max(int(windows[entry["window"]]["receipts"]), entry["local"])
            for slug, delta in row["windows"].items():
                if slug not in windows:
                    raise RecordRefused("window", f"the record moves window {slug!r} and the snapshot does not hold it", tick=tick, segment=segment.boot_id)
                _replay_window_delta(windows[slug], slug, delta, tick, segment)
            for slug, mark in row["published"].items():
                if slug not in windows:
                    raise RecordRefused("window", f"the record marks window {slug!r} and the snapshot does not hold it", tick=tick, segment=segment.boot_id)
                windows[slug]["published_tick"] = mark["tick"]
                windows[slug]["seq"] = mark["seq"] + 1
            head = link
            points.append((tick, digest, link))
        if not checked and running != anchor["chain"]:
            raise RecordRefused("join", "the record's chain at the snapshot's tick is not the one the checkpoint recorded", tick=start, segment=segment.boot_id)
        # Every segment the replay reaches stays in the history, a header-only one too — a boot whose
        # first cycle was torn — or the next boot names its predecessor's predecessor and the record
        # forks (confirmation review P1).
        reached[segment.boot_id] = (running, running_end)
        chain = running
    if points:
        state.update(tick=points[-1][0], truth=truth, dwell=dwell, lineage_head=head, receipt=receipt)
        body["identity"]["tick"] = points[-1][0]
    for entry in history:
        if entry.get("segment") in reached:
            entry["chain"], entry["offset"] = reached[entry["segment"]]
    for segment in segments:
        if segment.boot_id in reached and segment.boot_id not in known:
            header = segment.header
            body["segments"].append({
                "segment": header["segment"], "boot_id": header["boot_id"], "first_tick": header["first_tick"],
                "previous": header["previous"], "wall_epoch": header["wall_epoch"],
                "chain": reached[segment.boot_id][0], "offset": reached[segment.boot_id][1],
                "m": header["m"], "k": header["k"], "N": header["N"],
            })
    body["identity"]["segments"] = [entry.get("segment") if isinstance(entry, dict) else entry for entry in body["segments"]]
    return Replayed(body=decode(encode(body)), points=points, chain=chain)


def unwritten_results(record: Record) -> list[dict[str, Any]]:
    """Every recorded verdict whose result no `results_written` note covers, in the record's order (J rule 3).

    What a resume (child 3) re-publishes after a crash between a cycle's record and its results. Each
    entry is the receipt as recorded — window, window-local `local`, global `seq`, `state`,
    `offset_us`, `command`, `body` (cut and fingerprinted past their bounds, or fingerprint-only past
    the window's budget, which a re-publication must say it cannot reproduce) — plus the `tick` the
    verdict was decided at (the receipt block's, one before the row's), the `world_id` and the
    `boot_id`. Notes follow their cycle's last row and its receipts are on its first (#23, design §4),
    so the record is streamed with one *cycle's* receipts pending at a time: they are gathered at the
    cycle's first row — from the segment header's `k` — and whatever is still pending then is moved to
    the unwritten list, never dropped, so a cycle whose publication failed stays owed. A crash after a
    cycle's first row and before its notes leaves exactly that cycle's receipts owed. Under wall-stamped result names a crash *after* the files and before
    the note leaves results listed that are on disk; under child 12's L(b) names re-publication finds
    the exact name and skips it. A record read from a checkpoint's anchor (`read_record(anchor=)`) lists
    only the verdicts after it, in `O(L − T)` lines (addendum B5).
    """
    unwritten: list[dict[str, Any]] = []
    for segment in concatenated(record.segments):
        pending: dict[tuple[str, int], dict[str, Any]] = {}
        for kind, row, _end in record.lines(segment):
            if kind == "note":
                for slug, locals_ in row["results"].items():
                    for local in locals_:
                        pending.pop((slug, local), None)
                continue
            if "prev_cycle_us" not in row:
                continue  # rows 2..k of a cycle issue nothing and close nothing
            unwritten.extend(pending.values())
            pending = {
                (entry["window"], entry["local"]): {**entry, "tick": row["tick"] - 1, "world_id": row["world_id"], "boot_id": row["boot_id"]}
                for entry in row["receipts"]
            }
        unwritten.extend(pending.values())
    return unwritten


def receipt_line(entry: dict[str, Any]) -> str:
    """The receipt block a result for a recorded verdict ends with — `Window.receipt`'s line, from the record."""
    return (
        f"receipt: world={entry['world_id']} seq={entry['local']} window={entry['window']} "
        f"tick={entry['tick']} offset_us={entry['offset_us']} state={entry['state']}\n"
    )


def republication(entry: dict[str, Any]) -> tuple[str, str]:
    """`(command, text)` of the one result an owed verdict gets: the recorded body and its receipt block.

    A body recorded whole is the result the window would have had. One the record cut (past
    `RECORD_TEXT_BYTES`) says so, with the whole's length and SHA-256; one recorded fingerprint-only
    (past the window's budget that cycle) cannot be reproduced and says that, with both fingerprints
    — still one result for one command, as the contract requires.
    """
    if entry.get("fingerprint_only") is True:
        command = str(entry["verb"])
        body = (
            f"{entry['state']}: the vehicle decided this command (window receipt {entry['local']}) at tick {entry['tick']} and "
            "restarted before its result was written; that cycle this window's results passed the record's budget, so only the "
            f"fingerprints were kept: the command was {entry['command_bytes']} bytes, SHA-256 {entry['command_sha256']}, and "
            f"its result {entry['body_bytes']} bytes, SHA-256 {entry['body_sha256']}. The result's text cannot be reproduced; "
            "this file is its one result.\n"
        )
    else:
        command, body = str(entry["command"]), str(entry["body"])
        if "body_sha256" in entry:
            body += (
                ("" if body.endswith("\n") else "\n")
                + f"[the vehicle restarted before this result was written; it was recorded to {RECORD_TEXT_BYTES} bytes and is cut "
                f"here: the whole was {entry['body_bytes']} bytes, SHA-256 {entry['body_sha256']}]\n"
            )
    return command, body + receipt_line(entry)


@dataclass
class DiskScan:
    """What one bounded look at a window's `output/` found: the owed receipts already there, and what it cost."""

    found: set[int]
    examined: int = 0
    read: int = 0
    exhausted: bool = False
    # The file each found receipt is in, so it can be made durable before it counts (review F2).
    names: dict[int, str] = field(default_factory=dict)


def _fsync_file(dir_fd: int, name: str) -> None:
    """`fsync` one regular file by name through a held directory, following no link."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, f"{name} is not a regular file")
        os.fsync(fd)
    finally:
        os.close(fd)


def _could_be_named_for(rest: str, slug: str, entry: dict[str, Any]) -> bool:
    """Whether a result file's name, past its stamp, is one the writer could have given this owed result (review F5).

    The writer names a result `<stamp>_<slug>_<sanitise(command)>`, the raw command — leading
    whitespace and all — cut at `FILENAME_LIMIT_BYTES`. A receipt the record kept whole or cut keeps a
    prefix of that raw command, so its candidates start with its sanitised prefix exactly. A receipt the
    record kept fingerprint-only keeps only the verb as parsed (`command.strip().split()[0]`, at most 64
    bytes); the raw command's leading characters became a run of underscores in the name, so its
    candidates are the slug, any run of underscores, and as much of the verb's own sanitised text as the
    name had room for. A re-published result, named from what the record kept, matches the same way.
    """
    if not rest.startswith(f"{slug}_"):
        return False
    piece = rest[len(slug) + 1 :]
    if entry.get("fingerprint_only") is not True:
        return piece.startswith(sanitise(str(entry["command"])))
    leading = len(piece) - len(piece.lstrip("_"))
    verb = sanitise(str(entry["verb"])).lstrip("_")
    return piece[leading:].startswith(verb[: max(0, FILENAME_LIMIT_BYTES - leading)])


def results_on_disk(output_fd: int, slug: str, entries: list[dict[str, Any]]) -> DiskScan:
    """Which owed results of one window are already in its `output/`: by exact receipt line, bounded (B6).

    One `scandir` pass through the held `output/` handle. A candidate is a name the result itself could
    have had (`_could_be_named_for`: built as the writer builds it) — and it is opened `O_NOFOLLOW | O_NONBLOCK` through the handle,
    `fstat`ed regular, and its last `RESULT_TAIL_BYTES` read: it is the result when its last line is the
    exact receipt line the record says it ends with, which is unique per world, window and receipt. At
    most `OUTPUT_SCAN_ENTRIES` entries are examined and `OUTPUT_SCAN_BYTES` read; past either the scan
    stops (`exhausted`) and whatever it did not find is written. An agent can only fool this about its
    own window: deleting a result before a restart, or planting its receipt line, or flooding the
    directory — each costs it at most a duplicate or a missing copy of its own result.
    """
    wanted = {receipt_line(entry).encode("utf-8"): int(entry["local"]) for entry in entries}
    scan = DiskScan(found=set())
    stamp_length = len(stamp(utc_now()))
    with os.scandir(output_fd) as listing:
        for item in listing:
            if scan.examined >= OUTPUT_SCAN_ENTRIES or scan.read >= OUTPUT_SCAN_BYTES:
                scan.exhausted = True
                break
            scan.examined += 1
            name = item.name
            if not name.endswith(".txt") or len(name) <= stamp_length + 1:
                continue
            if not any(_could_be_named_for(name[stamp_length + 1 :], slug, entry) for entry in entries):
                continue
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=output_fd)
            except OSError:
                continue
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    continue
                length = min(info.st_size, RESULT_TAIL_BYTES, OUTPUT_SCAN_BYTES - scan.read)
                tail = os.pread(fd, length, info.st_size - length) if length > 0 else b""
            except OSError:
                continue
            finally:
                os.close(fd)
            scan.read += len(tail)
            last = tail[:-1].rpartition(b"\n")[2] + b"\n" if tail.endswith(b"\n") else b""
            if last in wanted:
                scan.found.add(wanted[last])
                scan.names[wanted[last]] = name
    return scan


def read_boot_marker(state_fd: int | None) -> str | None:
    """The boot id the state directory's marker names, or `None` (no state directory, no marker, or not one)."""
    return read_boot_lineage(state_fd)[0]


def read_boot_lineage(state_fd: int | None) -> tuple[str | None, list[str]]:
    """The marker's boot, and the earlier boots whose takes may still hold a window's only map (issue #39).

    `pending` is written by a resume before it reads any window and dropped once every window has
    recovered: a resume killed in between leaves it, so the next one still reads those boots' takes
    instead of sweeping them unread. A marker without it (a fresh start's, or a finished resume's)
    names no earlier boot.
    """
    if state_fd is None:
        return None, []
    marker = read_json_bounded(BOOT_FILE, dir_fd=state_fd)
    boot = marker.get("boot_id") if marker else None
    pending = marker.get("pending") if marker else None
    earlier = [b for b in pending if isinstance(b, str) and b] if isinstance(pending, list) else []
    return (boot if isinstance(boot, str) and boot else None), earlier


def write_boot_marker(state_fd: int | None, boot_id: str, pending: list[str] | None = None) -> None:
    """Name this boot in the state directory's marker, durably (file and directory `fsync`ed), with the boots still unrecovered."""
    if state_fd is not None:
        marker: dict[str, Any] = {"boot_id": boot_id}
        if pending:
            marker["pending"] = pending
        write_json_atomic(BOOT_FILE, marker, dir_fd=state_fd, durable=True)


def read_serves_record(dir_fd: int) -> tuple[str | None, str | None]:
    """The diode directory this state directory serves, `(None, None)` for none, or a refusal.

    The file is the executive's own, so one that exists and cannot be read is a problem and not an
    empty answer, like the root record: the one thing a start must not do is serve a directory it
    could not check it was meant to.
    """
    try:
        os.lstat(SERVES_FILE, dir_fd=dir_fd)
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"{SERVES_FILE} cannot be examined ({exc.strerror})"
    raw, problem = read_regular_bounded(SERVES_FILE, dir_fd=dir_fd)
    if raw is None:
        return None, problem
    try:
        loaded = loads_json(raw)
    except Exception as exc:  # noqa: BLE001 - the refusal names the shape
        return None, f"{SERVES_FILE} is not valid JSON ({type(exc).__name__})"
    served = loaded.get("diode_dir") if isinstance(loaded, dict) else None
    if not isinstance(served, str) or not served:
        return None, f"{SERVES_FILE} names no diode directory"
    return served, None


def write_serves_record(dir_fd: int, diode_dir: str | os.PathLike[str], journal: str | os.PathLike[str] | None = None) -> None:
    """Record, in the state directory, the diode directory it serves — the canonical path `main` compares.

    The caller passes `canonicalise`'s path, which is what `main` compares the record with at the next
    start; this resolves nothing itself (review F15: `Path.resolve()` here and the hand canonicalisation
    there were two answers to one question).
    """
    write_json_atomic(
        SERVES_FILE,
        {
            "diode_dir": str(Path(diode_dir)),
            # Where this state directory's world writes its record: an explicit `--journal`'s canonical
            # path, or `None` for its own segment files — so a restart naming another is told where the
            # record is (review F11).
            "journal": str(Path(journal)) if journal is not None else None,
            "recorded_at": utc_now().isoformat(),
        },
        dir_fd=dir_fd,
    )


def served_journal(dir_fd: int) -> tuple[bool, str | None]:
    """`(recorded, journal)` from `serves.json`: whether it says where the record is, and the explicit journal (or `None`)."""
    raw, _problem = read_regular_bounded(SERVES_FILE, dir_fd=dir_fd)
    if raw is None:
        return False, None
    try:
        loaded = loads_json(raw)
    except Exception:  # noqa: BLE001 - `read_serves_record` has already judged the file
        return False, None
    if not isinstance(loaded, dict) or "journal" not in loaded:
        return False, None
    value = loaded["journal"]
    return (True, value) if value is None or isinstance(value, str) else (False, None)


def root_record_from_checkpoint(body: dict[str, Any]) -> dict[str, Any]:
    """`.executive.json` as the windows' copy of a verified checkpoint's identity (ADR 0002 H(ii)).

    The same shape `Executive.root_record` writes — the world, the slugs with their ring bounds, the
    scenario, the seed, the tick — so `read_root_record` reads it unchanged. Nothing else of the
    checkpoint's header crosses: not `body_sha256` (a hash over the truth is the side channel the
    journal exists to keep private), not `engine`, `python` or `platform` (the host's), and not the
    state directory's path. A checkpoint is a world that exists, so its `world_id` is written whether
    or not the tick is zero; the live record's "bound by the first tick" is about a world that has
    not yet been saved.
    """
    windows = body["windows"]
    return {
        "world_id": body["identity"]["world_id"],
        "slugs": sorted(windows),
        "scenario": body["run"]["scenario"],
        "seed": body["run"]["seed"],
        "ring_slots": {slug: windows[slug]["ring_slots"] for slug in sorted(windows)},
        "tick": body["identity"]["tick"],
        "updated_at": utc_now().isoformat(),
    }


def reconcile_root_record(
    record: dict[str, Any] | None, problem: str | None, expected: dict[str, Any]
) -> tuple[str, str]:
    """What to do about the root record beside a verified checkpoint: `("agree" | "rewrite" | "refuse", why)`.

    `record` and `problem` are `read_root_record`'s answer; `expected` is `root_record_from_checkpoint`.
    A record that cannot be read, is missing, or disagrees with the checkpoint on any identity key is
    *rewritten* — never a refusal, because the root is agent-writable until the chassis adopts its
    per-slug mounts (`adf38d6`, chassis branch `aurora-port`) and a refusal there is a stop button in
    the agents' hands (ADR 0002 H). An unbound record (`world_id: null`) is a
    disagreement: the checkpoint is a world that exists. A *readable* record naming a different world
    is the one refusal: two executives with separate state directories on one diode directory.
    """
    if problem is not None:
        return "rewrite", f"the root record cannot be read ({problem}), so it is rewritten from the checkpoint"
    if record is None:
        return "rewrite", "there is no root record beside the checkpoint, so it is written from it"
    bound = record.get("world_id")
    if isinstance(bound, str) and bound and bound != expected["world_id"]:
        return "refuse", (
            f"the root record names world {bounded_repr(bound)} and the checkpoint records {expected['world_id']!r}: "
            "two executives with separate state directories on one diode directory (ADR 0002 H)"
        )
    differing = [key for key in ROOT_RECORD_IDENTITY if record.get(key) != expected[key]]
    if differing:
        return "rewrite", f"the root record disagrees with the checkpoint on {differing}, so it is rewritten from it"
    return "agree", "the root record is the checkpoint's copy"


# -- the clock (ADR 0002 A, B, C1, J; WP08 child 5, #23) -------------------------------------------------
# The exit a lag backstop ends a run with (design §5): its own, beside 0 (a run that ended), 3 (a refusal
# or a fault) and argparse's 2, so a supervisor and an operator can tell a backstop from a fault.
EXIT_BACKSTOP = 4
# The fixed-format line a backstop prints, in both shapes — the chassis's operator surfaces read it
# (`docker compose logs vehicle`), because exit 4 alone may not survive a restart policy's record.
BACKSTOP_LINE = "[console] lag_backstop lag_s={lag_s} consecutive={consecutive}"
# The scheduler's longest single sleep: a stop (SIGTERM, SIGINT) is seen within it.
WAIT_CAP_NS = 100_000_000
# A stall (design §5): a sleep that returns at least this much later than it asked, or a start lag that
# jumps by at least `max(STALL_NS, 10·k·dt/m)` between consecutive cycles.
STALL_NS = 1_000_000_000


class Pacer:
    """The scheduler's clock and sleeper, and the stop flag the signal handlers set (#23, design §1 and §5).

    `now_ns` is CLOCK_MONOTONIC (`time.monotonic_ns`) and `sleep` is `time.sleep`, unless a test injects
    others — the scheduler is tested against an injected clock with pacing on. `stop` is the handler
    `main` installs for `SIGTERM` and `SIGINT` before any recovery: it only sets `stopping`, which the
    loop reads at a cycle's boundary and the wait reads between its sleeps, so a `docker stop` finishes
    the cycle it lands in and takes the clean end. `signal` is the signal that asked, for the message.
    """

    def __init__(self, now_ns: Callable[[], int] | None = None, sleep: Callable[[float], object] | None = None) -> None:
        self.now_ns = now_ns or time.monotonic_ns
        self.sleep = sleep or time.sleep
        self.stopping = False
        self.signal: int | None = None

    def stop(self, signum: int | None = None, _frame: object = None) -> None:
        """The handler: the first signal asks for a stop at the next boundary; a second one stops the process now.

        A slow stop that is still making progress — a long replay, a slow clean end — can take longer
        than an operator will wait, so one who asks twice means it (candidate 1, systems P3). Python runs
        a handler only when the interpreter can process signals, so it may be delayed; this is not a
        guarantee of termination during blocked kernel I/O. A second `SIGINT` is the `KeyboardInterrupt` it always was. A second
        `SIGTERM` ends the process with `os._exit(128 + SIGTERM)` (143), after one best-effort line on
        stderr naming it — **not** by restoring the default action and raising the signal again: in the one-executive
        container the console is its PID namespace's PID 1, and the kernel never applies a default action
        the init of a namespace has not handled, so a `SIG_DFL` `SIGTERM` would be ignored and the
        handler that worked would be gone (candidate 2, Codex P2). The line is one non-blocking
        `os.write` to fd 2, never a buffered write and flush, so a full or stalled stderr pipe cannot hold
        the exit (candidate 2 confirmation, Codex P2); if it cannot be written at once it is dropped.
        Nothing else is flushed: the record and the checkpoints are crash-safe by construction, and the
        next start resumes. Called
        without a signal (in process), it only sets the flag.
        """
        if self.stopping and signum is not None:
            if signum == signal.SIGINT:
                signal.signal(signum, signal.default_int_handler)
                signal.raise_signal(signum)
                return
            with contextlib.suppress(Exception):
                os.set_blocking(2, False)
                os.write(2, f"[console] a second {signal.Signals(signum).name}: stopping now, without a clean end\n".encode())
            os._exit(128 + signum)
        self.stopping = True
        self.signal = signum


class LagBackstop(Exception):
    """A cycle's start lag past `LAG_CEILING_S`, found before anything of it was opened: the segment ends cleanly, exit 4."""

    def __init__(self, lag_ns: int, consecutive: int) -> None:
        self.lag_ns = lag_ns
        self.consecutive = consecutive
        super().__init__(
            f"the cycle is {lag_ns / 1e9:.1f} s behind its due time, past the {LAG_CEILING_S} s lag ceiling (ADR 0002 A); "
            f"backstop {consecutive} in a row"
        )

    @property
    def lag_s(self) -> int:
        return self.lag_ns // 1_000_000_000


class CycleStats:
    """A segment's cycles as the clean end summarises them (design §2): start lags and costs, counted by value.

    Counted by value, not listed, so a segment of days holds as many entries as distinct microsecond
    figures it saw rather than one per cycle; the percentiles are the same nearest-rank figures a list
    gives (`_nearest_ranks`), which is what lets a reader's summary of the record equal this one.
    """

    def __init__(self) -> None:
        self.lags: Counter[int] = Counter()
        self.costs: Counter[int] = Counter()
        self.cycles = 0
        self.stalls = 0
        self.backstops = 0

    def add(self, lag_us: int) -> None:
        self.lags[lag_us] += 1
        self.cycles += 1

    def cost(self, cost_us: int) -> None:
        self.costs[cost_us] += 1


def _nearest_ranks(counts: Counter[int]) -> dict[str, int] | None:
    """p50, p95, p99 and max of the counted values, by nearest rank (the `⌈p·n/100⌉`-th smallest); `None` for none."""
    total = sum(counts.values())
    if total == 0:
        return None
    wanted = {name: max(1, -(-p * total // 100)) for name, p in (("p50", 50), ("p95", 95), ("p99", 99))}
    found: dict[str, int] = {}
    seen = 0
    for value in sorted(counts):
        seen += counts[value]
        for name, rank in wanted.items():
            if name not in found and seen >= rank:
                found[name] = value
    return {"p50": found["p50"], "p95": found["p95"], "p99": found["p99"], "max": max(counts)}


def _summary(lags: Counter[int], costs: Counter[int], *, tick_us: int, m: Fraction | int | str, k: int) -> dict[str, Any]:
    tick = Fraction(tick_us) / Fraction(m)
    return {
        "cycles": sum(lags.values()),
        "start_lag_us": _nearest_ranks(lags),
        "cycle_us": _nearest_ranks(costs),
        "costs_known": sum(costs.values()),
        "missed": sum(count for lag, count in lags.items() if lag > tick),
        "overran": sum(count for cost, count in costs.items() if cost > int(k) * tick),
    }


def cycle_summary(lags_us: list[int], costs_us: list[int], *, tick_us: int, m: Fraction | int | str, k: int) -> dict[str, Any]:
    """The clock summary of a run of cycles (ADR 0002 C1; design §2): their count, start lag and cost, missed and overran.

    Start lag and cost are p50/p95/p99/max by nearest rank, over the cycles — cost over those whose cost
    is known (`costs_known`). **Missed** is a cycle whose start lag exceeds one tick period, `dt/m`;
    **overran** one whose cost exceeds its own period, `k·dt/m` (the completion deadline of
    `docs/completion.md`). Container CPU throttling can stall a cycle up to a 100 ms quota period, so a
    sporadic miss is not necessarily overload.
    """
    return _summary(Counter(lags_us), Counter(costs_us), tick_us=tick_us, m=m, k=k)


def clock_line(summary: dict[str, Any]) -> str:
    """A clock summary as the one line a clean end prints (design §2: written in the manifest and printed on stop)."""

    def ranks(name: str) -> str:
        found = summary.get(name)
        return "none" if found is None else f"{found['p50']}/{found['p95']}/{found['p99']}/{found['max']} µs"

    return (
        f"clock: {summary['cycles']} cycle(s); start lag p50/p95/p99/max {ranks('start_lag_us')}; cost {ranks('cycle_us')} "
        f"({summary['costs_known']} known); missed {summary['missed']}, overran {summary['overran']}, "
        f"stalls {summary.get('stalls', 0)}, backstops {summary.get('backstops', 0)}"
    )


def segment_summaries(record: Record, tick_us: int) -> dict[str, dict[str, Any]]:
    """Each segment's clock summary, as the manifest states it, computed by a reader from the record — a crashed segment's too.

    A cycle is a first row (`prev_cycle_us` present), so a partial final cycle counts as one cycle with
    its rows. Its start lag is its rows' `lag_us`; a cycle's cost is carried on the *next* cycle's first
    row, so the rows give every cost but the last cycle's — which only a clean end's manifest has
    (`last_cycle_us`), and a crashed segment's summary goes without. Stalls and backstops (design §2's
    summary has both): a segment that ended cleanly takes them from its manifest, which is authoritative
    (it counted what the executive saw, and an event whose advisory append failed never reached the
    journal); a crashed segment, which has no manifest, counts its own `stall` and `lag_backstop` events
    and marks the summary `"counts": "journaled"` — a lower bound. The thresholds are the segment's own
    `m` and `k`, from its header. Over the cycles the record holds from where it was read (an anchored
    read starts at its anchor). For a segment that ended cleanly the result is its manifest's `summary`,
    field for field. Every boot that ends cleanly has a segment, a header-only one if it ran no cycle
    (`Executive.open_segment`), so no manifest is outside the record.
    """
    summaries: dict[str, dict[str, Any]] = {}
    ended: dict[str, int] = {}  # a file's offset just after the last segment read from it
    for segment in concatenated(record.segments):
        lags: list[int] = []
        costs: list[int] = []
        for kind, row, _end in record.lines(segment):
            if kind != "row" or "prev_cycle_us" not in row:
                continue
            if lags:
                costs.append(row["prev_cycle_us"])
            lags.append(row["lag_us"])
        stalls = backstops = 0
        manifest: dict[str, Any] | None = None
        since = ended.get(segment.name, 0)
        ended[segment.name] = segment.end
        for event in record.events(segment, {"stall", "lag_backstop", "manifest"}, since):
            if event["event"] == "stall":
                stalls += 1
            elif event["event"] == "lag_backstop":
                backstops += 1
            else:
                manifest = event
        summary = cycle_summary(
            [*lags], [*costs, *([manifest["last_cycle_us"]] if manifest and lags and _count(manifest.get("last_cycle_us")) else [])],
            tick_us=tick_us, m=segment.header["m"], k=segment.header["k"],
        )
        stated = (manifest or {}).get("summary") if isinstance((manifest or {}).get("summary"), dict) else None
        if stated is not None and _count(stated.get("stalls")) and _count(stated.get("backstops")):
            # **The manifest is authoritative for its own counts** (candidate 2, Codex P2): it counted what the
            # executive saw, and a `stall` or `lag_backstop` event whose advisory append failed is not in the
            # journal for a reader to count.
            summaries[segment.boot_id] = {**summary, "stalls": stated["stalls"], "backstops": stated["backstops"]}
        else:
            # A crashed segment has no manifest: its counts are the events that reached the journal, a lower
            # bound, and the summary says so.
            summaries[segment.boot_id] = {**summary, "stalls": stalls, "backstops": backstops, "counts": "journaled"}
    return summaries


def max_channel_rate(world: World) -> Fraction | None:
    """The highest rate any declared channel publishes at (`channels.yaml#rate_hz`), exactly; `None` for none.

    A cycle publishes one frame, so `tick_hz / k` frames per mission second must reach it (ADR 0002 B):
    10 Hz in `channels.yaml` today, so `k ≤ 5` at `tick_hz = 50`.
    """
    rates = [
        Fraction(str(row["rate_hz"]))
        for row in world.channels.values()
        if isinstance(row.get("rate_hz"), (int, float)) and not isinstance(row.get("rate_hz"), bool)
        and math.isfinite(row["rate_hz"]) and row["rate_hz"] > 0
    ]
    return max(rates) if rates else None


def previous_manifest(dir_fd: int, name: str, boot_id: str) -> dict[str, Any] | None:
    """The manifest the boot `boot_id` ended its segment with, read back from the end of its journal file; `None` if none.

    The manifest is the last thing a segment journals, so it is found reading backwards past at most
    `STARTUP_LINES_BEFORE_HEADER` unchained events (a later boot's, in a shared `--journal`); a chained
    line, an unparseable one or a manifest of another boot first means this boot wrote none — it
    crashed — which resets the consecutive-backstop count (design §5).
    """
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            return None
        end = info.st_size
        if os.pread(fd, 1, end - 1) != b"\n":
            found = _line_ending_at(fd, end + 1)  # a torn tail: step over it
            if found is None:
                return None
            end = found[0]
        for _ in range(STARTUP_LINES_BEFORE_HEADER + 1):
            if end <= 0:
                return None
            found = _line_ending_at(fd, end)
            if found is None:
                return None
            end, line = found
            try:
                row = loads_json(line.decode("utf-8"))
            except Exception:  # noqa: BLE001 - a fragment or a damaged line: no manifest here
                return None
            if not isinstance(row, dict) or not _startup_event(row):
                return None
            if row.get("event") == "manifest":
                return row if row.get("boot_id") == boot_id else None
        return None
    except OSError:
        return None
    finally:
        os.close(fd)


@dataclass
class Verdict:
    """One result in the making: what a window's line became, and the receipts it was given.

    A verdict is created at validation, which is when its receipts are drawn — so a loser can name
    the winner's receipt in the same tick — and its body is finished after the step for the commands
    that staged an effect, because what changed in truth is not known until then. `receipt` is the
    executive's global sequence, kept for the journal and the executive's own record; `local` is the
    window's, and it is the one a result file carries: a window learns how many results it has been
    given, not how many the world has.
    """

    command: str
    state: str  # accepted | refused | settled | duplicate | superseded | deferred
    body: str
    receipt: int
    local: int
    tick: int
    window: str
    verb: str | None = None
    arguments: dict[str, str] = field(default_factory=dict)
    effect: Effect | None = None
    settled: bool = False


class Executive:
    """One physical world, stepped once per cycle, commanded and observed through its windows.

    Everything physical lives here and nowhere else: the truth map (`initial_values`, then
    `plant.step` each tick), the integer tick, the receipt sequence, the per-tick lineage, the
    commanded-state dwell records in simulated microseconds, the conflict claims of the current
    tick, and the attached windows. A `Window` can read the truth to validate and to publish; it
    cannot hold any.

    `world_id` is drawn fresh per instance and is not derived from the truth, so it reveals nothing
    about the state. The lineage is `sha256(lineage_{n-1} + state_hash(truth_n) + digest of the
    tick's accepted effects)`; the latest link is `lineage_head`, the recent window is `lineage`,
    the whole history is the record (the journal: `--journal`, or the state directory's segments),
    and none of it is in a window file.
    """

    def __init__(
        self,
        world: World,
        diode_dir: Path,
        *,
        phase: str,
        tripped_interlocks: set[str] | None = None,
        scenario: str = DEFAULT_SCENARIO,
        seed: int = DEFAULT_SEED,
        max_batch: int = DEFAULT_MAX_BATCH,
        journal: Path | None = None,
        record_slugs: dict[str, int] | None = None,
        state_dir: Path | None = None,
        boot_id: str | None = None,
        state_fd: int | None = None,
        journal_dir_fd: int | None = None,
        checkpoint_every: int | None = None,
        diode_fd: int | None = None,
        multiplier: Fraction | int | str = 1,
        cycle_ticks: int = 1,
        pacer: Pacer | None = None,
        scenario_file: ScenarioFile | None = None,
    ) -> None:
        if int(max_batch) < 1:
            raise ValueError(f"max_batch must be at least 1, not {max_batch!r}")
        # **The clock** (ADR 0002 A, B, J; #23): `m`, `k` and the checkpoint cadence `N`. `main` always
        # passes the three the operator named or the checkpoint remembered — on the command line they are
        # required with no default. The defaults here are the in-process seam only (the tests): `m = 1`,
        # `k = 1`, `N = tick_hz`, and no pacer, which is a clock that is always on time. Validated before
        # any handle is duplicated: a refusal here holds nothing (review F4).
        tick_hz = (world.documents.get("mission.yaml") or {}).get("tick_hz")
        cadence = checkpoint_every if checkpoint_every is not None else tick_hz
        if isinstance(cadence, bool) or not isinstance(cadence, int) or cadence < 1:
            raise ValueError(f"the checkpoint cadence must be a positive number of ticks, not {cadence!r}")
        rate = max_channel_rate(world)
        m = parse_multiplier(multiplier) if isinstance(multiplier, str) else Fraction(multiplier)
        problem = clock_problem(m, cycle_ticks, cadence, tick_hz=tick_hz, max_rate=rate)
        if problem is not None:
            raise ValueError(f"the clock cannot be run: {problem[1]}")
        # Every handle this executive may hold, `None` until it holds it, so that `close` — which a refusal
        # anywhere below calls — releases exactly what was opened (review F4).
        self.state_fd = self.journal_dir_fd = self.diode_fd = self._record_fd = None
        try:
            self._construct(
                world, diode_dir, phase=phase, tripped_interlocks=tripped_interlocks, scenario=scenario, seed=seed,
                max_batch=max_batch, journal=journal, record_slugs=record_slugs, state_dir=state_dir, boot_id=boot_id,
                state_fd=state_fd, journal_dir_fd=journal_dir_fd, cadence=cadence, diode_fd=diode_fd,
                scenario_file=scenario_file,
            )
            self.tick_hz, self.max_rate, self.pacer = tick_hz, rate, pacer
            self.set_clock(m, cycle_ticks, cadence)
        except BaseException:
            with contextlib.suppress(OSError):  # the refusal is what is raised (J4)
                self.close()
            raise

    def _construct(
        self,
        world: World,
        diode_dir: Path,
        *,
        phase: str,
        tripped_interlocks: set[str] | None,
        scenario: str,
        seed: int,
        max_batch: int,
        journal: Path | None,
        record_slugs: dict[str, int] | None,
        state_dir: Path | None,
        boot_id: str | None,
        state_fd: int | None,
        journal_dir_fd: int | None,
        cadence: int,
        diode_fd: int | None,
        scenario_file: ScenarioFile | None = None,
    ) -> None:
        self.world = world
        # The episode's overlay (`--scenario-file`): its allow-list is held at every validation, and its
        # name and hash are the world's identity (`identity.scenario_file`). A resume sets both again:
        # the identity from the checkpoint (`restore_state`), the overlay once `main` has held the named
        # file to it (`scenario_refusal`).
        self.scenario_overlay: Scenario | None = scenario_file.scenario if scenario_file is not None else None
        self.scenario_identity: dict[str, str] | None = scenario_file.identity if scenario_file is not None else None
        self.diode_dir = Path(diode_dir)
        # An explicit `--journal` every boot appends to, rather than one segment file per boot in the
        # state directory: a resume reads it by name through its held directory.
        self.journal_shared = journal is not None
        # One boot of this executive (ADR 0002's "segment"): the journal segment's name, and the id
        # `main` draws first so that a startup event and the ticks that follow share one file. A
        # window's own `boot_id` stays per window, as `presentation.yaml#frame` publishes it.
        self.boot_id = boot_id or uuid.uuid4().hex
        # The private directory (ADR 0002 H1), or `None` for the pre-`--state-dir` layout, and the
        # handle every access to it goes through. `main` has canonicalised and opened it once and
        # passes the canonical path with `state_fd`, of which this keeps a duplicate; an in-process
        # caller that passes a path alone has it checked and opened here, once, by the same helper
        # (third review) — nothing resolves it again.
        self.state_dir: Path | None = None
        self.state_fd: int | None = None
        # The journal's directory, opened once and held: every row is appended relative to it.
        self.journal_dir_fd: int | None = None
        if state_dir is not None:
            if state_fd is None:
                opened, canonical, problem = open_private_dir(state_dir, self.diode_dir)
                if problem is not None or opened is None or canonical is None:
                    raise ValueError(problem)
                self.state_fd, self.state_dir = opened, canonical
            else:
                self.state_fd, self.state_dir = os.dup(state_fd), Path(state_dir)
            if journal is None:
                journal = journal_segment_path(self.state_dir, self.boot_id)
                self.journal_dir_fd = os.dup(self.state_fd)
        self.phase = phase
        # Live interlock state the *operator* has asserted, and the default is nothing tripped. A
        # declared interlock is a guard evaluated when a command arrives, not a standing condition;
        # a tripped one refuses by name before the unevaluated rule gets to speak.
        self.tripped = set(tripped_interlocks or ())
        self.scenario = scenario
        self.seed = int(seed)
        self.max_batch = int(max_batch)
        # The clock (#23): `set_clock` fills these from `__init__`, and a resume sets them again after its
        # replay, from the operator's flags or the newest recovered policy (design §3).
        self.multiplier: Fraction = Fraction(1)
        self.cycle_ticks = 1
        self.checkpoint_every = cadence
        self.clock: dict[str, Any] = clock_section(1, 1, cadence)
        self.tick_hz: Any = None
        self.max_rate: Fraction | None = None
        self.pacer: Pacer | None = None
        # The scheduler (#23, design §1, §2, §5): the segment's epoch — `E` and its tick `t0`, read at its
        # first wait — the previous cycle's start lag, for a stall's jump, its carried-forward cost and end
        # lag, the segment's cycle statistics, the backstops that ended the segments before this one (read
        # back by a resume from its predecessor's manifest), and whether the next cycle is the one after a
        # crossing of `N`, which rewrites the generated files and reconciles the rings.
        self.epoch_ns: int | None = None
        self.epoch_tick = 0
        self.last_lag_ns: int | None = None
        self._carried: tuple[int, int] = (0, 0)
        self.stats = CycleStats()
        self.backstops_before = 0
        # The earlier boots a resume's marker names as unrecovered (issue #39): dropped from the marker by
        # `settle_marker` once no window still needs one of their takes.
        self.marker_pending: list[str] = []
        self._refresh_next = False
        self.in_cycle = False
        self.checkpoint_failures = 0
        self.last_checkpoint_tick: int | None = None
        self._compat: Compatibility | None = None
        self.dt = tick_seconds(world)
        self.tick_us = int(round(self.dt * 1_000_000))
        # MET 0: the declared vehicle, or the scenario's overlay on it for a new world started from one.
        self.truth: dict[str, Any] = initial_values(world, self.scenario_overlay)
        self.tick = 0
        self.world_id = uuid.uuid4().hex
        self.receipt = 0
        self.lineage_head = self._lineage_link("", self.truth, [])
        self.lineage: deque[str] = deque([self.lineage_head], maxlen=RECENT_LINEAGE)
        # When each commanded state last changed, in simulated microseconds, and what it left. The
        # old console kept this per window on the wall clock; a dwell is a fact about the vehicle's
        # one machine on a clock that cannot jump (`plant.md` §5), so it is the executive's and it is
        # `tick * tick_us + offset_us`.
        self.dwell: dict[str, dict[str, Any]] = {}
        # Conflict domains claimed *this tick*, mapping the domain to the winner. `apollo_diode.md:578`:
        # "Within one conflict domain, first valid command received wins for that tick", and `:579`:
        # "Later commands are not silently discarded: they receive CONFLICT_SUPERSEDED." One map for
        # the whole world, because the old per-window maps meant two windows never conflicted at all.
        self.claimed: dict[str, Verdict] = {}
        self.windows: dict[str, Window] = {}
        # Slugs the directory's record already names, with their ring bounds, so a record rewritten
        # by this executive keeps the windows another start prepared.
        self.record_slugs: dict[str, int] = dict(record_slugs or {})
        # Isolation failures: a window whose check, claim or publication raised, recorded here (the
        # count, and the most recent few) and on stderr, and skipped for that tick while the tick
        # and the other windows proceeded.
        self.failure_count = 0
        self.failures: deque[dict[str, Any]] = deque(maxlen=RECENT_FAILURES)
        # The record's segments this world has had, oldest first (ADR 0002 G: boot, wall epoch, first
        # tick, predecessor), which `checkpoint.capture_state` saves and `restore_state` sets back.
        # This boot's entry is appended when its header is written — at its first cycle, not here,
        # because a resumed executive (child 3) has its tick and its predecessors set by the restore.
        self.segments: list[dict[str, Any]] = []
        # A world restored from its checkpoint (`resume_executive`): it exists at any tick, tick 0 included.
        self.resumed = False
        # Results owed to windows (`OBLIGATIONS_PER_WINDOW`, addendum B4), each a recorded receipt entry
        # with its tick, world and boot (`unwritten_results`' shape); checkpointed, written at the
        # window's next publication, and removed only once written or given up.
        self.obligations: list[dict[str, Any]] = []
        self._segment: dict[str, Any] | None = None
        self._record_fd: int | None = None
        # The chain value of the last line this boot appended (format v2), `""` before its header.
        self._chain = ""
        self.journal: Path | None = None
        if journal is not None:
            if self.journal_dir_fd is not None:
                self.journal = Path(journal)  # the segment, in the held state directory
            elif journal_dir_fd is not None:
                self.journal, self.journal_dir_fd = Path(journal), os.dup(journal_dir_fd)
            else:
                opened, canonical, problem = open_journal_dir(journal, self.diode_dir)
                if problem is not None or opened is None or canonical is None:
                    with contextlib.suppress(OSError):  # the refusal is what is raised (J4)
                        self.close()
                    raise ValueError(problem)
                self.journal, self.journal_dir_fd = canonical, opened
        # Generated once, because the configuration does not change while an executive runs.
        self.readme_text = generate_readme(world.root)
        self._help_cache: dict[frozenset[str] | None, str] = {}
        # The diode directory, as a handle that follows no link: every window is opened relative to
        # it, and the directory's own record is written through it. `main` has canonicalised and opened
        # it once and passes the handle, of which this keeps a duplicate — nothing resolves the operator's
        # spelling a second time (review F15); an in-process caller without one has the path resolved
        # here, the operator's to alias, and nothing below it is.
        if diode_fd is not None:
            self.diode_fd = os.dup(diode_fd)
        else:
            self.diode_dir.mkdir(parents=True, exist_ok=True)
            self.diode_fd = open_directory(self.diode_dir.resolve())
        # The names the registry publishes as gate variables, instantiated: the only names an
        # agent's `variables` may carry besides `allowance`.
        self.gate_names: set[str] = {
            name
            for row in capability_snapshot(world, phase=phase)
            for name in row["gate_variables"]
        }

    @property
    def admitted_verbs(self) -> frozenset[str] | None:
        """The scenario's verb list (`--scenario-file`), or None for the whole registry."""
        overlay = self.scenario_overlay
        return frozenset(overlay.verbs) if overlay is not None and overlay.verbs is not None else None

    @property
    def help_text(self) -> str:
        """HELP.md: the whole registry, or under a scenario only the verbs it admits — a verb the run
        refuses NOT IN THIS SCENARIO is not one to advertise. Generated once per verb list, because
        the configuration does not change while an executive runs (a resume sets the overlay late)."""
        key = self.admitted_verbs
        if key not in self._help_cache:
            self._help_cache[key] = generate_help(self.world.root, key)
        return self._help_cache[key]

    # -- windows ------------------------------------------------------------------------------
    def attach(self, slug: str, *, ring_slots: int = DEFAULT_RING_SLOTS, prepare: bool = True) -> Window:
        """Create the view for one slug and prepare its directory. A slug attaches once.

        The slug is one safe path component. The window's paths are checked before anything is
        written — a directory that is a link, or an `output/` that is a file, is a failure recorded
        against the window rather than a traceback — and the window's record is written unbound
        (`world_id: null`): the first cycle that ticks it binds the directory.

        **With `prepare=False` nothing is written** (child 3): a resume attaches the windows a
        checkpoint names before `restore_state` can give them their state, and preparing them then
        rewrote every mirror and `pending.json` to tick 0 and the root record to an unbound world —
        a window shown an earlier tick than it had already shown (design note F1).
        """
        if not isinstance(slug, str) or not SLUG_PATTERN.match(slug):
            raise ValueError(
                f"slug {slug!r} is not one safe path component ({SLUG_PATTERN.pattern}); a slug "
                "is joined to --diode-dir and may not name another directory"
            )
        if slug in self.windows:
            raise ValueError(f"slug {slug!r} is already attached to world {self.world_id}")
        root = self.diode_dir / slug
        if not prepare:
            # A resumed window: its directory is checked handle-relative by every cycle, and a link
            # there is that window's recorded skip — never a refused start (child 3's S9).
            window = Window(self, root, slug, ring_slots=ring_slots)
            self.windows[slug] = window
            return window
        # Asked of the held diode handle, never of a path built from `--diode-dir`'s spelling (round 3, H3):
        # an alias retargeted after the open would otherwise have the check look at another directory.
        try:
            planted = stat.S_ISLNK(os.lstat(slug, dir_fd=self.diode_fd).st_mode)
        except FileNotFoundError:
            planted = False
        if planted:
            raise ValueError(f"the window directory {root} is a symlink, and a window is a directory")
        window = Window(self, root, slug, ring_slots=ring_slots)
        self.windows[slug] = window
        try:
            window.prepare()
        except Exception as exc:  # noqa: BLE001 - the window's failure, recorded, not the executive's
            self._record_failure(window, "prepare", exc, self.tick)
        finally:
            window.close_handles()
        self._write_root_record(self.tick)
        return window

    def close(self) -> None:
        """Release the held directory handles. The windows' handles live for one cycle and are closed by it.

        Safe on a partly constructed executive — `__init__` calls it when a later step refuses, so a
        refused in-process construction leaks no descriptor — and safe to call twice. Every handle is
        closed even when closing one fails, and each is forgotten before its `close`, so a second call
        never closes a number twice; the first failure is raised after, naming what the handle was
        (round 4, J4)."""
        failed: OSError | None = None
        for name in ("_record_fd", "diode_fd", "journal_dir_fd", "state_fd"):
            fd = getattr(self, name, None)
            if fd is None:
                continue
            setattr(self, name, None)
            try:
                os.close(fd)
            except OSError as exc:
                if failed is None:
                    failed = exc
                    journal = getattr(self, "journal", None)
                    named = {
                        "_record_fd": journal,
                        "diode_fd": getattr(self, "diode_dir", None),
                        "journal_dir_fd": journal.parent if journal is not None else getattr(self, "state_dir", None),
                        "state_fd": getattr(self, "state_dir", None),
                    }[name]
                    if exc.filename is None and named is not None:
                        exc.filename = str(named)
        if failed is not None:
            raise failed

    def order(self) -> list[Window]:
        """This cycle's visiting order: sorted slugs rotated left by the cycle's index, `(tick // k) % n` (ADR choice A).

        No name holds a permanent priority, file arrival time decides nothing, and the order is a
        pure function of (slugs, tick) — so two executives fed the same ingress arbitrate the same.
        **By cycle, not by tick** (#23, design §1): cycles start at ticks `0, k, 2k …`, and rotated by
        `tick % n` a world with `gcd(n, k) > 1` would give the first place to only `n / gcd` windows
        (ten windows at `k = 5`: two of them). Rotated by the cycle's index, each window goes first once
        in `n` cycles whatever `gcd(n, k)`, which is `tick % n` at `k = 1`. After an unaligned resume
        one window may go first twice in a row; the partial cycle before it published nothing.
        """
        slugs = sorted(self.windows)
        if not slugs:
            return []
        k = (self.tick // self.cycle_ticks) % len(slugs)
        return [self.windows[s] for s in slugs[k:] + slugs[:k]]

    # -- the clock (#23, WP08 child 5) ----------------------------------------------------------
    def set_clock(self, multiplier: Fraction | int | str, cycle_ticks: int, checkpoint_every: int) -> None:
        """Set `m`, `k` and `N` together, held to `clock_problem`'s bounds with this vehicle's channel rates; `ValueError` names why not."""
        m = parse_multiplier(multiplier) if isinstance(multiplier, str) else Fraction(multiplier)
        problem = clock_problem(m, cycle_ticks, checkpoint_every, tick_hz=self.tick_hz, max_rate=self.max_rate)
        if problem is not None:
            raise ValueError(f"the clock cannot be run: {problem[1]}")
        self.multiplier, self.cycle_ticks, self.checkpoint_every = m, int(cycle_ticks), int(checkpoint_every)
        self.clock = clock_section(m, self.cycle_ticks, self.checkpoint_every)

    def _due_ns(self, tick: int) -> int:
        """When tick `tick` is due on this segment's clock: `E + (tick − t0)·dt/m`, integer nanoseconds, rounded once.

        Absolute from the epoch, never accumulated cycle to cycle, so no drift builds up; `dt` is the
        integer tick in microseconds and `m` an exact fraction, so nothing passes through a float.
        """
        assert self.epoch_ns is not None
        return self.epoch_ns + round(Fraction((tick - self.epoch_tick) * self.tick_us * 1000) / self.multiplier)

    def _await_cycle(self) -> tuple[int, int] | None:
        """Wait until the cycle starting at this tick is due: `(start_ns, lag_ns)`, or `None` when a stop was asked for.

        **Never ahead** (John, design §1): the cycle covering `a+1 … a+k` starts at `max(due(a+k), end
        of the previous cycle)` — never before its last tick is due — so a scheduler that is behind runs
        whole cycles back to back without sleeping (burst = `k`, ADR 0002 A), and one that is early
        sleeps. The wait is a loop on CLOCK_MONOTONIC (`Pacer.now_ns`), each sleep at most 100 ms, so an
        early wake-up or a signal is handled and a stop (`Pacer.stopping`) is seen within 100 ms; a stop
        before the cycle starts is a boundary, and nothing of the cycle runs.

        **The epoch** is read here, at the segment's first wait — after the start's or the resume's
        recovery and its checkpoint — so recovery time is never lag: the first cycle covers `t0+1 … t0+k`
        and is due `k·dt/m` after it. CLOCK_MONOTONIC stops during host suspend, so the world pauses
        with no lag; it runs on through `docker pause`, SIGSTOP and VM steal, which the next two bound.

        **Stalls are named** (design §5): a sleep that returns at least 1 s later than it asked, or a
        start lag that jumps by at least `max(1 s, 10·k·dt/m)` from the previous cycle's, is a `stall`
        event, counted and journaled — distinct from overload. **The interim lag backstop** (John, until
        #26): a start lag past `LAG_CEILING_S` is checked here, before any handle is opened or console
        claimed, so no claimed batch is ever held. With a state directory it raises `LagBackstop` and
        `main` ends the segment cleanly with exit 4; without one there is no clean end to take, so the
        epoch is rebased — the world freezes through the stall rather than racing to catch up — the
        event is journaled where a journal is named, the fixed-format line is printed, and the run goes on.

        With no pacer (an in-process executive) the clock is always on time: no wait, a lag of 0.
        """
        pacer = self.pacer
        if pacer is None:
            return 0, 0
        if pacer.stopping:
            return None
        if self.epoch_ns is None:
            self.epoch_ns, self.epoch_tick = pacer.now_ns(), self.tick
        while True:
            due = self._due_ns(self.tick + self.cycle_ticks)
            late = 0
            now = pacer.now_ns()
            while now < due:
                if pacer.stopping:
                    return None
                ask = min(due - now, WAIT_CAP_NS)
                pacer.sleep(ask / 1_000_000_000)
                after = pacer.now_ns()
                late = max(late, after - (now + ask))
                now = after
            if pacer.stopping:
                return None
            lag = max(0, now - due)
            self._note_stall(lag, late)
            if lag > LAG_CEILING_S * 1_000_000_000:
                self.stats.backstops += 1
                if self.state_fd is None:
                    self._rebase(lag)
                    continue
                raise LagBackstop(lag, self.backstops_before + 1)
            self.last_lag_ns = lag
            return now, lag

    def _note_stall(self, lag: int, late: int) -> None:
        """Journal a `stall` when a sleep came back at least 1 s late or the start lag jumped (design §5)."""
        kinds = []
        if late >= STALL_NS:
            kinds.append("wait")
        cycle = round(Fraction(self.cycle_ticks * self.tick_us * 1000) / self.multiplier)
        jump = lag - self.last_lag_ns if self.last_lag_ns is not None else 0
        if jump >= max(STALL_NS, 10 * cycle):
            kinds.append("lag_jump")
        if not kinds:
            return
        self.stats.stalls += 1
        self.journal_event({
            "event": "stall", "wall": utc_now().isoformat(), "boot_id": self.boot_id, "world_id": self.world_id, "tick": self.tick,
            "kinds": kinds, "late_us": max(0, late // 1000), "jump_us": max(0, jump // 1000), "lag_us": lag // 1000,
        })

    def _rebase(self, lag: int) -> None:
        """The backstop without a state directory (design §5): a fresh epoch at this tick, journaled where a journal is named, always said."""
        consecutive = self.stats.backstops
        self.journal_event({
            "event": "lag_backstop", "wall": utc_now().isoformat(), "boot_id": self.boot_id, "world_id": self.world_id, "tick": self.tick,
            "lag_s": lag // 1_000_000_000, "consecutive": consecutive, "action": "rebase",
        })
        sys.stderr.write(BACKSTOP_LINE.format(lag_s=lag // 1_000_000_000, consecutive=consecutive) + "\n")
        assert self.pacer is not None
        self.epoch_ns, self.epoch_tick, self.last_lag_ns = self.pacer.now_ns(), self.tick, None

    def _end_cycle(self, start: int) -> None:
        """A cycle's cost and end lag, once its rows are durable and its checkpoint taken: carried to the next cycle's first row."""
        if self.pacer is None or self.epoch_ns is None:
            cost = end_lag = 0
        else:
            end = self.pacer.now_ns()
            cost, end_lag = max(0, end - start) // 1000, max(0, end - self._due_ns(self.tick)) // 1000
        self._carried = (cost, end_lag)
        self.stats.cost(cost)

    def summary(self) -> dict[str, Any]:
        """This segment's clock summary so far (design §2): `cycle_summary`'s, with its stalls and backstops."""
        return {
            **_summary(self.stats.lags, self.stats.costs, tick_us=self.tick_us, m=self.multiplier, k=self.cycle_ticks),
            "stalls": self.stats.stalls,
            "backstops": self.stats.backstops,
        }

    def open_segment(self) -> None:
        """Write this boot's segment header now, if it has none yet and there is a record: a header-only segment.

        A boot's header is written with its first cycle's rows (`_append_record`). One that ends cleanly
        without a cycle — its first wait backstopped, or a stop came before it — would otherwise journal a
        manifest no segment holds, and a reader of the record would not see that boot (candidate 2, Codex
        P3). The record already has header-only segments (a boot whose first cycle was torn) and every
        reader takes them, so this adds no rule: the next boot names this one as its predecessor, from the
        header's chain, and begins at the same tick. It is called before the clean-end checkpoint, so a
        clean-end checkpoint, **when one is taken**, lists the segment; a boot that resumed and ran no cycle
        already holds a checkpoint at this tick and takes none, so the header follows its newest checkpoint
        unlisted — which is consistent: replay from that anchor reaches the header, adds the segment, and
        the next resume inherits its clock from it (the "newer" rule). A failure is `RecordUnwritable`, as
        any append's.
        """
        if self.journal is not None and self.journal_dir_fd is not None and self._segment is None:
            self._append_record([], first_tick=self.tick)

    def settle_marker(self) -> None:
        """Drop the earlier boots from the marker once every window is done with their takes (issue #39).

        Until then a resume killed now must still read those boots' takes: a window not yet recovered, or
        one whose map is held only in an earlier boot's take, would otherwise have it swept unread. A
        failed write is retried next cycle; meanwhile the marker only names more takes than it needs.
        """
        if not self.marker_pending or self.state_fd is None:
            return
        current = f"{TAKE_PREFIX}{self.boot_id}."
        for window in self.windows.values():
            if window.recover_owed or window.recovering is not None:
                return
            if window.held is not None and not window.held.startswith(current):
                return
        with contextlib.suppress(Exception):  # retried next cycle; the marker it leaves is only wider
            write_boot_marker(self.state_fd, self.boot_id)
            self.marker_pending = []

    def journal_event(self, event: dict[str, Any]) -> None:
        """Append one unchained event to the journal, where one is named; advisory, unless the record cannot be restored (J2)."""
        if self.journal is None or self.journal_dir_fd is None:
            return
        try:
            append_journal_line(self.journal, event, dir_fd=self.journal_dir_fd)
        except RecordUnwritable:
            raise
        except Exception:  # noqa: BLE001 - advisory, and the append left the record as it was
            pass

    def write_manifest(self, ended: str) -> dict[str, Any]:
        """The segment's manifest (ADR 0002 C1, as #23 amends it: the clean-end event *is* the manifest), journaled; returned.

        `ended` is `clean` or `lag_backstop`. `consecutive_backstops` is how many segments in a row ended
        by the backstop, this one included — read back by the next resume from this event — and 0 for a
        segment that ends otherwise. `last_cycle_us` and `last_end_lag_us` are the last cycle's cost and
        end lag, which no row carries (design §2: "the segment's last cycle's cost goes only in the
        manifest"), `None` when the segment ran no cycle; with them a reader's `segment_summaries` of a
        cleanly ended segment is this `summary` exactly. A crashed segment has no manifest; its summary is
        a reader's, without its last cycle's cost.
        """
        ran = self.stats.cycles > 0
        event = {
            "event": "manifest", "wall": utc_now().isoformat(), "boot_id": self.boot_id, "world_id": self.world_id, "tick": self.tick,
            "ended": ended, "clock": {"m": self.clock["m"], "k": self.cycle_ticks, "N": self.checkpoint_every},
            "summary": self.summary(), "consecutive_backstops": self.backstops_before + 1 if ended == "lag_backstop" else 0,
            "last_cycle_us": self._carried[0] if ran else None, "last_end_lag_us": self._carried[1] if ran else None,
        }
        # Not advisory, unlike `journal_event`: the manifest is the clean end, and a resume that cannot
        # read it treats the segment as crashed (the backstop count resets). Its failure is raised.
        if self.journal is not None and self.journal_dir_fd is not None:
            append_journal_line(self.journal, event, dir_fd=self.journal_dir_fd)
        return event

    # -- the cycle ----------------------------------------------------------------------------
    def cycle(self) -> list[Path]:
        """One cycle: wait until it is due, settle every window's due deferrals, claim and validate every window, step `k` ticks, publish.

        **A cycle is `k` ticks** (ADR 0002 B2, #23): it claims every console once, stamps the accepted
        effects at `offset_us = 0` of its first tick — the receipt's tick is the cycle's start tick —
        steps `k` ticks (the other `k − 1` carry no effects) and publishes once, so within a segment the
        frames are exactly `k` ticks and `k·dt` of mission time apart. **Causality, stated plainly**: a
        command written while tick `a` is the newest frame is applied from tick `a`, whose due time has
        passed by up to `k·dt/m` plus the cycle's cost (more while catching up); "takes effect within `k`
        ticks" means it appears in the next frame. No claim time is published to a window. What *is*
        decided is that every window's validation reads the same truth, every accepted effect lands in
        the same step in arbitration order, and every window's frame is built from the same stepped truth.

        **Deferrals first, for every window, before any ingress.** `apollo_diode.md:578` is "first
        valid command *received*", and a command due now was received a cycle earlier than anything
        claimed now — so the settlements take their turn at the conflict domains before the fresh
        commands do, in rotation order, and a settlement is published whether or not the same
        window's claim then fails.

        The wait, the stall and backstop checks are `_await_cycle`'s, before anything is opened; a stop
        asked for during the wait returns `[]` with nothing run. The cycle's start lag is on each of its
        rows, and its cost is carried to the next cycle's first row (`_end_cycle`). A cycle that crosses
        a multiple of `N` ends with a checkpoint; the cycle after it rewrites the generated files and
        reconciles the ring (`Window.refresh`), so the two costs normally fall in different cycles.
        """
        started = self._await_cycle()
        if started is None:
            return []
        start, lag = started
        tick = self.tick
        lag_us = lag // 1000
        self.stats.add(lag_us)
        if self._refresh_next:
            self._refresh_next = False
            for window in self.windows.values():
                window.refresh = True
        # Until the cycle completes, its window counters may be ahead of its truth (a verdict draws its
        # receipt before the step): a checkpoint is never taken while this is set (`main`'s clean end).
        self.in_cycle = True
        self.claimed = {}
        verdicts: dict[str, list[Verdict]] = {}
        effects: list[Effect] = []
        applied: list[Verdict] = []
        order = self.order()
        healthy: list[Window] = []
        # Each window's half of the state before the cycle, so the record can carry what it changed.
        before_windows = {
            slug: (window.accepted, [entry.get("receipt") for entry in window.deferred], dict(window.arms), window.receipts)
            for slug, window in self.windows.items()
        }
        try:
            # **The window's directories are opened once, here, and every operation this cycle is
            # relative to those handles.** A check-then-act — `is_symlink()` then a write by path —
            # leaves the gap between the two to an agent that swaps `output/` for a link inside it;
            # a handle has no gap: a link swapped in before the open is `ELOOP`, one swapped in
            # after it is not where the handle points.
            for window in order:
                try:
                    window.open_handles()
                except WindowAbsent as exc:
                    # A dark cycle, then back: the directory is made again (handle-relative, following
                    # no link) and served next cycle with the identity the executive kept. Repair, not
                    # preparation: `prepare` wrote `pending.json` at tick 0 (addendum B7).
                    self._record_failure(window, "check", exc, tick)
                    try:
                        # Never a console while a resume's recovery waits (#39, option B): it would read as present
                        # and hide the ended boot's take, the only copy of the map; the recovery puts it back.
                        window.repair(console=window.recovering is None and not window.recover_owed)
                    except Exception as again:  # noqa: BLE001 - recorded, like the absence
                        self._record_failure(window, "prepare", again, tick)
                    finally:
                        window.close_handles()
                    continue
                except Exception as exc:  # noqa: BLE001 - the window's directory is the window's
                    self._record_failure(window, "check", exc, tick)
                    continue
                healthy.append(window)
                # The verdicts are made into the cycle's own list, so those made before an internal
                # fault are kept — recorded and published — rather than dropped with a local list
                # (child 4's review finding 7).
                verdicts[window.slug] = []
                try:
                    self._settle(window, verdicts[window.slug])
                except Exception as exc:  # noqa: BLE001 - the window's, not the tick's
                    self._record_failure(window, "settle", exc, tick)
            for window in healthy:
                try:
                    self._ingest(window, verdicts[window.slug])
                except Exception as exc:  # noqa: BLE001 - the window's, not the tick's
                    self._record_failure(window, "claim", exc, tick)
            self.settle_marker()
            for window in healthy:
                for verdict in verdicts.get(window.slug, []):
                    if verdict.effect is not None:
                        effects.append(verdict.effect)
                        applied.append(verdict)

            # **The record before anything of the cycle is published** (ADR 0002 J rules 1–3): the cycle's
            # `k` rows, with every window's published-tick mark on the last, appended and `fsync`ed —
            # the first alone, first, when it carries anything (write-ahead). A record that cannot be
            # made durable raises `RecordUnwritable` here, and nothing below runs.
            self._record_cycle(tick, effects, applied, verdicts, healthy, before_windows, lag_us)
            self._write_root_record(tick)

            written: list[Path] = []
            for window in healthy:
                # Rule 3's second half is inside `publish`: each window's results, made durable, then its
                # note, then its frame and mirror (child 4's review finding 6).
                window.landed = []
                try:
                    written.extend(window.publish(verdicts.get(window.slug, [])))
                except RecordUnwritable:
                    raise
                except Exception as exc:  # noqa: BLE001 - the window's, not the tick's
                    self._record_failure(window, "publish", exc, tick)
                    self._owe(window, [v for v in verdicts.get(window.slug, []) if v.local not in window.landed])
                    # The record marked this frame number as written (J (ii)); a publication that failed
                    # before the frame consumes it anyway, as a replay through the mark does, so a live
                    # checkpoint and a replayed one agree on the next frame number (design note S16).
                    if window.marked_seq is not None and window.seq == window.marked_seq:
                        window.seq += 1
            self.in_cycle = False
            # The cadence (ADR 0002 J, `N`): at the end of a cycle that **crossed** a multiple of `N` —
            # not one whose tick is one, which an unaligned resume would never reach again (#23) — once
            # every window has published, so the checkpoint's anchor is after the cycle's notes and its
            # obligations are what is owed. The next cycle rewrites the generated files.
            if self.tick // self.checkpoint_every > tick // self.checkpoint_every:
                self._refresh_next = True
                if self.state_fd is not None:
                    self._cadence_checkpoint()
            self._end_cycle(start)
            return written
        finally:
            for window in order:
                window.close_handles()

    def checkpoint(self) -> Path:
        """Capture this executive and write it, ADR 0002 I's sequence, through the held state-directory handle.

        The engine identity and the commit are computed once per executive, not once per checkpoint
        (`Compatibility.current` hashes the corpus) — and kept only once the identity is computed whole:
        an error listing or reading the corpus raises out of `Compatibility.current` with its path
        (`plant.corpus_files`, fourth round J1), nothing is kept, and the next checkpoint computes it
        again. Raises what `Compatibility.current`, `capture_state` and `write_checkpoint` raise; the
        callers decide what a failure means — a refused start for a world's genesis and for the
        checkpoint a resume takes before it serves (addenda B1, B3), a recorded failure for the cadence
        and for a clean end.
        """
        if self.state_dir is None or self.state_fd is None:
            raise RuntimeError("an executive without a state directory has nowhere to write a checkpoint")
        if self._compat is None:
            self._compat = Compatibility.current(self.world)
            self._git_commit = git_commit(self.world.root)
        body = capture_state(self, self._compat, git_commit=self._git_commit)
        written = write_checkpoint(self.state_dir, body, dir_fd=self.state_fd)
        self.last_checkpoint_tick = self.tick
        return written

    def _cadence_checkpoint(self) -> None:
        """The cadence's checkpoint (`checkpoint_or_record`)."""
        self.checkpoint_or_record("cadence")

    def checkpoint_or_record(self, occasion: str) -> bool:
        """A checkpoint whose failure is recorded, journaled and on stderr, and the run goes on (B11); `True` if written.

        For the cadence and for a clean end (review F10: the clean end's failure was on stderr only,
        where ADR 0002 J (xxii) says it is journaled). The record is what makes the run durable; a
        checkpoint only bounds how much of it a resume reads, and `write_checkpoint` leaves a verifying
        generation at every step — so a failure costs recovery time, not the world. The consecutive
        count says how long that has been so.
        """
        try:
            self.checkpoint()
        except Exception as exc:  # noqa: BLE001 - recorded, and the run goes on
            self.checkpoint_failures += 1
            self._record_failure_named(
                CURRENT, "checkpoint", RuntimeError(f"{exc} ({occasion}; {self.checkpoint_failures} consecutive)"), self.tick
            )
            if self.journal is not None and self.journal_dir_fd is not None:
                # The event is advisory, and a failure to append it is the record left as it was
                # (`append_or_restore`) — unless the record could not be restored, which stops the run
                # (J2): the next cycle's row would follow a fragment.
                try:
                    append_journal_line(
                        self.journal,
                        {
                            "event": "checkpoint_failed", "wall": utc_now().isoformat(), "boot_id": self.boot_id,
                            "world_id": self.world_id, "tick": self.tick, "occasion": occasion,
                            "consecutive": self.checkpoint_failures, "error": f"{type(exc).__name__}: {exc}",
                        },
                        dir_fd=self.journal_dir_fd,
                    )
                except RecordUnwritable:
                    raise
                except Exception:  # noqa: BLE001 - advisory, and the append left the record as it was
                    pass
            return False
        self.checkpoint_failures = 0
        return True

    def _owe(self, window: Window, verdicts: list[Verdict]) -> None:
        """Owe a window the results of verdicts whose publication failed (addendum B4), as the record holds them."""
        for entry in receipt_entries(sorted(verdicts, key=lambda v: v.receipt)):
            verdict = next(v for v in verdicts if v.local == entry["local"])
            self.owe({**entry, "tick": verdict.tick, "world_id": self.world_id, "boot_id": self.boot_id})

    def owe(self, entry: dict[str, Any]) -> None:
        """Add one obligation unless the window is already owed that receipt; past the bound, give up the oldest, recorded."""
        key = (entry["window"], entry["local"])
        if any((held["window"], held["local"]) == key for held in self.obligations):
            return
        self.obligations.append(entry)
        mine = [held for held in self.obligations if held["window"] == entry["window"]]
        if len(mine) > OBLIGATIONS_PER_WINDOW:
            oldest = mine[0]
            self.obligations.remove(oldest)
            self._record_failure_named(
                oldest["window"],
                "obligation",
                RuntimeError(
                    f"window receipt {oldest['local']} (tick {oldest['tick']}) is given up unwritten: the window is owed more "
                    f"than {OBLIGATIONS_PER_WINDOW} results it could not be written"
                ),
                self.tick,
            )

    def publish_obligations(self, window: Window) -> list[dict[str, Any]]:
        """Write what a window is owed, once each: skip a result already on disk (`results_on_disk`), write the rest.

        **An obligation leaves the list only behind the durability barrier** (review F2, ruling R2): with a
        record, every result it settles — written now (`write_result` `fsync`s the file) or found already
        on disk (whose file is `fsync`ed here) — is settled only once the `output/` directory has been
        `fsync`ed after them all. A failure anywhere before that leaves every one of them owed, and the
        next attempt finds what did reach the disk by its receipt line. Without a record nothing is made
        durable and nothing waits. Returns what happened to each: `written` (with the file name) or
        `on disk`.
        """
        mine = [entry for entry in self.obligations if entry["window"] == window.slug]
        if not mine:
            return []
        output = window._handles().output
        durable = self.journal is not None
        scan = results_on_disk(output, window.slug, mine)
        report: list[dict[str, Any]] = []
        for entry in mine:
            outcome: dict[str, Any] = {"window": window.slug, "local": entry["local"], "tick": entry["tick"]}
            if entry["local"] in scan.found:
                outcome["result"] = "on disk"
                if durable:
                    _fsync_file(output, scan.names[entry["local"]])
            else:
                command, text = republication(entry)
                outcome["result"], outcome["file"] = "written", window.write_result(command, text).name
            report.append(outcome)
        if durable:
            os.fsync(output)
        for entry in mine:
            self.obligations.remove(entry)
        if scan.exhausted:
            report.append({"window": window.slug, "scan": f"stopped after {scan.examined} entries and {scan.read} bytes; anything not found was written"})
        return report

    def _record_failure(self, window: Window, stage: str, exc: BaseException, tick: int) -> None:
        """Isolation: the failure is counted and recorded, on stderr and here, and the tick goes on without the window."""
        self._record_failure_named(window.slug, stage, exc, tick)

    def _record_failure_named(self, name: str, stage: str, exc: BaseException, tick: int) -> None:
        """`_record_failure` for a window's slug, or for `.executive.json` at the stage `root_record`."""
        entry = {
            "tick": tick,
            "window": name,
            "stage": stage,
            "error": f"{type(exc).__name__}: {exc}",
        }
        self.failure_count += 1
        self.failures.append(entry)
        what = (
            f"the directory's record {name} not written" if stage == "root_record"
            else f"the checkpoint {name} not written" if stage == "checkpoint"
            else f"window {name!r} skipped"
        )
        sys.stderr.write(f"[console] tick {tick}: {what} at {stage}: {entry['error']}\n")

    def _lineage_link(self, previous: str, truth: dict[str, Any], effects: list[Effect]) -> str:
        return lineage_link(previous, state_hash(truth), effects)

    # -- the record (ADR 0002 J, child 4) ------------------------------------------------------
    def _record_cycle(
        self,
        tick: int,
        effects: list[Effect],
        applied: list[Verdict],
        verdicts: dict[str, list[Verdict]],
        healthy: list[Window],
        before_windows: dict[str, tuple[int, list[Any], dict[str, str], int]],
        lag_us: int,
    ) -> None:
        """Step the cycle's `k` ticks into locals, append their rows and `fsync`, then commit; mark each publishing window.

        `tick` is the tick the cycle started at; each row is keyed by the tick it reached, as every
        journal row has been. **Stepping and effects** (determinism review P1-B): tick `tick+1` is stepped
        with the cycle's effects, and `_report_effect` and the dwell bookkeeping run against *that*
        step's before and after; the remaining `k − 1` ticks are stepped with none — exactly what replay
        does row by row (`replay_record`), so a target that keeps moving after its step is reported and
        dwelled the same live and replayed. Each step is `advance`, replay's own path from a tick to the
        next, and nothing is committed to `tick`, `truth` or `lineage` until its row is durable.

        **The rows** (format v3, design §4): the first carries the effects, every verdict's receipts
        (`receipt_entries`, within each window's budget — finding 1), the window deltas against
        `before_windows` (the accepted count — spend, version 0 until child 7; the window's receipt
        counter — finding 7: a number drawn before an internal fault is recorded though no verdict
        carries it; deferral entries removed by their window-local receipt and added whole — finding 4;
        arm tokens set and cleared; a window with a verdict gets an entry even when nothing moved) and
        the previous cycle's carried-forward cost; every row carries the receipt counter, the failure
        count and the cycle's start lag; the last carries every publishing window's mark. **Write-ahead**:
        when the first row's effects, receipts or deltas are not empty it is appended and `fsync`ed
        before step 2, so a claimed batch is in memory only for one step, as before #23; the rest follow
        with one `fsync`. A cycle with nothing to record appends all `k` with one.

        **A compare-point refusal at step `j`** (`plant.UncomparableState`): the completed rows not yet
        durable are appended with one `fsync` — rows `1 … j−1` on a quiet cycle, `2 … j−1` on a
        write-ahead one, nothing when `j = 2` — and only the durable rows are committed; the refusal
        carries `last_durable_tick`, which `main` names. Row 1 carries the cycle's receipts, so its batch is
        owed and answered on resume. If that append itself fails, the durable prefix stands and the
        refusal says so (`unwritable`). At `j = 1` nothing is recorded or committed, as before. Without a
        journal nothing is durable, and nothing is committed.

        Without a journal nothing is written and the marks are still set: `published_tick` is what the
        window has been told, whether or not anything keeps it.
        """
        k = self.cycle_ticks
        recording = self.journal is not None
        truth, head = self.truth, self.lineage_head
        steps: list[tuple[dict[str, Any], str, str]] = []
        rows: list[dict[str, Any]] = []
        durable = 0
        try:
            for j in range(1, k + 1):
                before = truth
                stepped = advance(self.world, before, head, effects if j == 1 else [], self.dt)
                truth, head = stepped[0], stepped[2]
                steps.append(stepped)
                if j == 1:
                    for verdict in applied:
                        verdict.body += self._report_effect(verdict, before, truth)
                marks: dict[str, dict[str, int]] = {}
                if j == k:
                    marks = {window.slug: {"tick": tick + k, "seq": window.seq} for window in healthy}
                    for window in self.windows.values():
                        window.marked_seq = window.seq if window.slug in marks else None
                if not recording:
                    continue
                row: dict[str, Any] = {
                    "tick": tick + j,
                    "world_id": self.world_id,
                    "boot_id": self.boot_id,
                    "lineage": stepped[2],
                    "state_hash": stepped[1],
                    "effects": [],
                    "receipts": [],
                    "receipt": self.receipt,
                    "windows": {},
                    "published": marks,
                    "failures": self.failure_count,
                    "lag_us": lag_us,
                }
                if j == 1:
                    row["effects"] = [[e.offset_us, e.verb, e.arguments] for e in effects]
                    row["receipts"] = [entry for verdict_rows in verdicts.values() for entry in receipt_entries(verdict_rows)]
                    row["windows"] = self._window_deltas(verdicts, before_windows)
                    row["prev_cycle_us"], row["prev_end_lag_us"] = self._carried
                rows.append(row)
                if j == 1 and k > 1 and (row["effects"] or row["receipts"] or row["windows"]):
                    self._append_record(rows, first_tick=tick)
                    durable = 1
        except UncomparableState as exc:
            if recording and len(rows) > durable:
                try:
                    self._append_record(rows[durable:], first_tick=tick)
                    durable = len(rows)
                except RecordUnwritable as again:
                    exc.unwritable = str(again)  # type: ignore[attr-defined]
            self._commit(steps[:durable] if recording else [])
            exc.last_durable_tick = self.tick  # type: ignore[attr-defined]
            raise
        if recording and durable < len(rows):
            try:
                self._append_record(rows[durable:], first_tick=tick)
            except RecordUnwritable:
                # Row 1 may be durable (write-ahead): commit exactly that prefix, so the tick `main` names is the
                # one recovery reaches (candidate 1, Codex P3, systems P3).
                self._commit(steps[:durable])
                raise
        self._commit(steps)
        for window in healthy:
            window.published_tick = self.tick

    def _commit(self, steps: list[tuple[dict[str, Any], str, str]]) -> None:
        """Commit stepped ticks — truth, tick and lineage together — once their rows are durable (or there is no record)."""
        for truth, _digest, link in steps:
            self.truth = truth
            self.tick += 1
            self.lineage_head = link
            self.lineage.append(link)

    def _window_deltas(
        self, verdicts: dict[str, list[Verdict]], before_windows: dict[str, tuple[int, list[Any], dict[str, str], int]]
    ) -> dict[str, dict[str, Any]]:
        """What the cycle changed of each window's half of the state, against `before_windows` (the first row's `windows`)."""
        changes: dict[str, dict[str, Any]] = {}
        for slug, window in self.windows.items():
            accepted, deferred_ids, arms, issued = before_windows.get(slug, (window.accepted, [], dict(window.arms), window.receipts))
            delta: dict[str, Any] = {}
            spend = window.accepted - accepted
            if verdicts.get(slug) or spend:
                delta["spend"] = {"version": SPEND_PLACEHOLDER_VERSION, "accepted": spend}
            if verdicts.get(slug) or window.receipts != issued:
                delta["receipts"] = window.receipts
            remaining = {entry.get("receipt") for entry in window.deferred}
            removed = [receipt for receipt in deferred_ids if receipt not in remaining]
            if removed:
                delta["deferred_removed"] = removed
            known = set(deferred_ids)
            added = [dict(queued) for queued in window.deferred if queued.get("receipt") not in known]
            if added:
                delta["deferred_added"] = added
            armed = {event: token for event, token in window.arms.items() if arms.get(event) != token}
            if armed:
                delta["arms_set"] = armed
            cleared = sorted(event for event in arms if event not in window.arms)
            if cleared:
                delta["arms_cleared"] = cleared
            if delta:
                changes[slug] = delta
        return changes

    def _note_window_results(self, window: Window) -> None:
        """Append and `fsync` one window's `results_written` note: its results on disk, by window-local receipt.

        Called by `Window.publish` once the window's result files and its `output/` directory are
        durable, and before its frame and mirror (child 4's review finding 6), so the stretch in which
        a result is published and still listed unwritten is one window's, not the cycle's. By receipt,
        not by file name: the name is wall-stamped until child 12's L(b) makes it a function of the
        trace, and the receipt is what a resume matches a recorded verdict on (`unwritten_results`).
        """
        if not window.landed or self.journal is None:
            return
        note = {
            "event": "results_written",
            "boot_id": self.boot_id,
            "world_id": self.world_id,
            "tick": self.tick,
            "results": {window.slug: list(window.landed)},
        }
        self._append_record([note], first_tick=self.tick - 1, published=True)

    def _record_handle(self) -> int:
        """The boot's segment, opened once and held: `O_APPEND | O_NOFOLLOW`, `0600`, relative to the journal's held directory.

        On creation the directory is `fsync`ed so the new name is durable with its first row. A file
        that exists is made `0600` if this process owns it and refused otherwise. A file
        that does not end in a newline — a previous boot's append torn by a crash, in an explicit
        `--journal` every boot shares — is ended first with `TORN_TAIL_TERMINATOR`, so this boot's header
        begins a line and the fragment can never parse as one (review F13).
        """
        if self._record_fd is not None:
            return self._record_fd
        assert self.journal is not None and self.journal_dir_fd is not None
        fd = os.open(
            self.journal.name, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
            dir_fd=self.journal_dir_fd,
        )
        try:
            private_record_file(fd, str(self.journal))
            info = os.fstat(fd)
            if info.st_size > 0 and os.pread(fd, 1, info.st_size - 1) != b"\n":
                append_or_restore(fd, TORN_TAIL_TERMINATOR, str(self.journal))
            os.fsync(self.journal_dir_fd)
        except BaseException:
            # A failing close never replaces the failure on its way out (fifth round, K1).
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        self._record_fd = fd
        return fd

    def _append_record(self, rows: list[dict[str, Any]], *, first_tick: int, published: bool = False) -> None:
        """Append rows to the boot's segment as one write, and `fsync`; on the boot's first append, its header first.

        The header is ADR 0002 G's segment entry — the boot, the tick its first cycle started at
        (`first_tick`), the segment before it and the chain value it ended on (the last of `segments`,
        which a restore sets), its wall epoch and its clock (`m`, `k`, `N`, #23) — with the format and the world. Every line gets its
        `chain` (`record_chain`); the boot's entry in `segments` carries the chain reached, so a
        checkpoint names the exact point of the record it was taken at. The entry is appended to
        `segments` only once the header is durable. A line past `MAX_RECORD_LINE_BYTES`, or any failure
        to write or `fsync`, is `RecordUnwritable` — whose sentence says whether anything of the cycle
        was already published (`published`, true for a window's note after its results).
        """
        header: dict[str, Any] | None = None
        entry: dict[str, Any] | None = None
        chain = self._chain
        if self._segment is None:
            last = self.segments[-1] if self.segments else None
            previous = last.get("segment") if isinstance(last, dict) else last
            previous_chain = last.get("chain", "") if isinstance(last, dict) else ""
            entry = {
                "segment": self.boot_id,
                "boot_id": self.boot_id,
                "first_tick": first_tick,
                "previous": previous,
                "wall_epoch": utc_now().isoformat(),
                # The boot's clock (#23, format v3): a reader's cycle boundaries are `first_tick + i·k`.
                "m": self.clock["m"],
                "k": self.cycle_ticks,
                "N": self.checkpoint_every,
            }
            header = {"event": "segment", "format": RECORD_FORMAT, "world_id": self.world_id, "previous_chain": previous_chain, **entry}
            header["chain"] = chain = record_chain(previous_chain, header)
        lines = [record_line(header)] if header is not None else []
        for row in rows:
            row["chain"] = chain = record_chain(chain, row)
            lines.append(record_line(row))
        after = (
            "the window's results are on disk and the record will list them as unwritten"
            if published
            else "nothing of the cycle has been published"
        )
        for line in lines:
            if len(line) > MAX_RECORD_LINE_BYTES:
                raise RecordUnwritable(
                    f"a record line encodes to {len(line)} bytes, past the {MAX_RECORD_LINE_BYTES} a record line may be; {after}"
                )
        try:
            fd = self._record_handle()
            # A failed append is cut back to where it began (`append_or_restore`, J2), so the segment
            # ends at its last whole line whatever the next boot finds; one that cannot be cut is
            # `RecordUnwritable` by itself, said with what of the cycle was published.
            append_or_restore(fd, b"".join(lines), str(self.journal))
            # One writer appends to the segment (`O_APPEND`, under the lock), so the file's size is the
            # byte offset just after this append's last line: the anchor a checkpoint records (B5).
            reached = os.fstat(fd).st_size
        except RecordUnwritable as exc:
            raise RecordUnwritable(
                f"the record at {self.journal} cannot be written or made durable: {exc}; the vehicle stops, and {after} (ADR 0002 J)"
            ) from exc
        except OSError as exc:
            raise RecordUnwritable(
                f"the record at {self.journal} cannot be written or made durable "
                f"({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror}); the vehicle stops, and {after} (ADR 0002 J)"
            ) from exc
        self._chain = chain
        if entry is not None:
            self._segment = entry
            self.segments.append(entry)
        if self._segment is not None:
            self._segment["chain"] = chain
            self._segment["offset"] = reached

    def root_record(self) -> dict[str, Any]:
        """The directory's record: which world this is, which windows it serves, its identity."""
        rings = dict(self.record_slugs)
        rings.update({slug: window.ring_slots for slug, window in self.windows.items()})
        return {
            # Bound by the first tick, like the windows' own records (ADR 0001 choice D) — or by a
            # checkpoint: a resumed world exists at tick 0 too (child 3, addendum B9).
            "world_id": self.world_id if self.tick > 0 or self.resumed else None,
            "slugs": sorted(rings),
            "scenario": self.scenario,
            "seed": self.seed,
            "ring_slots": {slug: rings[slug] for slug in sorted(rings)},
            "tick": self.tick,
            "updated_at": utc_now().isoformat(),
        }

    def _write_root_record(self, tick: int) -> None:
        """Write the directory's record; a failure is recorded like a window's, and the tick goes on.

        **The first version let this raise out of `cycle()`** (review F6): a directory put in place of
        `.executive.json` while the executive ran ended the run, which is the stop button ADR 0002 H
        takes away from the agents, moved from the lock to the record. The record is a copy — of the
        checkpoint with `--state-dir`, and of the executive's own memory without it — so a write that
        fails is counted, named on stderr and in `failures` under the stage `root_record` with the
        record's name where a window's slug goes, and the next cycle writes it again.
        """
        try:
            write_json_atomic(RECORD_FILE, self.root_record(), dir_fd=self.diode_fd)
        except Exception as exc:  # noqa: BLE001 - the record's failure, recorded, not the tick's
            self._record_failure_named(RECORD_FILE, "root_record", exc, tick)

    # -- ingress ------------------------------------------------------------------------------
    def _verdict(self, window: Window, command: str, state: str, body: str, **extra: Any) -> Verdict:
        self.receipt += 1
        window.receipts += 1
        return Verdict(command, state, body, self.receipt, window.receipts, self.tick, window.slug, **extra)

    def _ingest(self, window: Window, verdicts: list[Verdict]) -> list[Verdict]:
        """Claim one window's console and validate what it held, in order, into `verdicts` (the cycle's list)."""
        claimed = window.claim()
        if isinstance(claimed, str):
            verdicts.append(
                self._verdict(
                    window,
                    "console_unreadable",
                    "refused",
                    f"refused: {claimed}. The console has been claimed — commands emptied, "
                    "variables preserved — so this is one refusal and not one per cycle; rewrite "
                    "the whole file to submit again.\n",
                )
            )
            return verdicts
        if claimed and not all(isinstance(item, str) for item in claimed):
            # "One malformed element refuses the whole batch. If any element of `commands` is not a
            # string, none of it runs, and exactly one result file records that. Partial execution
            # of a malformed batch is worse than none."
            kinds = ", ".join(sorted({type(item).__name__ for item in claimed}))
            verdicts.append(
                self._verdict(
                    window,
                    "malformed_batch",
                    "refused",
                    "refused: the whole batch. It contained a non-string element "
                    f"({kinds}), so none of its {len(claimed)} command(s) ran. Exactly one result "
                    "records this, which is the contract's requirement and not a convenience: "
                    "partial execution of a malformed batch is worse than none.\n",
                )
            )
            return verdicts
        if len(claimed) > self.max_batch:
            verdicts.append(
                self._verdict(
                    window,
                    "batch_over_cap",
                    "refused",
                    f"refused: the whole batch. It held {len(claimed)} command(s) and this "
                    f"executive's cap is {self.max_batch} per window per cycle (`--max-batch`, an "
                    "operator ceiling a window cannot raise — ADR 0001 choice B). None of it ran, "
                    "by the same rule as a malformed batch: one result, and a window that floods "
                    "fills only its own output.\n",
                )
            )
            return verdicts
        for command in claimed:
            verdicts.append(self.validate(window, command))
        return verdicts

    def _settle(self, window: Window, verdicts: list[Verdict]) -> list[Verdict]:
        """Run every deferral of this window that has come due, and give each its own result.

        A due command is **revalidated** through the whole chain — phase, gate, interlocks,
        arguments, dwell, conflict — at the moment of effect, which is §9 check 9 and the reason the
        acceptance-time answer is not reused; its conflict domain is claimed *here*, at settlement,
        and not at acceptance. It **expires** if it has waited longer than its own
        `maximum_queue_age_s`, in simulated seconds: `(tick - accepted_tick) * dt`, so the poll
        interval no longer decides whether a command's intent has gone stale. And it **reports in a
        file of its own**, because a command that takes longer than one cycle reports when it is done.
        Each due entry leaves the queue as it is taken, and its verdict goes into `verdicts` (the
        cycle's list), so an internal fault part-way leaves neither a settled entry queued nor a
        settlement unrecorded (child 4's review finding 7). The entry is the parsed command (finding 4).
        """
        for entry in list(window.deferred):
            if self.tick < int(entry.get("due_tick", 0)):
                continue
            window.deferred = [queued for queued in window.deferred if queued is not entry]
            verb = str(entry.get("verb"))
            command = str(entry.get("command", verb))
            accepted_tick = int(entry.get("accepted_tick", self.tick))
            age = (self.tick - accepted_tick) * self.dt
            limit = entry.get("maximum_queue_age_s")
            if isinstance(limit, (int, float)) and age > float(limit):
                verdicts.append(
                    self._verdict(
                        window,
                        command,
                        "refused",
                        f"refused: EXPIRED. {verb!r} was accepted at tick {accepted_tick} and has "
                        f"waited {age:.1f} s of simulated time, past its own maximum_queue_age_s of "
                        f"{limit:g}. V-02 makes `EXPIRED` a refusal reached from REVALIDATING, so "
                        "the command is re-checked when it is due and it is *this* check that fires "
                        "first — a command whose intent has gone stale is declined rather than run "
                        "late.\n",
                        verb=verb,
                        settled=True,
                    )
                )
                continue
            verdicts.append(self.validate(window, command, settling=entry))
        return verdicts

    @staticmethod
    def parse_arguments(text: str) -> dict[str, str]:
        """`key=value` pairs from a command line, which is the form the contract's examples use.

        What the tokens *mean* is `argument_refusal`'s question, asked against the verb's own
        `argument_schema`; this only splits them.
        """
        arguments: dict[str, str] = {}
        for token in text.split()[1:]:
            if "=" in token:
                key, _, value = token.partition("=")
                arguments[key] = value
        return arguments

    @staticmethod
    def argument_refusal(verb: str, spec: dict[str, Any], arguments: dict[str, str]) -> str | None:
        """A command's arguments against its verb's `argument_schema`: three refusals, by name.

        The schema was documentation: the executive handed the whole parsed map to `apply_command`,
        which reads only the keys it needs, so a name the schema does not declare ran as if it were
        not there, an enum value off its list fell through to whatever the plant made of it, and a
        value had no size at all. A name not in the schema, an enum value not in its `values`, and a
        value past its declared `max_length` (or `ARGUMENT_LENGTH_BYTES` where none is declared) are
        refused here, before the effect is resolved. Nothing else is checked: a missing argument is
        the plant's to name (`NOT IMPLEMENTED` carries `Unconfigured`'s sentence), and a number's
        range is the verb's declaration to make.
        """
        schema = spec.get("argument_schema") or {}
        if not isinstance(schema, dict):
            schema = {}
        for name, value in arguments.items():
            declared = schema.get(name)
            if not isinstance(declared, dict):
                return (
                    f"refused: {name!r} is not an argument of {verb!r}. Its argument_schema declares "
                    f"{sorted(schema)}, and a name the schema does not declare is a name the plant "
                    "would silently ignore.\n"
                )
            limit = declared.get("max_length")
            bound = int(limit) if isinstance(limit, int) and not isinstance(limit, bool) else ARGUMENT_LENGTH_BYTES
            size = len(value.encode("utf-8"))
            if size > bound:
                source = "max_length" if isinstance(limit, int) and not isinstance(limit, bool) else "the vehicle's bound"
                return (
                    f"refused: {name!r} is {size} bytes, past its {source} of {bound}. A value with "
                    "no size is a result file and a value map with no size either.\n"
                )
            if declared.get("type") == "enum":
                values = [str(v) for v in declared.get("values") or []]
                if values and value not in values:
                    return (
                        f"refused: {name!r} is {value!r}, which is not one of {verb!r}'s declared "
                        f"values {values}. The enum is the registry's, and a value off it is a command "
                        "the plant has no mapping for.\n"
                    )
        return None

    @staticmethod
    def instantiate(template: str, arguments: dict[str, str]) -> str:
        """A template with every placeholder the command's own arguments can fill, filled."""
        for name in re.findall(r"<([^>]+)>", template):
            if name in arguments:
                template = template.replace(f"<{name}>", str(arguments[name]), 1)
        return template

    def conflict_domains(self, spec: dict[str, Any], arguments: dict[str, str]) -> list[str]:
        """The domain a command collides in: its verb's `conflict_domain`, instantiated.

        Most domains are plain names; a few are templates — `prop.<engine>.run` is one domain per
        engine. A placeholder names the argument it varies over, so the command's own argument fills
        it where it is given; where it is not, every instantiation is claimed, because a command
        that does not say which engine it means collides with all of them. The expansion rule is
        `gate_instantiations`', so the published gate variables and the conflict domains cannot
        disagree about how a template is read.
        """
        declared = spec.get("conflict_domain")
        if not declared:
            return []
        template = self.instantiate(str(declared), arguments)
        if "<" not in template:
            return [template]
        try:
            return gate_instantiations(template, spec.get("argument_schema") or {}, str(spec.get("verb")))
        except Unconfigured:
            # A domain that cannot be expanded is a domain nothing can collide in, which is worse
            # than a wrong one, so it is claimed under its literal text and the linter's business is
            # to refuse the template rather than this file's to guess.
            return [template]

    def gate_for(self, spec: dict[str, Any], arguments: dict[str, str], row: dict[str, Any]) -> tuple[str, list[str]]:
        """The command's own gate variable, and the instantiations its gate check reads.

        `set_rcs_mode mode=auto` is gated by `rcs_mode_auto_enable` and by nothing else: closing
        `rcs_mode_manual_enable` closes the manual command and not the verb. The old chain read the
        verb's row, which `capability_snapshot` closes when *any* instantiation is closed, and named
        the first instantiation whatever the command said. Where the command leaves a placeholder
        unfilled, every instantiation is read, as the conflict domain is.
        """
        gate = spec.get("gate") if isinstance(spec.get("gate"), dict) else {}
        template = str(gate.get("variable") or "")
        variable = self.instantiate(template, arguments) if template else ""
        if variable and "<" not in variable:
            return variable, [variable]
        instantiations = list(row.get("gate_variables") or [])
        return (instantiations[0] if instantiations else variable), instantiations

    def value_of(self, values: dict[str, Any], state: Any) -> list[str]:
        """The current value(s) of a state, as text, wherever the map keeps them (`value_of`)."""
        return value_of(values, state)

    def dwell_refusal(self, verb: str, staged: dict[str, Any] | None) -> str | None:
        """The minimum-dwell guard, in simulated seconds, evaluated at the moment of effect.

        `min_on_s` is how long the state must hold a value before it may change; `min_off_s` is
        how long it must stay away from a value before it may return to it. Both are measured from
        the last change on the executive's clock — `tick * tick_us + offset_us`, which cannot jump
        and does not care how long a fleet thought — and a state that has never changed has no
        floor, because the vehicle starts with its machine where the configuration put it.
        """
        now_us = self.tick * self.tick_us
        for state, min_on_s, min_off_s in command_dwell(self.world, verb):
            last = self.dwell.get(state.id)
            if last is None:
                continue
            if min_on_s is None or min_off_s is None:
                return (
                    f"refused: GUARD OWED. {verb!r} moves {state.id!r}, whose dwell is "
                    "UNCONFIGURED — so the vehicle cannot say how long that mode must be held "
                    "before it may be commanded again, and a command it cannot guard is a command "
                    "it must not accept. An owed dwell must stay visible until its command "
                    "policy or hardware path is resolved.\n"
                )
            held = (now_us - int(last["changed_at_us"])) / 1_000_000
            if held < min_on_s:
                return (
                    f"refused: DWELL. {verb!r} moves {state.id!r}, which was last changed "
                    f"{held:.1f} s ago and must hold a value for {min_on_s:g} s before it may "
                    "change. This is the guard that makes a commanded state machine a machine "
                    "rather than a relay — `check_domain` refuses a hysteresis band on one for "
                    "the same reason: a band answers 'has the quantity crossed', and a command "
                    "does not cross anything.\n"
                )
            was = last.get("was")
            if was is not None and min_off_s > 0 and staged is not None:
                away = (now_us - int(was["left_at_us"])) / 1_000_000
                becomes = self.value_of({**self.truth, **staged}, state)
                if becomes == was["value"] and away < min_off_s:
                    return (
                        f"refused: DWELL. {verb!r} would return {state.id!r} to a value it left "
                        f"{away:.1f} s ago, and it must stay away for {min_off_s:g} s before it "
                        "may go back. `propulsion.sps_state`'s five seconds are the case this "
                        "exists for: 'a five-second floor between burns is what keeps a fleet from "
                        "spending its restart budget in a minute'.\n"
                    )
        return None

    def interlock_reason(self, name: str) -> str:
        """Why one declared interlock cannot be evaluated this tick, from the configuration.

        The chain is the registry's own: the interlock names a threshold (`profiles.yaml`) with a
        comparator, a band and a dwell, the threshold watches a point, the point is a reading of a
        state, and the state either has a value this tick or does not. Where the whole chain reads,
        `validate` evaluates it (ADR 0004); this sentence is for the rest, and says which link is
        missing *first*, because that is what an implementer reads. **The sentence never carries the value**: a refusal is a result file
        an agent reads, and a live reading in it is truth published outside the instrument
        (`plant.md` §7) — the point *has* a reading or has none, and that is all a refusal may say.
        """
        # ADR 0004: the chain is `plant.resolve_interlock`'s, which `validate` evaluates where it reads;
        # this is the sentence for an interlock where it does not.
        interlock, problem = resolve_interlock(self.world, name)
        if interlock is None:
            return problem or f"`{name}` resolves to no threshold this executive can read"
        point = interlock.point
        source = str((self.world.points.get(point) or {}).get("from") or "")
        state = next((s for s in self.world.states if s.id == source), None)
        assert state is not None  # resolve_interlock refuses a point read from no state
        if state_level(self.truth, state) is None:
            if state.id in self.world.rules:
                # A domain rule that returned its honest `None` (`params.no_value`): the rule exists
                # and this tick is outside what it can answer. The rule's own reason carries the
                # live load and current, so it stays in the plant's gap, not in a refusal.
                why = "its rule has no value this tick (the plant's gap for the state says which limit)"
            elif state.method == "algebraic":
                why = "its algebraic rule is UNCONFIGURED"
            elif state.owed:
                why = f"it owes {', '.join(state.owed)}"
            else:
                why = "no tick has produced it"
            return (
                f"`{name}` watches `{point}`, read from `{source}` ({state.method}), which has no "
                f"value this tick: {why}"
            )
        return (
            f"`{name}` watches `{point}`, read from `{source}`, whose state has a value this tick and whose "
            "channel arithmetic gives no reading from it"
        )

    def validate(self, window: Window, command: str, settling: dict[str, Any] | None = None) -> Verdict:
        """The verdict for one line, in the chain's order; the first refusal wins.

        Empty; unknown verb; phase and tripped interlock (the capability snapshot) and this
        command's own gate; interlocks the executive cannot evaluate (ADR choice C); the arguments
        against the schema; dwell; argument resolution; conflict. Everything this refuses, it refuses
        by naming what refused it, because that is the property §9's checks 4 and 5 test. A verdict
        carries an `Effect` only when the command stages a state; the plant's `step` is the only
        thing that applies it.
        """
        text = command.strip()
        verb = text.split()[0] if text else ""

        def refused(body: str, state: str = "refused", **extra: Any) -> Verdict:
            if settling is not None and state in ("refused", "superseded"):
                body = (
                    f"refused: INHIBITED. {verb!r} was valid when it was accepted at tick "
                    f"{settling.get('accepted_tick')} and is not valid now that it is due at tick "
                    f"{self.tick} — validity at admission is not validity at effect, which is the "
                    "whole reason V-02 calls the state REVALIDATING (contract §9 check 9). The "
                    f"re-check said: {body}"
                )
                extra.setdefault("settled", True)
            return self._verdict(window, command, state, body, verb=verb or None, **extra)

        if not text:
            return refused("refused: empty command. There is no verb here to resolve.\n")
        spec = self.world.verbs.get(verb)
        if spec is None:
            return refused(
                f"refused: unknown verb {verb!r}. This vehicle's vocabulary is closed and is "
                f"published in HELP.md and in state.json's `available_commands`; {verb!r} is not "
                "in it. No effect, no spend, no state change.\n"
            )
        # The episode's allow-list (`--scenario-file`'s `verbs`), held here, so at acceptance and again
        # at settlement: a deferral accepted under it is revalidated against it when it comes due.
        if self.scenario_overlay is not None:
            try:
                self.scenario_overlay.admit(verb)
            except EffectRefused as exc:
                return refused(
                    f"refused: NOT IN THIS SCENARIO. {exc}. The world was started from that scenario "
                    "and its verb list is part of the run; no effect, no spend, no state change.\n"
                )
        row = next((r for r in window.capability(closed=False) if r["verb"] == verb), None)
        if row is None:
            return refused(f"refused: {verb!r} is registered and could not be resolved.\n")
        arguments = self.parse_arguments(text)
        gate_variable, gate_reads = self.gate_for(spec, arguments, row)
        if not row["available"]:
            return refused(
                f"refused: {verb!r} is closed. {row['availability_reason']}. The gate variable is "
                f"published in state.json.variables as {gate_variable!r}.\n"
            )
        shut = [name for name in gate_reads if name in window.closed_gates()]
        if shut:
            return refused(
                f"refused: {verb!r} is closed. gate: {shut[0]} is closed. The gate variable is "
                f"published in state.json.variables as {shut[0]!r}, and this window closed it.\n"
            )

        # The two-step verbs. `execute_event` checks its token *before* the interlock rule, so a
        # fleet is told "not armed" rather than "unevaluated" when it has no authority at all — and
        # the interlock refusal that follows does not consume a token it did not use.
        if verb == "execute_event":
            event = str(arguments.get("event", ""))
            offered = str(arguments.get("arm_token", ""))
            outstanding = window.arms.get(event)
            if outstanding is None:
                return refused(
                    f"refused: {verb!r} fires {event!r}, which is not armed in this window. This is "
                    "the arm-then-commit pattern the one-way event taxonomy is built on "
                    "(domains/structure/components.yaml#one_way_events): a pyro, an undocking and "
                    "a staging are irreversible, so the arming step is what separates a decision "
                    "from an accident. A token is bound to the window that armed it; nothing "
                    "written into pending.json is read back as one. Nothing has been fired.\n"
                )
            if not offered or offered != outstanding:
                return refused(
                    f"refused: {verb!r} offered arm_token {offered!r}, which is not the outstanding "
                    f"token for {event!r} in this window. A token is bound to one event and one "
                    "arming; a token for another event, or one already consumed, is not authority "
                    "to fire this one. Nothing has been fired.\n"
                )

        # ADR 0004 (narrowing ADR 0001 choice C): an interlock whose chain reads is evaluated against
        # its threshold's band and dwell, with the dwell history the truth carries; one whose chain
        # does not read is refused as unevaluated, as before. Only the interlocks that guard *this*
        # command's direction are asked (`interlocks_when`): the safing direction — an amplifier off,
        # a pump or an evaporator on under a hot loop — needs no guard and is taken however the guard
        # reads. Never the value: a refusal is a result file an agent reads, and a live reading in it
        # is truth outside the instruments.
        declared = guarding_interlocks(spec, arguments)
        unreadable = []
        tripped = []
        for name in declared:
            interlock, _problem = resolve_interlock(self.world, name)
            if interlock is None or point_reading(self.world, interlock.point, self.truth) is None:
                unreadable.append(name)
            elif interlock_tripped(self.world, interlock, self.truth):
                tripped.append(interlock)
        if tripped and not unreadable:
            named = ", ".join(
                f"`{interlock.name}` (threshold `{interlock.threshold}` on `{interlock.point}`)" for interlock in tripped
            )
            return refused(
                f"refused: INTERLOCK TRIPPED. {verb!r} is interlocked by {named}: the reading has been past its "
                "threshold for at least the threshold's declared dwell, so the command is not accepted "
                "(ADR 0004). Nothing has been staged"
                + (" and no arm token has been consumed" if verb == "execute_event" else "")
                + ".\n"
            )
        declared = unreadable
        if declared:
            reasons = "\n".join(f"  - {self.interlock_reason(name)}" for name in declared)
            return refused(
                f"refused: INTERLOCK UNEVALUATED. {verb!r} declares {len(declared)} interlock(s) "
                "this executive cannot evaluate, so it must not accept the command "
                "(ADR 0001 choice C: a command it cannot guard is a command it must not accept — "
                f"the same rule an owed dwell is refused by):\n{reasons}\n"
                "The executive evaluates an interlock whose threshold, band, dwell and reading all "
                "resolve (ADR 0004); each line above names the link that does not. Nothing has been staged"
                + (" and no arm token has been consumed" if verb == "execute_event" else "")
                + ".\n"
            )

        bad_argument = self.argument_refusal(verb, spec, arguments)
        if bad_argument is not None:
            return refused(bad_argument)

        # The effect is resolved on a copy of the truth *before* anything is stamped, so `step`
        # never raises for an argument the corpus has not answered, and the dwell's return-to-value
        # half can see what the command would make the state.
        staged: dict[str, Any] | None = None
        unconfigured: Unconfigured | None = None
        if _stages_a_state(self.world, verb):
            probe = {**self.truth, "internal": dict(self.truth.get("internal") or {})}
            try:
                staged = apply_command(self.world, probe, verb, arguments)
            except Unconfigured as exc:
                unconfigured = exc
        guard = self.dwell_refusal(verb, staged)
        if guard is not None:
            return refused(guard)
        if unconfigured is not None:
            return refused(
                f"refused: NOT IMPLEMENTED. {verb!r} is a valid command and the vehicle cannot "
                f"apply it yet: {unconfigured}. The declaration is complete and the value is not — "
                "the corpus says which state this command moves and what each of its argument's "
                "values becomes, and what it does not yet say is what one of those values *is*.\n"
            )

        # The conflict policy, checked *after* everything that could refuse the command on its own:
        # `:578` says "first **valid** command", and a refusal that claimed the domain would let a
        # closed gate block a working command behind it. A deferral does not claim here either — it
        # claims when it settles, at the moment of effect.
        domains = self.conflict_domains(spec, arguments)
        for domain in domains:
            winner = self.claimed.get(domain)
            if winner is None:
                continue
            if winner.command.strip() == text:
                return refused(
                    f"accepted: DUPLICATE. {verb!r} is the same text as receipt #{winner.local} "
                    f"from window {winner.window!r}, the first valid command in conflict domain "
                    f"{domain!r} this tick, so it is accepted as a duplicate of it and stages "
                    "nothing further: a command takes effect at most once per tick, and a repeated "
                    "line is a repeated command rather than a second effect.\n",
                    "duplicate",
                    arguments=arguments,
                )
            return refused(
                f"refused: CONFLICT_SUPERSEDED. {verb!r} is valid but {winner.verb!r} from window "
                f"{winner.window!r} (receipt #{winner.local}) was the first valid command in "
                f"conflict domain {domain!r} this tick, and first valid wins (apollo_diode.md:578). "
                "Nothing is silently discarded — apollo:579 is explicit that the loser must be told, "
                "which is why this is a result file and not a dropped line. Re-issue next tick if "
                "the effect is still wanted.\n",
                "superseded",
                arguments=arguments,
            )

        if verb == "arm_event":
            # Reached only once `arm_event`'s own interlocks can be evaluated (WP05). The token is
            # bound to this window and this event, minted from the window's identity, and it is
            # never read back from any file.
            event = str(arguments.get("event", ""))
            if not event:
                return refused(f"refused: {verb!r} names no event, so there is nothing to arm.\n")
            verdict = self._verdict(window, command, "accepted", "", verb=verb, arguments=arguments)
            token = hashlib.sha256(
                f"{window.boot_id}:{window.slug}:{event}:{self.tick}:{verdict.receipt}".encode()
            ).hexdigest()[:16]
            window.arms[event] = token
            window.accepted += 1
            verdict.body = (
                f"accepted: {verb!r} armed {event!r} for window {window.slug!r}. Token: {token}\n"
                "This is the only result on the vehicle that carries a token, and it is bound to "
                "this window and this event: `execute_event` will refuse a token minted for a "
                "different one, from a different window, or already consumed. Arming does nothing "
                "physical — every guard is evaluated at the moment of effect, not now.\n"
            )
            return verdict

        verdict = self._verdict(window, command, "accepted", "", verb=verb, arguments=arguments)

        if row["deferrable"] and settling is None:
            # §9 check 9's whole content is *when* the re-check happens — "a deferred command is
            # re-checked when it is due, not when it was scheduled" — and the contract is equally
            # clear that the result arrives later. So the deferral is a live queue entry in ticks,
            # and `_settle` runs the whole chain again when it is due. It is counted as accepted
            # once, here; its settlement is the same command reporting. **It is due at the next cycle's
            # start, `tick + k`** (#23, design §1): `tick + 1` named a tick a cycle of `k` never starts at.
            # It settles at the first cycle boundary at or after its due tick, which after a crash
            # mid-cycle and a resume at `a + j` is a later one (`a + j + i·k`) — the text says so.
            window.accepted += 1
            due = self.tick + self.cycle_ticks
            # The parse, not the line: a deferral is queued, checkpointed and recorded as its verb, its
            # schema-checked arguments and the command they spell (child 4's review finding 4).
            window.deferred.append(
                {
                    "verb": verb,
                    "command": canonical_command(verb, arguments),
                    "arguments": dict(arguments),
                    "accepted_tick": self.tick,
                    "due_tick": due,
                    "maximum_queue_age_s": spec.get("maximum_queue_age_s"),
                    "receipt": verdict.local,
                }
            )
            verdict.state = "deferred"
            verdict.body = (
                f"accepted: {verb!r} deferrable. Recorded at tick {self.tick}, due at tick {due} (later across a restart); "
                "it will be re-checked against the phase, its gate, its interlocks, its dwell and "
                "its conflict domain when it is due rather than now (contract §9 check 9), and it "
                f"expires if it is still waiting after {spec.get('maximum_queue_age_s')} s of "
                "simulated time (V-02's `EXPIRED`). The result arrives as its own file when it "
                "settles, because a command that takes longer than one cycle reports when it is "
                "done.\n"
            )
            return verdict

        for domain in domains:
            self.claimed.setdefault(domain, verdict)
        if settling is not None:
            verdict.state = "settled"
            verdict.settled = True
            age = (self.tick - int(settling.get("accepted_tick", self.tick))) * self.dt
            verdict.body = (
                f"settled: {verb!r} at tick {self.tick}, {age:.1f} s after acceptance at tick "
                f"{settling.get('accepted_tick')}, re-checked against the phase, its gate, its "
                "interlocks, its dwell and its conflict domain at the moment of effect rather than "
                "at the moment it was scheduled. "
            )
        else:
            window.accepted += 1
            declared = spec.get("interlocks")
            declared = [str(g) for g in declared] if isinstance(declared, list) else []
            guards = guarding_interlocks(spec, arguments)
            if guards:
                checked = f"interlock(s) {', '.join(guards)} evaluated and none tripped (ADR 0004). "
            elif declared:
                checked = (
                    f"interlock(s) {', '.join(declared)} guard the other direction of this verb, not "
                    "this one (ADR 0004). "
                )
            else:
                checked = "no interlocks declared. "
            verdict.body = (
                f"accepted: {verb!r}. Authority {spec.get('authority')}, phase {self.phase}, gate "
                f"{gate_variable!r} open, " + checked
            )
        if staged is None:
            verdict.body += (
                f"No physical state staged: {verb!r} reads, configures or reports, so the plant's "
                "value map is unchanged by it and the tick carried on.\n"
            )
            return verdict
        verdict.effect = Effect(0, verb, arguments)
        return verdict

    def _report_effect(self, verdict: Verdict, before: dict[str, Any], after: dict[str, Any]) -> str:
        """What the step made of the command's own target states, written after the step.

        The sentence names the states the command declares it moves (`command_targets`) and their
        values in the stepped truth — the command's own declared effect, not hidden truth beyond
        it. The wording stays the old console's ("Changed: bus_tie=closed") so readers can follow.
        The dwell's clock is written only where a value actually moved: a command that set what was
        already set has changed nothing and must not restart the floor. **And the value left is the
        value the state held before the change**, from the first change on: the first version read
        it from the previous *record*, which was empty at the first change, so the first return to
        the configuration's initial value was never guarded.
        """
        verb = str(verdict.verb)
        now_us = verdict.tick * self.tick_us + verdict.effect.offset_us
        changed = dwell_after_effect(self.world, self.dwell, verb, now_us, before, after)
        if changed:
            return (
                f"succeeded: {verb!r} applied at tick {verdict.tick}, offset 0 µs. "
                f"Changed: {', '.join(changed)}.\n"
            )
        return (
            f"succeeded: {verb!r} applied at tick {verdict.tick}, offset 0 µs. No value changed: "
            "the states it moves already held what it sets, which is what `idempotent: true` "
            "means.\n"
        )


class TakeUnretirable(RuntimeError):
    """A take a resume must retire before it advances the boot marker could not be (issue #39)."""


class WindowAbsent(RuntimeError):
    """A window's directory or subdirectory is gone (`ENOENT`) — distinct from a link or a wrong type.

    Nothing was planted and there is nothing to follow; the window's identity (its `seq`, `boot_id`
    and queue) is the executive's, not the directory's. So the executive records the dark tick and
    re-prepares the directory for the next one, where a planted link or a wrong type stays a skip.
    """


@dataclass
class Handles:
    """One cycle's open directories of one window: the directory, `output/`, `telemetry/`."""

    root: int
    output: int
    telemetry: int

    def close(self) -> None:
        for fd in (self.root, self.output, self.telemetry):
            with contextlib.suppress(OSError):
                os.close(fd)


class Window:
    """One `<slug>` directory: ingress, gate preferences, results, deferrals, ring. No physics.

    A window is created by `Executive.attach` and never on its own, and everything it knows about
    the vehicle it reads from the executive at publication time. What it owns is the fleet-facing
    half of the contract for one principal: the claim, the result files, the variables the agent
    may lower, the deferral queue, the arm tokens bound to it, and the ring's slot count. It is an
    agent's directory, so it is opened once per cycle as a set of handles that follow no link, and
    every read, write, rename, unlink and listing is relative to them.
    """

    FILES = ("console.json", "state.json", "HELP.md", "README.md", "pending.json")

    def __init__(self, executive: Executive, root: Path, slug: str, *, ring_slots: int) -> None:
        self.executive = executive
        self.root = root
        self.slug = slug
        # **The ring's slot count, which the contract demands and nothing bounded.**
        # `docs/diode-contract.md:183-189`: "**Publish a ring, not a snapshot.** ... A bonded ring of
        # recent frames with a **fixed slot count** is self-describing about its own cadence and its
        # own losses". `presentation.yaml#ring` declares the cadence *structure* and deliberately
        # declines to set the count — "a slot count is a memory decision" — so the run declares it.
        self.ring_slots = max(1, int(ring_slots))
        # The window's files, by *name*: every operation on them is relative to the directory handle
        # of the cycle, never by a path an agent can redirect.
        self.console = "console.json"
        self.output = "output"
        self.telemetry = "telemetry"
        self.state = "state.json"
        self.help_file = "HELP.md"
        self.readme = "README.md"
        self.pending = "pending.json"
        self.handles: Handles | None = None
        # **Preserved, verbatim.** The contract: `variables` is "a flat map of gate settings the
        # vehicle chooses to honour. Persistent — the vehicle never clears it", and the claim rewrites
        # the console "with commands emptied and variables preserved". So this is exactly the object
        # the agent last wrote (replace, not merge — bounded by construction, because it came from a
        # file of at most `MAX_READ_BYTES` and the rewrite is no larger), and what the vehicle
        # *honours* of it is computed from it each cycle by `honoured()`.
        self.variables: dict[str, Any] = {}
        # Whether `variables` is the map the agent last wrote. A resume does not have it — ADR 0002 G
        # keeps it out of the checkpoint, in the agent's own console — until it reads a console that
        # carries one; while it is unknown the gates are at their defaults and no rewrite of the
        # console invents a map (child 3).
        self.variables_known = True
        # The frame number the record's mark for this cycle named, so a publication that fails before
        # its frame still consumes it (design note S16); `None` when this cycle did not mark the window.
        self.marked_seq: int | None = None
        # `honoured()`'s answer for the current preserved map, computed once per cycle after the
        # claim and invalidated when the map is replaced.
        self._honoured: tuple[dict[str, bool], int] | None = None
        self.deferred: list[dict[str, Any]] = []
        # Outstanding arm tokens, by event, bound to this window. Never read back from a file.
        self.arms: dict[str, str] = {}
        self.seq = 0
        self.receipts = 0
        # The newest tick a frame or mirror of this window has been allowed to describe: set once the
        # cycle's record, which carries it, is durable (ADR 0002 J rule 2), and `None` until the
        # window first publishes. `checkpoint.capture_state` saves it.
        self.published_tick: int | None = None
        # The window-local receipts of the results this cycle's publication has written so far; the
        # executive empties it before each publication and notes it after (ADR 0002 J rule 3).
        self.landed: list[int] = []
        self.boot_id = uuid.uuid4().hex
        self.started = utc_now()
        self.accepted = 0
        # The claim's take (#39, option B): `[name, phase]` while a console taken aside still has work to
        # do — "unanswered" until the take is durable and read, "retire" until it is removed or moved
        # aside, "barrier" until that removal is durable. While it is set the window claims nothing and
        # adopts no map: one take per window, ever, so a take can never outlive a newer map.
        self.take: list[str] | None = None
        self.take_seq = 0
        # A republish that failed after a take, so the next claim's republish of the absent console is
        # not also refused as an absent console.
        self.republish_owed = False
        # Whether this boot has cleared the window of takes from other boots and of moved-aside ones, and
        # whether a removal it made still waits for its directory `fsync` (remembered across retries).
        self.swept = False
        self.sweep_barrier = False
        # A resume's map recovery not yet finished, because its sweep's barrier failed: `[evidence]`, the
        # ended boot's take it keeps for the retry (or `[None]`). The window claims and adopts nothing
        # until the recovery is done.
        self.recovering: list[str | None] | None = None
        # A resume's map recovery that never started, because the window failed before it read its takes
        # (an `output/` an agent replaced, a listing that failed): the ended boot, kept so the claim starts
        # the recovery before any sweep, which would otherwise retire that boot's take unread.
        self.recover_owed = False
        self.recover_from: list[str] = []
        # A take kept because it holds the window's map and nothing else on disk does (issue #39): the
        # republish after it lost to an agent's console without `variables`, or failed, or a resume adopted
        # the map from it while the console carries none. Never swept; retired by `_settle_held` once
        # the console carries a map again, or when a newer take takes over holding it.
        self.held: str | None = None
        # Whether the take being carried brought a `variables` object, so it is the map's newest copy.
        self.take_map = False
        # **The slow cadence** (#23, design §1 and §7): whether this window's next publication rewrites
        # its generated `HELP.md` and `README.md` and reconciles its ring with a scan of `telemetry/` —
        # on a segment's first cycle (a new `Window` is one), after a repair, and on the cycle after the
        # one that crossed a multiple of `N` (`Executive._refresh_next`); never every cycle.
        self.refresh = True
        # **The ring's held frames, `(number, name)` oldest first, kept in memory** (design §7) — a cache on
        # the window, independent of the per-cycle handles: `None` until a scan fills it, then pushed and
        # pruned by name per frame. At 3,000 slots and ten windows, four listings per window per cycle
        # were 120,000 directory entries a cycle. `ring_dir` is the `(st_dev, st_ino)` of the `telemetry/`
        # the last cycle opened: another one means an agent replaced the directory, and the cache is dropped.
        self.ring: deque[tuple[int, str]] | None = None
        self.ring_dir: tuple[int, int] | None = None

    # -- the directory ----------------------------------------------------------------------
    def open_handles(self) -> Handles:
        """Open the window's directory and its two subdirectories, following no link, and check the files.

        `alpha/telemetry -> ../bravo/telemetry` let alpha's ring prune bravo's frames; `alpha/output
        -> <anywhere>` wrote result files outside the diode directory. The three directories are opened
        `O_DIRECTORY | O_NOFOLLOW` relative to the diode handle and to each other — a link is `ELOOP`
        and a file where a directory should be is `ENOTDIR`, and either is this window's failure for
        the cycle, with no write — and the five files are `lstat`ed through the directory handle:
        regular where they exist, never a link. The handles are what every operation of the cycle
        then uses, which is what makes the check more than a check.
        """
        self.close_handles()

        def opened(name: str, dir_fd: int) -> int:
            where = name if dir_fd == self.executive.diode_fd else f"{self.slug}/{name}"
            try:
                return open_directory(name, dir_fd=dir_fd)
            except FileNotFoundError as exc:
                raise WindowAbsent(
                    f"{where} is absent (ENOENT); the window is re-prepared for the next cycle"
                ) from exc
            except OSError as exc:
                code = errno.errorcode.get(exc.errno or 0, type(exc).__name__)
                raise RuntimeError(
                    f"{where}: {code} ({exc.strerror}); a window is a directory of regular files and "
                    "directories, and the vehicle follows no link an agent plants"
                ) from exc

        root = opened(self.slug, self.executive.diode_fd)
        output = telemetry = None
        try:
            output = opened(self.output, root)
            telemetry = opened(self.telemetry, root)
            # The ring's cache describes the directory it was built from (#23, design §7): an agent that
            # replaced `telemetry/` replaced what it held, so a changed identity drops it, and the next
            # frame rescans. Opening it every cycle is not a scan trigger.
            info = os.fstat(telemetry)
            identity = (info.st_dev, info.st_ino)
            if self.ring_dir is not None and identity != self.ring_dir:
                self.ring = None
            self.ring_dir = identity
            for name in self.FILES:
                try:
                    info = os.lstat(name, dir_fd=root)
                except FileNotFoundError:
                    continue
                if stat.S_ISLNK(info.st_mode):
                    raise RuntimeError(f"{self.slug}/{name} is a symlink, and the vehicle follows none")
                if not stat.S_ISREG(info.st_mode):
                    raise RuntimeError(f"{self.slug}/{name} is not a regular file")
        except BaseException:
            for fd in (root, output, telemetry):
                if fd is not None:
                    with contextlib.suppress(OSError):
                        os.close(fd)
            raise
        self.handles = Handles(root, output, telemetry)
        return self.handles

    def close_handles(self) -> None:
        if self.handles is not None:
            self.handles.close()
            self.handles = None

    def _handles(self) -> Handles:
        if self.handles is None:
            raise RuntimeError(f"window {self.slug!r} is not open; a window is used inside a cycle")
        return self.handles

    # -- setup ------------------------------------------------------------------------------
    def prepare(self) -> None:
        """Create the window and write its unbound record. Nothing physical is published yet.

        `console.json` is written last, because it is the file a reader treats as "the vehicle is
        here": a window with the console and not yet the mirror is a vehicle that appears to publish
        nothing. The record says `world_id: null` and `ticks: 0` — the first cycle to tick this
        window binds it — and that is also exactly what `--init` leaves behind. The directories are
        made relative to the diode handle and checked by opening them; a window whose `output/` is a
        file is a `RuntimeError` the executive records against the window.
        """
        with contextlib.suppress(FileExistsError):
            os.mkdir(self.slug, dir_fd=self.executive.diode_fd)
        root = open_directory(self.slug, dir_fd=self.executive.diode_fd)
        try:
            for name in (self.output, self.telemetry):
                with contextlib.suppress(FileExistsError):
                    os.mkdir(name, dir_fd=root)
        finally:
            os.close(root)
        handles = self.open_handles()
        write_text_atomic(self.readme, self.executive.readme_text, dir_fd=handles.root)
        write_text_atomic(self.help_file, self.executive.help_text, dir_fd=handles.root)
        write_json_atomic(self.state, self.mirror(), dir_fd=handles.root)
        write_json_atomic(self.pending, {
            "pending": [],
            "ticks": 0,
            "seq": 0,
            "ring_slots": self.ring_slots,
            "world_id": None,
        }, dir_fd=handles.root)
        # Made only where none is (#39, option B): a link fails rather than replace a console an agent
        # put there after any check, which `lstat` then `os.replace` did.
        with contextlib.suppress(FileExistsError):
            write_json_atomic(self.console, {"commands": [], "variables": {}}, dir_fd=handles.root, noclobber=True)

    def repair(self, *, console: bool = True) -> None:
        """Make a window's missing directories again, and an empty console where none is — nothing else.

        Repair is not initialisation (addendum B7): a directory lost while the vehicle runs, or while
        it is down, is re-made handle-relative and following no link, and the next publication writes
        its mirror, `pending.json` and generated files from the state the executive holds. `prepare`
        wrote `pending.json` at tick 0 here, which showed a window an earlier tick than it had seen. The
        window's next publication rewrites the generated files and rescans its ring (#23, design §1, §7).
        """
        self.refresh = True
        self.ring = None
        with contextlib.suppress(FileExistsError):
            os.mkdir(self.slug, dir_fd=self.executive.diode_fd)
        root = open_directory(self.slug, dir_fd=self.executive.diode_fd)
        try:
            for name in (self.output, self.telemetry):
                with contextlib.suppress(FileExistsError):
                    os.mkdir(name, dir_fd=root)
            # A resume repairs without the console (#39, option B): `recover_map` puts it back once it knows
            # the map, and a console made here first would read as present and hide the take's.
            if console:
                with contextlib.suppress(FileExistsError):
                    write_json_atomic(self.console, self.claimed_console(), dir_fd=root, noclobber=True)
        finally:
            os.close(root)

    # -- the claim --------------------------------------------------------------------------
    def claim(self) -> list[Any] | str:
        """Take the console aside and answer what was taken, *before* acting on anything.

        The contract's order: "**Intake is destructive and atomic.** ... **Clear before you act.**" So
        the claim happens here and the commands are returned for the executive to validate afterwards.
        A console that is not one — a link, not a regular file, oversized, invalid, not an object — is
        *also* claimed, and the reason is returned instead of a batch for the one refusal result
        (ADR 0001).

        **Preserved verbatim; honoured separately.** `variables` is "persistent — the vehicle never
        clears it": the object the agent wrote becomes the preserved map as written (replace, not
        merge; a payload without a `variables` object keeps the previous map), bounded by
        construction because it came from a file of at most `MAX_READ_BYTES`. What the vehicle acts
        on is `honoured()`'s business, computed from the preserved map once per cycle.

        **A console with nothing to claim is left as it is (#39, tier 1):** an object whose `commands`
        is exactly `[]` and that already shows the map — its own `variables` object, adopted, or no
        `variables` key while the window has none. Decided from types alone, before the map is
        adopted, so no JSON value can make it raise.

        **Anything else is taken by a rename, never rewritten over (#39, option B).** The claim was a
        read and then an `os.replace` of a fresh copy, and no rename can check that the file it
        replaces is the file it read: a batch put in place between the two was renamed over, unread.
        Now the console is renamed aside — `rename` moves whatever is at the name at that instant, a
        link as a link — and **what was taken is the claim**, read through its private name; a batch
        the agent put in place before the take superseded the one read, as on any filesystem. The
        take is durable before anything is answered (#21's rule: the record may not outrun it). The
        emptied console is then put back by a `link`, which fails rather than replace a console the
        agent has already written again; that one is left for the next claim. So the console is never
        a vehicle file older than the agent's newest, and is briefly absent while a claim takes it
        (John, 2026-10-11: agents read an absent console as transient).

        **One take per window, ever** (`self.take`): a take whose durability, removal or removal's
        durability fails stays pending, the window claims nothing and adopts no map until it is
        done, and each cycle retries it; a take that cannot be removed is moved aside, and only one
        that can be neither blocks the window, naming itself every cycle. Nothing after the take
        withholds a batch that was answered: a failure there is recorded beside its verdicts.
        """
        root = self._handles().root
        durable = self.executive.journal is not None
        if self.recover_owed:
            self.recover_map(root, self.recover_from)
        if self.recovering is not None and not self._finish_recovery(root, durable):
            return []
        if not self.swept and not self._sweep(root, durable):
            return []
        if self.take is not None:
            outcome = self._carry_take(root, durable)
            if outcome is not None or self.take is not None:
                return [] if outcome is None else outcome
        self._settle_held(root, durable)
        payload, problem = read_ingress(self.console, dir_fd=root)
        if payload is None:
            try:
                info = os.lstat(self.console, dir_fd=root)
            except FileNotFoundError:
                return self._republish_absent(root, durable, str(problem))
            if stat.S_ISDIR(info.st_mode):
                raise RuntimeError(f"{self.slug}/{self.console} is a directory; a console is a file, and a directory is not taken")
        else:
            commands = payload.get("commands")
            variables = payload.get("variables")
            if (
                isinstance(commands, list)
                and not commands
                and (isinstance(variables, dict) or ("variables" not in payload and not self.variables_known))
            ):
                if isinstance(variables, dict):
                    self._adopt(variables)
                return []
        self.take_seq += 1
        name = f"{TAKE_PREFIX}{self.executive.boot_id}.{self.take_seq}"
        try:
            os.rename(self.console, name, src_dir_fd=root, dst_dir_fd=root)
        except FileNotFoundError:
            return []
        self.take = [name, "unanswered"]
        outcome = self._carry_take(root, durable)
        return [] if outcome is None else outcome

    def _adopt(self, variables: dict[str, Any]) -> None:
        """Replace, not merge: the object the agent wrote *is* the preserved map."""
        self.variables = variables
        self.variables_known = True
        self._honoured = None

    def _failed(self, exc: BaseException) -> None:
        """A failure after the take, recorded against the window beside whatever the claim answers."""
        self.executive._record_failure(self, "claim", exc, self.executive.tick)

    @staticmethod
    def _errno(exc: OSError) -> str:
        return f"{errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror}"

    @classmethod
    def _describe(cls, exc: BaseException) -> str:
        return cls._errno(exc) if isinstance(exc, OSError) else f"{type(exc).__name__}: {exc}"

    def _carry_take(self, root: int, durable: bool) -> list[Any] | str | None:
        """Carry the pending take as far as it goes: durable, read and answered, republished, removed, durable.

        Returns the claim's answer when this call read the take, else `None`. Whatever stays undone is
        left in `self.take`, and the window claims nothing until a later cycle finishes it.
        """
        assert self.take is not None
        name, phase = self.take
        outcome: list[Any] | str | None = None
        if phase == "unanswered":
            if durable:
                try:
                    os.fsync(root)
                except OSError as exc:
                    self._failed(
                        RuntimeError(
                            f"the console taken as {self.slug}/{name} cannot be made durable ({self._errno(exc)}); none of it "
                            "is answered or run until it is, and the window claims nothing meanwhile"
                        )
                    )
                    return None
            outcome = self._read_take(root, name)
            try:
                # `False` is the agent's newer console, left for the next claim: either way none is owed.
                # Its directory entry is made durable by the take's removal barrier below, one `fsync` for both.
                self._republish(root, durable, sync_dir=False)
                self.republish_owed = False
            except Exception as exc:  # noqa: BLE001 - after the read nothing may withhold the answer
                self.republish_owed = True
                self._failed(
                    RuntimeError(
                        f"the emptied console could not be put back after the take ({self._describe(exc)}); it is absent until "
                        "the next claim puts it back"
                    )
                )
            self.take[1] = phase = "retire"
        if phase == "retire":
            if self.take_map and self.variables_known and not self._console_has_map(root):
                # Issue #39: this take is the map's only copy on disk (the republish lost to an agent's
                # console without `variables`, or failed). Kept, not retired, until the console carries one.
                previous, self.held = self.held, name
                self.take, self.take_map = None, False
                if previous is not None and previous != name:
                    self._retire_held(root, durable, previous)
                return outcome
            if not self._remove_take(root, name):
                return outcome
            self.take[1] = phase = "barrier"
        if durable:
            try:
                os.fsync(root)
            except OSError as exc:
                self._failed(
                    RuntimeError(
                        f"the removal of the take {self.slug}/{name} cannot be made durable ({self._errno(exc)}); the window "
                        "claims nothing and adopts no map until it is"
                    )
                )
                return outcome
        self.take, self.take_map = None, False
        return outcome

    def _console_has_map(self, root: int) -> bool:
        """Whether the console on disk carries a `variables` object: the map's durable copy, ours or the agent's newer one."""
        payload, _problem = read_ingress(self.console, dir_fd=root)
        return payload is not None and isinstance(payload.get("variables"), dict)

    def _retire_held(self, root: int, durable: bool, name: str) -> None:
        """Retire a held take whose map has another copy; a removal not yet durable leaves only an older map that nothing prefers."""
        self._retire_entry(root, name, DEAD_PREFIX + name[len(TAKE_PREFIX):], blocking=False)
        if durable:
            with contextlib.suppress(OSError):
                os.fsync(root)

    def retire_superseded_takes(self, root: int, boots: list[str]) -> set[str]:
        """Before a resume advances the marker: when the console carries a map, retire the earlier boots' takes, durably.

        Returns the boots that still have a take here. Raises `TakeUnretirable` when a superseded take
        can be neither removed nor moved aside, or its retirement cannot be made durable.
        """
        if not boots:
            return set()
        prefixes = {f"{TAKE_PREFIX}{boot}.": boot for boot in boots}
        found = [(entry, boot) for entry in os.listdir(root) for prefix, boot in prefixes.items() if entry.startswith(prefix)]
        if not found or not self._console_has_map(root):
            return {boot for _entry, boot in found}
        for entry, _boot in found:
            if not self._retire_entry(root, entry, DEAD_PREFIX + entry[len(TAKE_PREFIX):], blocking=False):
                raise TakeUnretirable(f"{self.slug}/{entry}, which {self.slug}/{self.console} supersedes, cannot be removed or moved aside")
        if self.executive.journal is not None:
            try:
                os.fsync(root)
            except OSError as exc:
                raise TakeUnretirable(f"the retirement of {self.slug}'s superseded takes cannot be made durable ({self._errno(exc)})") from exc
        return set()

    def _settle_held(self, root: int, durable: bool) -> None:
        """Retire the held take once the console carries a map again (issue #39)."""
        if self.held is not None and self._console_has_map(root):
            name, self.held = self.held, None
            self._retire_held(root, durable, name)

    def _read_take(self, root: int, name: str) -> list[Any] | str:
        """What was taken is the claim: its commands, or the reason it is not a console; its map, adopted."""
        payload, problem = read_ingress(name, dir_fd=root, label=self.console)
        if payload is None:
            return str(problem)
        commands = payload.get("commands")
        variables = payload.get("variables")
        if isinstance(variables, dict):
            self._adopt(variables)
            self.take_map = True
        if commands is None:
            return []
        if not isinstance(commands, list):
            return (
                f"console.json's `commands` is a JSON {type(commands).__name__}, not a list, so "
                "there is no batch here to run"
            )
        return commands

    def _republish(self, root: int, durable: bool, *, sync_dir: bool | None = None) -> bool:
        """Put the emptied console back where none is; `False` when the agent has already written one."""
        text = dumps_json(self.claimed_console(), indent=2, sort_keys=False) + "\n"
        try:
            write_text_atomic(
                self.console, text, dir_fd=root, noclobber=True, sync_file=durable, sync_dir=durable if sync_dir is None else sync_dir
            )
        except FileExistsError:
            return False
        return True

    def _republish_absent(self, root: int, durable: bool, problem: str) -> list[Any] | str:
        """An absent console: put the emptied one back, refused once — unless the agent made one meanwhile."""
        owed, self.republish_owed = self.republish_owed, False
        if not self._republish(root, durable):
            return []
        return [] if owed else problem

    def _remove_entry(self, root: int, name: str) -> None:
        if stat.S_ISDIR(os.lstat(name, dir_fd=root).st_mode):
            shutil.rmtree(name, dir_fd=root)
        else:
            os.unlink(name, dir_fd=root)

    def _remove_take(self, root: int, name: str) -> bool:
        """Remove the take, else move it aside where nothing reads it; `False` only when neither can be done."""
        dead = DEAD_PREFIX + name[len(TAKE_PREFIX):]
        return self._retire_entry(root, name, dead, blocking=True)

    def _retire_entry(self, root: int, name: str, dead: str, *, blocking: bool) -> bool:
        """Remove `name`, else rename it to `dead`; `False` only when neither works.

        **Any** exception counts, not only `OSError`: `rmtree` on a deeply nested directory an agent swapped
        in raises `RecursionError`, and an exception escaping here would drop an answer already read.
        """
        try:
            self._remove_entry(root, name)
            return True
        except FileNotFoundError:
            return True
        except Exception as exc:  # noqa: BLE001 - see the docstring
            try:
                os.rename(name, dead, src_dir_fd=root, dst_dir_fd=root)
            except Exception as again:  # noqa: BLE001 - named in the failure
                consequence = (
                    "the window claims nothing until it is gone, and removing it unblocks it" if blocking
                    else "nothing reads it, and it does not block the window"
                )
                self._failed(
                    RuntimeError(
                        f"{self.slug}/{name} cannot be removed ({self._describe(exc)}) or moved aside ({self._describe(again)}); "
                        + consequence
                    )
                )
                return False
            self._failed(
                RuntimeError(
                    f"{self.slug}/{name} cannot be removed ({self._describe(exc)}); it is moved aside to {dead}, which "
                    "nothing reads, and removed when the window next starts"
                )
            )
            return True

    def _sweep(self, root: int, durable: bool, *, keep: str | None = None) -> bool:
        """Once a boot, before any claim or adoption: retire takes other boots left, and takes moved aside.

        None of them is read. Each is removed, else moved aside; one that can be neither is named and
        left (it is not this boot's, so nothing ever reads it, and it blocks nothing). The removals are
        made durable before the window claims or adopts anything (B5): `False` while that barrier
        fails, and the next cycle tries again. `keep` is the take a resume is still reading.
        """
        current = f"{TAKE_PREFIX}{self.executive.boot_id}."
        pending = {self.take[0]} if self.take is not None else set()
        if keep is not None:
            pending.add(keep)
        if self.held is not None:
            pending.add(self.held)
        try:
            names = os.listdir(root)
        except OSError as exc:
            self._failed(RuntimeError(f"the window {self.slug} cannot be listed for leftover takes ({self._errno(exc)})"))
            return False
        for entry in names:
            if entry in pending:
                continue
            if entry.startswith(DEAD_PREFIX):
                dead = entry
            elif entry.startswith(TAKE_PREFIX) and not entry.startswith(current):
                dead = DEAD_PREFIX + entry[len(TAKE_PREFIX):]
            else:
                continue
            self.sweep_barrier = True
            if entry == dead:
                try:
                    self._remove_entry(root, entry)
                except FileNotFoundError:
                    pass
                except Exception as exc:  # noqa: BLE001 - named; a moved-aside file blocks nothing
                    self._failed(RuntimeError(f"{self.slug}/{entry}, moved aside earlier, cannot be removed ({self._describe(exc)}); nothing reads it"))
            else:
                self._retire_entry(root, entry, dead, blocking=False)
        if self.sweep_barrier and durable:
            try:
                os.fsync(root)
            except OSError as exc:
                self._failed(
                    RuntimeError(
                        f"the removal of earlier takes from {self.slug} cannot be made durable ({self._errno(exc)}); the window "
                        "claims nothing and adopts no map until it is"
                    )
                )
                return False
        self.sweep_barrier = False
        self.swept = True
        return True

    def recover_map(self, root: int, boots: list[str]) -> None:
        """A resume's map (#39, option B): the console's own, else the newest take carrying one, else unknown.

        A take speaks for the map only to the resumes after the boot that made it, while the boot marker
        names that boot (`boots`, newest first: the boot that ended, then any whose own resume did not
        finish recovering, issue #39). Its newest take carrying a `variables` object holds the newest map
        claimed — a newer take without one kept that map — unless the console carries its own, which is
        newer. An absent console is put back with the map chosen; a console the agent made meanwhile is
        read once more. The take is then retired before the first claim, like any take, unless it is
        the map's only copy on disk, when it is held.
        """
        durable = self.executive.journal is not None
        evidence = None
        if boots:
            entries = os.listdir(root)
            for boot in boots:
                prefix = f"{TAKE_PREFIX}{boot}."
                numbered = sorted(
                    ((int(entry[len(prefix):]), entry) for entry in entries if entry.startswith(prefix) and entry[len(prefix):].isdigit()),
                    reverse=True,
                )
                for _n, entry in numbered:
                    taken, _problem = read_ingress(entry, dir_fd=root, label=self.console)
                    if taken is not None and isinstance(taken.get("variables"), dict):
                        evidence = entry
                        break
                if evidence is not None:
                    break
        self.recovering = [evidence]
        self.recover_owed, self.recover_from = False, []
        self._finish_recovery(root, durable)

    def _finish_recovery(self, root: int, durable: bool) -> bool:
        """The resume's recovery, retried each cycle until its sweep is durable; `False` while it waits.

        Every other take is retired, durably, before the map is read (B3 §1 step 1, B5); while that
        barrier fails, nothing is adopted and the ended boot's take is kept for the retry.
        """
        assert self.recovering is not None
        evidence = self.recovering[0]
        if not self._sweep(root, durable, keep=evidence):
            return False
        self.recovering = None
        payload, _problem = read_ingress(self.console, dir_fd=root)
        from_take = False
        if payload is not None and isinstance(payload.get("variables"), dict):
            self._adopt(payload["variables"])
        elif evidence is not None:
            taken, _problem = read_ingress(evidence, dir_fd=root, label=self.console)
            if taken is not None and isinstance(taken.get("variables"), dict):
                self._adopt(taken["variables"])
                from_take = True
        if payload is None:
            try:
                os.lstat(self.console, dir_fd=root)
            except FileNotFoundError:
                if not self._republish(root, durable):
                    again, _problem = read_ingress(self.console, dir_fd=root)
                    if again is not None and isinstance(again.get("variables"), dict):
                        self._adopt(again["variables"])
        if evidence is not None:
            # Held rather than retired when the console still carries no map (issue #39): see `_carry_take`.
            self.take, self.take_map = [evidence, "retire"], from_take
            self._carry_take(root, durable)
        return True

    def claimed_console(self) -> dict[str, Any]:
        """What the claim rewrites the console to: commands emptied, the preserved `variables` — when known.

        A resumed window whose console could not be read has no map to preserve (ADR 0002 G keeps it
        out of the checkpoint); its claim leaves the `variables` key out rather than writing `{}`,
        which would read as "the vehicle cleared it", and the window honours the defaults until the
        agent writes a console that carries one. The mid-run claim is this same rule with a known map.
        """
        if not self.variables_known:
            return {"commands": []}
        return {"commands": [], "variables": self.variables}

    def honoured(self) -> tuple[dict[str, bool], int]:
        """What the vehicle honours of the preserved map: the published gates, and the allowance.

        **Preserved is not honoured.** The map is the agent's and is kept verbatim; what the vehicle
        acts on is computed from it here, every cycle, and nothing in it can raise: a name is a gate
        only where the registry publishes one by that (instantiated) name and its value is a bool —
        anything else is treated as absent, so the gate stays at its default; `allowance` is honoured
        only as a non-negative integer, clamped to the operator's ceiling (§9 check 8: a preference
        may lower, never raise) — anything else leaves the ceiling in force. `{"allowance": "lots"}`
        was a `ValueError` in every tick's publication before this split.
        """
        if self._honoured is not None:
            return self._honoured
        gates: dict[str, bool] = {}
        allowance = DEFAULT_ALLOWANCE
        for name, value in self.variables.items():
            key = str(name)
            if key == "allowance":
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    allowance = min(value, DEFAULT_ALLOWANCE)
            elif key in self.executive.gate_names and isinstance(value, bool):
                gates[key] = value
        self._honoured = (gates, allowance)
        return self._honoured

    @property
    def allowance(self) -> int:
        return self.honoured()[1]

    def closed_gates(self) -> set[str]:
        return {name for name, value in self.honoured()[0].items() if not value}

    def capability(self, *, closed: bool = True) -> list[dict[str, Any]]:
        """The capability snapshot as this window sees it: its own closed gates, the operator's trips.

        With `closed=False` the window's gates are left out, for the per-command gate check: the
        snapshot closes a *verb* when any instantiation is closed, and a command is gated by its own.
        """
        rows = capability_snapshot(
            self.executive.world,
            phase=self.executive.phase,
            closed_gates=self.closed_gates() if closed else set(),
            tripped_interlocks=self.executive.tripped,
        )
        # Under a scenario, its verb list is the command surface: `available_commands` and the gate
        # variables name only what the run admits, as HELP.md does.
        admitted = self.executive.admitted_verbs
        return rows if admitted is None else [row for row in rows if row["verb"] in admitted]

    # -- results ----------------------------------------------------------------------------
    def write_result(self, command: str, body: str) -> Path:
        """One file per command, refusals included, and nothing ever overwritten.

        The name is `<stamp>_<slug>_<sanitised command>.txt`, made with `os.link` relative to the
        `output/` handle, which fails rather than replaces: a filename collision inside one
        microsecond is possible when a batch repeats a command, and the contract forbids
        overwriting — so the second one gets a suffix rather than replacing the first.
        """
        output = self._handles().output
        moment = utc_now()
        base = f"{stamp(moment)}_{self.slug}_{sanitise(command)}"
        name = f"{base}.txt"
        counter = 1
        while True:
            try:
                write_text_atomic(name, body, dir_fd=output, noclobber=True, sync_file=self.executive.journal is not None)
                return self.root / self.output / name
            except FileExistsError:
                name = f"{base}_{counter}.txt"
                counter += 1

    def receipt(self, verdict: Verdict) -> str:
        """The block every result ends with: where in the one world this result was decided.

        `seq` is this window's own count of results, so a window learns how many results it has
        been given and not how many the world has; the world and the tick are shared facts.
        """
        offset_us = verdict.effect.offset_us if verdict.effect is not None else 0
        return (
            f"receipt: world={self.executive.world_id} seq={verdict.local} window={self.slug} "
            f"tick={verdict.tick} offset_us={offset_us} state={verdict.state}\n"
        )

    # -- publication ------------------------------------------------------------------------
    def publish(self, verdicts: list[Verdict]) -> list[Path]:
        """Results, one frame, `state.json` and `pending.json` every cycle; `HELP.md` and `README.md` on the slow cadence.

        `state.json` is rewritten "whether or not anything was submitted", which is what makes the
        probe's `check_state_is_a_mirror` meaningful. **The generated files are rewritten from the
        cached text every `N` ticks, not every cycle** (John, #23 design §1): 85 KB a window a cycle was
        the cost ADR 0002 B moved to a slower cadence. They are rewritten at the end of the cycle *after*
        the one that crossed a multiple of `N`, so the static and the checkpoint costs normally fall in
        different cycles — also on a segment's first cycle and the cycle after a repair (`refresh`); when
        `N = k` every cycle checkpoints, and a first-cycle or repair rewrite can coincide with a
        checkpoint. A hand-edit lasts about a mission second. The same publication reconciles the ring
        with one scan (`ring`). The window-local
        receipts of its results are appended to `landed` — and named in the record's `results_written`
        note (ADR 0002 J rule 3) — only once their files and `output/` are durable; a publication that
        fails before that leaves them owed (review F2), and the window's next publication finds what did
        reach the disk by its receipt line.
        """
        root = self._handles().root
        written = []
        # What the window is owed from earlier cycles first, so a failure here leaves this cycle's
        # results owed too rather than written ahead of older ones (addendum B4).
        for outcome in self.executive.publish_obligations(self):
            if "file" in outcome:
                written.append(self.root / self.output / outcome["file"])
        made: list[int] = []
        for verdict in sorted(verdicts, key=lambda v: v.receipt):
            written.append(self.write_result(verdict.command, verdict.body + self.receipt(verdict)))
            made.append(verdict.local)
        if made and self.executive.journal is not None:
            # Each result file was `fsync`ed as it was made; the directory makes their names durable, and
            # only then are they landed — noted, and not owed (child 4's review finding 6; review F2 and
            # ruling R2: a directory `fsync` that fails leaves every one of them owed and none noted).
            # With no record nothing relies on it, and nothing is `fsync`ed.
            os.fsync(self._handles().output)
            self.landed.extend(made)
            self.executive._note_window_results(self)
        else:
            self.landed.extend(made)
        refresh = self.refresh
        if refresh:
            self.ring = None  # the reconcile: this frame's prune rescans `telemetry/` once
        # The frame first, so the mirror's ring accounting describes the directory as it is: the old
        # console wrote the mirror before the frame and its `newest_seq` ran one behind the ring.
        self.write_frame()
        write_json_atomic(self.state, self.mirror(), dir_fd=root)
        if refresh:
            write_text_atomic(self.help_file, self.executive.help_text, dir_fd=root)
            write_text_atomic(self.readme, self.executive.readme_text, dir_fd=root)
            self.refresh = False
        write_json_atomic(
            self.pending,
            {
                "pending": self.deferred,
                "ticks": self.executive.tick,
                "seq": self.seq,
                "boot_id": self.boot_id,
                # **No scenario and no seed.** The run's identity is the operator's: it lives in the
                # directory's `.executive.json` (and on the startup banner), which no agent can read
                # under the per-slug mounts; checkpoints will carry it too once they are written. This file is in the agent's own window, and the seed keys the
                # fault plan and the scenario names how hard the run is — telling the fleet either
                # would do part of the diagnosis for it.
                # The ring's own accounting: what it is bounded to, and what it has lost.
                "ring_slots": self.ring_slots,
                "ring_losses": self.ring_losses(),
                # The binding (ADR 0001 choice D): which world's physics this window has shown.
                "world_id": self.executive.world_id,
            },
            dir_fd=root,
        )
        return written

    def mirror(self) -> dict[str, Any]:
        """`state.json`: the capability snapshot, the gates, the budget, the ring, the executive."""
        executive = self.executive
        rows = self.capability()
        variables = {name: True for row in rows for name in row["gate_variables"]}
        # The window's honoured gates win where they name a published one, because the console is
        # the fleet's hand and the registry is only the default. §9 check 8's direction is that the
        # console may lower and never raise, so a gate the window has closed stays closed.
        honoured, allowance = self.honoured()
        variables.update(honoured)
        held, losses = self.ring_counts()
        return {
            "published_at": utc_now().isoformat(),
            "available_commands": [row["verb"] for row in rows if row["available"]],
            "variables": variables,
            # The budget's *semantics* — what a window-hour is, when the oldest spend expires — are
            # WP08's with the clock; `oldest_expires_in_seconds` still counts the wall clock here.
            "budget": {
                "used_this_window": self.accepted,
                "limit_per_window": allowance,
                "window_seconds": 3600,
                "oldest_expires_in_seconds": 3600 - int((utc_now() - self.started).total_seconds()),
            },
            "queue_depth": len(self.deferred),
            # **The ring, described rather than only published**: the bound, what is held, what fell
            # out of the far end, and `held + losses` is what the window has produced.
            "ring": {
                "slots": self.ring_slots,
                "held": held,
                "losses": losses,
                "newest_seq": max(0, self.seq - 1),
            },
            # `posture` is the *execution* machine's posture (`mission.yaml#postures`), which the
            # executive does not drive and which stays empty. The run's difficulty (`scenario`) is
            # not published: it is the operator's record of the run, not something the vehicle's
            # instruments could tell a crew, and `presentation.yaml#mirror` never declared it.
            "vehicle": {
                "phase": executive.phase,
                "posture": "",
                "abort_latched": False,
            },
            # Which world this window is a view of, and how far it has ticked. No truth, no lineage,
            # and no roster: which other windows exist is the executive's to know, not a window's.
            "executive": {
                "world_id": executive.world_id if executive.tick > 0 else None,
                "tick": executive.tick,
            },
            "capability": rows,
        }

    def ring_frames(self) -> list[str]:
        """The frames the ring holds, oldest first, by *number* — and only the frames.

        `sorted(glob("*.json"))` put `1000.json` before `999.json`, so from the thousandth frame the
        pruner deleted the newest frame every tick and the ring froze. The frames are the regular,
        non-link entries of the `telemetry/` handle whose stem is all digits **and below the window's
        own `seq`** — a number this boot has written — ordered by `int(stem)`; anything else in the
        directory is neither held, nor pruned, nor counted, so junk dropped there, numbered or not,
        cannot push a real frame out (`900000.json` sorts after every real frame and would otherwise
        have been held as the newest). The `NNN` minimum-three-digit naming stays for readers that
        already sort it.
        """
        telemetry = self._handles().telemetry
        frames: list[tuple[int, str]] = []
        with os.scandir(telemetry) as entries:
            for entry in entries:
                stem, dot, suffix = entry.name.rpartition(".")
                if not dot or suffix != "json" or not stem.isdigit() or int(stem) >= self.seq:
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                frames.append((int(stem), entry.name))
        return [name for _, name in sorted(frames)]

    def ring_counts(self) -> tuple[int, int]:
        """`(held, losses)` from the ring's cache, scanning `telemetry/` once if there is none (#23, design §7).

        `losses` is derived, not counted: the frames this window has produced that the ring no longer
        holds, `seq − held`. An agent's deletion is not seen until the next reconcile, at most `N` ticks
        later; until then `held` counts what the vehicle last knew it held.
        """
        if self.ring is None:
            self.ring = deque((int(name.rpartition(".")[0]), name) for name in self.ring_frames())
        held = len(self.ring)
        return held, max(0, self.seq - held)

    def ring_losses(self) -> int:
        """Frames this window has produced that the ring no longer holds — derived, not counted."""
        return self.ring_counts()[1]

    def write_frame(self) -> None:
        """Append one frame from the stepped truth, and drop the ones that fall out of the far end.

        **The instrument between truth and this frame is the identity, until WP09.** `emit_frame`
        publishes the declared channels — never residuals, rings, the sentinel or fault plans — and
        every measurement channel carries the truth's own number with no noise, lag, quantisation or
        quality model; `quality` is empty. ADR 0001 records that substitution, and so does this.

        `NNN.json` is the *sequence* number, so a name is never reused and a reader can always tell
        a new frame from a rewritten one. The bound is a deletion rather than a wrap, for the same
        reason, and the deletion is relative to the `telemetry/` handle. **The held list is the
        window's cache** (#23, design §7): the new frame is pushed onto it and the oldest pruned by name,
        with no listing; the one scan is made where the cache is empty — a segment's first cycle, a
        reconcile every `N` ticks, a replaced `telemetry/`, a repair. A name an agent already deleted is
        pruned as gone; a frame is forgotten only once its `unlink` succeeded (or found it gone), and any
        other failure drops the cache — recorded, and the publication goes on — so the counts are a rescan's
        rather than a prune around a frame still on disk.
        """
        executive = self.executive
        telemetry = self._handles().telemetry
        met_s = executive.tick * executive.tick_us / 1_000_000
        frame = emit_frame(
            executive.world,
            tick=executive.tick,
            seq=self.seq,
            boot_id=self.boot_id,
            met_s=met_s,
            sensor_time_s=met_s,
            values=executive.truth,
            quality={},
            phase=executive.phase,
            vehicle="csm",
            state_revision=executive.tick,
        )
        name = f"{self.seq:03d}.json"
        write_json_atomic(name, frame, dir_fd=telemetry)
        self.seq += 1
        if self.ring is None:
            self.ring_counts()  # the scan, which finds the frame just written
        else:
            self.ring.append((self.seq - 1, name))
        assert self.ring is not None
        while self.ring is not None and len(self.ring) > self.ring_slots:
            _number, stale = self.ring[0]
            try:
                os.unlink(stale, dir_fd=telemetry)
            except FileNotFoundError:
                pass  # gone already (an agent deleted it): pruned all the same
            except OSError as exc:
                # A frame that could not be deleted is still on disk, so the cache would forget a frame the
                # ring holds and prune newer ones in its place (candidate 1, Codex P2). The cache is dropped
                # instead, and the failure is recorded as the window's `prune` — while the publication goes
                # on (candidate 2, systems P3): the mirror and `pending.json` are still written, their counts
                # from a rescan of what is on disk, so a deletion that keeps failing costs a scan a cycle,
                # not the window's whole publication.
                self.ring = None
                self.executive._record_failure(self, "prune", exc, self.executive.tick - self.executive.cycle_ticks)
                break
            self.ring.popleft()


# The old name, for readers of the round log: the class that used to own the physics.
Console = Window


# -- resume (ADR 0002, WP08 child 3 — #21) ------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioFile:
    """An episode's overlay on the declared vehicle (`plant.Scenario`), as a window run names it.

    `--scenario-file` (not `--scenario`, which names the fault posture): the file's initial conditions
    seed a **new** world's MET 0 (`plant.initial_values(world, scenario)`), its `verbs` are the
    allow-list `validate` holds every command to at acceptance and again at settlement, and its name
    and the SHA-256 of its bytes are the world's identity (`identity.scenario_file` in every
    checkpoint), so a resume names the same file or is refused.
    """

    path: Path
    scenario: Scenario
    sha256: str

    @property
    def identity(self) -> dict[str, str]:
        return {"name": self.scenario.name, "sha256": self.sha256}


def load_scenario_file(world: World, path: Path) -> ScenarioFile:
    """The scenario file, read once and hashed from the bytes read; a `ValueError` naming why not.

    A scenario's `script` is batch mode's (`plant.run_scenario`): a window run takes its commands
    through the window, so a file that carries one is refused rather than half-applied.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"--scenario-file {path} cannot be read ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror})") from None
    if len(raw) > MAX_READ_BYTES:
        raise ValueError(f"--scenario-file {path} is {len(raw)} bytes, past the {MAX_READ_BYTES} a scenario may be")
    digest = hashlib.sha256(raw).hexdigest()
    # `plant.load_scenario` reads a path; it is handed a private copy of the bytes hashed, so the file
    # the world starts from is the file its identity names even if the original is replaced meanwhile.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / Path(path).name
        copy.write_bytes(raw)
        try:
            scenario = load_scenario(world, copy)
        except Unconfigured as exc:
            raise ValueError(f"--scenario-file {path} is not a scenario this vehicle runs: {exc}") from None
        except Exception as exc:  # noqa: BLE001 - a file that is not YAML, or not a mapping, is refused by name
            raise ValueError(f"--scenario-file {path} cannot be read as a scenario ({type(exc).__name__}: {exc})") from None
    if scenario.script:
        raise ValueError(
            f"--scenario-file {path} carries a `script`, which is batch mode's: a window run takes its commands "
            "through the window, so the file is refused rather than half-applied"
        )
    return ScenarioFile(Path(path), scenario, digest)


def scenario_refusal(named: ScenarioFile | None, body: dict[str, Any], path: Path) -> str | None:
    """The sentence a restart is refused with when its scenario file is not the world's, or `None`.

    The checkpoint's `identity.scenario_file` is the overlay the world started from (absent: the declared
    vehicle). A resume names the same file, by its bytes, or is refused: a different file, or none, would
    resume a world under initial conditions and an allow-list it did not start with.
    """
    saved = body["identity"].get("scenario_file")
    world_id = body["identity"]["world_id"]
    if saved is None and named is None:
        return None
    if saved is None:
        assert named is not None
        return (
            f"--scenario-file names {named.path} (scenario {named.scenario.name!r}, sha256 {named.sha256}) and the checkpoint "
            f"{path} records world {world_id} started from the declared vehicle with no scenario: a scenario seeds a new "
            "world's MET 0 and is never laid over a running one"
        )
    if named is None:
        return (
            f"the checkpoint {path} records world {world_id} started from scenario {saved['name']!r} (sha256 "
            f"{saved['sha256']}) and this start names no --scenario-file: a resume names the scenario its world started "
            "from, so that its verb allow-list still holds"
        )
    if named.sha256 != saved["sha256"]:
        return (
            f"--scenario-file names {named.path} (scenario {named.scenario.name!r}, sha256 {named.sha256}) and the checkpoint "
            f"{path} records world {world_id} started from scenario {saved['name']!r} (sha256 {saved['sha256']}): a "
            "different file is a different world, never a changed flag"
        )
    return None


def identity_refusal(args: argparse.Namespace, body: dict[str, Any], path: Path) -> str | None:
    """The one sentence a restart naming another world's identity is refused with, or `None` (commitment 2).

    A checkpoint is the world; a flag that names the run's identity either names nothing (`None`: the
    checkpoint's is resumed) or names the checkpoint's. A different slug set, scenario, seed, phase or
    ring bound would be a different world, and that is the operator's `--new-world` (#28), never a
    changed flag. The sentence names the flag, both values and the file.
    """
    world_id = body["identity"]["world_id"]
    tail = (
        f"(world {world_id}): a restart resumes the world its state directory holds, and a different world is the "
        "operator's --new-world (#28), not a changed flag"
    )
    saved_slugs = sorted(body["windows"])
    if args.slug is not None and sorted(args.slug) != saved_slugs:
        return f"--slug names {sorted(args.slug)} and the checkpoint {path} records {saved_slugs} {tail}"
    for flag, named, saved in (
        ("--scenario", args.scenario, body["run"]["scenario"]),
        ("--seed", args.seed, body["run"]["seed"]),
        ("--phase", args.phase, body["run"]["phase"]),
    ):
        if named is not None and named != saved:
            return f"{flag} names {named!r} and the checkpoint {path} records {saved!r} {tail}"
    if args.ring_slots is not None:
        for slug in saved_slugs:
            saved = body["windows"][slug]["ring_slots"]
            if args.ring_slots != saved:
                return f"--ring-slots names {args.ring_slots} and the checkpoint {path} records {saved} for window {slug!r} {tail}"
    return None


def state_record_files(state_fd: int, journal_fd: int | None, journal: Path | None) -> list[str]:
    """The journal files that hold a segment of a record — read to their first header only (S11).

    The state directory's segments, and an explicit `--journal`'s file when there is one. A file that
    holds only startup events (a refused start's) holds no record; one that cannot be read past its
    startup events, or holds a line before any header, is named too — it is not a fresh directory.
    """
    places: list[tuple[int, str]] = [(state_fd, name) for name in sorted(os.listdir(state_fd)) if JOURNAL_SEGMENT_NAME.fullmatch(name)]
    if journal is not None and journal_fd is not None:
        with contextlib.suppress(FileNotFoundError):
            os.lstat(journal.name, dir_fd=journal_fd)
            places.append((journal_fd, journal.name))
    # An `OSError` here (a listing or an `lstat` that fails) is the caller's to turn into a refusal by
    # name; `RecordRefused` from a file's first lines means the file is not a fresh directory's.
    holding = []
    for dir_fd, name in places:
        try:
            if _first_header(dir_fd, name) is not None:
                holding.append(name)
        except RecordRefused:
            holding.append(name)
    return holding


class ResumeRefused(Exception):
    """A saved world this start will not resume; the message is the operator's sentence."""


@dataclass
class Resumption:
    """What a resume did, for the banner, the journal and the tests."""

    snapshot_tick: int
    tick: int
    fell_back: str | None
    root_record: str
    run_inputs: dict[str, Any]
    advisories: list[dict[str, Any]]
    events: list[dict[str, Any]] = field(default_factory=list)
    republished: list[dict[str, Any]] = field(default_factory=list)

    @property
    def replayed(self) -> int:
        return self.tick - self.snapshot_tick


def classify_root_record(
    record: dict[str, Any] | None, problem: str | None, expected: dict[str, Any], snapshot_tick: int
) -> tuple[str, str]:
    """`reconcile_root_record` against the *recovered* state, with one more answer: `routine` (#20's note 1).

    The root record is rewritten every cycle after the cycle's row (`cycle`), and a checkpoint is taken
    every `N` ticks, so on an ordinary restart the record is ahead of the checkpoint and at, or one
    behind, the last durable row `L`. Compared with the checkpoint's own tick that is a disagreement on
    every boot, and the `root_record_rewritten` event would stop meaning "damaged or tampered". So the
    record is compared with the state the replay recovered: a record that agrees on every identity key
    but the tick, naming this world at a tick in `[T, L]`, is **routine** — journaled inside the
    `resumed` event and rewritten without a mismatch event. So is an unbound record at tick 0 beside a
    world whose checkpoint is its genesis and that recovered at most one tick (`T = 0`, `L ≤ 1`: addendum
    B9 as widened by review F8 and bounded by confirmation G7 — a kill after the first row and before the
    first root-record write leaves it, and nothing later does). Everything else is
    `reconcile_root_record`'s: agree, rewrite with its event, or — a readable record of another world —
    refuse. A record ahead of `L` is a disagreement: an `fsync`ed row does not vanish.
    """
    action, why = reconcile_root_record(record, problem, expected)
    if action != "rewrite" or record is None or problem is not None:
        return action, why
    tick, bound = record.get("tick"), record.get("world_id")
    if not all(record.get(key) == expected[key] for key in ROOT_RECORD_IDENTITY if key not in ("world_id", "tick")):
        return action, why
    recovered = expected["tick"]
    if bound == expected["world_id"] and isinstance(tick, int) and not isinstance(tick, bool) and snapshot_tick <= tick <= recovered:
        return "routine", f"the root record is at tick {tick}, within the checkpoint's tick {snapshot_tick} and the recovered tick {recovered}: routine"
    if bound is None and tick == 0 and snapshot_tick == 0 and recovered <= 1:
        # The genesis checkpoint precedes every row, so a kill after the first row and before the first
        # cycle's root-record write leaves exactly this (review F8) — and only up to `L = 1`: every later
        # cycle rewrites the record, so an unbound one beside more is not what a kill leaves (confirmation G7).
        return "routine", f"the root record is unbound at tick 0 beside a world saved at tick 0 and recovered to tick {recovered}: routine"
    return action, why


def _newest_journal_mtime(executive: Executive) -> tuple[str | None, str]:
    """`wall_down`, and where it came from: the newest journal file's last write (rows carry no wall stamp)."""
    dir_fd = executive.journal_dir_fd
    if dir_fd is None or executive.journal is None:
        return None, "no record"
    names = [executive.journal.name] if executive.journal_shared else [n for n in os.listdir(dir_fd) if JOURNAL_SEGMENT_NAME.fullmatch(n)]
    newest: tuple[float, str] | None = None
    for name in names:
        with contextlib.suppress(OSError):
            info = os.lstat(name, dir_fd=dir_fd)
            if stat.S_ISREG(info.st_mode) and (newest is None or info.st_mtime > newest[0]):
                newest = (info.st_mtime, name)
    if newest is None:
        return None, "no journal file"
    return datetime.fromtimestamp(newest[0], UTC).isoformat(), f"mtime of {newest[1]}, its last append"


def resume_executive(
    world: World,
    diode_dir: Path,
    loaded: Any,
    *,
    boot_id: str | None = None,
    state_dir: Path | None = None,
    state_fd: int | None = None,
    journal: Path | None = None,
    journal_dir_fd: int | None = None,
    max_batch: int | None = None,
    closed_interlocks: set[str] | None = None,
    checkpoint_every: int | None = None,
    diode_fd: int | None = None,
    multiplier: Fraction | int | str | None = None,
    cycle_ticks: int | None = None,
    pacer: Pacer | None = None,
) -> tuple[Executive, Resumption]:
    """An executive resumed from a verified checkpoint (`checkpoint.choose_generation`) and the record after it.

    ADR 0002 F1, G, J and L, as the design note for child 3 (#21) and its addenda decide them:

    1. The executive is built at the checkpoint's phase, scenario and seed, and its windows are
       attached **without preparing them** (`attach(prepare=False)`), so nothing in a window is written
       before the state exists.
    2. The record is read from the checkpoint's anchor through the held handle (`read_record(anchor=)`)
       and replayed onto the body (`replay_record`): every row after the snapshot's tick `T` to the last
       durable row `L`. Mission time resumes at `L` (F1). There is no effect-free tail to step: a
       window's published tick is set only after its cycle's row is durable, so it is never past `L`.
    3. `restore_state` sets the world, the tick, truth, dwell, lineage, the receipt counters, the
       segments and every window's `seq`, receipts, spend, deferrals, arm tokens and published tick.
       Each window keeps its new `boot_id`, so the frames say the vehicle restarted; `seq` continues.
    4. The operator's live inputs: a named `--max-batch` replaces the saved one; named interlocks are
       added to the saved trips (a restart that names none cannot un-trip one). **The clock** (#23,
       design §3): each of `m` (`multiplier`), `k` (`cycle_ticks`) and `N` (`checkpoint_every`) is the
       named value, else the newest recovered policy — the newer of the checkpoint's `clock` and the last
       replayed segment's header — resolved *after* the replay and validated together. Changes are
       journaled, and the checkpoint the caller takes before serving makes them durable.
    5. The root record is classified against the recovered state (`classify_root_record`); the
       `resumed` event — the downtime gap `(wall_down, wall_up, tick)`, the generation and whether it
       was a fall-back, the root record's class, the run-input changes and any `pending.json`
       advisories — is journaled, then a mismatch event if there is one, then the record is rewritten.
    6. Each window is opened once: a lost directory is repaired (never re-initialised), the agent's
       preserved `variables` are read back from its console without claiming it, and a window that
       cannot be opened is a recorded failure — never a refused start, because a file an agent planted
       in its own window must not hold the vehicle dark.

    Refusals are `ResumeRefused`, with the executive closed. The caller holds the lock.
    """
    body = loaded.body
    run = body["run"]
    snapshot_tick = int(body["identity"]["tick"])
    try:
        # Built at `k = 1` and the checkpoint's `N`, both of which any world accepts: the clock it serves on
        # is resolved after the replay (`_resume`), from the flags or the newest recovered policy.
        executive = Executive(
            world,
            diode_dir,
            phase=run["phase"],
            scenario=run["scenario"],
            seed=run["seed"],
            max_batch=run["max_batch"],
            journal=journal,
            record_slugs={slug: row["ring_slots"] for slug, row in body["windows"].items()},
            state_dir=state_dir,
            boot_id=boot_id,
            state_fd=state_fd,
            journal_dir_fd=journal_dir_fd,
            checkpoint_every=(body.get("clock") or {}).get("N"),
            diode_fd=diode_fd,
            pacer=pacer,
        )
    except ValueError as exc:
        raise ResumeRefused(str(exc)) from exc
    except OSError as exc:
        raise ResumeRefused(_io_refusal(exc, Path(state_dir) if state_dir is not None else Path(diode_dir))) from exc
    named = (
        multiplier_text(parse_multiplier(multiplier) if isinstance(multiplier, str) else multiplier) if multiplier is not None else None,
        cycle_ticks,
        checkpoint_every,
    )
    try:
        return executive, _resume(executive, world, loaded, snapshot_tick, max_batch, closed_interlocks, named)
    except OSError as exc:
        # Every I/O failure on the resume's path is a refusal by name, never a traceback (review F4).
        with contextlib.suppress(OSError):  # the refusal is what is raised (J4)
            executive.close()
        raise ResumeRefused(_io_refusal(exc, executive.state_dir or executive.journal or Path(diode_dir))) from exc
    except BaseException:
        with contextlib.suppress(OSError):
            executive.close()
        raise


def _io_refusal(exc: OSError, where: Path) -> str:
    """The sentence for an `OSError` on the resume's path: the file (or the directory it was under) and the errno."""
    named = exc.filename if isinstance(exc.filename, (str, bytes, os.PathLike)) else where
    code = errno.errorcode.get(exc.errno or 0, type(exc).__name__)
    return f"the resume could not read or write {os.fsdecode(named)} ({code}: {exc.strerror}); nothing was claimed"


def _resume(
    executive: Executive,
    world: World,
    loaded: Any,
    snapshot_tick: int,
    max_batch: int | None,
    closed_interlocks: set[str] | None,
    named: tuple[str | None, int | None, int | None] = (None, None, None),
) -> Resumption:
    body = loaded.body
    where = f"the checkpoint at {loaded.path}"
    if executive.journal is None or executive.journal_dir_fd is None:
        raise ResumeRefused(f"{where} can only be resumed with its record, and no journal is named for this executive")
    anchor = record_anchor(body)
    try:
        if executive.journal_shared:
            record = read_record(executive.journal, dir_fd=executive.journal_dir_fd, names=[executive.journal.name], anchor=anchor)
        else:
            record = read_record(executive.state_dir or executive.journal.parent, dir_fd=executive.journal_dir_fd, anchor=anchor)
        with record:
            replayed = replay_record(world, body, record)
            unwritten = unwritten_results(record)
    except RecordRefused as exc:
        raise ResumeRefused(f"the record cannot continue {where}: {exc}") from exc
    recovered = replayed.body
    tick = int(recovered["identity"]["tick"])
    for slug, row in recovered["windows"].items():
        if row["published_tick"] is not None and row["published_tick"] > tick:
            raise ResumeRefused(f"window {slug!r} was published at tick {row['published_tick']}, past the record's last durable tick {tick}")
    for slug in sorted(recovered["windows"]):
        executive.attach(slug, ring_slots=recovered["windows"][slug]["ring_slots"], prepare=False)
    try:
        restore_state(executive, recovered)
    except ValueError as exc:
        raise ResumeRefused(f"{where} cannot be restored: {exc}") from exc
    executive.resumed = True
    # **The clock, resolved after the replay** (#23, design §3). The newest recovered policy is the last
    # replayed segment's header when the replay crossed into segments the checkpoint does not list — a boot
    # after it, whose named change a fall-back to this older generation must not silently undo — and the
    # checkpoint's own `clock` otherwise (the checkpoint a boot takes before it serves records the change
    # it named before that boot's header exists). A named value wins; the three are validated together.
    listed = {entry.get("segment") for entry in body["segments"] if isinstance(entry, dict)}
    newer = [entry for entry in recovered["segments"] if isinstance(entry, dict) and entry.get("segment") not in listed]
    policy = newer[-1] if newer else body["clock"]
    inherited = {"m": policy["m"], "k": policy["k"], "N": policy["N"]}
    resolved = {key: value if value is not None else inherited[key] for key, value in zip(("m", "k", "N"), named, strict=True)}
    try:
        executive.set_clock(resolved["m"], resolved["k"], resolved["N"])
    except ValueError as exc:
        spelled = ", ".join(f"{key} = {resolved[key]}" for key in ("m", "k", "N"))
        which = ", ".join(flag for flag, value in zip(("--multiplier", "--cycle-ticks", "--checkpoint-ticks"), named, strict=True) if value is not None)
        raise ResumeRefused(
            f"{where} cannot be resumed on the clock {spelled} ({'named: ' + which if which else 'all inherited'}): {exc}"
        ) from exc
    clock_changes = {key: [inherited[key], resolved[key]] for key in ("m", "k", "N") if resolved[key] != inherited[key]}

    # Addendum B2: a fall-back never lets the next write rotate the unverified current generation over
    # the good previous one. The current is moved aside — to a name no generation has — before anything
    # writes a checkpoint, so `write_checkpoint`'s rename of current to previous finds nothing to rotate.
    rejected = None
    if getattr(loaded, "fell_back", None) is not None and executive.state_fd is not None:
        with contextlib.suppress(FileNotFoundError):
            os.lstat(CURRENT, dir_fd=executive.state_fd)
            rejected = f"checkpoint.rejected.{executive.boot_id}.json"
            try:
                os.rename(CURRENT, rejected, src_dir_fd=executive.state_fd, dst_dir_fd=executive.state_fd)
                os.fsync(executive.state_fd)
            except OSError as exc:
                raise ResumeRefused(
                    f"{where} was chosen because {CURRENT} was refused ({loaded.fell_back}), and {CURRENT} cannot be moved aside to "
                    f"{rejected} ({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}): the next checkpoint would rotate it over the good one"
                ) from exc
    # What the windows are owed (addendum B4): the checkpoint's obligations, and every verdict after its
    # tick the record holds with no note — a crash between the record and the results, or a publication
    # that failed after the checkpoint. Rows at or before the snapshot were published, or are owed in
    # the checkpoint, because a checkpoint is taken only once every window of its cycle has published.
    for entry in unwritten:
        if entry["tick"] >= snapshot_tick:
            executive.owe(entry)

    run_inputs: dict[str, Any] = dict(clock_changes)
    if max_batch is not None and int(max_batch) != executive.max_batch:
        run_inputs["max_batch"] = [executive.max_batch, int(max_batch)]
        executive.max_batch = int(max_batch)
    added = sorted(set(closed_interlocks or ()) - executive.tripped)
    if added:
        run_inputs["tripped_interlocks"] = [sorted(executive.tripped), sorted(executive.tripped | set(added))]
        executive.tripped |= set(added)

    # Read as `main` reads it at every start: a scenario that is not one of the vehicle's postures is garbled.
    try:
        postures: set[str] | None = set(load_postures(Path(world.root)))
    except Exception:  # noqa: BLE001 - a record is then read without that one check
        postures = None
    record_now, problem, record_bytes = read_root_record_bytes(RECORD_FILE, dir_fd=executive.diode_fd, postures=postures)
    expected = root_record_from_checkpoint(recovered)
    action, why = classify_root_record(record_now, problem, expected, snapshot_tick)
    if action == "refuse":
        raise ResumeRefused(
            f"the root record at {executive.diode_dir / RECORD_FILE} and {where} disagree about which world this is: {why}. "
            "Neither is rewritten; stop the other executive or point --state-dir at the directory that serves this one"
        )

    advisories: list[dict[str, Any]] = []
    for slug in sorted(executive.windows):
        # ADR 0002 H: beside a verified checkpoint the legacy `pending.json` checks are advisory. The
        # window's copy is read for nothing but a note to the operator.
        with contextlib.suppress(OSError):
            window_fd = open_directory(slug, dir_fd=executive.diode_fd)
            try:
                legacy = read_json_bounded("pending.json", dir_fd=window_fd) or {}
            finally:
                os.close(window_fd)
            named, ticks = legacy.get("world_id"), legacy.get("ticks")
            if isinstance(named, str) and named and named != executive.world_id:
                advisories.append({"window": slug, "pending_world_id": bounded_repr(named)})
            elif isinstance(ticks, int) and not isinstance(ticks, bool) and ticks > tick:
                advisories.append({"window": slug, "pending_ticks": ticks})

    wall_down, source = _newest_journal_mtime(executive)
    segments = recovered["segments"]
    resumed_event = {
        "event": "resumed",
        "wall": utc_now().isoformat(),
        "boot_id": executive.boot_id,
        "world_id": executive.world_id,
        "tick": tick,
        "wall_down": wall_down,
        "wall_down_source": source,
        "wall_up": utc_now().isoformat(),
        "previous_boot": segments[-1]["segment"] if segments else None,
        "checkpoint": {
            "file": Path(loaded.path).name,
            "tick": snapshot_tick,
            "fell_back": str(loaded.fell_back) if getattr(loaded, "fell_back", None) is not None else None,
            "rejected": rejected,
        },
        "replayed": tick - snapshot_tick,
        "root_record": f"{action}: {why}",
        "run_inputs": run_inputs,
        "advisories": advisories,
    }
    events = [resumed_event]
    if action == "rewrite":
        events.append({
            "event": "root_record_rewritten",
            "wall": utc_now().isoformat(),
            "boot_id": executive.boot_id,
            "world_id": expected["world_id"],
            "tick": expected["tick"],
            "checkpoint": Path(loaded.path).name,
            "reason": why,
            "problem": problem,
            **superseded_record(record_now, record_bytes),
        })
    try:
        for event in events:
            append_journal_line(executive.journal, event, dir_fd=executive.journal_dir_fd)
    except Exception as exc:  # noqa: BLE001 - the refusal names it
        raise ResumeRefused(
            f"the journal at {executive.journal} cannot take the resume's events ({type(exc).__name__}: {exc}), so nothing was rewritten"
        ) from exc
    # The operator's view is stderr (`docker compose logs vehicle`), not the private journal (review F14):
    # one line for a fall-back, one for a mismatched root record, one per advisory.
    if resumed_event["checkpoint"]["fell_back"] is not None:
        sys.stderr.write(
            f"[console] resume: fell back to {Path(loaded.path).name} at tick {snapshot_tick}: {CURRENT} was refused "
            f"({resumed_event['checkpoint']['fell_back']}), and the refused file is kept as {rejected}\n"
        )
    for advisory in advisories:
        said = (
            f"names world {advisory['pending_world_id']}" if "pending_world_id" in advisory
            else f"says tick {advisory['pending_ticks']}, past the recovered tick {tick}"
        )
        sys.stderr.write(
            f"[console] resume: window {advisory['window']!r}: its pending.json {said}; advisory only (ADR 0002 H), and its next "
            "publication rewrites it\n"
        )
    if action != "agree":
        try:
            write_json_atomic(RECORD_FILE, executive.root_record(), dir_fd=executive.diode_fd)
        except Exception as exc:  # noqa: BLE001 - the refusal names it
            raise ResumeRefused(
                f"the root record at {executive.diode_dir / RECORD_FILE} cannot be rewritten from the recovered world "
                f"({type(exc).__name__}: {exc}); {why}. The events were journaled first: remove what is at that path and start again"
            ) from exc
        if action == "rewrite":
            # Said once it is so (confirmation G6): a failed rewrite says only that it failed, above.
            sys.stderr.write(f"[console] resume: the root record at {executive.diode_dir / RECORD_FILE} was rewritten: {why}; the mismatch is journaled\n")

    # **The boot marker, before any window is read (#39, option B).** The boot that ended is read from it
    # and this boot is written over it, durably, so a take speaks for a window's map only to the resume
    # right after the boot that made it; the record cannot say this, because a boot's segment header is
    # written with its first cycle. Once written it is never rolled back, whatever later refuses.
    prev_boot, earlier = read_boot_lineage(executive.state_fd)
    # Newest first: the ended boot, then any boots its own resume had not finished recovering (issue #39).
    recover_boots = list(dict.fromkeys(b for b in [prev_boot, *earlier] if b))
    # **The consecutive-backstop count** (#23, design §5), read back from the segment the ended boot closed
    # with: its manifest, if it ended by the backstop; any other end — a clean one, a crash — resets it.
    if prev_boot is not None and executive.journal is not None and executive.journal_dir_fd is not None:
        segment_file = executive.journal.name if executive.journal_shared else JOURNAL_SEGMENT.format(boot_id=prev_boot)
        manifest = previous_manifest(executive.journal_dir_fd, segment_file, prev_boot)
        if manifest is not None and manifest.get("ended") == "lag_backstop" and _count(manifest.get("consecutive_backstops"), 1):
            executive.backstops_before = manifest["consecutive_backstops"]
    # **Superseded takes first** (issue #39): a window whose console carries its own map has no use for an
    # earlier boot's take, and once the marker names those boots as still pending a take left here could
    # outlive that map (the agent then writing a console without one) and be adopted, stale. So they are
    # retired, durably, while the marker still names only the ended boot, as the old order did; one that
    # cannot be is a refusal, before the marker moves. The same listing says which boots still have a take
    # anywhere: only those stay pending, so the marker is bounded by the takes, never truncated.
    remaining: set[str] | None = set()
    for window in executive.windows.values():
        try:
            left = window.retire_superseded_takes(window.open_handles().root, recover_boots)
        except WindowAbsent:
            left = set()  # no directory, no takes
        except TakeUnretirable as exc:
            raise ResumeRefused(f"{exc}; the boot marker is not advanced past a take that could resurrect an older map") from exc
        except Exception:  # noqa: BLE001 - the window's recovery below meets it again and records it
            left = None
        finally:
            window.close_handles()
        remaining = None if remaining is None or left is None else remaining | left
    if remaining is not None:
        recover_boots = [boot for boot in recover_boots if boot in remaining]
    try:
        write_boot_marker(executive.state_fd, executive.boot_id, recover_boots)
        executive.marker_pending = recover_boots
    except Exception as exc:  # noqa: BLE001 - the refusal names it
        raise ResumeRefused(
            f"the boot marker {executive.state_dir / BOOT_FILE if executive.state_dir else BOOT_FILE} cannot be written "
            f"into the state directory ({type(exc).__name__}: {exc}); a resume "
            "that cannot say which boot it is cannot tell a window's last take from an older one"
        ) from exc
    republished: list[dict[str, Any]] = []
    for window in executive.windows.values():
        window.variables_known = False
        # Owed until `recover_map` has read the window's takes: a failure before that leaves it for the claim.
        window.recover_owed, window.recover_from = True, recover_boots
        try:
            try:
                handles = window.open_handles()
            except WindowAbsent:
                window.repair(console=False)
                handles = window.open_handles()
            # The console's map, else the ended boot's take's, else unknown (ADR 0002 (xxxv)).
            window.recover_map(handles.root, recover_boots)
            republished.extend(executive.publish_obligations(window))
        except Exception as exc:  # noqa: BLE001 - the window's, recorded; the world resumes
            executive._record_failure(window, "resume", exc, tick)
        finally:
            window.close_handles()
    if republished:
        # The operator's account of what was owed and what became of it; the dedupe does not rely on it.
        event = {"event": "results_republished", "wall": utc_now().isoformat(), "boot_id": executive.boot_id, "world_id": executive.world_id, "results": republished}
        try:
            append_journal_line(executive.journal, event, dir_fd=executive.journal_dir_fd)
            events.append(event)
        except RecordUnwritable as exc:
            # The record could not be restored after a failed append (J2): nothing may follow it this boot.
            raise ResumeRefused(f"the journal at {executive.journal} cannot take the resume's events ({exc})") from exc
        except Exception:  # noqa: BLE001 - advisory, and the append left the record as it was
            pass
    return Resumption(
        snapshot_tick=snapshot_tick,
        tick=tick,
        fell_back=resumed_event["checkpoint"]["fell_back"],
        root_record=f"{action}: {why}",
        run_inputs=run_inputs,
        advisories=advisories,
        events=events,
        republished=republished,
    )


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, not {value}")
    return value


class _StartPath(contextlib.ExitStack):
    """`main`'s start path: the descriptors it holds, each with its path, closed once; and its one `OSError` boundary (H2)."""

    def __init__(self) -> None:
        super().__init__()
        self.paths: dict[int, Path] = {}
        self.where: Path | None = None
        self.unclosed: OSError | None = None

    def hold(self, fd: int, path: str | os.PathLike[str]) -> int:
        """Register a descriptor the moment it is opened, with the path it was opened for; it is closed on the way out."""
        self.closing(functools.partial(os.close, fd), path)
        self.paths[fd] = self.where = Path(path)
        return fd

    def closing(self, close: Callable[[], object], path: str | os.PathLike[str]) -> None:
        """Run `close` on the way out (round 4, J4): every one runs, and none raises past `main`.

        A `close` that fails while something else is already on its way out — a refusal's exception, a
        kill — is not what is reported, and is dropped; the first that fails when nothing else has is kept
        as `unclosed`, naming `path` when the error names nothing, for `main` to report as exit 3.
        """
        named = Path(path)

        def leave(exc_type: object, _exc: object, _tb: object) -> bool:
            try:
                close()
            except OSError as error:
                if exc_type is None and self.unclosed is None:
                    if error.filename is None:
                        error.filename = str(named)
                    self.unclosed = error
            return False

        self.push(leave)

    def at(self, path: str | os.PathLike[str] | None) -> None:
        """Say what the start is working on, for a refusal from a call that names no file (`fsync`, `fstat`)."""
        self.where = Path(path) if path is not None else None

    def refusal(self, exc: OSError) -> str:
        code = errno.errorcode.get(exc.errno or 0, type(exc).__name__)
        named = os.fsdecode(exc.filename) if isinstance(exc.filename, (str, bytes, os.PathLike)) else None
        if named is None:
            where = str(self.where) if self.where is not None else "a file the start was using"
        elif not os.path.isabs(named) and self.where is not None:
            where = f"{named} in {self.where}"
        else:
            where = named
        return f"the start could not read or write {where} ({code}: {exc.strerror}); every handle it held is closed, and nothing was started"

    def unclosed_refusal(self) -> str:
        assert self.unclosed is not None
        code = errno.errorcode.get(self.unclosed.errno or 0, type(self.unclosed).__name__)
        named = os.fsdecode(self.unclosed.filename) if isinstance(self.unclosed.filename, (str, bytes, os.PathLike)) else "a handle"
        return f"[console] {named} could not be closed ({code}: {self.unclosed.strerror}); every other handle was closed"


def main(argv: list[str] | None = None, *, pacer: Pacer | None = None) -> int:
    """The console's command line; `pacer` injects the scheduler's clock and sleeper (#23: the tests' seam, never a flag)."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--diode-dir", default=".scratch/diode")
    parser.add_argument(
        "--slug",
        action="append",
        default=None,
        help="a window to serve from this executive; repeatable, default `vehicle`",
    )
    parser.add_argument(
        "--phase",
        default=None,
        help=f"the phase a new world starts in (default {DEFAULT_PHASE}); a restart resumes the phase its checkpoint "
        "records, and naming another refuses",
    )
    # **The clock** (ADR 0002 A, B, J; #23): three run inputs, required with no default on a serving start
    # that has no checkpoint — the deployed stack names them — and remembered by the checkpoint, so each
    # defaults to `None` (`check_console_flags`: a named value and "named nothing" must be two things).
    parser.add_argument(
        "--multiplier",
        default=None,
        metavar="M",
        help="m, mission seconds per wall second (ADR 0002 A), an exact decimal or fraction such as 1, 0.5 or 1/3; "
        "required with no default on a fresh serving start, and a restart keeps its checkpoint's unless this names another",
    )
    parser.add_argument(
        "--cycle-ticks",
        type=int,
        default=None,
        metavar="K",
        help="k, the ticks of one cycle: one claim and one publication per cycle (ADR 0002 B), at most tick_hz over the "
        "highest channel rate; required with no default on a fresh serving start, and a restart keeps its checkpoint's "
        "unless this names another",
    )
    parser.add_argument(
        "--checkpoint-ticks",
        type=int,
        default=None,
        metavar="N",
        help="N, the ticks between checkpoints (ADR 0002 J), a multiple of k; the generated HELP.md and README.md are "
        "rewritten on the same cadence. Required with no default on a fresh serving start, and a restart keeps its "
        "checkpoint's unless this names another",
    )
    parser.add_argument("--cycles", type=int, default=0, help="the cycles this invocation runs; 0 runs until stopped")
    parser.add_argument(
        "--closed-interlock",
        action="append",
        default=None,
        metavar="THRESHOLD",
        help="an interlock that is currently tripped, by threshold id; repeatable. A restart keeps every "
        "interlock its checkpoint records as tripped and adds these",
    )
    parser.add_argument("--init", action="store_true", help="prepare the windows, bind nothing, stop")
    parser.add_argument(
        "--ring-slots",
        type=int,
        default=None,
        metavar="N",
        help="how many frames each telemetry ring holds. `docs/diode-contract.md:186` requires a "
        "fixed slot count and `presentation.yaml#ring` declines to set it — 'a slot count is a "
        "memory decision' — so the run declares it",
    )
    parser.add_argument(
        "--max-batch",
        type=positive_int,
        default=None,
        metavar="N",
        help=f"the most commands one window may submit in one cycle (default {DEFAULT_MAX_BATCH}); a longer batch "
        "is refused whole with one result (ADR 0001 choice B). A restart keeps its checkpoint's unless this names another",
    )
    parser.add_argument(
        "--journal",
        default=None,
        metavar="PATH",
        help="the durable per-cycle record (ADR 0002 J): a segment header per boot, then one fsync'd "
        "JSON line per tick — lineage, state hash, effects, receipts, window deltas, published-tick "
        "marks — for the operator and for replay; refused inside --diode-dir. With --state-dir and no "
        "--journal, the record is one segment file per boot in the state directory",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        metavar="PATH",
        help="the executive's private directory (ADR 0002 H): checkpoint generations, the exclusive "
        "lock and the journal segments. Refused inside --diode-dir. Optional until the chassis mounts "
        "one; without it the lock and the journal are where ADR 0001 put them",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="print what this scenario and seed decide — the scheduled faults, the placed ones and "
        "the factors — and stop, without running a cycle",
    )
    parser.add_argument(
        "--plan-json",
        action="store_true",
        help="the same plan as JSON, for a caller that wants to store or diff it",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        metavar="POSTURE",
        help="the run's difficulty identity: a `mission.yaml#scenario_postures` id "
        "(nominal, degraded, crisis). Recorded in the directory's own record (never in a window), and "
        "a prepared directory keeps the one it recorded unless this names another",
    )
    parser.add_argument(
        "--scenario-file",
        default=None,
        metavar="PATH",
        help="an episode's overlay on the declared vehicle (`scenarios/<name>.yaml`; not --scenario's posture): its "
        "`initial` values seed a new world's MET 0 and its `verbs` are the only verbs the world accepts. Its name and "
        "SHA-256 are the world's identity, so a restart names the same file, and naming another or none refuses",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="the run's master seed, for the fault streams `tools/faults.py` draws from. "
        "A scenario and a seed together are what make a run reproducible, and a prepared directory "
        "keeps the pair it recorded unless this names another",
    )
    args = parser.parse_args(argv)
    # `--slug` named nothing is `None`: a fresh world serves `vehicle`, a resumed one the slugs it was bound with.
    slugs = list(args.slug or ["vehicle"])
    for slug in slugs:
        if not SLUG_PATTERN.match(slug):
            sys.stderr.write(
                f"--slug {slug!r} is not one safe path component ({SLUG_PATTERN.pattern}); a slug is "
                "joined to --diode-dir and may not name another directory\n"
            )
            return 3
    repeated = sorted({s for s in slugs if slugs.count(s) > 1})
    if repeated:
        sys.stderr.write(
            f"--slug names {repeated} more than once; a slug attaches to one executive once\n"
        )
        return 3

    # A named clock input is refused by name when it is not one, before anything is opened; whether the three
    # together are a clock, and whether one is missing, is asked once the start knows if it resumes (`start`).
    named_m: Fraction | None = None
    if args.multiplier is not None:
        try:
            named_m = parse_multiplier(args.multiplier)
        except ValueError as exc:
            sys.stderr.write(f"--multiplier {args.multiplier}: {exc}; m is mission seconds per wall second, a positive number (ADR 0002 A)\n")
            return 3
    for flag, value in (("--cycle-ticks", args.cycle_ticks), ("--checkpoint-ticks", args.checkpoint_ticks)):
        if value is not None and value < 1:
            sys.stderr.write(f"{flag} {value} is not a positive number of ticks\n")
            return 3

    pacer = pacer if pacer is not None else Pacer()

    try:
        world = load_world(Path(args.dir))
    except Exception as exc:  # noqa: BLE001 - the loader's refusals are the point
        sys.stderr.write(f"the configuration cannot be loaded: {exc}\n")
        return 3

    # **A scenario that names no posture is refused rather than accepted and ignored.** The list
    # comes from the mission file through the module that already consumes it, so there is one
    # declaration of what the scenarios are.
    try:
        postures = load_postures(Path(args.dir))
    except Exception as exc:  # noqa: BLE001 - a refusal is the answer here too
        sys.stderr.write(f"the scenario postures cannot be loaded: {exc}\n")
        return 3

    # **The episode's overlay** (`--scenario-file`), read and hashed once, before anything is opened: a
    # file that is not a scenario this vehicle runs is refused by name with nothing written.
    scenario_file: ScenarioFile | None = None
    if args.scenario_file is not None:
        try:
            scenario_file = load_scenario_file(world, Path(args.scenario_file))
        except ValueError as exc:
            sys.stderr.write(f"{exc}\n")
            return 3

    def start(starting: _StartPath) -> int | Callable[[], int]:
        """The start path: everything up to the first cycle, inside `main`'s one `OSError` boundary (round 3, H2).

        Returns an exit code, or the run itself — which `main` calls outside the boundary, because once the
        first cycle claims, an `OSError` is the cycle's to handle (per window, or `RecordUnwritable`).
        """
        # ---- one world per directory, and everything the start reads is read under the lock -------
        #
        # The lock says *an* executive is here; the directory's record says *which* world, and what
        # identity it has. Without `--state-dir` both live in the diode root and the lock is the root's
        # (ADR 0001). With `--state-dir` the lock is the state directory's (ADR 0002 H(i)): the root is
        # agent-writable until the chassis adopts its per-slug mounts (`adf38d6`, chassis branch
        # `aurora-port`), and a lock an agent can hold is a stop button, so the root lock is not
        # opened at all and the record alone holds one world per diode directory. Either way the record
        # is read only while this executive's lock is held. An executive on a directory whose record names
        # a world refuses, live or not — starting a fresh world on it would silently reset its physics —
        # until child 3 resumes it (ADR 0001 choice D). A record that cannot be read is a refusal and
        # never "a fresh directory", except beside a verified checkpoint, where it is the checkpoint's
        # copy and is rewritten (ADR 0002 H(ii), below).
        diode_dir = Path(args.diode_dir)
        state_dir = Path(args.state_dir) if args.state_dir else None
        state_fd: int | None = None
        # **Every destination is checked before the first write** (review F3): the diode directory, the
        # lock, `serves.json` and a startup event are all written below, and the `--journal` rule used to
        # be asked only by `Executive`, which a start on a checkpoint never builds. **Each private path
        # is canonicalised once, by hand, and opened once, by a walk that follows nothing** (third
        # review): every hop is held to the diode directory, the open is held to what the hop check saw,
        # and the handle is all that is used after it. A loop is a refusal by name (second review, P2).
        diode_canonical, problem = canonicalise("--diode-dir", diode_dir, "the diode directory")
        if problem is not None or diode_canonical is None:
            sys.stderr.write(f"{problem}\n")
            return 3
        # An explicit journal: its file canonicalised under the hop rule, its directory opened and held.
        journal_explicit: Path | None = None
        journal_fd: int | None = None
        if args.journal:
            starting.at(Path(args.journal))
            journal_fd, journal_explicit, problem = open_journal_dir(args.journal, diode_canonical)
            if problem is not None:
                sys.stderr.write(problem + "\n")
                return 3
            if journal_fd is not None and journal_explicit is not None:
                starting.hold(journal_fd, journal_explicit.parent)
        # The state directory as spelled is the operator's word, kept for the messages; once it is
        # checked and opened, every access goes through `state_fd`, or its canonical path `state_path`
        # where only a path is taken — never the spelling.
        state_path: Path | None = None
        if state_dir is not None:
            starting.at(state_dir)
            state_fd, state_path, problem = open_private_dir(state_dir, diode_canonical)
            if problem is not None:
                sys.stderr.write(problem + "\n")
                return 3
            if state_fd is not None and state_path is not None:
                starting.hold(state_fd, state_path)
            # The boot marker's name is reserved (#39, option B): a journal written there would be
            # replaced by the next boot's marker. Refused before anything is written.
            if journal_explicit is not None and state_path is not None and journal_explicit == state_path / BOOT_FILE:
                sys.stderr.write(
                    f"--journal {args.journal} names the state directory's boot marker {state_path / BOOT_FILE}, which the "
                    "executive rewrites at every start; name another file\n"
                )
                return 3

        def errno_name(exc: BaseException) -> str:
            if isinstance(exc, OSError):
                return f"{errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror}"
            return f"{type(exc).__name__}: {exc}"

        # **The operator's own writes fail by name too** (second review, Opus 1): a diode directory that
        # cannot be made or opened, and a lock that cannot be opened — a read-only mount, a directory where
        # the lock goes — were tracebacks.
        # Opened from its one resolution by a walk that follows nothing and holds each component to what the
        # resolution saw (confirmation G1): the directory served is the one the confinement checks were
        # made against, and nothing resolves the spelling again.
        starting.at(diode_canonical.path)
        try:
            opened_diode, why = walk_open_dir(diode_canonical, "--diode-dir", create=True)
        except OSError as exc:
            opened_diode, why = None, errno_name(exc)
        if opened_diode is None:
            sys.stderr.write(f"--diode-dir {diode_dir} cannot be made or opened ({why})\n")
            return 3
        diode_fd = starting.hold(opened_diode, diode_canonical.path)
        lock_in = state_fd if state_fd is not None else diode_fd
        lock_where = state_path if state_path is not None else diode_canonical.path
        starting.at(lock_where / LOCK_FILE)
        try:
            lock_fd = starting.hold(
                os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=lock_in), lock_where / LOCK_FILE
            )
        except OSError as exc:
            sys.stderr.write(
                f"the lock {lock_where / LOCK_FILE} cannot be opened ({errno_name(exc)}). The executive "
                "does not run without its lock; repair what is at that path, or the directory's permissions\n"
            )
            return 3

        def close_all() -> None:
            """Nothing to do by hand: every descriptor the start holds is in `starting`, closed once on the way out (H2)."""

        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            try:
                holder = os.read(lock_fd, 256).decode("utf-8", "replace").strip() or "unknown holder"
            except OSError:
                holder = "unknown holder"
            close_all()
            if state_dir is not None:
                sys.stderr.write(
                    f"another executive holds the state directory {state_dir} ({holder}). One state "
                    "directory is one executive (ADR 0002 H); stop it, or point --state-dir at another directory\n"
                )
            else:
                sys.stderr.write(
                    f"another executive holds {diode_dir} ({holder}). One directory is one world "
                    "(ADR 0001); stop it, or point --diode-dir at another directory\n"
                )
            return 3

        def refuse(message: str) -> int:
            sys.stderr.write(message + "\n")
            close_all()
            return 3

        def serves_refusal() -> str | None:
            """Write `serves.json`; the refusal sentence if it cannot be written (second review, Opus 1)."""
            if state_fd is None or state_path is None:
                return "no state directory is open, so serves.json cannot be written"
            try:
                write_serves_record(state_fd, diode_canonical.path, journal_explicit)
            except Exception as exc:  # noqa: BLE001 - the refusal names it
                return (
                    f"the state directory's record {state_path / SERVES_FILE} cannot be written ({errno_name(exc)}). "
                    "A state directory that cannot say which diode directory it serves is not one to run"
                )
            return None

        # This boot's id is drawn here so that a startup event and the ticks that follow share one
        # journal segment; the executive is handed it below.
        boot_id = uuid.uuid4().hex
        journal = journal_explicit
        if journal is None and state_path is not None:
            journal = journal_segment_path(state_path, boot_id)

        starting.at(diode_canonical.path / RECORD_FILE)
        record, problem, _record_bytes = read_root_record_bytes(RECORD_FILE, dir_fd=diode_fd, postures=set(postures))
        checkpoint_found = None
        if state_fd is not None:
            starting.at(state_path)
            # One state directory serves one diode directory, and says which (ADR 0002 H).
            served, serves_problem = read_serves_record(state_fd)
            if serves_problem is not None:
                return refuse(
                    f"the state directory's record at {state_dir / SERVES_FILE} cannot be read: {serves_problem}. "
                    "Repair or clear it; a state directory that cannot say which diode directory it serves is not one to run"
                )
            if served is not None and served != str(diode_canonical.path):
                return refuse(
                    f"the state directory {state_dir} serves the diode directory {served}, not {diode_canonical.path}. "
                    "One state directory serves one diode directory (ADR 0002 H); point --state-dir at the directory "
                    "that serves this one, or at a fresh one"
                )
            # The checkpoint is authoritative for identity (ADR 0002 H(ii)); K2 chooses the generation and
            # its refusals — corrupt both, incompatible — are the operator's to read (K).
            try:
                checkpoint_found = choose_generation(state_path, Compatibility.current(world), dir_fd=state_fd)
            except CheckpointRefused as exc:
                return refuse(
                    f"{exc}. The state directory {state_dir} holds a checkpoint this engine will not resume from "
                    "and the executive does not start a fresh world over one (ADR 0002 K)"
                )

        def run(executive: Executive, banner: str) -> int:
            """The loop, for a fresh world and a resumed one alike: the lock's holder line, the banner, the cycles, a clean end.

            **The clean end** — `--cycles` exhausted, or a stop asked for by `SIGTERM` or `SIGINT`, which the
            loop reads at a cycle's boundary (#23, design §5) — checkpoints the last completed cycle and
            journals the segment's manifest (ADR 0002 C1: the clean-end event is the manifest), with its
            clock summary, which it also prints. **A lag backstop** (`LagBackstop`, raised before the cycle
            opened anything) journals `lag_backstop`, takes the same clean end with the manifest saying so,
            prints `BACKSTOP_LINE` and exits `EXIT_BACKSTOP`; the restart resumes on a fresh epoch.
            """
            # The holder's line in the lock, for the next start's refusal to name; a failure is named too.
            try:
                os.ftruncate(lock_fd, 0)
                os.write(lock_fd, f"pid={os.getpid()} world={executive.world_id}\n".encode())
            except OSError as exc:
                with contextlib.suppress(OSError):  # the refusal is what is reported (fifth round)
                    executive.close()
                return refuse(f"the lock {lock_where / LOCK_FILE} cannot be written ({errno_name(exc)})")
            print(banner, flush=True)
            # `--cycles` counts the cycles **this invocation** runs; a resumed world continues its tick.
            ran = 0
            clean = False
            ended = "clean"
            backstop: LagBackstop | None = None
            try:
                try:
                    while (args.cycles == 0 or ran < args.cycles) and not pacer.stopping:
                        before = executive.stats.cycles
                        written = executive.cycle()
                        if executive.stats.cycles == before:
                            break  # a stop came during the wait: the cycle never started
                        ran += 1
                        if written:
                            print(f"[console] tick {executive.tick}: {len(written)} result(s)", flush=True)
                    clean = True
                    if pacer.stopping:
                        asked = f" ({signal.Signals(pacer.signal).name})" if pacer.signal is not None else ""
                        print(f"\n[console] stopped after {executive.tick} tick(s){asked}", flush=True)
                except LagBackstop as exc:
                    backstop, ended, clean = exc, "lag_backstop", True
                    try:
                        executive.journal_event({
                            "event": "lag_backstop", "wall": utc_now().isoformat(), "boot_id": executive.boot_id,
                            "world_id": executive.world_id, "tick": executive.tick, "lag_s": exc.lag_s, "consecutive": exc.consecutive,
                            "action": "stop",
                        })
                    except RecordUnwritable as again:
                        # The event's failed append could not be cut back (J2): the record is unwritable, and the
                        # clean end cannot follow it — the named refusal, never a traceback (candidate 1, Codex P2).
                        sys.stderr.write(f"[console] stopped at tick {executive.tick}: {again}\n")
                        return 3
                except KeyboardInterrupt:
                    # Where no handler could be installed (`main` off the main thread), an interrupt still raises.
                    print(f"\n[console] stopped after {executive.tick} tick(s)", flush=True)
                    # A checkpoint only at a cycle's boundary: mid-cycle the window counters can be ahead of the truth.
                    clean = not executive.in_cycle
                except UncomparableState as exc:
                    # Only the cycle's durable rows were committed (#23, design §1): the refusal names the last of them.
                    durable = getattr(exc, "last_durable_tick", executive.tick)
                    unwritable = getattr(exc, "unwritable", None)
                    sys.stderr.write(
                        f"[console] stopped at tick {durable}: the next tick's state cannot be compared "
                        f"({exc}). The executive did not commit it; the lineage ends at tick {durable}, the last durable tick"
                        + (f" (the rows before the refusal could not be appended: {unwritable})" if unwritable else "")
                        + "\n"
                    )
                    return 3
                except RecordUnwritable as exc:
                    sys.stderr.write(f"[console] stopped at tick {executive.tick}: {exc}\n")
                    return 3
                # A clean end checkpoints the last completed cycle, unless the cadence just did; a failure is
                # recorded and journaled as a cadence failure is, and not a changed exit, because the record
                # already holds every tick. The manifest is the segment's last event.
                if clean:
                    try:
                        # A boot that ran no cycle (a backstop in its first wait, a stop before its first cycle)
                        # has no segment yet: its header comes first, so its manifest belongs to a segment of the
                        # record and the clean-end checkpoint lists it (candidate 2, Codex P3).
                        executive.open_segment()
                        if executive.state_fd is not None and executive.last_checkpoint_tick != executive.tick:
                            executive.checkpoint_or_record("clean end")
                        manifest = executive.write_manifest(ended)
                    except RecordUnwritable as exc:
                        # Its event's failed append could not be cut back (J2): the record is unwritable.
                        sys.stderr.write(f"[console] stopped at tick {executive.tick}: {exc}\n")
                        return 3
                    except OSError as exc:
                        # The append was cut back, but the segment has no manifest: it did not end cleanly.
                        sys.stderr.write(
                            f"[console] stopped at tick {executive.tick}: the clean end cannot be journaled "
                            f"({errno_name(exc)}); the next resume reads this segment as one that crashed\n"
                        )
                        return 3
                    print(f"[console] {clock_line(manifest['summary'])}", flush=True)
                if backstop is not None:
                    sys.stderr.write(BACKSTOP_LINE.format(lag_s=backstop.lag_s, consecutive=backstop.consecutive) + "\n")
                    return EXIT_BACKSTOP
                return 0
            finally:
                # The executive is closed on the way out of `starting`, with every handle the start holds,
                # where a failing `close` is named rather than raised past `main` (J4).
                close_all()

        if checkpoint_found is not None:
            body = checkpoint_found.body
            # **A restart names the world it resumes, or names nothing** (commitment 2): a named scenario, seed,
            # phase, ring bound or slug set the checkpoint does not record is refused by one sentence.
            named_other = identity_refusal(args, body, checkpoint_found.path) or scenario_refusal(
                scenario_file, body, checkpoint_found.path
            )
            if named_other is not None:
                return refuse(named_other)
            if args.init:
                return refuse(
                    f"--init prepares an unbound directory, and the state directory {state_dir} holds world "
                    f"{body['identity']['world_id']} at tick {body['identity']['tick']}, which a start without --init resumes "
                    "(ADR 0001: a bound directory refuses every --init)"
                )
            expected = root_record_from_checkpoint(body)
            if not (args.plan or args.plan_json):
                action, why = reconcile_root_record(record, problem, expected)
                if action == "refuse":
                    return refuse(
                        f"the root record at {diode_dir / RECORD_FILE} and the checkpoint at {checkpoint_found.path} "
                        f"disagree about which world this is: {why}. Neither is rewritten; stop the other executive "
                        "or point --state-dir at the directory that serves this one"
                    )
                starting.at(state_path)
                # Review F11: the record is read where it was written, and a restart naming another journal is
                # told where that is, before anything is written.
                recorded, previous = served_journal(state_fd)
                current = str(journal_explicit) if journal_explicit is not None else None
                if recorded and previous != current:
                    own = "the state directory's own segments"
                    return refuse(
                        f"--journal names {current or 'none, which means ' + own} and this state directory's record was written to "
                        f"{previous or own} (its serves.json): a restart reads the record where it was written, so name the same "
                        "--journal, or none"
                    )
                unserved = serves_refusal()
                if unserved is not None:
                    return refuse(unserved)
                # **Resume** (ADR 0002 F1, G, J, L; child 3): the checkpoint and the record after it.
                try:
                    executive, resumption = resume_executive(
                        world,
                        diode_dir,
                        checkpoint_found,
                        boot_id=boot_id,
                        state_dir=state_path,
                        state_fd=state_fd,
                        journal=journal_explicit,
                        journal_dir_fd=journal_fd,
                        max_batch=args.max_batch,
                        closed_interlocks=set(args.closed_interlock or []),
                        diode_fd=diode_fd,
                        multiplier=named_m,
                        cycle_ticks=args.cycle_ticks,
                        checkpoint_every=args.checkpoint_ticks,
                        pacer=pacer,
                    )
                except ResumeRefused as exc:
                    return refuse(f"{exc}. The executive does not start a fresh world over a saved one (ADR 0002 K)")
                starting.closing(executive.close, state_path or diode_canonical.path)
                # The named file was held to the checkpoint's identity above; its allow-list holds again.
                executive.scenario_overlay = scenario_file.scenario if scenario_file is not None else None
                # Addendum B3: a checkpoint at the recovered tick before anything is claimed — it makes the
                # named run inputs durable and bounds the next resume's replay and re-publication.
                try:
                    executive.checkpoint()
                except Exception as exc:  # noqa: BLE001 - the refusal names it
                    with contextlib.suppress(OSError):  # the refusal is what is reported (fifth round)
                        executive.close()
                    return refuse(
                        f"the checkpoint at the recovered tick {resumption.tick} cannot be written into {state_path} ({exc}); nothing has been "
                        "claimed this boot, and the world resumes from the record at the next start"
                    )
                rings = sorted({w.ring_slots for w in executive.windows.values()})
                return functools.partial(
                    run,
                    executive,
                    f"[console] {diode_dir} resumed world {executive.world_id} at tick {executive.tick} "
                    f"(checkpoint {checkpoint_found.path.name} at tick {resumption.snapshot_tick}"
                    + (", fell back" if resumption.fell_back else "")
                    + f", replayed {resumption.replayed}, republished {sum(1 for r in resumption.republished if r.get('result') == 'written')}) "
                    f"slugs={','.join(sorted(executive.windows))} phase={executive.phase} scenario={executive.scenario} "
                    f"seed={executive.seed} ring={','.join(map(str, rings))} m={executive.clock['m']} k={executive.cycle_ticks} "
                    f"N={executive.checkpoint_every} cycles={args.cycles or 'until stopped'} state-dir={state_dir}"
                    + (f" scenario-file={scenario_file.scenario.name}:{scenario_file.sha256[:12]}" if scenario_file is not None else ""),
                )
            # `--plan` answers from the checkpoint's identity and writes nothing in the diode directory
            # (the state directory and its lock were made above, as for any start).
            record, problem = expected, None
        if checkpoint_found is None and state_fd is not None and not (args.init or args.plan or args.plan_json):
            # Addendum B11 (S11): a fresh world over a record with no checkpoint. Its first segment would be a
            # second root of the record, and every resume after it would refuse; one state directory is one
            # world's (ADR 0002 H). Only the first header of each journal file is read. It is the first thing
            # said (review F9): the state directory is the problem, whatever the diode directory holds.
            try:
                holding = state_record_files(state_fd, journal_fd, journal_explicit)
            except OSError as exc:
                # Confirmation G4: every `OSError` on a start's path is a refusal by name, with every handle closed.
                return refuse(f"the state directory {state_dir} cannot be read for a record ({errno_name(exc)}); nothing was started")
            if holding:
                return refuse(
                    f"the state directory {state_dir} holds a record ({', '.join(holding)}) and no checkpoint: another world's, "
                    "or one that died before its first checkpoint was written. One state directory is one world's "
                    f"(ADR 0002 H): move {', '.join(holding)} out of {state_dir}, or point --state-dir at an empty directory"
                )
        if checkpoint_found is None and not (args.init or args.plan or args.plan_json):
            # **A fresh serving start names its clock** (ADR 0002 A, B, J; #23): `m`, `k` and `N` are required
            # with no default — the deployed stack names them, and the console assumes none. Every missing
            # input is named, and the three are then held together to `clock_problem`'s bounds.
            missing = [
                flag for flag, value in (("--multiplier", args.multiplier), ("--cycle-ticks", args.cycle_ticks), ("--checkpoint-ticks", args.checkpoint_ticks))
                if value is None
            ]
            if missing:
                return refuse(
                    f"a serving start names the clock it runs on, and this one names no {' and no '.join(missing)}: m, k and N are "
                    "required with no default (ADR 0002 A, B and J), and the stack that starts the vehicle names them. A restart "
                    "inherits them from its checkpoint; --init and --plan run no clock"
                )
            tick_hz = (world.documents.get("mission.yaml") or {}).get("tick_hz")
            clock = clock_problem(named_m, args.cycle_ticks, args.checkpoint_ticks, tick_hz=tick_hz, max_rate=max_channel_rate(world))
            if clock is not None:
                flag, value = {
                    "m": ("--multiplier", args.multiplier), "k": ("--cycle-ticks", args.cycle_ticks), "N": ("--checkpoint-ticks", args.checkpoint_ticks),
                }[clock[0]]
                return refuse(f"{flag} {value}: {clock[1]}")
        if problem is not None:
            return refuse(
                f"the directory's record at {diode_dir / RECORD_FILE} cannot be read: {problem}. A record "
                "that cannot be read is not a fresh directory; repair or clear it"
            )
        record = record or {}
        recorded_slugs: dict[str, int] = {
            str(slug): int((record.get("ring_slots") or {}).get(slug, DEFAULT_RING_SLOTS))
            for slug in record.get("slugs") or []
        }

        # ---- the run's identity, resolved once against the directory's record --------------------
        #
        # A caller who names a value gets it. A caller who names nothing inherits whatever the
        # directory's own record holds. A directory with no record gets the declared default. One
        # directory is one world, so the identity is the directory's and not a window's.
        recorded_scenario = record.get("scenario")
        if not isinstance(recorded_scenario, str) or not recorded_scenario:
            recorded_scenario = None
        scenario = resolve_remembered(args.scenario, recorded_scenario, DEFAULT_SCENARIO)
        if scenario not in postures:
            if args.scenario is not None:
                return refuse(
                    f"scenario {scenario!r} is not one of the vehicle's {len(postures)}: {sorted(postures)}"
                )
            return refuse(
                f"the directory {diode_dir} records scenario {scenario!r}, which is not one of the "
                f"vehicle's {len(postures)}: {sorted(postures)}. Name one that is, or point `--diode-dir` "
                "at another directory"
            )
        recorded_seed = record.get("seed")
        if isinstance(recorded_seed, bool) or not isinstance(recorded_seed, int) or recorded_seed < 0:
            recorded_seed = None
        seed = resolve_remembered(args.seed, recorded_seed, DEFAULT_SEED)
        # **`--plan` answers "what will this run be" before it is run**, and it takes the *resolved*
        # pair, so `--plan` on a directory recorded as `crisis` describes the crisis it is in. It binds
        # nothing and writes nothing in the diode directory (its lock aside, and with `--state-dir` the state
        # directory and its lock are made as for any start), so a bound directory may be asked — under the
        # lock, like every read.
        if args.plan or args.plan_json:
            faults = load_faults(Path(args.dir))
            if not faults:
                return refuse(f"no faults under {Path(args.dir) / 'domains'}")
            phases = [
                float(row.get("duration_h", 0))
                for row in (yaml.safe_load((Path(args.dir) / "mission.yaml").read_text()) or {}).get(
                    "phases"
                )
                or []
            ]
            hours = sum(phases)
            try:
                plan = scenario_report(Path(args.dir), faults, postures, scenario, seed, hours)
            except Exception as exc:  # noqa: BLE001 - the refusal is the answer
                return refuse(f"the scenario cannot be planned: {exc}")
            plan.pop("_armed_faults", None)
            close_all()
            if args.plan_json:
                json.dump(plan, sys.stdout, indent=2)
                sys.stdout.write("\n")
                return 0
            print(
                f"scenario {plan['posture']!r} at seed {plan['master_seed']}, over {plan['hours']:g} h"
            )
            print(
                f"  hazard x{plan['hazard_factor']:g}, demand x{plan['on_demand_factor']:g}"
                f"  ·  seeded: {plan['seeded_faults']}"
            )
            print(f"  {len(plan['events'])} scheduled event(s), {len(plan['armed'])} armed fault(s)")
            for event in plan["events"][:10]:
                print(
                    f"    MET {event['met_h']:8.3f} h  {event['fault']:38} {event['kind']:22} "
                    f"-> {', '.join(event['perturbs'][:2])}"
                )
            if len(plan["events"]) > 10:
                print(f"    … and {len(plan['events']) - 10} more")
            return 0

        resolved_slots: dict[str, int] = {}
        for slug in slugs:
            # **The ring is the one remembered value a restart may not re-bound.** Whatever bound the
            # frames on disk were written under is the bound the window keeps; a caller who names a
            # *different* one is told, instead of being handed the old one with no remark.
            recorded_slots = recorded_slugs.get(slug)
            if args.ring_slots is not None and recorded_slots is not None and args.ring_slots != recorded_slots:
                return refuse(
                    f"--ring-slots {args.ring_slots} names a bound the window at {diode_dir / slug} does "
                    f"not have: its record holds {recorded_slots}, and the frames on disk were written "
                    "under it. A restart keeps the bound the ring already has — re-bounding it would make "
                    "the frames held, the losses accounted and the declared slot count three answers to "
                    "one question. Point `--slug` at a new window to run a differently bounded ring"
                )
            resolved_slots[slug] = resolve_remembered(args.ring_slots, recorded_slots, DEFAULT_RING_SLOTS)
            # **The legacy check, and it is the only read of a window's `pending.json`: refuse-only.** A
            # window the old console ticked records `ticks` and no `world_id`; a window another executive
            # ticked records a `world_id`. Either, on a slug the directory's record does not name, is a
            # window whose frames came from a world this executive cannot continue. Where the record
            # names the slug, the record governs, and whatever an agent wrote there is not read.
            if slug not in recorded_slugs:
                try:
                    window_fd = open_directory(slug, dir_fd=diode_fd)
                except FileNotFoundError:
                    legacy: dict[str, Any] = {}
                except OSError as exc:
                    return refuse(
                        f"the window at {diode_dir / slug} is not a directory this executive can open "
                        f"({errno.errorcode.get(exc.errno or 0, type(exc).__name__)}: {exc.strerror}); a "
                        "window is a directory, never a link"
                    )
                else:
                    try:
                        legacy = read_json_bounded("pending.json", dir_fd=window_fd) or {}
                    finally:
                        os.close(window_fd)
                ticks = legacy.get("ticks")
                named = legacy.get("world_id")
                if (isinstance(ticks, int) and not isinstance(ticks, bool) and ticks > 0) or (
                    isinstance(named, str) and named
                ):
                    return refuse(
                        f"the window at {diode_dir / slug} is a legacy window: its pending.json records "
                        f"{ticks if isinstance(ticks, int) else 0} tick(s) and world_id {named!r} while "
                        "the directory's record does not name it, so its frames came from a world this "
                        "executive cannot continue. Clear or rename it (ADR 0001 choice D)"
                    )

        bound = record.get("world_id")
        if isinstance(bound, str) and bound:
            return refuse(
                f"the directory {diode_dir} is bound to world {bound} (tick {record.get('tick')}), which "
                "is not this executive's. Starting a fresh world on it would silently reset its physics, "
                "and restart continuity is WP08's to define — clear or rename the directory (ADR 0001 "
                "choice D)"
            )

        if state_fd is not None:
            problem = serves_refusal()
            if problem is not None:
                return refuse(problem)
        phase = args.phase if args.phase is not None else DEFAULT_PHASE
        starting.at(diode_canonical.path)
        try:
            executive = Executive(
                world,
                diode_dir,
                phase=phase,
                tripped_interlocks=set(args.closed_interlock or []),
                scenario=scenario,
                seed=seed,
                max_batch=args.max_batch if args.max_batch is not None else DEFAULT_MAX_BATCH,
                journal=journal,
                record_slugs=recorded_slugs,
                state_dir=state_path,
                boot_id=boot_id,
                state_fd=state_fd,
                # The default segment lives in the held state directory, so its handle is that one: a
                # path alone would have `Executive` walk the state directory a second time.
                journal_dir_fd=journal_fd if journal_fd is not None else state_fd,
                diode_fd=diode_fd,
                # Named, all three, on a serving start (above); `--init` runs no clock, and builds with what it names.
                multiplier=named_m if named_m is not None else 1,
                cycle_ticks=args.cycle_ticks if args.cycle_ticks is not None else 1,
                checkpoint_every=args.checkpoint_ticks,
                pacer=pacer,
                scenario_file=scenario_file,
            )
        except ValueError as exc:
            return refuse(str(exc))
        starting.closing(executive.close, state_path or diode_canonical.path)
        for slug in slugs:
            try:
                executive.attach(slug, ring_slots=resolved_slots[slug])
            except ValueError as exc:
                with contextlib.suppress(OSError):  # the refusal is what is reported (fifth round)
                    executive.close()
                return refuse(str(exc))
        if executive.failure_count:
            with contextlib.suppress(OSError):  # the refusal is what is reported (fifth round)
                executive.close()
            return refuse(
                "a window or the directory's record could not be prepared: "
                + "; ".join(f"{diode_canonical.path / f['window']}: {f['error']}" for f in executive.failures)
                + ". Repair or clear it; a window is a directory of regular files and nothing else"
            )
        if args.init:
            for slug in slugs:
                print(f"initialised {diode_dir / slug} for slug {slug!r} at phase {phase!r}")
            # `--init` binds nothing: the lock is released and the records say `world_id: null`.
            executive.close()
            close_all()
            return 0
        if state_fd is not None:
            starting.at(state_path)
            # Addendum B1: a world's genesis checkpoint, at tick 0, before its first cycle — so a kill before
            # the first cadence checkpoint resumes rather than finding a bound root record and no checkpoint.
            # It is mandatory: nothing is bound yet, so a failure refuses with nothing lost.
            try:
                executive.checkpoint()
            except Exception as exc:  # noqa: BLE001 - the refusal names it
                with contextlib.suppress(OSError):  # the refusal is what is reported (fifth round)
                    executive.close()
                return refuse(
                    f"the world's first checkpoint cannot be written into {state_dir} ({exc}); nothing is bound yet, and a "
                    "world without a checkpoint cannot be resumed (ADR 0002 H)"
                )
            # The boot marker (#39, option B), before the first claim: a fresh world has no map to recover,
            # so it only names this boot, for the next resume to tell this boot's take from an older one.
            try:
                write_boot_marker(state_fd, executive.boot_id)
            except Exception as exc:  # noqa: BLE001 - the refusal names it
                with contextlib.suppress(OSError):  # the refusal is what is reported (fifth round)
                    executive.close()
                return refuse(f"the boot marker {state_path / BOOT_FILE} cannot be written ({errno_name(exc)}); nothing has been claimed")

        rings = sorted(set(resolved_slots.values()))
        ring = str(rings[0]) if len(rings) == 1 else ",".join(f"{s}:{resolved_slots[s]}" for s in slugs)
        return functools.partial(
            run,
            executive,
            f"[console] {diode_dir} slugs={','.join(slugs)} phase={phase} "
            f"scenario={executive.scenario} seed={executive.seed} ring={ring} "
            f"m={executive.clock['m']} k={executive.cycle_ticks} N={executive.checkpoint_every} "
            f"cycles={args.cycles or 'until stopped'} world={executive.world_id}"
            + (f" state-dir={state_dir}" if state_dir is not None else "")
            + (f" scenario-file={scenario_file.scenario.name}:{scenario_file.sha256[:12]}" if scenario_file is not None else ""),
        )


    # **One boundary for the start path** (round 3, H2): every descriptor it holds is registered in
    # `starting` the moment it is opened, with the path it was opened for, and is closed once on the way
    # out whatever happens; an `OSError` nothing on the path turned into a refusal of its own is exit 3
    # naming the file (`exc.filename`, or the path of what was in use) and the errno.
    # A `close` on the way out that fails is not raised past `main` (round 4, J4): every handle is still
    # closed, and the first such failure — when nothing else failed first — is named, and the exit is 3.
    #
    # **The stop handlers are installed first** (#23, design §5): before any recovery, so a `SIGTERM` during a
    # long resume ends the run at its first boundary, and a `docker stop` finishes the cycle it lands in and
    # takes the clean end — in the one-executive shape the console is PID 1, and only this handler makes
    # `SIGTERM` effective at all. `SIGINT` is the same. They are restored on the way out, so an in-process
    # caller's own handling of an interrupt is left as it was; off the main thread none can be installed.
    stopper = pacer
    installed: list[tuple[int, Any]] = []
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            installed.append((signum, signal.signal(signum, stopper.stop)))
    try:
        with _StartPath() as starting:
            try:
                prepared = start(starting)
            except OSError as exc:
                sys.stderr.write(starting.refusal(exc) + "\n")
                prepared = 3
            outcome = prepared if isinstance(prepared, int) else prepared()
    finally:
        for signum, previous in installed:
            signal.signal(signum, previous if previous is not None else signal.SIG_DFL)
    if starting.unclosed is not None:
        sys.stderr.write(starting.unclosed_refusal() + "\n")
        return outcome or 3
    return outcome

if __name__ == "__main__":
    raise SystemExit(main())
