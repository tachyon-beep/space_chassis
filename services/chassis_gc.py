"""Checkpoint-safe collection (K-F1 GC): the plan, the intent's validation, the unlinks.

Standard library only. Contract: SV-015 v2 section 1.4.5 (retained set,
eligibility, `GC_INTENT` -> unlink -> fsync(blobs/), fsync(ledger/) ->
`GC_DONE`), 1.4.10's GC row, O2-1/O2-4, SV-013 C-G1; SV-022 preflight A-C.

Three pieces, kept apart:

* `plan_collection` (pure): from verified ledger records and the blob names
  present, the exact bounded batch one intent may name -- or None.
* `intent_problem` (pure): why a payload is not deletion authority over these
  records, or None. It runs on every intent before any unlink: the live one
  before it is written, a pending one again at restart.
* `unlink_intent` (mutation): exactly the intent's fixed list. Segments oldest
  first, each unlink fenced by fsync(ledger/) before the next one; then the
  blobs; then fsync(blobs/) and fsync(ledger/).

**The retained set** (v2 1.4.5). `C_n` is the newest checkpoint and `C_p` the
checkpoint its `prev` tuple names -- exactly that record (seq, covers,
conversation hash and size), which may be older than the CHECKPOINT record
before `C_n` (SV021-02). Kept: every record with seq > `C_p.covers_seq` (so
`C_p`, its whole replay interval, `C_n` and the suffix, which also holds the
latest file binding), and the blobs `refs(C_n.state) | refs(C_p.state) |
refs(those records)`. A checkpoint naming no previous base gives no floor and
nothing is collected.

**Never candidates.** Only `ledger/NNNNNN.svl` segments and `blobs/<sha256>`
blobs can ever be named, by number and by 64-hex name -- never by a path. So
IDENTITY, RECOVERING, ACKNOWLEDGED, STOPPED, FSYNC_FAILED, run.json, both
conversation files, HANDOFF.md, corrupt/ and temporary files are outside the
namespace altogether. The active segment, the segment holding the first
retained record and every later one are excluded by the validator.

**Why each segment unlink is fenced.** Under M-2 an unlink whose directory
fsync has not returned may or may not survive a host loss, independently of
the others. Unfenced unlinks of several old segments could leave a surviving
segment between two lost ones, and the strict scanner rightly refuses a gap.
With a fence after each segment, at most the newest-attempted unlink is
undecided at any cut, so the segments that survive are always a suffix of the
list: the ledger stays contiguous and the pending intent stays readable.
Blobs need no order: no reader finds a record through a blob.

The batch is bounded (`GC_BATCH_MAX` items, the encoded body under
MAX_LEDGER_BODY); what does not fit stays for the next checkpoint's batch. A
collection never checkpoints, so it cannot recurse.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path

import chassis_persistence as cp
import chassis_replay as rp

# [CM] Items one intent may name. 4,096 names encode to under 300 KB, far
# below MAX_LEDGER_BODY; the validator also checks the encoded size itself.
GC_BATCH_MAX = 4096
INTENT_KEYS = frozenset({"records_through", "checkpoint_seq", "segments", "blobs"})


class GCRefused(Exception):
    """No collection is authorized: a dependency is missing or does not verify."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def checkpoint_tuple(record) -> dict:
    """The `prev` tuple that names a CHECKPOINT record."""
    return {
        "covers_seq": record.payload["covers_seq"],
        "conv_sha256": record.payload["conv"]["sha256"],
        "conv_bytes": record.payload["conv"]["bytes"],
        "checkpoint_seq": record.seq,
    }


# ---------------------------------------------------------------------------
# The retained set (pure)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Basis:
    newest: cp.Record  # C_n
    previous: cp.Record  # C_p, exactly the record C_n.prev names
    floor: int  # C_p.covers_seq: records at or below it are not retained
    retained: frozenset  # blob names that must stay
    keep_segment: int  # the segment holding the first retained record


def previous_checkpoint(records, newest) -> cp.Record | None:
    """The record `newest.prev` names, verified field by field; None when it names none."""
    prev = newest.payload["prev"]
    if prev is None:
        return None
    found = [r for r in records if isinstance(prev, dict) and r.seq == prev.get("checkpoint_seq")]
    if len(found) != 1 or found[0].type_name != "CHECKPOINT":
        raise GCRefused("previous_checkpoint_missing")
    if checkpoint_tuple(found[0]) != prev:
        raise GCRefused("previous_checkpoint_mismatch")
    return found[0]


def retained_basis(records, newest) -> Basis | None:
    """What checkpoint `newest` requires to be kept, over contiguous verified `records`."""
    previous = previous_checkpoint(records, newest)
    if previous is None:
        return None
    floor = previous.payload["covers_seq"]
    if not floor < previous.seq < newest.seq:
        raise GCRefused("previous_checkpoint_order")
    # The whole replay interval must be present: never collect against a
    # shortened retained set.
    if not records or records[0].seq > floor + 1:
        raise GCRefused("retained_interval_missing")
    try:
        rp.SessionState.from_wire(newest.payload["state"])
        rp.SessionState.from_wire(previous.payload["state"])
        retained = set(newest.payload["state"]["blobs_live"]) | set(previous.payload["state"]["blobs_live"])
        for record in records:
            if record.seq > floor:
                retained |= rp.record_refs(record)
    except (rp.StateError, KeyError, TypeError) as error:
        raise GCRefused(f"reference_graph_invalid: {type(error).__name__}") from error
    keep = next(record.segment for record in records if record.seq > floor)
    return Basis(newest, previous, floor, frozenset(retained), keep)


def pending_intent(records) -> cp.Record | None:
    """The GC_INTENT with no GC_DONE naming it, if any. More than one pending is refused."""
    done = {r.payload["intent_seq"] for r in records if r.type_name == "GC_DONE"}
    pending = [r for r in records if r.type_name == "GC_INTENT" and r.seq not in done]
    if len(pending) > 1:
        raise GCRefused("several_intents_pending")
    return pending[0] if pending else None


def unauthorized_prefix(records) -> int | None:
    """The oldest present segment, if segments below it are missing and no retained intent named them.

    Collection deletes segments oldest first, and the newest intent that
    deleted any is itself in a later segment, so after any collection --
    complete or interrupted -- the segment just below the oldest present one
    is named by a retained GC_INTENT. A missing prefix without one is not
    collection, and is not reinterpreted as collection.
    """
    if not records or records[0].segment == 0:
        return None
    below = records[0].segment - 1
    for record in records:
        if record.type_name == "GC_INTENT":
            segments = record.payload.get("segments")
            if isinstance(segments, list) and any(_counter(n) and n == below for n in segments):
                return None
    return records[0].segment


def blob_names(blobs_dir: Path) -> list[str]:
    """The canonical blob names present: 64-hex file names only (temporary files are never candidates)."""
    blobs_dir = Path(blobs_dir)
    if not blobs_dir.is_dir():
        return []
    return sorted(path.name for path in blobs_dir.iterdir() if rp.is_hex64(path.name))


# ---------------------------------------------------------------------------
# The plan (pure)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Plan:
    payload: dict  # the GC_INTENT body
    leftover: int  # eligible items not in this batch, for a later checkpoint


def plan_collection(records, *, active_segment: int, blob_names, batch_max: int = GC_BATCH_MAX) -> Plan | None:
    """One bounded batch right after the newest checkpoint, or None when nothing is eligible.

    `records`: a clean, verified scan whose last record is the newest
    CHECKPOINT (GC follows CK6 at once). Eligible segments are the closed
    ones, oldest first, whose last record is at or below the floor -- a
    prefix, since segments hold ascending seqs; the segment holding the
    first retained record is never one of them, so no segment is ever
    shortened. Eligible blobs are the present names outside the retained
    set. Deterministic: segments ascending, then blobs ascending.
    """
    if not 1 <= batch_max <= GC_BATCH_MAX:
        raise ValueError(f"batch_max must be 1..{GC_BATCH_MAX}")
    if not records or records[-1].type_name != "CHECKPOINT":
        raise GCRefused("not_after_checkpoint")
    if pending_intent(records) is not None:
        raise GCRefused("intent_pending")
    newest = records[-1]
    basis = retained_basis(records, newest)
    if basis is None:
        return None
    last_seq: dict[int, int] = {}
    for record in records:
        last_seq[record.segment] = record.seq
    segments = []
    for number in sorted(last_seq):
        if number >= min(active_segment, basis.keep_segment) or last_seq[number] > basis.floor:
            break
        segments.append(number)
    blobs = sorted(name for name in set(blob_names) if rp.is_hex64(name) and name not in basis.retained)
    batch_segments = segments[:batch_max]
    batch_blobs = blobs[: batch_max - len(batch_segments)]
    if not batch_segments and not batch_blobs:
        return None
    payload = {"records_through": basis.floor, "checkpoint_seq": newest.seq, "segments": batch_segments, "blobs": batch_blobs}
    return Plan(payload, len(segments) + len(blobs) - len(batch_segments) - len(batch_blobs))


# ---------------------------------------------------------------------------
# Validation (pure): deletion authority
# ---------------------------------------------------------------------------
def _counter(value) -> bool:
    return rp.counter(value)


def structure_problem(payload) -> str | None:
    """Why `payload` is not a well-formed intent: keys, domains, names, order, uniqueness, size."""
    if not isinstance(payload, dict) or set(payload) != INTENT_KEYS:
        return "keys"
    if not _counter(payload["records_through"]) or not rp.counter(payload["checkpoint_seq"], minimum=1):
        return "cover"
    segments, blobs = payload["segments"], payload["blobs"]
    if not isinstance(segments, list) or not isinstance(blobs, list):
        return "lists"
    if not all(_counter(n) and n <= cp.MAX_SEGMENT_NO for n in segments):
        return "segment name"
    if not all(rp.is_hex64(name) for name in blobs):
        return "blob name"
    if any(a >= b for a, b in zip(segments, segments[1:])) or any(a >= b for a, b in zip(blobs, blobs[1:])):
        return "order or duplicate"
    if not 1 <= len(segments) + len(blobs) <= GC_BATCH_MAX:
        return "batch size"
    try:
        if len(cp.canonical_body(payload)) > cp.MAX_LEDGER_BODY:
            return "body size"
    except cp.LedgerError:
        return "body"
    return None


def segments_form_prefix(listed, present) -> bool:
    """Whether deleting `listed` (ascending) leaves the surviving segments contiguous (SV022-02).

    The fenced oldest-first order keeps the ledger contiguous only if the
    list covers a prefix of the surviving segments: no listed segment may be
    deleted while an older surviving one is omitted. Listed segments already
    gone must lie below every survivor -- the leading items an interrupted
    run of this same fixed list removed.
    """
    present = set(present)
    oldest = min(present) if present else None
    surviving = [number for number in listed if number in present]
    if any(number not in present and oldest is not None and number > oldest for number in listed):
        return False
    if surviving:
        listed_set = set(listed)
        if any(number < surviving[-1] and number not in listed_set for number in present):
            return False
    return True


def intent_problem(payload, records, *, intent_seq: int | None = None, active_segment: int | None = None) -> str | None:
    """Why `payload` is not deletion authority over `records`, or None.

    `records`: the verified contiguous records. `intent_seq`: where the intent
    already stands (a restart); None for an intent about to be appended after
    the last record. The intent must immediately follow the checkpoint it
    names; its cover must be that checkpoint's actual previous base; every
    segment must lie below the first retained record's segment (and so below
    the intent's own and the active one) and the list must cover a prefix of
    the surviving segments (SV022-02); no blob may be retained by that
    checkpoint, nor named by any record after the intent.
    """
    problem = structure_problem(payload)
    if problem:
        return problem
    if intent_seq is None:
        before, after = list(records), []
    else:
        found = [r for r in records if r.seq == intent_seq and r.type_name == "GC_INTENT"]
        if len(found) != 1 or found[0].payload != payload:
            return "intent record"
        before = [r for r in records if r.seq < intent_seq]
        after = [r for r in records if r.seq > intent_seq]
    if not before or before[-1].type_name != "CHECKPOINT" or before[-1].seq != payload["checkpoint_seq"]:
        return "not after its checkpoint"
    try:
        basis = retained_basis(before, before[-1])
    except GCRefused as refusal:
        return refusal.reason
    if basis is None:
        return "no previous checkpoint"
    if payload["records_through"] != basis.floor:
        return "cover"
    limit = basis.keep_segment if active_segment is None else min(basis.keep_segment, active_segment)
    if any(number >= limit for number in payload["segments"]):
        return "protected segment"
    if not segments_form_prefix(payload["segments"], {record.segment for record in records}):
        return "segment prefix"
    if basis.retained & set(payload["blobs"]):
        return "retained blob"
    try:
        later = set().union(*(rp.record_refs(r) for r in after)) if after else set()
    except (KeyError, TypeError):
        return "later reference"
    if later & set(payload["blobs"]):
        return "later reference"
    return None


# ---------------------------------------------------------------------------
# The unlinks (mutation)
# ---------------------------------------------------------------------------
def _unlink(ops: cp.DurableOps, path: Path) -> None:
    try:
        ops.unlink(str(path))
    except FileNotFoundError:
        pass  # already gone: re-running an intent is idempotent


def sync_intent(session_dir: Path, intent: cp.Record, ops: cp.DurableOps) -> None:
    """fsync the segment file holding `intent`'s frame: the restart's deletion gate (SV022-01).

    A complete intent readable after a process death may be an append whose
    fsync never returned; directory fences do not make its bytes durable, and
    syncing any other (newer) segment does not cover it. So before a restart
    removes anything under it, the intent's own segment is synced. A failure
    is a PersistenceFailure, before any unlink.
    """
    path = Path(session_dir) / "ledger" / cp.segment_name(intent.segment)
    fd = None
    try:
        fd = ops.open(str(path), os.O_RDONLY | os.O_CLOEXEC)
        ops.fsync(fd)
    except OSError as error:
        raise cp.PersistenceFailure(f"the pending intent could not be made durable: {type(error).__name__}: {error}") from error
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                ops.close(fd)


def unlink_intent(session_dir: Path, payload: dict, ops: cp.DurableOps) -> None:
    """Remove exactly the intent's items, with the fences above. Any other error is PersistenceFailure.

    Paths are built from validated segment numbers and 64-hex names only.
    The caller has made the intent durable and validated it.
    """
    problem = structure_problem(payload)
    if problem:
        raise cp.LedgerError(f"not an intent: {problem}")
    session_dir = Path(session_dir)
    ledger, blobs = session_dir / "ledger", session_dir / "blobs"
    try:
        for number in payload["segments"]:
            _unlink(ops, ledger / cp.segment_name(number))
            ops.sync_dir(str(ledger))  # this deletion is durable before the next is attempted
        for name in payload["blobs"]:
            _unlink(ops, blobs / name)
        if payload["blobs"]:
            ops.sync_dir(str(blobs))
        ops.sync_dir(str(ledger))
    except OSError as error:
        raise cp.PersistenceFailure(f"collection failed: {type(error).__name__}: {error}") from error
