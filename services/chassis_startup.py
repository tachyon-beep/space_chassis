"""Startup: classify a session, recover it, and hand over exactly one `Session`.

Standard library only. Contracts: SV-013 section 2.2.2's authority table
A0-A15 with SV-015 v2's replacements (A3 by the tail classes of 1.3; replay
from newest and previous base, 1.4.4; quarantine pre-admission, 1.4.8;
FSYNC_FAILED honesty, 1.4.9). Nothing here sends a request or invokes a tool:
startup ends with a `Session` positioned after recovery, or a diagnostic stop.

**The authority rule** (D13, retained): the ledger is authoritative for runtime
events; the conversation file is authoritative memory only when bound; a
readable unbound list is a duty edit; an absent file after a bound checkpoint
is a duty deletion; an unreadable file is never treated as absent; anything
unclassifiable stops. Nothing bootstraps over memory that may exist.

**The recovery transaction** (SV021). Setting a damaged tail aside destroys
the only in-place evidence for its classification, and the records that
carry the outcome (SYNTH/UNRUN, RECOVERY, notices) are written afterwards. A
crash between the two would make a later start see a clean ledger and call a
possibly-run call "unrun". So, before any copy or truncation, a durable
`RECOVERING` intent names the valid prefix's end and the tail's hash. Both
are made durable first -- their segments fsynced, ledger/ fenced -- so the
intent never outlives what it names (SV024-02). A
restart rebuilds the identical tail from its quarantined copy, re-derives the
identical outcome, checks that whatever was already written is a prefix of
it, and writes only the rest. The intent is removed only after the outcome,
and its notices, are durable.

**Acknowledgements** are made durable as `ACKNOWLEDGED` before STOPPED is
removed, and transcribed into the ledger as RECOVERY_ACK (with an `ack_id`
that makes the transcription idempotent) at the next start, before any effect.

**A pending collection** (SV-022). A valid `GC_INTENT` in P with no `GC_DONE`
is finished here, whatever the session's `collect` setting: re-validated
against the retained records (`chassis_gc.intent_problem`; invalid -> stop
`gc_intent_invalid`, nothing removed), its own segment fsynced (a readable
intent may never have been synced), its *fixed* list re-run before this
start writes any blob -- a blob it names could otherwise be recreated by this
start and then removed -- and `GC_DONE` is the first record of the recovery
core. A torn or damaged intent is in T, not P, and is never authority. A
missing segment prefix that no retained intent names stops as damage
(`ledger_prefix_missing`).

**Witnessed file-repair resolutions** (SV-023). `continue-from-bound` for
`conversation_unreadable_unbound` (A14) and `run_json_unreadable` (CK5) is
permitted only when the stop carries a checked *witness*. The witness is
captured from the ledger and IDENTITY at the moment of the stop, never from
the damaged file, and only when the ledger end is strictly clean and no
transaction of its own is open. Acknowledgement verifies that every witnessed
fact is unchanged and that the externally repaired file is exactly the newest
checkpoint's (conversation bytes, or run.json by its recorded hash). It then
makes a sealed carrier durable before removing STOPPED. The start that
consumes the carrier verifies it again before it changes anything. That start
fences session/, writes RECOVERY_ACK first and only once, and only then
finishes the ordinary TC0 closure. A carrier whose evidence no longer holds
stops (`acknowledgement_unverified`) and grants nothing. Nothing here repairs
a file, chooses an older checkpoint or resets an epoch, lineage, note
watermark or request identity.

**bootstrap-preserving** (SV-028, W1 only). Admitted only for a witnessed
`conversation_unreadable_unbound` stop whose records after the newest
checkpoint are state-neutral. The command (Phase A) admits purely, then
publishes a sealed inventory of every session file and HANDOFF.md into
`preserved/<ack_id>.partial/` -- the durable snapshot boundary -- copies each
file as independent bytes, establishes every file and name dependency of the
set (E), seals it by renaming it to `preserved/<ack_id>/`, publishes the
carrier and removes STOPPED. After the boundary a changed source refuses and
never replaces a copy; only provably owned scratch is ever deleted; a sealed
set is never modified. The consuming start (Phase B) verifies the sealed set
and the preserved STOPPED it binds, derives the frozen plan Π (receipt,
optional spend, one EXTERNAL_DELETE at epoch+1) from the witnessed head
before applying any owned record, appends only Π's missing continuation,
fsyncs every owned segment and ledger/ (B3) -- even when it wrote nothing --
and only then removes the preserved unreadable conversation.json. Lineage,
request identity, notes, legacy status and originals are carried unchanged;
the duty sees exactly A12's path. A carrier-free restart under RECOVERING is
authenticated by the intent's sealed context against the ledger head and
writes nothing missing.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path

import chassis_envelope as envelope
import chassis_gc as gc
import chassis_persistence as cp
import chassis_replay as rp
from chassis_replay import Replay, ReplayMismatch, SessionState
from chassis_session import BLOB_READ_MAX, Session, SessionInvariant, checkpoint_tuple, read_identity

STOPPED = "STOPPED"
FSYNC_FAILED = "FSYNC_FAILED"
RECOVERING = "RECOVERING"
ACKNOWLEDGED = "ACKNOWLEDGED"
CONVERSATION_READ_MAX = 64 * 1024 * 1024  # today's read bound for conversation.json
META_READ_MAX = 1024 * 1024
LEGACY_HANDOFF_READ_MAX = 64 * 1024  # the legacy runtime's own HANDOFF.md read bound

LINEAGE_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")  # the chassis's own rule
SWITCH_TYPES = ("LEGACY_IMPORT", "EXTERNAL_EDIT", "LEGACY_REIMPORT")
MESSAGE_RECORDS = ("TURN_RESPONSE", "RESPONSE_REFUSED", "DONE", "UNRUN", "SYNTH", "MSG_APPEND", "HISTORY_REPLACED")

# The one registry of resolutions this runtime can carry out, each with its
# mechanism; the sets below are its exact subsets. Every other pair named by
# SV-013/v2 (bootstrap-preserving for any other stop; continue-from-bound for
# a damaged or missing ledger) is refused rather than half-performed. The
# persistence layer's generic resolution names authorize nothing by themselves.
# SV-023: the two witnessed file-repair pairs. SV-028: one bootstrap-preserving
# pair, only for a witnessed A14 stop over a state-neutral suffix (W1).
RESOLUTION_MECHANISM = {
    ("ledger_tail_ambiguous", "continue-conservative"): "tail",
    ("fsync_failed_previous_run", "continue-from-bound"): "plain",
    ("corrupt_quarantine_full", "continue-from-bound"): "plain",
    ("conversation_unreadable_unbound", "continue-from-bound"): "witnessed",
    ("run_json_unreadable", "continue-from-bound"): "witnessed",
    ("conversation_unreadable_unbound", "bootstrap-preserving"): "preserving",
}
IMPLEMENTED_RESOLUTIONS = frozenset(RESOLUTION_MECHANISM)
WITNESSED_RESOLUTIONS = frozenset(pair for pair, mechanism in RESOLUTION_MECHANISM.items() if mechanism == "witnessed")
PRESERVING_RESOLUTIONS = frozenset(pair for pair, mechanism in RESOLUTION_MECHANISM.items() if mechanism == "preserving")
STOP_WITNESS_RESOLUTIONS = WITNESSED_RESOLUTIONS | PRESERVING_RESOLUTIONS
WITNESSED_REASONS = frozenset(reason for reason, _resolution in STOP_WITNESS_RESOLUTIONS)

A14_NOTICE = (
    "[runtime] conversation.json could not be read; it was set aside in corrupt/ and the conversation "
    "was rebuilt from the last bound checkpoint and the ledger"
)
UNMERGED_NOTICE = (
    "[runtime] the conversation file was replaced outside the runtime; ledger records {first}–{last} "
    "after the last checkpoint are not in it{calls}"
)
UNMERGED_CALLS_SHOWN = 32


@dataclass
class Opening:
    # A0..A15; a "t" suffix (A9t, A12t, A8t) means the file is already bound by
    # a recorded transition (switch, deletion, adoption) after the newest checkpoint.
    classification: str
    session: Session | None = None
    stop: str | None = None
    detail: dict | None = None
    had_memory: bool = False


class StartupStop(Exception):
    def __init__(self, reason: str, detail=None, classification: str = "stop", *, write: bool = True) -> None:
        super().__init__(reason)
        self.reason, self.detail, self.classification, self.write = reason, detail, classification, write


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Reading the session's files
# ---------------------------------------------------------------------------
@dataclass
class FileState:
    status: str  # absent | unreadable | ok
    data: bytes | None = None
    messages: list | None = None

    @property
    def sha(self) -> str | None:
        return sha256(self.data) if self.data is not None else None


def _read(ops: cp.DurableOps, path: Path, limit: int) -> tuple[str, bytes | None]:
    try:
        return "ok", ops.read(str(path), limit)
    except FileNotFoundError:
        return "absent", None
    except OSError:  # unreadable, or over its bound: never "absent"
        return "unreadable", None


def parse_messages(data: bytes) -> list | None:
    try:
        messages = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(messages, list):
        return None
    if not all(isinstance(m, dict) and isinstance(m.get("role"), str) for m in messages):
        return None
    return messages


def read_conversation(path: Path, ops: cp.DurableOps) -> FileState:
    status, data = _read(ops, path, CONVERSATION_READ_MAX)
    if status != "ok":
        return FileState(status)
    messages = parse_messages(data)
    if messages is None:
        return FileState("unreadable", data)
    return FileState("ok", data, messages)


def _read_json_object(ops, path: Path, limit: int = META_READ_MAX) -> tuple[str, dict | None]:
    status, data = _read(ops, path, limit)
    if status != "ok":
        return status, None
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return "unreadable", None
    return ("ok", value) if isinstance(value, dict) else ("unreadable", None)


def _segment_lineage(segments: list[cp.Segment]) -> str | None:
    """The lineage named by the oldest segment's LEDGER_HEADER, if it parses."""
    if not segments:
        return None
    oldest = min(segments, key=lambda segment: segment.number)
    header = cp.read_header(oldest.data, 0)
    if header is None or not header.check_ok:
        return None
    record = cp.parse_record(oldest.data, 0, header.seq, None, oldest.number)
    if isinstance(record, cp.Record) and record.type_name == "LEDGER_HEADER":
        return record.payload["lineage_id"]
    return None


def _quarantine_file(session_dir: Path, name: str, data: bytes, quarantine: cp.Quarantine, ops) -> Path:
    """Copy a file's bytes into corrupt/ under admission (v2 1.4.8). The original stays in place."""
    corrupt = Path(quarantine.corrupt_dir)
    copy = corrupt / f"{name}-{sha256(data)[:16]}"
    already = False
    with contextlib.suppress(OSError):
        already = ops.read(str(copy), len(data)) == data
    if not already and not quarantine.admits(len(data)):
        raise StartupStop("corrupt_quarantine_full", {"bytes": len(data)})
    try:
        if not corrupt.is_dir():
            ops.mkdir(str(corrupt))
        ops.sync_dir(str(corrupt.parent))
    except OSError as error:
        raise cp.PersistenceFailure(f"corrupt/ could not be made durable: {error}") from error
    cp.write_bytes_durable(copy, data, ops=ops)
    return copy


# ---------------------------------------------------------------------------
# Acknowledgement (operator capability; tested with temporary data only)
# ---------------------------------------------------------------------------
def acknowledge(
    session_dir: Path, reason: str, resolution: str, *, ops: cp.DurableOps | None = None, home_dir: Path | None = None
) -> dict:
    """Make the acknowledgement durable, then lift the stop: ACKNOWLEDGED -> (FSYNC_FAILED) -> STOPPED.

    A crash before ACKNOWLEDGED is durable changes nothing; after it, STOPPED
    still stops every start (A0) until it is removed last, so no crash cut
    grants permission that was not durably given. Repeating the command is
    harmless. It adds no evidence about what any damaged bytes held.

    The two witnessed pairs (SV-023) go through `_acknowledge_witnessed`:
    the same order, after a pure verification of the stop's witness against
    the repaired store, with the verified evidence sealed into the carrier.
    The preserving pair (SV-028) goes through `_acknowledge_preserving`.
    `home_dir` (for HANDOFF.md) defaults to the chassis's own layout rule,
    `session_dir = home_dir / "session"` (chassis.py).
    """
    ops = ops or cp.DurableOps()
    session_dir = Path(session_dir)
    if (reason, resolution) not in IMPLEMENTED_RESOLUTIONS:
        raise cp.LedgerError(f"{resolution!r} for {reason!r} is not implemented by this runtime; nothing was changed")
    mechanism = RESOLUTION_MECHANISM[(reason, resolution)]
    if mechanism == "witnessed":
        return _acknowledge_witnessed(session_dir, reason, resolution, ops)
    if mechanism == "preserving":
        return _acknowledge_preserving(session_dir, reason, resolution, Path(home_dir) if home_dir is not None else session_dir.parent, ops)
    ack = cp.acknowledge_stop(session_dir, reason, resolution, ops=ops)
    stopped = ops.read(str(session_dir / STOPPED), cp.MAX_MARKER_READ)
    ack["ack_id"] = sha256(stopped + f"\n{reason}\n{resolution}".encode())[:32]
    # SV023-02: an unfinished carrier is never replaced. Only this same
    # acknowledgement (the same stop, pair and binding) may be written again.
    held_kind, held, _problem = read_carrier(session_dir, ops)
    if held_kind != "absent" and not (held_kind == "old" and held == ack):
        _refuse("another acknowledgement is pending and is never replaced; it keeps its transaction")
    cp.write_bytes_durable(session_dir / ACKNOWLEDGED, json.dumps(ack, sort_keys=True).encode(), ops=ops)
    if reason == "fsync_failed_previous_run":
        try:
            if (session_dir / FSYNC_FAILED).exists():
                ops.unlink(str(session_dir / FSYNC_FAILED))
            ops.sync_dir(str(session_dir))
        except OSError as error:
            raise cp.PersistenceFailure(f"FSYNC_FAILED could not be removed durably: {error}") from error
    cp.clear_stop(session_dir, ops=ops)
    return ack


OLD_CARRIER_KEYS = frozenset({"reason", "resolution", "ack_id"})
WITNESSED_ENVELOPE_KEYS = frozenset({"witness", "evidence", "check"})


def read_carrier(session_dir: Path, ops) -> tuple[str, dict | None, str | None]:
    """ACKNOWLEDGED classified: ("absent" | "old" | "witnessed" | "preserving" | "invalid", carrier, problem).

    SV023-01: absence is the only state that grants nothing and stops
    nothing. A present file that cannot be read, or whose types, pair or
    schema are not exactly a carrier this runtime writes, is "invalid": the
    start stops before any change. Types are checked before the pair is
    looked up. An old-pair carrier has exactly the old schema; a witnessed
    envelope is never reinterpreted as one.
    """
    status, carrier = _read_json_object(ops, Path(session_dir) / ACKNOWLEDGED, cp.MAX_MARKER_READ)
    if status == "absent":
        return "absent", None, None
    if status != "ok":
        return "invalid", None, "unreadable"
    reason, resolution = carrier.get("reason"), carrier.get("resolution")
    if not (isinstance(reason, str) and isinstance(resolution, str)) or (reason, resolution) not in IMPLEMENTED_RESOLUTIONS:
        return "invalid", None, "pair"
    if (reason, resolution) in WITNESSED_RESOLUTIONS:
        problem = carrier_problem(carrier)
        return ("invalid", None, problem) if problem else ("witnessed", carrier, None)
    if (reason, resolution) in PRESERVING_RESOLUTIONS:
        problem = preserving_carrier_problem(carrier)
        return ("invalid", None, problem) if problem else ("preserving", carrier, None)
    keys = set(carrier)
    tail = reason == "ledger_tail_ambiguous"
    if keys & WITNESSED_ENVELOPE_KEYS or keys != (OLD_CARRIER_KEYS | ({"tail_sha256"} if tail else set())):
        return "invalid", None, "keys"
    if not (isinstance(carrier["ack_id"], str) and HEX32.fullmatch(carrier["ack_id"])):
        return "invalid", None, "ack_id"
    if tail and not rp.is_hex64(carrier["tail_sha256"]):
        return "invalid", None, "tail_sha256"
    return "old", carrier, None


def _remove(session_dir: Path, name: str, ops) -> None:
    try:
        if (session_dir / name).exists():
            ops.unlink(str(session_dir / name))
            ops.sync_dir(str(session_dir))
    except OSError as error:
        raise cp.PersistenceFailure(f"{name} could not be removed durably: {error}") from error


def _fence_session(session_dir: Path, ops) -> None:
    """fsync(session/): the carrier's name and STOPPED's removal are durable before anything depends on them."""
    try:
        ops.sync_dir(str(session_dir))
    except OSError as error:
        raise cp.PersistenceFailure(f"session/ could not be fenced: {error}") from error


def _fence_intent_inputs(session_dir: Path, scan: cp.LedgerScan, ops) -> None:
    """Make durable everything a new RECOVERING intent depends on, before it is published (SV024-02).

    The intent names P's last record (its anchor) and the exact tail bytes at
    (segment, offset). Both were only read; an earlier process may have died
    before their fsync returned, and a new segment's name may never have been
    fenced (a rotation header torn in flight, M-1). So: fsync the anchor's
    segment and the tail's segment, then fsync(ledger/) for their names.
    (ledger/'s own name was fenced in session/ before its first segment was
    created, SV020-01.) Earlier segments were synced before anything rotated
    away from them. Any failure is a persistence failure before the intent
    exists: nothing is copied, truncated or published.
    """
    ledger = Path(session_dir) / "ledger"
    for number in sorted({scan.records[-1].segment, scan.tail_segment}):
        fd = None
        try:
            fd = ops.open(str(ledger / cp.segment_name(number)), os.O_RDONLY | os.O_CLOEXEC)
            ops.fsync(fd)
        except OSError as error:
            raise cp.PersistenceFailure(f"the recovery's source could not be made durable: {type(error).__name__}: {error}") from error
        finally:
            if fd is not None:
                with contextlib.suppress(OSError):
                    ops.close(fd)
    try:
        ops.sync_dir(str(ledger))
    except OSError as error:
        raise cp.PersistenceFailure(f"ledger/ could not be fenced before the recovery intent: {error}") from error


def _sync_record(session_dir: Path, record: cp.Record, ops) -> None:
    """fsync the segment holding `record`, which a previous process wrote but may never have synced.

    Readable is not durable (the SV022-01 rule): a receipt found after a
    process death is made durable before the carrier it retires is removed.
    """
    path = Path(session_dir) / "ledger" / cp.segment_name(record.segment)
    fd = None
    try:
        fd = ops.open(str(path), os.O_RDONLY | os.O_CLOEXEC)
        ops.fsync(fd)
    except OSError as error:
        raise cp.PersistenceFailure(f"the acknowledgement receipt could not be made durable: {type(error).__name__}: {error}") from error
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                ops.close(fd)


# ---------------------------------------------------------------------------
# Witnessed file-repair resolutions (SV-023; engineering schema, not canonical fields)
# ---------------------------------------------------------------------------
WITNESS_VERSION = 1
WITNESS_KEYS = frozenset({"version", "reason", "stop_id", "lineage_id", "ledger", "checkpoint", "identity_reserved", "check"})
WITNESS_LEDGER_KEYS = frozenset({"first_seq", "last_seq", "last_chain", "last_segment", "end_segment", "end_offset"})
WITNESS_CHECKPOINT_KEYS = frozenset({"checkpoint_seq", "covers_seq", "conv_sha256", "conv_bytes", "chain", "run_sha256"})
CARRIER_KEYS = frozenset({"reason", "resolution", "ack_id", "witness", "evidence", "check"})
HEX32 = re.compile(r"[0-9a-f]{32}")
# A witness is never taken over an open transaction or another resolution's
# carrier; FSYNC_FAILED keeps A1's authority over every later step.
WITNESS_BLOCKERS = (RECOVERING, ACKNOWLEDGED, FSYNC_FAILED)
# Records that bind the file to something other than the newest checkpoint.
SWITCH_RECORDS = (*SWITCH_TYPES, "EXTERNAL_DELETE")


class AcknowledgementRefused(cp.LedgerError):
    """A witnessed resolution whose evidence does not verify. Nothing was changed."""


def _refuse(why: str):
    raise AcknowledgementRefused(f"{why}; nothing was changed")


def _sealed(body: dict) -> dict:
    return {**body, "check": _intent_check(body)}


def _check_ok(value: dict) -> bool:
    body = {key: item for key, item in value.items() if key != "check"}
    try:
        return value["check"] == _intent_check(body)
    except (TypeError, ValueError):
        return False


def stop_witness(session_dir: Path, reason: str, scan: cp.LedgerScan | None, lineage: str | None, ops) -> dict | None:
    """The checked witness of a qualifying file-repair stop, or None: the stop is then recorded as before, ineligible.

    Taken from the ledger and IDENTITY only, never from the damaged file, and
    only over a strictly clean end (TC0, no A2) with no transaction of its own
    open: no RECOVERING, carrier or FSYNC_FAILED, no pending or unauthorized
    collection. The newest checkpoint's state must validate and the checked
    reservation must cover every turn the records show. Sealed by a SHA-256
    over every field (M-3); `stop_id` makes each stop distinct.
    """
    session_dir = Path(session_dir)
    if reason not in WITNESSED_REASONS or lineage is None or scan is None or scan.stop or scan.tail or not scan.records:
        return None
    if any((session_dir / name).exists() for name in WITNESS_BLOCKERS):
        return None
    records = scan.records
    try:
        if gc.unauthorized_prefix(records) is not None or gc.pending_intent(records) is not None:
            return None
    except gc.GCRefused:
        return None
    checkpoints = [record for record in records if record.type_name == "CHECKPOINT"]
    if not checkpoints:
        return None
    newest = checkpoints[-1]
    try:
        state = SessionState.from_wire(newest.payload["state"])
    except rp.StateError:
        return None
    reserved = read_identity(session_dir, lineage, ops)
    used = [record.payload["turn_seq"] for record in records if record.type_name == "REQUEST_SENT"]
    if state.requests_last is not None:
        used.append(state.requests_last["turn_seq"])
    if state.lineage_id != lineage or reserved is None or reserved < max(used, default=0):
        return None
    last = records[-1]
    witness = _sealed({
        "version": WITNESS_VERSION, "reason": reason, "stop_id": secrets.token_hex(16), "lineage_id": lineage,
        "ledger": {
            "first_seq": records[0].seq, "last_seq": last.seq, "last_chain": last.chain, "last_segment": last.segment,
            "end_segment": scan.tail_segment, "end_offset": scan.tail_offset,
        },
        "checkpoint": {**checkpoint_tuple(newest), "chain": newest.chain, "run_sha256": newest.payload["run_sha256"]},
        "identity_reserved": reserved,
    })
    return witness if witness_problem(witness, reason) is None else None


def witness_problem(witness, reason: str | None = None) -> str | None:
    """Why `witness` is not a valid stop witness (for `reason`, if given), or None."""
    if not isinstance(witness, dict) or set(witness) != WITNESS_KEYS:
        return "keys"
    if not _check_ok(witness):
        return "check"
    if witness["version"] != WITNESS_VERSION:
        return "version"
    if witness["reason"] not in WITNESSED_REASONS or (reason is not None and witness["reason"] != reason):
        return "reason"
    if not (isinstance(witness["stop_id"], str) and HEX32.fullmatch(witness["stop_id"])):
        return "stop_id"
    if not (isinstance(witness["lineage_id"], str) and LINEAGE_ID.fullmatch(witness["lineage_id"])):
        return "lineage_id"
    ledger, checkpoint = witness["ledger"], witness["checkpoint"]
    if not (isinstance(ledger, dict) and set(ledger) == WITNESS_LEDGER_KEYS):
        return "ledger"
    if not (
        rp.counter(ledger["first_seq"], minimum=1)
        and rp.counter(ledger["last_seq"], minimum=1)
        and ledger["first_seq"] <= ledger["last_seq"]
        and rp.is_hex64(ledger["last_chain"])
        and all(rp.counter(ledger[key]) and ledger[key] <= cp.MAX_SEGMENT_NO for key in ("last_segment", "end_segment"))
        and ledger["last_segment"] <= ledger["end_segment"]
        and rp.counter(ledger["end_offset"])
    ):
        return "ledger"
    if not (isinstance(checkpoint, dict) and set(checkpoint) == WITNESS_CHECKPOINT_KEYS):
        return "checkpoint"
    if not (
        rp.counter(checkpoint["checkpoint_seq"], minimum=1)
        and rp.counter(checkpoint["covers_seq"])
        and rp.counter(checkpoint["conv_bytes"])
        and checkpoint["covers_seq"] < checkpoint["checkpoint_seq"]
        and ledger["first_seq"] <= checkpoint["checkpoint_seq"] <= ledger["last_seq"]
        and all(rp.is_hex64(checkpoint[key]) for key in ("conv_sha256", "chain", "run_sha256"))
    ):
        return "checkpoint"
    if not rp.counter(witness["identity_reserved"]):
        return "identity_reserved"
    return None


def carrier_problem(carrier) -> str | None:
    """Why ACKNOWLEDGED's content is not a sealed witnessed carrier, or None."""
    if not isinstance(carrier, dict) or set(carrier) != CARRIER_KEYS:
        return "keys"
    if not _check_ok(carrier):
        return "check"
    if (carrier["reason"], carrier["resolution"]) not in WITNESSED_RESOLUTIONS:
        return "pair"
    if not (isinstance(carrier["ack_id"], str) and HEX32.fullmatch(carrier["ack_id"])):
        return "ack_id"
    problem = witness_problem(carrier["witness"], carrier["reason"])
    if problem:
        return f"witness {problem}"
    if not isinstance(carrier["evidence"], dict) or carrier["evidence"].get("witness_check") != carrier["witness"]["check"]:
        return "evidence"
    return None


def receipt_payload(carrier: dict) -> dict:
    """The RECOVERY_ACK this carrier's consumption writes, first and once."""
    return {
        "reason": carrier["reason"], "resolution": carrier["resolution"], "ack_id": carrier["ack_id"],
        "stop_id": carrier["witness"]["stop_id"], "evidence_sha256": sha256(cp.canonical_body(carrier["evidence"])),
    }


@dataclass(frozen=True)
class Verified:
    evidence: dict
    written: tuple = ()  # at consumption: this transaction's own records after the witnessed end, receipt first


@dataclass(frozen=True)
class Witnessed:
    carrier: dict
    receipt: dict
    written: tuple  # this transaction's records already in the ledger (receipt first), or ()


def witnessed_evidence(session_dir: Path, witness: dict, ops=None, *, receipt: dict | None = None) -> Verified:
    """Verify a witnessed stop against the store as it is now. Pure: it only reads.

    Every witnessed fact must be unchanged: the lineage, the strictly clean
    ledger (same first and last record, chain and physical end), no missing
    prefix or pending collection, IDENTITY exactly as witnessed, the same
    newest checkpoint. Its conversation must be directly bound: no switch
    after it, the latest binding is its own hash, and conversation.json is
    its bytes. run.json must be the metadata that checkpoint recorded (by
    `run_sha256`) and agree with it field by field. Its state, the blobs that
    state needs and the suffix replay must verify, and the TC0 closure must
    be derivable. No FSYNC_FAILED or RECOVERING may be present.

    `receipt`: at the start that consumes the acknowledgement. Bytes after
    the witnessed end are then allowed only as this transaction's own:
    segment headers, this receipt, then exactly the closure derived here, in
    order (returned as `written`), optionally followed by a strict byte prefix
    of its next frame -- an append a process death cut short (M-1), which the
    ordinary TC1 rule then sets aside. A RECOVERING is allowed only if
    anchored at or after the witnessed end; what follows its anchor is that
    intent's to check. Otherwise nothing may follow the witnessed end.
    Raises AcknowledgementRefused.
    """
    ops = ops or cp.DurableOps()
    session_dir = Path(session_dir)
    problem = witness_problem(witness)
    if problem:
        _refuse(f"the stop witness is not valid ({problem})")
    if (session_dir / FSYNC_FAILED).exists():
        _refuse(f"{FSYNC_FAILED} is present and is resolved first")
    lineage, ledger, wanted = witness["lineage_id"], witness["ledger"], witness["checkpoint"]
    try:
        segments = cp.read_segments(session_dir / "ledger", ops=ops) if (session_dir / "ledger").is_dir() else []
    except OSError as error:
        _refuse(f"the ledger cannot be read ({type(error).__name__})")
    if _segment_lineage(segments) != lineage:
        _refuse("the ledger is not the witnessed lineage's")
    scan = cp.scan_segments(segments, lineage)
    if scan.stop or (scan.tail and receipt is None):
        _refuse("the ledger does not end cleanly (TC0)")
    head = tuple(record for record in scan.records if record.seq <= ledger["last_seq"])
    after = [record for record in scan.records if record.seq > ledger["last_seq"]]
    anchor = (head[0].seq, head[-1].seq, head[-1].chain, head[-1].segment) if head else None
    if anchor != (ledger["first_seq"], ledger["last_seq"], ledger["last_chain"], ledger["last_segment"]):
        _refuse("the ledger is not the witnessed ledger")
    if after and receipt is None:
        _refuse("records were written after the witnessed end")
    if not after and not scan.tail and (scan.tail_segment, scan.tail_offset) != (ledger["end_segment"], ledger["end_offset"]):
        _refuse("the ledger does not end where the witness says")
    intent_status, intent = _read_json_object(ops, session_dir / RECOVERING, cp.MAX_MARKER_READ)
    intent_seq = None
    if intent_status != "absent":
        if receipt is None:
            _refuse(f"{RECOVERING} is present and is resolved first")
        last_seq = intent.get("last_seq") if intent_status == "ok" else None
        found = next((r for r in scan.records if r.seq == last_seq), None) if rp.counter(last_seq, minimum=1) else None
        # SV023-03: only an intent this transaction wrote, naming this receipt
        # and this witnessed end (the intent itself is validated in full later).
        context = intent.get("witnessed") if intent_status == "ok" else None
        own_intent = context == {"ack_id": receipt["ack_id"], "receipt": receipt, "after_seq": ledger["last_seq"]}
        if found is None or found.seq < ledger["last_seq"] or found.chain != intent.get("chain") or not own_intent:
            _refuse("a recovery is open that is not this acknowledgement's own")
        intent_seq = found.seq
    own = [record for record in after if intent_seq is None or record.seq <= intent_seq]
    try:
        if gc.unauthorized_prefix(head) is not None:
            _refuse("segments below the ledger are missing")
        if gc.pending_intent(head) is not None:
            _refuse("a collection is pending")
    except gc.GCRefused as refusal:
        _refuse(f"the collection records are invalid ({refusal.reason})")
    reserved = read_identity(session_dir, lineage, ops)
    if reserved != witness["identity_reserved"]:
        _refuse("IDENTITY is not the witnessed reservation")
    checkpoints = [record for record in head if record.type_name == "CHECKPOINT"]
    newest = checkpoints[-1] if checkpoints else None
    if newest is None or {**checkpoint_tuple(newest), "chain": newest.chain, "run_sha256": newest.payload["run_sha256"]} != wanted:
        _refuse("the newest checkpoint is not the witnessed one")
    try:
        state_n = SessionState.from_wire(newest.payload["state"])
    except rp.StateError as error:
        _refuse(f"the checkpoint state is invalid ({str(error)[:200]})")
    suffix = [record for record in head if record.seq > newest.payload["covers_seq"]]
    if any(
        record.type_name in SWITCH_RECORDS or (record.type_name == "RECOVERY" and record.payload.get("kind") == "conversation_adopted")
        for record in suffix
    ):
        _refuse("the conversation was switched after the newest checkpoint")
    kind, bound, _binder = _binding(head, newest)
    if kind not in ("checkpoint", "restored") or bound != wanted["conv_sha256"]:
        _refuse("the conversation file is not bound to the newest checkpoint")
    conv = read_conversation(session_dir / "conversation.json", ops)
    if conv.status != "ok" or conv.sha != wanted["conv_sha256"] or len(conv.data) != wanted["conv_bytes"]:
        _refuse("conversation.json is not the newest checkpoint's bytes")
    status, run_bytes = _read(ops, session_dir / "run.json", META_READ_MAX)
    if status != "ok" or sha256(run_bytes) != wanted["run_sha256"]:
        _refuse("run.json is not the metadata the newest checkpoint recorded")
    try:
        meta = json.loads(run_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        meta = None
    recorded = meta.get("checkpoint") if isinstance(meta, dict) else None
    if not (
        isinstance(recorded, dict)
        and meta.get("format") == 2
        and meta.get("lineage_id") == lineage
        and recorded.get("covers_seq") == wanted["covers_seq"]
        and recorded.get("conv") == {"sha256": wanted["conv_sha256"], "bytes": wanted["conv_bytes"]}
    ):
        _refuse("run.json does not agree with the newest checkpoint")
    blobs = cp.BlobStore(session_dir / "blobs", ops=ops)
    read_blob = lambda sha: blobs.get(sha, BLOB_READ_MAX)  # noqa: E731
    if any(read_blob(sha) is None for sha in state_n.blobs_live()):
        _refuse("a blob the checkpoint state needs is missing or damaged")
    last = head[-1]
    head_scan = cp.LedgerScan(head, last.seq, last.chain, b"", last.segment, last.offset + last.length)
    try:
        replay = _replay(json.loads(conv.data), state_n.copy(), suffix, read_blob)
        tail = cp.classify_tail(head_scan)
        plan = cp.plan_recovery(head_scan, tail, read_blob=read_blob)
        core = derive_core(replay, plan, tail, head_scan, None, lineage, identity_reserved=reserved)
    except ReplayMismatch as error:
        _refuse(f"the bound replay does not verify ({str(error)[:200]})")
    if plan.action != "continue" or tail.kind != "TC0":
        _refuse("the ledger end does not continue as TC0")
    evidence = {
        "witness_check": witness["check"],
        "conv_sha256": conv.sha,
        "run_sha256": sha256(run_bytes),
        "replay_sha256": sha256(rp.conversation_bytes(replay.messages)),
        "state_sha256": sha256(cp.canonical_body(replay.state.to_wire(next_seq=last.seq + 1))),
        "open_group": None if replay.group is None else [replay.group.turn_seq, replay.group.answered],
        "closure_sha256": sha256(cp.canonical_body({"core": [[name, payload] for name, payload in core]})),
    }
    written = tuple(record for record in own if record.type_name != "LEDGER_HEADER")
    planned = [("RECOVERY_ACK", receipt), *core] if receipt is not None else []
    if len(written) > len(planned) or not all(_same_record(record, item) for record, item in zip(written, planned)):
        _refuse("records after the witnessed end are not this acknowledgement's own")
    if scan.tail and intent_seq is None:
        expected = _next_own_frame((*head, *own)[-1], planned, len(written), lineage, scan.tail_segment)
        if expected is None or len(scan.tail) >= len(expected) or not expected.startswith(scan.tail):
            _refuse("the bytes after the witnessed end are not this acknowledgement's own")
    return Verified(evidence, written)


def _next_own_frame(last: cp.Record, planned: list, written: int, lineage: str, tail_segment) -> bytes | None:
    """The exact frame this transaction appends next after `last`, or None if it appends none there."""
    if tail_segment != last.segment:
        if tail_segment != last.segment + 1:
            return None
        payload = {"lineage_id": lineage, "segment_no": tail_segment, "first_seq": last.seq + 1, "prev_chain": last.chain}
        return cp.encode_frame(last.seq + 1, "LEDGER_HEADER", payload, last.chain)[0]
    if written >= len(planned):
        return None
    name, payload = planned[written]
    return cp.encode_frame(last.seq + 1, name, payload, last.chain)[0]


def _acknowledge_witnessed(session_dir: Path, reason: str, resolution: str, ops) -> dict:
    """SV-023: verify the witnessed stop, make the sealed carrier durable, then remove STOPPED.

    Refusals happen before any write. The same command repeated is
    idempotent: with STOPPED still present it rewrites the identical carrier
    (its fences again) and removes STOPPED; after STOPPED's removal it only
    repeats the session/ fence. Any other pending carrier is refused rather
    than replaced.
    """
    status, stopped = _read(ops, session_dir / STOPPED, cp.MAX_MARKER_READ)
    held_kind, held, _problem = read_carrier(session_dir, ops)
    held_ok = held_kind == "witnessed"
    if status == "absent" and held_ok and (held["reason"], held["resolution"]) == (reason, resolution):
        _fence_session(session_dir, ops)
        return held
    cp.acknowledge_stop(session_dir, reason, resolution, ops=ops)  # STOPPED readable, this reason: else LedgerError
    detail = json.loads(stopped.decode("utf-8")).get("detail")
    witness = detail.get("witness") if isinstance(detail, dict) else None
    problem = witness_problem(witness, reason)
    if problem:
        _refuse(f"the {reason} stop carries no valid witness ({problem}); a stop without one is not eligible")
    ack_id = sha256(stopped + f"\n{reason}\n{resolution}".encode())[:32]
    if held_kind != "absent" and not (held_ok and held["ack_id"] == ack_id):
        _refuse("another acknowledgement is pending and is never replaced; it keeps its transaction")
    verified = witnessed_evidence(session_dir, witness, ops)
    carrier = _sealed({"reason": reason, "resolution": resolution, "ack_id": ack_id, "witness": witness, "evidence": verified.evidence})
    if held_kind != "absent" and held != carrier:
        _refuse("the pending acknowledgement of this stop was made on other evidence")
    cp.write_bytes_durable(session_dir / ACKNOWLEDGED, json.dumps(carrier, sort_keys=True).encode(), ops=ops)
    cp.clear_stop(session_dir, ops=ops)
    return carrier


# ---------------------------------------------------------------------------
# bootstrap-preserving (SV-028 W1; engineering schema, not canonical fields)
# ---------------------------------------------------------------------------
PRESERVED = "preserved"
MANIFEST = "MANIFEST"
MANIFEST_VERSION = 1
MANIFEST_READ_MAX = META_READ_MAX  # [CM] the inventory's own read bound
NEUTRAL_SUFFIX = frozenset({"LEDGER_HEADER", "RUN_END", "GC_INTENT", "GC_DONE"})
# [CM] Admission bounds over the measured preserved/ namespace (logical sizes):
# an admission rule, not a filesystem quota.
PRESERVED_MAX_SETS = 4
PRESERVED_MAX_FILES = 16_384
PRESERVED_MAX_BYTES = 512 * 1024 * 1024
PRESERVED_FILE_MAX = 64 * 1024 * 1024  # = the largest runtime per-file bound (conversation, blob)
PRESERVED_NAME = re.compile(r"[A-Za-z0-9._:+=@,-]{1,255}")
SET_NAME = re.compile(r"([0-9a-f]{32})(\.partial)?")
SESSION_SUBDIRS = ("ledger", "blobs", "corrupt")
SET_DIRS = ("session/ledger", "session/blobs", "session/corrupt", "session", "home")  # leaves first
OWNED_TEMP = re.compile(r"\.(.+)\.[0-9a-f]{16}\.tmp")  # write_bytes_durable's temp name for <B>
EVIDENCE_KEYS = frozenset(
    {"witness_check", "manifest_sha256", "conv_sha256", "conv_bytes", "run_sha256", "state_sha256", "suffix", "continuation_sha256", "epoch"}
)
MANIFEST_KEYS = frozenset(
    {"version", "ack_id", "reason", "resolution", "stop_sha256", "stop_id", "witness_check", "lineage_id", "entries", "totals", "check"}
)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _suffix_problem(records) -> str | None:
    """Why the records after the newest checkpoint are not state-neutral (W1), or None."""
    for record in records:
        if record.type_name not in NEUTRAL_SUFFIX:
            return f"{record.type_name} at seq {record.seq}"
    return None


def _source(session_dir: Path, home_dir: Path, rel: str) -> Path:
    return home_dir / "HANDOFF.md" if rel == "home/HANDOFF.md" else session_dir / rel[len("session/"):]


def _entry_problem(path) -> str | None:
    if not isinstance(path, str):
        return "path"
    if path == "home/HANDOFF.md":
        return None
    for prefix in ("session/ledger/", "session/blobs/", "session/corrupt/", "session/"):
        if path.startswith(prefix):
            name = path[len(prefix):]
            return None if PRESERVED_NAME.fullmatch(name) and name not in (".", "..") else "path"
    return "path"


def preservation_domain(session_dir: Path, home_dir: Path) -> list[tuple[str, Path]]:
    """(inventory path, source) for every admitted pre-resolution file, sorted. Pure; refuses unsupported shapes.

    Every regular file of session/ (top level, ledger/, blobs/, corrupt/) and
    the one named HANDOFF.md. preserved/ is counted for capacity, never copied.
    No name is excluded: a temp-shaped name proves nothing about who wrote it.
    """
    found: list[tuple[str, Path]] = []

    def add(rel: str, path: Path) -> None:
        found.append((rel, path))
        if len(found) > PRESERVED_MAX_FILES:
            _refuse("preserved_capacity:files: the session holds more files than one preserved set may")

    def mode_of(path: Path) -> int:
        try:
            return os.lstat(path).st_mode
        except OSError as error:
            _refuse(f"preservation_unsupported_shape: {path.name} cannot be inspected ({type(error).__name__})")

    def named(name: str, where: str) -> None:
        if not (PRESERVED_NAME.fullmatch(name) and name not in (".", "..")):
            _refuse(f"preservation_unsupported_name: {where}{name!r}")

    for name in sorted(os.listdir(session_dir)):
        path = session_dir / name
        mode = mode_of(path)
        if name == PRESERVED:
            if not stat.S_ISDIR(mode):
                _refuse("preservation_unsupported_shape: preserved is not a directory")
            continue
        named(name, "")
        if name in SESSION_SUBDIRS:
            if not stat.S_ISDIR(mode):
                _refuse(f"preservation_unsupported_shape: {name} is not a directory")
            for child in sorted(os.listdir(path)):
                named(child, f"{name}/")
                if not stat.S_ISREG(mode_of(path / child)):
                    _refuse(f"preservation_unsupported_shape: {name}/{child} is not a regular file")
                add(f"session/{name}/{child}", path / child)
        elif stat.S_ISREG(mode):
            add(f"session/{name}", path)
        else:
            _refuse(f"preservation_unsupported_shape: {name} is not a regular file")
    handoff = home_dir / "HANDOFF.md"
    try:
        mode = os.lstat(handoff).st_mode
    except FileNotFoundError:
        mode = None
    if mode is not None:
        if not stat.S_ISREG(mode):
            _refuse("preservation_unsupported_shape: HANDOFF.md is not a regular file")
        add("home/HANDOFF.md", handoff)
    return sorted(found)


def _read_source(ops, path: Path, rel: str, limit: int) -> bytes:
    try:
        return ops.read(str(path), limit)
    except cp.ReadTooLarge:
        _refuse(f"preserved_file_too_large: {rel} is over {limit} bytes")
    except FileNotFoundError:
        _refuse(f"preserved_source_missing: {rel} is gone")
    except OSError as error:
        _refuse(f"preservation_unsupported_shape: {rel} cannot be read ({type(error).__name__})")


def _inventory(domain, ops) -> list[dict]:
    """Read #1: the size and hash of every admitted file, one file at a time."""
    entries = []
    for rel, path in domain:
        data = _read_source(ops, path, rel, PRESERVED_FILE_MAX)
        entries.append({"path": rel, "bytes": len(data), "sha256": sha256(data)})
    return entries


def _stop_binding(stopped: bytes, witness: dict, reason: str, resolution: str, ack_id: str) -> dict:
    return {
        "ack_id": ack_id, "reason": reason, "resolution": resolution, "stop_sha256": sha256(stopped),
        "stop_id": witness["stop_id"], "witness_check": witness["check"], "lineage_id": witness["lineage_id"],
    }


def _manifest(binding: dict, entries: list) -> bytes:
    body = {
        "version": MANIFEST_VERSION, **binding, "entries": entries,
        "totals": {"files": len(entries), "bytes": sum(entry["bytes"] for entry in entries)},
    }
    return _canonical(_sealed(body))


def manifest_problem(data: bytes, binding: dict | None) -> tuple[str | None, dict | None]:
    """(why the bytes are not a valid sealed inventory for `binding`, or None; the inventory)."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return "json", None
    if not isinstance(value, dict) or set(value) != MANIFEST_KEYS:
        return "keys", None
    try:
        if _canonical(value) != data:
            return "canonical", None
    except (TypeError, ValueError):
        return "canonical", None
    if not _check_ok(value):
        return "check", None
    if value["version"] != MANIFEST_VERSION:
        return "version", None
    if binding is not None:
        for key, item in binding.items():
            if value[key] != item:
                return f"binding {key}", None
    entries = value["entries"]
    if not isinstance(entries, list) or not entries:
        return "entries", None
    paths = []
    for entry in entries:
        if not (isinstance(entry, dict) and set(entry) == {"path", "bytes", "sha256"}):
            return "entry keys", None
        if _entry_problem(entry["path"]) or not rp.counter(entry["bytes"]) or not rp.is_hex64(entry["sha256"]):
            return "entry", None
        paths.append(entry["path"])
    if paths != sorted(set(paths)):
        return "entry order", None
    if value["totals"] != {"files": len(entries), "bytes": sum(entry["bytes"] for entry in entries)}:
        return "totals", None
    return None, value


def _read_manifest(set_dir: Path, ops, token: str) -> bytes:
    try:
        return ops.read(str(set_dir / MANIFEST), MANIFEST_READ_MAX)
    except cp.ReadTooLarge:
        _refuse(f"{token}: the inventory is over its read bound")
    except OSError as error:
        _refuse(f"{token}: the inventory cannot be read ({type(error).__name__})")


def _set_files(set_dir: Path) -> list[str]:
    """Every regular file of one set, by path inside it. Pure; any other shape refuses."""
    files: list[str] = []
    allowed = set(SET_DIRS)

    def walk(rel: str) -> None:
        directory = set_dir / rel if rel else set_dir
        for name in sorted(os.listdir(directory)):
            child = f"{rel}/{name}" if rel else name
            mode = os.lstat(directory / name).st_mode
            if stat.S_ISDIR(mode) and child in allowed:
                walk(child)
            elif stat.S_ISREG(mode):
                files.append(child)
                if len(files) > 2 * PRESERVED_MAX_FILES:
                    _refuse("preserved_capacity:files: the preserved namespace is over its listing bound")
            else:
                _refuse(f"preservation_unsupported_shape: preserved set entry {child}")

    walk("")
    return files


@dataclass(frozen=True)
class PreservedUsage:
    files: int
    bytes: int
    sets: frozenset


def preserved_usage(preserved: Path) -> PreservedUsage:
    """The measured usage U of all of preserved/ (every set, sealed or unfinished, temps included). Pure."""
    if not os.path.lexists(preserved):
        return PreservedUsage(0, 0, frozenset())
    if not stat.S_ISDIR(os.lstat(preserved).st_mode):
        _refuse("preservation_unsupported_shape: preserved is not a directory")
    files = total = 0
    sets = set()
    for name in sorted(os.listdir(preserved)):
        match = SET_NAME.fullmatch(name)
        if not match or not stat.S_ISDIR(os.lstat(preserved / name).st_mode):
            _refuse(f"preservation_unsupported_shape: preserved/{name} is not a preserved set")
        sets.add(match.group(1))
        for rel in _set_files(preserved / name):
            files += 1
            total += os.lstat(preserved / name / rel).st_size
            if files > 2 * PRESERVED_MAX_FILES:
                _refuse("preserved_capacity:files: the preserved namespace is over its listing bound")
    return PreservedUsage(files, total, frozenset(sets))


def _lifecycle(preserved: Path, ack_id: str) -> str:
    """none | pre (unfinished, no inventory) | post (unfinished, inventory published) | sealed."""
    sealed, partial = preserved / ack_id, preserved / f"{ack_id}.partial"
    if os.path.lexists(sealed) and os.path.lexists(partial):
        _refuse("preserved_set_mismatch: both the sealed and the unfinished own set exist; both are kept untouched")
    if os.path.lexists(sealed):
        return "sealed"
    if not os.path.lexists(partial):
        return "none"
    return "post" if os.path.lexists(partial / MANIFEST) else "pre"


def _pre_boundary_scratch(partial: Path) -> list[tuple[str, int]]:
    """Before the inventory exists the only owned files are MANIFEST temps; anything else refuses."""
    found = []
    for name in sorted(os.listdir(partial)):
        status = os.lstat(partial / name)
        match = OWNED_TEMP.fullmatch(name)
        if not (stat.S_ISREG(status.st_mode) and match and match.group(1) == MANIFEST):
            _refuse("preserved_inventory_missing: the unfinished own set holds files but no inventory; it is kept untouched")
        found.append((name, status.st_size))
    return found


def _verify_sources(session_dir: Path, home_dir: Path, entries: list, ops) -> None:
    """After the boundary the live domain must be the inventory, byte for byte (missing first, then added, then changed)."""
    for entry in entries:
        if not os.path.lexists(_source(session_dir, home_dir, entry["path"])):
            _refuse(f"preserved_source_missing: {entry['path']} is gone; the inventory and copies are kept")
    added = {rel for rel, _path in preservation_domain(session_dir, home_dir)} - {entry["path"] for entry in entries}
    if added:
        _refuse(f"preserved_domain_changed: {sorted(added)[:3]} appeared after the inventory; nothing is replaced")
    for entry in entries:
        data = _read_source(ops, _source(session_dir, home_dir, entry["path"]), entry["path"], PRESERVED_FILE_MAX)
        if len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
            _refuse(f"preserved_source_changed: {entry['path']} no longer has its inventoried bytes; its copy is kept")


def _classify_partial(partial: Path, entries: list, ops) -> tuple[list, list]:
    """(owned deletions [(path, size)], entries still to copy). Pure; unowned files refuse.

    Called only after every live source verified: a deleted destination or
    copy temp is therefore never the sole preserved original.
    """
    dests = {entry["path"]: entry for entry in entries}
    present, deletions = set(), []
    for rel in _set_files(partial):
        if rel == MANIFEST:
            continue
        size = os.lstat(partial / rel).st_size
        if rel in dests:
            entry = dests[rel]
            try:
                data = ops.read(str(partial / rel), entry["bytes"])
            except OSError:
                data = None
            if data is not None and len(data) == entry["bytes"] and sha256(data) == entry["sha256"]:
                present.add(rel)
            else:
                deletions.append((rel, size))
            continue
        parent, _sep, name = rel.rpartition("/")
        match = OWNED_TEMP.fullmatch(name)
        base = match.group(1) if match else None
        if match and ((not parent and base == MANIFEST) or (parent and f"{parent}/{base}" in dests)):
            deletions.append((rel, size))
            continue
        _refuse(f"preserved_scratch_unowned: {rel} is not this transaction's scratch; it is kept untouched")
    return deletions, [entry for entry in entries if entry["path"] not in present]


def _verify_set(set_dir: Path, entries: list, ops, token: str) -> None:
    files = set(_set_files(set_dir))
    expected = {MANIFEST, *(entry["path"] for entry in entries)}
    if files != expected:
        _refuse(f"{token}: the set's files are not its inventory ({sorted(files ^ expected)[:3]})")
    for entry in entries:
        try:
            data = ops.read(str(set_dir / entry["path"]), entry["bytes"])
        except OSError:
            data = None
        if data is None or len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
            _refuse(f"{token}:{entry['path']}: preserved bytes differ")


def _ensure_dir(path: Path, parent: Path, ops) -> None:
    """mkdir if absent; the parent's fsync runs whether or not it existed (SV020-01)."""
    if not path.is_dir():
        ops.mkdir(str(path))
    ops.sync_dir(str(parent))


def _ensure_subdirs(set_dir: Path, entries: list, ops) -> None:
    needed = set()
    for entry in entries:
        parts = entry["path"].split("/")[:-1]
        for end in range(1, len(parts) + 1):
            needed.add("/".join(parts[:end]))
    for rel in ("session", "home", "session/ledger", "session/blobs", "session/corrupt"):
        if rel in needed:
            _ensure_dir(set_dir / rel, (set_dir / rel).parent, ops)


def _write_copy(source: Path, dest: Path, data: bytes, ops) -> None:
    """One independent copy from bytes read now (never a link): temp, fsync, rename, directory fsync."""
    cp.write_bytes_durable(dest, data, ops=ops)


def _copy_entry(session_dir: Path, home_dir: Path, set_dir: Path, entry: dict, ops) -> None:
    source = _source(session_dir, home_dir, entry["path"])
    data = _read_source(ops, source, entry["path"], PRESERVED_FILE_MAX)  # read #2
    if len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
        _refuse(f"preserved_source_changed: {entry['path']} changed after the inventory; the inventory and earlier copies are kept")
    _write_copy(source, set_dir / entry["path"], data, ops)


def _fsync_file(path: Path, ops) -> None:
    fd = ops.open(str(path), os.O_RDONLY | os.O_CLOEXEC)
    try:
        ops.fsync(fd)
    finally:
        with contextlib.suppress(OSError):
            ops.close(fd)


def _establish_inventory(partial: Path, session_dir: Path, ops) -> None:
    """L1: a readable inherited inventory is made durable with its names before any further archive mutation."""
    _fsync_file(partial / MANIFEST, ops)
    ops.sync_dir(str(partial))
    ops.sync_dir(str(partial.parent))
    ops.sync_dir(str(session_dir))


def _establish_set(set_dir: Path, entries: list, session_dir: Path, ops) -> None:
    """E (SV028-06): every set file's data, every set directory leaves first, then preserved/ and session/.

    Covers reused copies as well as new ones: a final name may be readable
    while its writer's leaf fence never returned. Allocates nothing.
    """
    for rel in (MANIFEST, *(entry["path"] for entry in entries)):
        _fsync_file(set_dir / rel, ops)
    for rel in SET_DIRS:
        if (set_dir / rel).is_dir():
            ops.sync_dir(str(set_dir / rel))
    ops.sync_dir(str(set_dir))
    ops.sync_dir(str(set_dir.parent))
    ops.sync_dir(str(session_dir))


@dataclass
class _Head:
    lineage: str
    scan: cp.LedgerScan
    head: tuple
    after: list
    newest: cp.Record
    state0: SessionState
    suffix: list  # head records after the newest checkpoint's covers_seq: C_n itself and the neutral records
    read_blob: object


def _preserving_head(session_dir: Path, witness: dict, ops, *, owned: bool) -> _Head:
    """The witnessed facts, unchanged (P3–P8). `owned`: records and a tail after the witnessed end may exist."""
    lineage, ledger, wanted = witness["lineage_id"], witness["ledger"], witness["checkpoint"]
    try:
        segments = cp.read_segments(session_dir / "ledger", ops=ops) if (session_dir / "ledger").is_dir() else []
    except OSError as error:
        _refuse(f"ledger_not_witnessed: the ledger cannot be read ({type(error).__name__})")
    if _segment_lineage(segments) != lineage:
        _refuse("ledger_not_witnessed: the ledger is not the witnessed lineage's")
    scan = cp.scan_segments(segments, lineage)
    if scan.stop:
        _refuse("ledger_not_witnessed: the ledger is damaged")
    head = tuple(record for record in scan.records if record.seq <= ledger["last_seq"])
    after = [record for record in scan.records if record.seq > ledger["last_seq"]]
    anchor = (head[0].seq, head[-1].seq, head[-1].chain, head[-1].segment) if head else None
    if anchor != (ledger["first_seq"], ledger["last_seq"], ledger["last_chain"], ledger["last_segment"]):
        _refuse("ledger_not_witnessed: the ledger is not the witnessed ledger")
    if not owned and (after or scan.tail):
        _refuse("ledger_not_witnessed: records or bytes follow the witnessed end")
    if not after and not scan.tail and (scan.tail_segment, scan.tail_offset) != (ledger["end_segment"], ledger["end_offset"]):
        _refuse("ledger_not_witnessed: the ledger does not end where the witness says")
    try:
        if gc.unauthorized_prefix(head) is not None:
            _refuse("collection_pending_or_unauthorized: segments below the ledger are missing")
        if gc.pending_intent(head) is not None:
            _refuse("collection_pending_or_unauthorized: a collection is pending")
    except gc.GCRefused as refusal:
        _refuse(f"collection_pending_or_unauthorized: {refusal.reason}")
    if read_identity(session_dir, lineage, ops) != witness["identity_reserved"]:
        _refuse("identity_not_witnessed: IDENTITY is not the witnessed reservation")
    checkpoints = [record for record in head if record.type_name == "CHECKPOINT"]
    newest = checkpoints[-1] if checkpoints else None
    if newest is None or {**checkpoint_tuple(newest), "chain": newest.chain, "run_sha256": newest.payload["run_sha256"]} != wanted:
        _refuse("checkpoint_not_witnessed: the newest checkpoint is not the witnessed one")
    try:
        state0 = SessionState.from_wire(newest.payload["state"])
    except rp.StateError as error:
        _refuse(f"checkpoint_not_witnessed: its state is invalid ({str(error)[:200]})")
    blobs = cp.BlobStore(session_dir / "blobs", ops=ops)
    read_blob = lambda sha: blobs.get(sha, BLOB_READ_MAX)  # noqa: E731
    if any(read_blob(sha) is None for sha in state0.blobs_live()):
        _refuse("state_blob_missing: a blob the checkpoint state needs is missing or damaged")
    problem = _suffix_problem([record for record in head if record.seq > newest.seq])
    if problem:
        _refuse(f"suffix_not_neutral: {problem} follows the newest checkpoint")
    status, run_bytes = _read(ops, session_dir / "run.json", META_READ_MAX)
    if status != "ok" or sha256(run_bytes) != wanted["run_sha256"]:
        _refuse("run_json_not_witnessed: run.json is not the metadata the newest checkpoint recorded")
    try:
        meta = json.loads(run_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        meta = None
    recorded = meta.get("checkpoint") if isinstance(meta, dict) else None
    if not (
        isinstance(recorded, dict)
        and meta.get("format") == 2
        and meta.get("lineage_id") == lineage
        and recorded.get("covers_seq") == wanted["covers_seq"]
        and recorded.get("conv") == {"sha256": wanted["conv_sha256"], "bytes": wanted["conv_bytes"]}
    ):
        _refuse("run_json_not_witnessed: run.json does not agree with the newest checkpoint")
    suffix = [record for record in head if record.seq > newest.payload["covers_seq"]]
    return _Head(lineage, scan, head, after, newest, state0, suffix, read_blob)


def _previous_base_problem(session_dir: Path, h: _Head, conv_data: bytes | None, ops) -> str | None:
    """P10: no file holds C_n's bytes and C_n's own previous base is not available (A14-unbound still holds)."""
    newest_sha = h.newest.payload["conv"]["sha256"]
    prev = read_conversation(session_dir / "conversation.prev.json", ops)
    if (conv_data is not None and sha256(conv_data) == newest_sha) or (prev.status == "ok" and prev.sha == newest_sha):
        return "a file holds the newest checkpoint's bytes"
    info = h.newest.payload["prev"]
    if info and prev.status == "ok" and prev.sha == info["conv_sha256"] and any(
        record.seq == info["checkpoint_seq"] and record.type_name == "CHECKPOINT" for record in h.head
    ):
        return "the newest checkpoint's previous base is available"
    return None


def _still_unbound(session_dir: Path, h: _Head, ops) -> bytes:
    """P9/P10: the live conversation is present, regular, within its bound, unreadable as a list, and still unbound."""
    path = session_dir / "conversation.json"
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        _refuse("conversation_absent: the ordinary start is A12; no acknowledgement is needed")
    if not stat.S_ISREG(mode):
        _refuse("preservation_unsupported_shape: conversation.json is not a regular file")
    try:
        data = ops.read(str(path), CONVERSATION_READ_MAX)
    except cp.ReadTooLarge:
        _refuse("conversation_over_bound: conversation.json cannot be preserved under its read bound")
    except OSError as error:
        _refuse(f"conversation_over_bound: conversation.json cannot be read ({type(error).__name__})")
    if parse_messages(data) is not None:
        _refuse("conversation_readable: the stop no longer holds; start normally")
    problem = _previous_base_problem(session_dir, h, data, ops)
    if problem:
        _refuse(f"previous_base_available: {problem}")
    return data


def preserving_continuation(newest, suffix, head, *, lineage, ack_id, manifest_sha256, read_blob, identity_reserved=None):
    """(C_n's state, the frozen continuation [spend?, activation]) from the witnessed head alone (SV028-02).

    Derived once, before any owned record is applied: applying a readable
    spend would change the very state the spend is derived from.
    """
    state0 = SessionState.from_wire(newest.payload["state"])
    replay = Replay([], state0.copy(), read_blob)
    for record in suffix:
        replay.apply(record)
    last = head[-1]
    scan_h = cp.LedgerScan(tuple(head), last.seq, last.chain, b"", last.segment, last.offset + last.length)
    tail0 = cp.classify_tail(scan_h)
    plan0 = cp.plan_recovery(scan_h, tail0, read_blob=read_blob)
    if plan0.action != "continue" or tail0.kind != "TC0" or replay.group is not None:
        raise ReplayMismatch("the witnessed head does not continue as TC0 at a unit boundary")
    spend = derive_core(replay, plan0, tail0, scan_h, None, lineage, identity_reserved=identity_reserved)
    if spend and not (len(spend) == 1 and spend[0][0] == "RECOVERY" and spend[0][1]["kind"] == "possible_duplicate_spend"):
        raise ReplayMismatch("the witnessed head needs a closure the preserving plan does not carry")
    activation = (
        "EXTERNAL_DELETE",
        {"epoch": replay.state.history_epoch + 1, "notices": [], "cause": "bootstrap_preserving", "ack_id": ack_id, "manifest_sha256": manifest_sha256},
    )
    return state0, [*spend, activation]


def preserving_evidence(witness, manifest_sha256, conv_entry, newest, state0, suffix_types, continuation) -> dict:
    return {
        "witness_check": witness["check"],
        "manifest_sha256": manifest_sha256,
        "conv_sha256": conv_entry["sha256"],
        "conv_bytes": conv_entry["bytes"],
        "run_sha256": newest.payload["run_sha256"],
        "state_sha256": sha256(cp.canonical_body(state0.to_wire(next_seq=witness["ledger"]["last_seq"] + 1))),
        "suffix": {"count": len(suffix_types), "types_sha256": sha256(cp.canonical_body({"types": suffix_types}))},
        "continuation_sha256": _continuation_sha(continuation),
        "epoch": continuation[-1][1]["epoch"],
    }


def _continuation_sha(continuation) -> str:
    return sha256(cp.canonical_body({"continuation": [[name, payload] for name, payload in continuation]}))


def _suffix_types(h: _Head) -> list[str]:
    return [record.type_name for record in h.head if record.seq > h.newest.seq]


def preserving_evidence_problem(evidence) -> str | None:
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
        return "evidence keys"
    for key in ("witness_check", "manifest_sha256", "conv_sha256", "run_sha256", "state_sha256", "continuation_sha256"):
        if not rp.is_hex64(evidence[key]):
            return f"evidence {key}"
    if not (rp.counter(evidence["conv_bytes"]) and rp.counter(evidence["epoch"], minimum=2)):
        return "evidence counters"
    suffix = evidence["suffix"]
    if not (isinstance(suffix, dict) and set(suffix) == {"count", "types_sha256"} and rp.counter(suffix["count"]) and rp.is_hex64(suffix["types_sha256"])):
        return "evidence suffix"
    return None


def preserving_carrier_problem(carrier) -> str | None:
    """Why ACKNOWLEDGED's content is not a sealed preserving carrier, or None."""
    if not isinstance(carrier, dict) or set(carrier) != CARRIER_KEYS:
        return "keys"
    if not _check_ok(carrier):
        return "check"
    if (carrier["reason"], carrier["resolution"]) not in PRESERVING_RESOLUTIONS:
        return "pair"
    if not (isinstance(carrier["ack_id"], str) and HEX32.fullmatch(carrier["ack_id"])):
        return "ack_id"
    problem = witness_problem(carrier["witness"], carrier["reason"])
    if problem:
        return f"witness {problem}"
    problem = preserving_evidence_problem(carrier["evidence"])
    if problem:
        return problem
    if carrier["evidence"]["witness_check"] != carrier["witness"]["check"]:
        return "evidence"
    return None


def _preflight(carrier: dict, receipt: dict, witness: dict, plan_len: int, epoch: int) -> None:
    """P14: counter domains and the exact serialized carrier and maximal RECOVERING, before any write."""
    if epoch > rp.MAX_COUNTER or witness["ledger"]["last_seq"] + plan_len + 3 > cp.MAX_SEQ:
        _refuse("plan_out_of_domain: the epoch or sequence would leave its 12-digit domain")
    if len(json.dumps(carrier, sort_keys=True).encode()) > cp.MAX_MARKER_READ:
        _refuse("carrier_too_large: the carrier would exceed its reader's bound")
    context = {"ack_id": carrier["ack_id"], "receipt": receipt, "after_seq": witness["ledger"]["last_seq"], "evidence": carrier["evidence"]}
    maximal = _sealed_intent({
        "lineage_id": witness["lineage_id"], "last_seq": cp.MAX_SEQ, "chain": "f" * 64, "segment": cp.MAX_SEGMENT_NO,
        "offset": 10**12 - 1, "tail_sha256": "f" * 64, "tail_bytes": 10**12 - 1, "ack": None,
        "identity_reserved": rp.MAX_COUNTER, "witnessed": context,
    })
    if len(json.dumps(maximal, sort_keys=True).encode()) > cp.MAX_MARKER_READ:
        _refuse("recovery_context_too_large: a recovery intent for this transaction would exceed its reader's bound")


def _acknowledge_preserving(session_dir: Path, reason: str, resolution: str, home_dir: Path, ops) -> dict:
    """SV-028 Phase A: admission (pure) -> durable inventory -> copies -> E -> seal -> carrier -> STOPPED's removal.

    Every refusal in admission happens before any write. After the inventory
    is published (the durable boundary) a later refusal leaves the inventory
    and the copies made so far for diagnosis; it never rolls anything back.
    A persistence failure attempts the best-effort FSYNC_FAILED marker and
    stops the transaction where it is: completed renames and unlinks stay.
    Phase A never touches the live conversation.
    """
    status, stopped = _read(ops, session_dir / STOPPED, cp.MAX_MARKER_READ)
    held_kind, held, _problem = read_carrier(session_dir, ops)
    if status == "absent" and held_kind == "preserving" and (held["reason"], held["resolution"]) == (reason, resolution):
        _fence_session(session_dir, ops)
        return held
    cp.acknowledge_stop(session_dir, reason, resolution, ops=ops)  # STOPPED readable, this reason: else LedgerError
    detail = json.loads(stopped.decode("utf-8")).get("detail")
    witness = detail.get("witness") if isinstance(detail, dict) else None
    problem = witness_problem(witness, reason)
    if problem:
        _refuse(f"the {reason} stop carries no valid witness ({problem}); a stop without one is not eligible")
    ack_id = sha256(stopped + f"\n{reason}\n{resolution}".encode())[:32]
    if held_kind != "absent" and not (held_kind == "preserving" and held["ack_id"] == ack_id):
        _refuse("another acknowledgement is pending and is never replaced; it keeps its transaction")
    for name in (RECOVERING, FSYNC_FAILED):
        if os.path.lexists(session_dir / name):
            _refuse(f"transaction_open: {name} is present and is resolved first")
    h = _preserving_head(session_dir, witness, ops, owned=False)
    conv_data = _still_unbound(session_dir, h, ops)
    binding = _stop_binding(stopped, witness, reason, resolution, ack_id)
    preserved = session_dir / PRESERVED
    sealed, partial = preserved / ack_id, preserved / f"{ack_id}.partial"
    usage = preserved_usage(preserved)
    state = _lifecycle(preserved, ack_id)
    if held_kind == "preserving" and state != "sealed":
        _refuse("preserved_set_mismatch: a carrier is held but its set is not sealed")
    deletions: list = []
    writes: list = []
    manifest_new = None
    if state == "sealed":
        data = _read_manifest(sealed, ops, "preserved_set_mismatch")
        problem, manifest = manifest_problem(data, binding)
        if problem:
            _refuse(f"preserved_set_mismatch: the sealed inventory is not valid ({problem}); it is kept untouched")
        entries = manifest["entries"]
        _verify_set(sealed, entries, ops, "preserved_set_mismatch")
    elif state == "post":
        data = _read_manifest(partial, ops, "preserved_inventory_invalid")
        problem, manifest = manifest_problem(data, binding)
        if problem:
            _refuse(f"preserved_inventory_invalid: {problem}; the unfinished set is kept untouched")
        entries = manifest["entries"]
        _verify_sources(session_dir, home_dir, entries, ops)
        deletions, writes = _classify_partial(partial, entries, ops)
    else:
        if state == "pre":
            deletions = _pre_boundary_scratch(partial)
        entries = _inventory(preservation_domain(session_dir, home_dir), ops)
        data = _manifest(binding, entries)
        if len(data) > MANIFEST_READ_MAX:
            _refuse(f"preserved_manifest_too_large: the inventory is {len(data)} bytes, over its read bound {MANIFEST_READ_MAX}")
        manifest_new, writes = data, entries
    conv_entry = next((entry for entry in entries if entry["path"] == "session/conversation.json"), None)
    if conv_entry is None or (conv_entry["bytes"], conv_entry["sha256"]) != (len(conv_data), sha256(conv_data)):
        _refuse("preserved_source_changed: the live conversation is not the inventoried one")
    manifest_sha = sha256(data)
    try:
        state0, continuation = preserving_continuation(
            h.newest, h.suffix, h.head, lineage=h.lineage, ack_id=ack_id, manifest_sha256=manifest_sha,
            read_blob=h.read_blob, identity_reserved=witness["identity_reserved"],
        )
    except (ReplayMismatch, rp.StateError) as error:
        _refuse(f"plan_unexpected: {str(error)[:200]}")
    evidence = preserving_evidence(witness, manifest_sha, conv_entry, h.newest, state0, _suffix_types(h), continuation)
    carrier = _sealed({"reason": reason, "resolution": resolution, "ack_id": ack_id, "witness": witness, "evidence": evidence})
    receipt = receipt_payload(carrier)
    _preflight(carrier, receipt, witness, len(continuation) + 1, continuation[-1][1]["epoch"])
    if held_kind == "preserving" and held != carrier:
        _refuse("the pending acknowledgement of this stop was made on other evidence")
    # P13 on every branch (L4): F = U - D + A; deletions precede allocations, so F is the allocation peak.
    final_files = usage.files - len(deletions) + len(writes) + (1 if manifest_new is not None else 0)
    final_bytes = usage.bytes - sum(size for _rel, size in deletions) + sum(entry["bytes"] for entry in writes) + len(manifest_new or b"")
    if len(usage.sets | {ack_id}) > PRESERVED_MAX_SETS:
        _refuse(f"preserved_capacity:sets: {len(usage.sets | {ack_id})} sets would exceed {PRESERVED_MAX_SETS}")
    if final_files > PRESERVED_MAX_FILES:
        _refuse(f"preserved_capacity:files: {final_files} files would exceed {PRESERVED_MAX_FILES}")
    if final_bytes > PRESERVED_MAX_BYTES:
        _refuse(f"preserved_capacity:bytes: {final_bytes} bytes would exceed {PRESERVED_MAX_BYTES}")
    try:
        if state == "sealed":
            _establish_set(sealed, entries, session_dir, ops)
        else:
            if state == "post":
                _establish_inventory(partial, session_dir, ops)  # L1: before any cleanup, child mkdir or copy
            touched = set()
            for rel, _size in deletions:
                ops.unlink(str(partial / rel))
                touched.add((partial / rel).parent)
            for directory in sorted(touched, key=lambda path: len(path.parts), reverse=True):
                ops.sync_dir(str(directory))
            if manifest_new is not None:
                _ensure_dir(preserved, session_dir, ops)
                _ensure_dir(partial, preserved, ops)
                cp.write_bytes_durable(partial / MANIFEST, manifest_new, ops=ops)  # the durable inventory boundary
            _ensure_subdirs(partial, entries, ops)
            for entry in writes:
                _copy_entry(session_dir, home_dir, partial, entry, ops)
            _establish_set(partial, entries, session_dir, ops)
            ops.rename(str(partial), str(sealed))
            ops.sync_dir(str(preserved))
        if held_kind != "preserving":
            cp.write_bytes_durable(session_dir / ACKNOWLEDGED, json.dumps(carrier, sort_keys=True).encode(), ops=ops)
        cp.clear_stop(session_dir, ops=ops)
    except OSError as error:
        cp.mark_fsync_failed(session_dir, f"bootstrap-preserving: {type(error).__name__}: {error}", ops=ops)
        raise cp.PersistenceFailure(f"the preservation could not be made durable: {type(error).__name__}: {error}") from error
    return carrier


@dataclass(frozen=True)
class Preserving:
    plan: tuple  # Π: receipt, spend?, activation -- frozen from the witnessed head
    evidence: dict
    receipt: dict
    witness_end: int
    witness_segment: int
    state0: SessionState
    newest: cp.Record
    carrier: dict | None  # None on the carrier-free route
    written: tuple = ()


def preserving_verification(session_dir: Path, carrier: dict, ops) -> Preserving:
    """Phase B's B0 (pure): the sealed set, the preserved stop's binding (L2), the witnessed head, Π, the owned prefix.

    Live STOPPED was removed by Phase A on purpose; the stop is bound through
    its preserved copy. Raises AcknowledgementRefused.
    """
    witness, evidence, ack_id = carrier["witness"], carrier["evidence"], carrier["ack_id"]
    reason, resolution = carrier["reason"], carrier["resolution"]
    preserved = session_dir / PRESERVED
    sealed = preserved / ack_id
    if not sealed.is_dir() or os.path.lexists(preserved / f"{ack_id}.partial"):
        _refuse("manifest: the sealed preserved set is missing")
    data = _read_manifest(sealed, ops, "manifest")
    if sha256(data) != evidence["manifest_sha256"]:
        _refuse("manifest: the sealed inventory is not the acknowledged one")
    problem, manifest = manifest_problem(data, None)
    if problem:
        _refuse(f"manifest: {problem}")
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    stop_entry = entries.get("session/STOPPED")
    if stop_entry is None:
        _refuse("stop_binding: the preserved set holds no STOPPED")
    try:
        stop_bytes = ops.read(str(sealed / "session" / STOPPED), cp.MAX_MARKER_READ)
    except OSError:
        _refuse("preserved_entry:session/STOPPED: it cannot be read")
    if (len(stop_bytes), sha256(stop_bytes)) != (stop_entry["bytes"], stop_entry["sha256"]):
        _refuse("preserved_entry:session/STOPPED: preserved bytes differ")
    try:
        stop_record = json.loads(stop_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        stop_record = None
    detail = stop_record.get("detail") if isinstance(stop_record, dict) else None
    if not (isinstance(stop_record, dict) and stop_record.get("reason") == reason and isinstance(detail, dict) and detail.get("witness") == witness):
        _refuse("stop_binding: the preserved STOPPED is not the acknowledged stop")
    if sha256(stop_bytes + f"\n{reason}\n{resolution}".encode())[:32] != ack_id:
        _refuse("stop_binding: the preserved STOPPED does not give this acknowledgement's identity")
    problem, _manifest_value = manifest_problem(data, _stop_binding(stop_bytes, witness, reason, resolution, ack_id))
    if problem:
        _refuse(f"stop_binding: the inventory's binding does not match ({problem})")
    _verify_set(sealed, manifest["entries"], ops, "preserved_entry")
    conv_entry = entries.get("session/conversation.json")
    if conv_entry is None or (conv_entry["sha256"], conv_entry["bytes"]) != (evidence["conv_sha256"], evidence["conv_bytes"]):
        _refuse("evidence_changed: the preserved conversation is not the acknowledged one")
    h = _preserving_head(session_dir, witness, ops, owned=True)
    try:
        state0, continuation = preserving_continuation(
            h.newest, h.suffix, h.head, lineage=h.lineage, ack_id=ack_id, manifest_sha256=evidence["manifest_sha256"],
            read_blob=h.read_blob, identity_reserved=witness["identity_reserved"],
        )
    except (ReplayMismatch, rp.StateError) as error:
        _refuse(f"evidence_changed: the plan cannot be derived ({str(error)[:200]})")
    receipt = receipt_payload(carrier)
    plan = (("RECOVERY_ACK", receipt), *continuation)
    last = witness["ledger"]["last_seq"]
    own_all = [record for record in h.after if record.type_name != "LEDGER_HEADER"]
    intent_status, intent = _read_json_object(ops, session_dir / RECOVERING, cp.MAX_MARKER_READ)
    intent_seq = None
    if intent_status != "absent":
        expected = {"ack_id": ack_id, "receipt": receipt, "after_seq": last, "evidence": evidence}
        last_seq = intent.get("last_seq") if intent_status == "ok" else None
        found = next((r for r in h.scan.records if r.seq == last_seq), None) if rp.counter(last_seq, minimum=1) else None
        if found is None or found.seq < last or found.chain != intent.get("chain") or intent.get("witnessed") != expected:
            _refuse("own_prefix: a recovery is open that is not this acknowledgement's own")
        intent_seq = found.seq
    own = [record for record in own_all if intent_seq is None or record.seq <= intent_seq]
    if len(own) > len(plan) or not all(_same_record(record, item) for record, item in zip(own, plan)):
        _refuse("own_prefix: records after the witnessed end are not this acknowledgement's own")
    if intent_seq is None and h.scan.tail:
        frame = _next_own_frame((*h.head, *h.after)[-1], list(plan), len(own), h.lineage, h.scan.tail_segment)
        if frame is None or len(h.scan.tail) >= len(frame) or not frame.startswith(h.scan.tail):
            _refuse("own_prefix: the bytes after the witnessed end are not this acknowledgement's own")
    activated = any(_same_record(record, plan[-1]) for record in own_all)
    conv_path = session_dir / "conversation.json"
    conv_data = None
    if os.path.lexists(conv_path):
        status, conv_data = _read(ops, conv_path, CONVERSATION_READ_MAX)
        if status != "ok" or sha256(conv_data) != evidence["conv_sha256"]:
            _refuse("conversation_changed: the live conversation is not the preserved one")
    elif not activated:
        _refuse("conversation_changed: the conversation is absent but the activation is not in the ledger")
    problem = _previous_base_problem(session_dir, h, conv_data, ops)
    if problem:
        _refuse(f"previous_base_available: {problem}")
    recomputed = preserving_evidence(witness, evidence["manifest_sha256"], conv_entry, h.newest, state0, _suffix_types(h), continuation)
    if recomputed != evidence:
        _refuse("evidence_changed: the verified evidence differs from the acknowledged evidence")
    return Preserving(plan, evidence, receipt, last, witness["ledger"]["last_segment"], state0, h.newest, carrier, tuple(own))


def preserving_from_context(p0, context: dict, lineage: str, read_blob) -> Preserving:
    """The carrier-free route: Π re-derived from the immutable witnessed head and authenticated by the sealed context."""

    def bad(why: str):
        raise StartupStop("recovery_intent_invalid", {"field": f"preserving context: {why}"}, "intent")

    after, evidence, receipt = context["after_seq"], context["evidence"], context["receipt"]
    head = tuple(record for record in p0 if record.seq <= after)
    if not head or head[-1].seq != after:
        bad("after_seq")
    checkpoints = [record for record in head if record.type_name == "CHECKPOINT"]
    if not checkpoints:
        bad("checkpoint")
    newest = checkpoints[-1]
    if _suffix_problem([record for record in head if record.seq > newest.seq]):
        bad("suffix")
    suffix = [record for record in head if record.seq > newest.payload["covers_seq"]]
    try:
        state0, continuation = preserving_continuation(
            newest, suffix, head, lineage=lineage, ack_id=context["ack_id"], manifest_sha256=evidence["manifest_sha256"], read_blob=read_blob,
        )
    except (ReplayMismatch, rp.StateError):
        bad("plan")
    if _continuation_sha(continuation) != evidence["continuation_sha256"]:
        bad("continuation")
    if sha256(cp.canonical_body(state0.to_wire(next_seq=after + 1))) != evidence["state_sha256"]:
        bad("state")
    if continuation[-1][1]["epoch"] != evidence["epoch"] or newest.payload["run_sha256"] != evidence["run_sha256"]:
        bad("epoch or run")
    plan = (("RECOVERY_ACK", receipt), *continuation)
    return Preserving(plan, evidence, receipt, after, head[-1].segment, state0, newest, None)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def open_session(
    session_dir: Path,
    home_dir: Path,
    *,
    ops: cp.DurableOps | None = None,
    lifecycle=None,
    repair=None,
    new_lineage=None,
    quarantine: cp.Quarantine | None = None,
    **session_kwargs,
) -> Opening:
    """Classify and recover. A stop writes STOPPED (except A0) and returns no session.

    `repair(messages, folded) -> (messages, folded)` repairs a list adopted
    from outside the runtime (the chassis's recap-frame repair).
    """
    ops = ops or cp.DurableOps()
    session_dir, home_dir = Path(session_dir), Path(home_dir)
    context = _Context(
        session_dir,
        home_dir,
        ops,
        lifecycle or (lambda event, **fields: None),
        repair or (lambda messages, folded: (messages, folded)),
        new_lineage,
        quarantine or cp.Quarantine(session_dir / "corrupt", ops=ops),
        session_kwargs,
    )
    try:
        return context.open()
    except StartupStop as stop:
        if stop.write:
            try:
                cp.write_stop(session_dir, stop.reason, stop.detail, ops=ops)
            except cp.PersistenceFailure as error:
                context.lifecycle("stop_unwritten", reason=stop.reason, error=str(error)[:300])
                cp.mark_fsync_failed(session_dir, f"STOPPED unwritten: {error}", ops=ops)
        return Opening(stop.classification, stop=stop.reason, detail=stop.detail)
    except cp.PersistenceFailure as error:
        # The session-level boundary for failures outside a writer: attempt
        # the marker once (it may fail on the same medium; nothing is claimed).
        cp.mark_fsync_failed(session_dir, f"startup: {error}", ops=ops)
        raise


@dataclass
class _Context:
    session_dir: Path
    home_dir: Path
    ops: cp.DurableOps
    lifecycle: object
    repair: object
    new_lineage: object
    quarantine: cp.Quarantine
    session_kwargs: dict = field(default_factory=dict)

    # -- A0..A7 -------------------------------------------------------------------
    def open(self) -> Opening:
        session_dir = self.session_dir
        if (session_dir / STOPPED).exists():
            raise StartupStop("diagnostic_stop", None, "A0", write=False)
        if (session_dir / FSYNC_FAILED).exists():
            raise StartupStop("fsync_failed_previous_run", None, "A1")
        carrier_kind, self.ack, problem = read_carrier(session_dir, self.ops)
        if carrier_kind == "invalid":
            # SV023-01: a present carrier that cannot be classified grants nothing
            # and is not absence: stop before any change, its bytes kept.
            raise StartupStop("acknowledgement_unverified", {"problem": f"carrier: {problem}"}, "ACK")
        self.witnessed = None
        self.preserving = None
        self.clean_end = None
        if carrier_kind == "witnessed":
            # SV-023: verified before this start changes anything at all.
            self.witnessed = self._verify_carrier(self.ack)
        elif carrier_kind == "preserving":
            # SV-028 B0: the sealed set, the preserved stop and the frozen plan, before any change.
            self.preserving = self._verify_preserving(self.ack)
        meta_status, meta = _read_json_object(self.ops, session_dir / "run.json")
        self.meta = meta if meta_status == "ok" else None
        self.meta_unreadable = meta_status == "unreadable"
        format2 = self.meta is not None and self.meta.get("format") == 2
        try:
            segments = cp.read_segments(session_dir / "ledger", ops=self.ops) if (session_dir / "ledger").is_dir() else []
        except OSError as error:
            raise StartupStop("ledger_unreadable", {"error": f"{type(error).__name__}"}, "A2") from error
        if format2:
            lineage = self.meta.get("lineage_id")
            if not isinstance(lineage, str) or not lineage:
                raise StartupStop("run_json_unreadable", {"field": "lineage_id"}, "CK5")
        else:
            lineage = _segment_lineage(segments)
        scan = cp.scan_segments(segments, lineage or "-") if segments else None
        if scan is None or not scan.records:
            if scan is not None:
                self._settle_empty_ledger(scan)
            if format2:
                raise StartupStop("ledger_missing", None, "A7")
            return self._start_legacy()
        if self.meta_unreadable:
            # The lineage and scan here come from the ledger itself, never from run.json.
            raise StartupStop("run_json_unreadable", self._witness("run_json_unreadable", scan, lineage), "CK5")
        checkpointed = any(record.type_name == "CHECKPOINT" for record in scan.records)
        if format2:
            authority = "format2"
        elif checkpointed and self.meta is None:
            # CK5 made run.json durable before any CHECKPOINT (M-4: it cannot
            # revert), so its absence is a deletion, not a crash.
            raise StartupStop("run_json_missing", None, "CK5")
        elif checkpointed:
            authority = "rollback"  # A8: an older runtime rewrote run.json after our checkpoint
        else:
            # This lineage never reached its first CK5: our own first run was
            # interrupted (A13), whatever run.json still says.
            authority = "unpublished"
            lineage = _segment_lineage(segments)
        return self._recover(scan, lineage, authority)

    def _settle_empty_ledger(self, scan: cp.LedgerScan) -> None:
        """No valid record at all: only a torn first header (TC1) carries no effect and is set aside."""
        tail = cp.classify_tail(scan)
        plan = cp.plan_recovery(scan, tail, read_blob=lambda _sha: None)
        if plan.action == "stop":
            raise StartupStop(plan.stop_reason, {"damaged_at": tail.damaged_at, "bytes": tail.length}, "A2")
        if scan.tail:
            result = cp.quarantine_tail(self.session_dir, scan, plan, self.quarantine, ops=self.ops)
            if not result.applied:
                raise StartupStop(result.stop_reason, {"bytes": len(scan.tail)}, write=False)

    def _verify_carrier(self, carrier: dict) -> Witnessed:
        """SV-023: a witnessed carrier grants nothing unless the store is still what was acknowledged.

        Verified over the records up to the witnessed end; anything after it
        must be this same transaction's own prefix. Otherwise stop
        `acknowledgement_unverified` (no resolution), with only STOPPED
        written. On success session/ is fenced: the carrier's name and
        STOPPED's removal are durable before any record depends on them.
        """
        problem = carrier_problem(carrier)
        if problem:
            raise StartupStop("acknowledgement_unverified", {"problem": f"carrier: {problem}"}, "ACK")
        receipt = receipt_payload(carrier)
        try:
            verified = witnessed_evidence(self.session_dir, carrier["witness"], self.ops, receipt=receipt)
        except AcknowledgementRefused as refusal:
            raise StartupStop("acknowledgement_unverified", {"ack_id": carrier["ack_id"], "problem": str(refusal)[:300]}, "ACK") from refusal
        if verified.evidence != carrier["evidence"]:
            raise StartupStop("acknowledgement_unverified", {"ack_id": carrier["ack_id"], "problem": "the evidence changed"}, "ACK")
        _fence_session(self.session_dir, self.ops)
        return Witnessed(carrier, receipt, verified.written)

    def _verify_preserving(self, carrier: dict) -> Preserving:
        """SV-028 B0: grants nothing unless the sealed set, the stop it binds and the witnessed store still verify.

        On success session/ is fenced (the carrier's name and STOPPED's removal
        are durable before any record depends on them), and the frozen plan Π
        is kept for `_recover`: it is never re-derived from a replay that
        applied this transaction's own records.
        """
        try:
            verified = preserving_verification(self.session_dir, carrier, self.ops)
        except AcknowledgementRefused as refusal:
            raise StartupStop("acknowledgement_unverified", {"ack_id": carrier["ack_id"], "problem": str(refusal)[:300]}, "ACK") from refusal
        _fence_session(self.session_dir, self.ops)
        self.witnessed = Witnessed(carrier, verified.receipt, verified.written)
        return verified

    def _preserving_decision(self, preserving: Preserving, p0, extra, scan0, plan, fetch_blob):
        """The BP decision: replay from C_n's state through the neutral suffix and the owned prefix, each once.

        core = Π[k:] + T, where k counts the owned records already in p0 and T
        is the recovery record of this start's (or the frozen intent's)
        original torn own frame. The carrier-free route writes nothing: its
        extras must already be the whole core, and the live file absent.
        """
        own = [record for record in p0 if record.seq > preserving.witness_end and record.type_name != "LEDGER_HEADER"]
        planned = list(preserving.plan)
        if len(own) > len(planned) or not all(_same_record(record, item) for record, item in zip(own, planned)):
            raise StartupStop("recovery_intent_mismatch", {"problem": "the owned records are not the frozen plan's prefix"}, "intent")
        covers = preserving.newest.payload["covers_seq"]
        suffix = [record for record in p0 if record.seq > covers]
        replay = Replay([], preserving.state0.copy(), fetch_blob=fetch_blob)
        try:
            for record in suffix:
                replay.apply(record)
        except ReplayMismatch as error:
            raise StartupStop("replay_mismatch", {"error": str(error)[:200]}) from error
        tail_records = []
        if scan0.tail:
            tail_sha = sha256(scan0.tail)
            tail_records = [
                ("RECOVERY", {"kind": item["kind"], "detail": {**item["detail"], "tail_sha256": tail_sha}})
                for item in plan.recovery_records
                if item["kind"] != "possible_duplicate_spend"
            ]
        core = [*planned[len(own):], *tail_records]
        if preserving.carrier is None:
            if len(extra) != len(core) or not all(_same_record(record, item) for record, item in zip(extra, core)):
                raise StartupStop("recovery_intent_mismatch", {"problem": "a retired activation must already be complete"}, "intent")
            if os.path.lexists(self.session_dir / "conversation.json"):
                raise StartupStop("recovery_intent_mismatch", {"problem": "the conversation is present after a retired activation"}, "intent")
        checkpoints = [record for record in p0 if record.type_name == "CHECKPOINT"]
        collected = max((r.payload["records_through"] for r in p0 if r.type_name == "GC_INTENT"), default=0)
        known = {r.payload["conv"]["sha256"]: checkpoint_tuple(r) for r in checkpoints if r.seq > collected}
        decision = _Decision("BP", replay, FileState("absent"), preserving.newest, suffix, known)
        decision.preserving = preserving
        return decision, core

    def _establish_owned_durability(self, session: Session, preserving: Preserving) -> None:
        """B3 (SV028-01): every segment from the witnessed end through the active one, then ledger/.

        Runs even when this start wrote nothing: an activation an earlier
        process wrote may be readable while its fsync never returned. Only
        after this returns may the live conversation be removed. A failure
        takes the session's persistence boundary; the conversation is untouched.
        """
        ledger = self.session_dir / "ledger"
        try:
            for number in range(preserving.witness_segment, session.writer.segment_no + 1):
                path = ledger / cp.segment_name(number)
                if path.exists():
                    _fsync_file(path, self.ops)
            self.ops.sync_dir(str(ledger))
        except OSError as error:
            session._fail(error)

    def _complete_preserving(self, session: Session, preserving: Preserving) -> None:
        """B3, then B4: the preserved unreadable file's name is removed and session/ fenced (or an absence fenced)."""
        self._establish_owned_durability(session, preserving)
        path = self.session_dir / "conversation.json"
        if os.path.lexists(path):
            status, data = _read(self.ops, path, CONVERSATION_READ_MAX)
            if status != "ok" or sha256(data) != preserving.evidence["conv_sha256"]:
                raise StartupStop(
                    "acknowledgement_unverified", {"problem": "conversation_changed: the live conversation is not the preserved one"}, "ACK"
                )
            try:
                self.ops.unlink(str(path))
                self.ops.sync_dir(str(self.session_dir))
            except OSError as error:
                session._fail(error)
        else:
            try:
                self.ops.sync_dir(str(self.session_dir))
            except OSError as error:
                session._fail(error)

    def _witness(self, reason: str, scan, lineage) -> dict | None:
        """A stop's detail carrying its witness, or None (the stop as before, ineligible)."""
        witness = stop_witness(self.session_dir, reason, scan, lineage, self.ops)
        return {"witness": witness} if witness is not None else None

    def _new_session(self, lineage: str) -> Session:
        return Session.start_fresh(self.session_dir, self.home_dir, lineage, ops=self.ops, lifecycle=self.lifecycle, **self.session_kwargs)

    def _start_legacy(self) -> Opening:
        """A4 absent / A5 legacy list / A6 corrupt legacy: the only paths that create a lineage."""
        conv = read_conversation(self.session_dir / "conversation.json", self.ops)
        if conv.status == "unreadable":
            if conv.data is not None:
                _quarantine_file(self.session_dir, "legacy-conversation", conv.data, self.quarantine, self.ops)
            raise StartupStop("legacy_conversation_unreadable", {"bytes": len(conv.data or b"")}, "A6")
        lineage = (self.meta or {}).get("lineage_id")
        if not (isinstance(lineage, str) and LINEAGE_ID.fullmatch(lineage)):
            lineage = self.new_lineage() if self.new_lineage else sha256(self.session_dir.as_posix().encode())[:16]
            self.lifecycle("lineage_started", lineage_id=lineage)
        session = self._new_session(lineage)
        messages, folded = [], 0
        if conv.status == "ok":
            legacy_folded = (self.meta or {}).get("recap_folded", 0)
            legacy_folded = legacy_folded if rp.counter(legacy_folded) else 0
            messages, folded = self.repair(conv.messages, legacy_folded)
            folded = min(folded, len(messages))
        legacy, note_text = self._legacy_note(messages)
        payload = {"conv_sha": conv.sha, "recap_folded": folded, "legacy": legacy}
        if note_text is not None:
            # SV021-03: the unadopted legacy note is a pending generation of
            # this same record (its blob durable first), so "processed" is
            # never durable without the obligation to adopt it.
            stored, _info = envelope.truncate_marked(note_text, session.caps.note)
            note_blob = stored.encode("utf-8")
            key = session._put_blob(note_blob)
            payload["note"] = {
                "gen": session.state.notes_next_gen, "blob": key, "bytes": len(note_blob),
                "sha256": key, "mirror_sha256": legacy["handoff_sha256"],
            }
        if conv.status == "ok":
            data = rp.conversation_bytes(messages)
            session._commit("LEGACY_IMPORT", lambda blob: {**payload, "blob": blob}, blob=data)
        else:
            session._commit("LEGACY_IMPORT", payload)
        self._consume_ack(session)
        session.unit_end()  # SV026/SV027: the import is a closed unit -- threshold, or rotate a full segment
        classification = "A5" if conv.status == "ok" else "A4"
        return Opening(classification, session, had_memory=bool(messages) or note_text is not None)

    def _legacy_note(self, messages: list) -> tuple[dict, str | None]:
        """D13 2.2.5 rule 5: matched (not re-appended) or unadopted-unproven (adopted once)."""
        status, data = _read(self.ops, self.home_dir / "HANDOFF.md", LEGACY_HANDOFF_READ_MAX)
        if status != "ok" or not data:
            return {"status": "none", "handoff_sha256": None}, None
        text = data.decode("utf-8", "ignore")  # exactly what the legacy runtime appended
        if not text:
            return {"status": "none", "handoff_sha256": None}, None
        wanted = rp.NOTE_PREFIX + text
        if any(m.get("role") == "user" and m.get("content") == wanted for m in messages):
            return {"status": "legacy_matched_unproven", "handoff_sha256": sha256(data)}, None
        return {"status": "legacy_unadopted_unproven", "handoff_sha256": sha256(data)}, text

    # -- A8..A15 and the recovery transaction ---------------------------------------
    def _recover(self, scan: cp.LedgerScan, lineage: str, authority: str) -> Opening:
        format2 = authority != "rollback"
        ops, session_dir = self.ops, self.session_dir
        blobs = cp.BlobStore(session_dir / "blobs", ops=ops)
        read_blob = lambda sha: blobs.get(sha, BLOB_READ_MAX)  # noqa: E731 -- planning reads: not replay work
        # SV026: the selected replay's reads, each reporting what it obtained.
        fetch_blob = lambda sha: blobs.fetch(sha, BLOB_READ_MAX)  # noqa: E731
        intent_status, intent = _read_json_object(ops, session_dir / RECOVERING, cp.MAX_MARKER_READ)
        if intent_status == "unreadable":
            raise StartupStop("recovery_intent_unreadable", None, "intent")
        ack = self.ack
        live = read_identity(session_dir, lineage, ops)  # checked allocation high-water, or None
        identity = live  # the reservation the outcome is derived from
        if intent is not None:
            # SV021-08: the frozen transaction input is validated as a whole
            # (schema, domains, checksum, lineage) before any of it is used.
            intent = _validated_intent(intent, lineage)
            p0, extra, original_tail = self._from_intent(scan, intent)
            ack = intent["ack"]
            # Re-deriving the already-started outcome uses the frozen value;
            # the live reservation can only have stayed equal (nothing reserves
            # while an intent is pending) -- a lower live value is not
            # reconcilable and stops.
            identity = intent["identity_reserved"]
            if live is not None and identity is not None and live < identity:
                raise StartupStop("identity_inconsistent", {"live": live, "frozen": identity}, "intent")
            scan0 = cp.LedgerScan(p0, p0[-1].seq, p0[-1].chain, original_tail, intent["segment"], intent["offset"])
        else:
            p0, extra, scan0 = scan.records, (), scan
        # SV023-03: the witnessed transaction's receipt and end, from its carrier
        # or, once the carrier is retired, from the intent that carries them.
        context = intent.get("witnessed") if intent is not None else None
        if self.witnessed is not None:
            receipt, witness_end = self.witnessed.receipt, self.witnessed.carrier["witness"]["ledger"]["last_seq"]
        elif context is not None:
            receipt, witness_end = context["receipt"], context["after_seq"]
        else:
            receipt = witness_end = None
        # SV-028: the frozen plan, from B0 (carrier) or authenticated from the sealed context (carrier-free).
        preserving = self.preserving
        if preserving is None and context is not None and (context["receipt"]["reason"], context["receipt"]["resolution"]) in PRESERVING_RESOLUTIONS:
            preserving = preserving_from_context(p0, context, lineage, read_blob)
        # What IDENTITY is carried forward as: never below either checked value.
        high_water = max((v for v in (live, identity) if v is not None), default=None)
        tail_ack = ack if ack and ack.get("reason") == "ledger_tail_ambiguous" else None
        tail = cp.classify_tail(scan0)
        if tail_ack is not None and intent is None:
            # SV023-04/-05: whether this permission was already used is decided by
            # its exact recorded receipt (bound to its own tail), whatever the
            # tail is now. Used: it is never applied to another tail; only its
            # carrier is left to retire. Unused: it applies only to its own
            # acknowledged bytes. A different tail that would continue under it
            # (TC0-TC2) is refused before any change; one that stops anyway (TC3,
            # A2, another TC4) keeps its own ordinary stop, unacknowledged.
            if any(r.type_name == "RECOVERY_ACK" and r.payload == _wire(tail_ack) for r in p0):
                tail_ack = None
            elif not (scan0.tail and sha256(scan0.tail) == tail_ack["tail_sha256"]):
                if tail.kind in ("TC0", "TC1", "TC2"):
                    raise StartupStop("acknowledgement_unverified", {"ack_id": tail_ack["ack_id"], "problem": "the acknowledged tail is not the ledger's"}, "ACK")
                tail_ack = None
        plan = cp.plan_recovery(scan0, tail, read_blob=read_blob, acknowledgement=tail_ack)
        if plan.action == "stop":
            if plan.stop_reason == "ledger_tail_ambiguous":
                raise StartupStop("ledger_tail_ambiguous", cp.tail_stop_detail(scan0.tail), "TC4")
            raise StartupStop(plan.stop_reason, {"damaged_at": tail.damaged_at}, "A2")
        if authority == "format2":
            covers = (self.meta.get("checkpoint") or {}).get("covers_seq") if isinstance(self.meta.get("checkpoint"), dict) else None
            if self.meta.get("checkpoint") is not None and not rp.counter(covers):
                raise StartupStop("run_json_unreadable", {"field": "checkpoint"}, "CK5")
            if covers is not None and covers > scan0.last_seq:
                raise StartupStop("checkpoint_ahead_of_ledger", {"covers_seq": covers, "last_seq": scan0.last_seq}, "A15")

        if tail.kind == "TC4" and identity is None:
            # SV021-01: hidden records may hold requests under any turn; only a
            # valid reservation bounds them. Without one, nothing is changed and
            # no new identity is issued.
            raise StartupStop("identity_unproven", {"tail_sha256": sha256(scan0.tail)}, "TC4")

        # SV-022: a shortened ledger only as collection left it, and a pending
        # intent only as authority it still is -- both checked before anything
        # is written, copied, truncated or removed.
        missing = gc.unauthorized_prefix(p0)
        if missing is not None:
            raise StartupStop("ledger_prefix_missing", {"oldest_segment": missing}, "A2")
        collecting = self._pending_collection(p0)
        # SV-023: only a strictly clean end with no transaction of its own can witness an A14 stop.
        self.clean_end = scan0 if intent is None and tail.kind == "TC0" and collecting is None else None

        if preserving is not None:
            # SV-028: core = Π[k:] + T; never derive_core over a replay that applied owned records.
            decision, core = self._preserving_decision(preserving, p0, extra, scan0, plan, fetch_blob)
        else:
            decision = self._classify_base(p0, extra, format2, lineage, read_blob, fetch_blob=fetch_blob)
            if self.witnessed is not None and decision.case not in ("A9", "A9t"):
                raise StartupStop("acknowledgement_unverified", {"problem": f"classified {decision.case}"}, "ACK")
            try:
                core = derive_core(decision.replay, plan, tail, scan0, tail_ack, lineage, identity_reserved=identity)
            except ReplayMismatch as error:
                raise StartupStop("replay_mismatch", {"error": str(error)[:200]}) from error
            if decision.adopt is not None:
                # A10: bind the file as the base it equals, before anything follows it.
                core = [decision.adopt, *core]
            if collecting is not None:
                # The pending collection completes first: GC_DONE immediately
                # follows its intent, before any record (or blob) of this start.
                core = [("GC_DONE", {"intent_seq": collecting.seq}), *core]
            if receipt is not None and not any(r.seq > witness_end and _same_record(r, ("RECOVERY_ACK", receipt)) for r in p0):
                # SV-023: the receipt is this transaction's first record, before any closure.
                core = [("RECOVERY_ACK", receipt), *core]

        # Set the tail aside only under a durable intent (see the module docstring).
        if scan0.tail and intent is None:
            if tail_ack is not None and tail_ack.get("tail_sha256") != sha256(scan0.tail):
                # SV023-05: an intent's acknowledgement is always for that intent's own tail.
                raise SessionInvariant("a recovery intent whose acknowledgement names another tail")
            body = {
                "lineage_id": lineage, "last_seq": scan0.last_seq, "chain": scan0.last_chain,
                "segment": scan0.tail_segment, "offset": scan0.tail_offset,
                "tail_sha256": sha256(scan0.tail), "tail_bytes": len(scan0.tail), "ack": tail_ack,
                "identity_reserved": identity,
            }
            if receipt is not None:
                # SV023-03: the witnessed context outlives the carrier, sealed with
                # the rest, so the whole core (receipt first) is re-derived alike.
                body["witnessed"] = {"ack_id": receipt["ack_id"], "receipt": receipt, "after_seq": witness_end}
                if preserving is not None:
                    # SV-028: enough to authenticate Π against the ledger head with no carrier.
                    body["witnessed"]["evidence"] = preserving.evidence
            intent = _sealed_intent(body)
            # SV024-02: what the intent names -- its anchor and the exact tail --
            # is durable before the intent, so no host loss can leave the intent
            # without both its original bytes and its copy.
            _fence_intent_inputs(session_dir, scan0, ops)
            cp.write_bytes_durable(session_dir / RECOVERING, json.dumps(intent, sort_keys=True).encode(), ops=ops)
        if scan0.tail and scan.records[-1].seq == scan0.last_seq and scan.tail == scan0.tail:
            result = cp.quarantine_tail(session_dir, scan, plan, self.quarantine, ops=ops)
            if not result.applied:
                raise StartupStop(result.stop_reason, {"bytes": len(scan.tail)}, write=False)
        now = cp.scan_segments(cp.read_segments(session_dir / "ledger", ops=ops), lineage)
        if now.tail and intent is not None:
            # A torn record of this recovery's own: it carries no effect.
            own = cp.plan_recovery(now, cp.classify_tail(now), read_blob=read_blob)
            if own.action != "continue" or own.tail.kind not in ("TC1", "TC2"):
                raise StartupStop("recovery_intent_damaged", {"bytes": len(now.tail)}, "intent")
            result = cp.quarantine_tail(session_dir, now, own, self.quarantine, ops=ops)
            if not result.applied:
                raise StartupStop(result.stop_reason, {"bytes": len(now.tail)}, write=False)
            now = cp.scan_segments(cp.read_segments(session_dir / "ledger", ops=ops), lineage)
        if now.tail or now.stop:
            raise StartupStop("ledger_changed_during_recovery", None, "intent")
        extra = tuple(record for record in now.records if record.seq > p0[-1].seq)

        writer = cp.LedgerWriter.continue_after(session_dir, lineage, now, ops=ops)
        replay = decision.replay
        for index, record in enumerate(extra):
            if index < len(core) and not _same_record(record, core[index]):
                raise StartupStop("recovery_intent_mismatch", {"seq": record.seq}, "intent")
            try:
                replay.apply(record)
            except ReplayMismatch as error:
                raise StartupStop("replay_mismatch", {"seq": record.seq, "error": str(error)[:200]}) from error
        if receipt is not None and len(extra) > len(core):
            # SV023-03: a witnessed recovery writes exactly its core; nothing more is its own.
            raise StartupStop("recovery_intent_mismatch", {"seq": extra[len(core)].seq}, "intent")
        if collecting is not None and not extra:
            # The intent's own fixed list, re-run idempotently -- never a fresh
            # scan -- before this start can write a blob. (With `extra`, its
            # GC_DONE, compared above, is already durable.) First its own
            # segment is synced (SV022-01): readable is not durable.
            gc.sync_intent(session_dir, collecting, ops)
            gc.unlink_intent(session_dir, collecting.payload, ops)
        session = Session(
            session_dir, self.home_dir, writer, replay, ops=ops, lifecycle=self.lifecycle,
            checkpoints=decision.checkpoints, identity_reserved=high_water, **self.session_kwargs,
        )
        # SV026: the work of the selected replay -- the suffix after its origin
        # and this transaction's readable extras -- added to any reuse header
        # the session already claimed; each record committed below adds its own.
        session.since_records += replay.work_records
        session.since_bytes += replay.work_bytes
        session.since_unmeasured += replay.work_unmeasured
        for type_name, payload in core[len(extra):]:
            if type_name == "ADOPT":
                data = payload
                session._commit(
                    "RECOVERY",
                    lambda blob: {"kind": "conversation_adopted", "detail": {"conv_sha": sha256(data), "blob": blob}},
                    blob=data,
                )
            else:
                session._commit(type_name, payload)
        after_core = extra[len(core):]
        self._finish_case(session, decision, plan, core, after_core)
        if intent is not None:
            # Records an earlier start wrote under this intent were read here,
            # not necessarily synced: durable before the intent can go (SV023-04).
            for record in {r.segment: r for r in extra}.values():
                _sync_record(session_dir, record, ops)
        if receipt is not None:
            # SV023-03: the carrier first, then the intent. A surviving intent
            # still holds the witnessed context; with neither, all is done.
            self._consume_ack(session)
            _remove(session_dir, RECOVERING, ops)
        else:
            _remove(session_dir, RECOVERING, ops)
            self._consume_ack(session)
        # SV021-01: the reservation now covers every turn this ledger used and
        # the next one, durably, before the duty can cause any request.
        used = [r.payload["turn_seq"] for r in now.records if r.type_name == "REQUEST_SENT"]
        target = max([*used, session.state.requests_next["turn_seq"], high_water or 0])
        session.identity_reserved = live  # what the file actually holds: rewrite it if missing or lower
        session.reserve_turns(target, exact=True)
        # SV026/SV027: the startup transaction is one closed unit. Only now --
        # after the extras' syncs, the carrier and RECOVERING retired durably,
        # and IDENTITY covering every used turn -- may its threshold checkpoint
        # or the rotation of a full inherited segment be written: under an
        # intent either would be an unplanned extra.
        session.unit_end()
        had_memory = bool(session.messages) or bool(session.state.notes_pending)
        return Opening(decision.case, session, had_memory=had_memory)

    def _pending_collection(self, p0):
        """The pending GC_INTENT that ends P and is still deletion authority, or None.

        It must be P's last record (GC_DONE always follows its intent first)
        and pass the same validation as when it was written, over the
        retained records. Otherwise stop with nothing removed.
        """
        try:
            pending = gc.pending_intent(p0)
        except gc.GCRefused as refusal:
            raise StartupStop("gc_intent_invalid", {"problem": refusal.reason}, "GC") from refusal
        if pending is None:
            return None
        if pending.seq != p0[-1].seq:
            problem = "records follow the pending intent"
        else:
            problem = gc.intent_problem(pending.payload, p0, intent_seq=pending.seq)
        if problem:
            raise StartupStop("gc_intent_invalid", {"seq": pending.seq, "problem": problem}, "GC")
        return pending

    def _from_intent(self, scan: cp.LedgerScan, intent: dict):
        """The prefix the intent names, the records written after it, and its original tail."""
        last = intent.get("last_seq")
        by_seq = {record.seq: record for record in scan.records}
        anchor = by_seq.get(last)
        if anchor is None or anchor.chain != intent.get("chain") or intent.get("lineage_id") is None:
            raise StartupStop("recovery_intent_mismatch", {"last_seq": last}, "intent")
        p0 = tuple(record for record in scan.records if record.seq <= last)
        extra = tuple(record for record in scan.records if record.seq > last)
        if not extra and scan.tail and sha256(scan.tail) == intent["tail_sha256"] and scan.tail_offset == intent["offset"]:
            return p0, extra, scan.tail
        name = f"ledger-{intent['segment']:06d}-{intent['offset']}-{intent['tail_sha256'][:16]}.bin"
        status, data = _read(self.ops, Path(self.quarantine.corrupt_dir) / name, intent["tail_bytes"])
        if status != "ok" or sha256(data) != intent["tail_sha256"]:
            raise StartupStop("recovery_intent_copy_missing", {"copy": name}, "intent")
        return p0, extra, data

    # -- base classification (A8-A14) ------------------------------------------------
    def _classify_base(self, p0, extra, format2: bool, lineage: str, read_blob, *, fetch_blob=None) -> _Decision:
        """The base decision and its one selected replay.

        `read_blob(sha) -> bytes | None` is the accepted reader. With
        `fetch_blob` (SV026, recovery's own call) every candidate replay reads
        through it instead, so the selected one reports the work it did.
        """
        reader = {"fetch_blob": fetch_blob} if fetch_blob is not None else {"read_blob": read_blob}
        session_dir = self.session_dir
        conv = read_conversation(session_dir / "conversation.json", self.ops)
        prev = read_conversation(session_dir / "conversation.prev.json", self.ops)
        checkpoints = [record for record in p0 if record.type_name == "CHECKPOINT"]
        newest = checkpoints[-1] if checkpoints else None
        covers = newest.payload["covers_seq"] if newest else 0
        suffix = [record for record in p0 if record.seq > covers]
        strict = None
        newest_bytes = None  # C_n's exact bytes, when some file or the previous base yields them
        try:
            if newest is None:
                strict = _replay([], SessionState(lineage), p0, **reader)
                state_n = None
            else:
                state_n = SessionState.from_wire(newest.payload["state"])
                base = next((f for f in (conv, prev) if f.status == "ok" and f.sha == newest.payload["conv"]["sha256"]), None)
                if base is not None:
                    newest_bytes = base.data
                    strict = _replay(json.loads(base.data), state_n.copy(), suffix, **reader)
                else:
                    strict, newest_bytes = self._previous_base(p0, newest, state_n, (conv, prev), suffix, reader)
        except rp.StateError as error:
            raise StartupStop("checkpoint_state_invalid", {"error": str(error)[:200]}) from error
        except ReplayMismatch as error:
            raise StartupStop("replay_mismatch", {"error": str(error)[:200]}) from error

        def lenient() -> Replay:
            try:
                return _replay([], state_n.copy(), suffix, lenient=True, **reader)
            except ReplayMismatch as error:
                raise StartupStop("replay_mismatch", {"error": str(error)[:200]}) from error

        # SV021-04/-05: the file's authority is decided by the latest
        # transition that bound it -- the newest CHECKPOINT, or a later
        # import/edit/reimport/deletion/adoption, including one this recovery
        # already wrote (`extra`). A file matching it is never adopted again;
        # anything else is a new edit or deletion, even if it matches an
        # older source.
        kind, bound, binder = _binding([*p0, *extra], newest)
        carried = binder is not None and binder in extra and binder.type_name in (*SWITCH_TYPES, "EXTERNAL_DELETE")
        # SV-022: a checkpoint at or below any collection's floor may have lost
        # interval records or blobs, so it is never offered as a later `prev`.
        collected = max((r.payload["records_through"] for r in p0 if r.type_name == "GC_INTENT"), default=0)
        known = {r.payload["conv"]["sha256"]: checkpoint_tuple(r) for r in checkpoints if r.seq > collected}
        decision = _Decision("", strict, conv, newest, suffix, known, carried=carried, kind=kind, bound=bound)
        if not format2:
            consumed = kind not in ("checkpoint", "start") and (
                (conv.status == "ok" and conv.sha == bound) or (conv.status == "absent" and bound is None)
            )
            decision.case = "A8t" if consumed else "A8"
            if decision.case == "A8" and conv.status == "unreadable":
                if conv.data is not None:
                    _quarantine_file(session_dir, "legacy-conversation", conv.data, self.quarantine, self.ops)
                raise StartupStop("legacy_conversation_unreadable", {"bytes": len(conv.data or b"")}, "A8")
        elif conv.status == "ok":
            if bound is not None and conv.sha == bound:
                decision.case = "A9" if kind == "checkpoint" else "A9t"
                if kind == "adopted" and binder in extra:
                    decision.adopt = ("ADOPT", None)  # already written first by this recovery
            elif strict is not None and conv.data == rp.conversation_bytes(strict.messages):
                # A10: the file is this replay (a checkpoint died after CK4).
                # Bound by a durable adoption, so later records cannot make it
                # look like an edit.
                decision.case = "A10"
                decision.adopt = ("ADOPT", conv.data)
            else:
                decision.case = "A11"
        elif conv.status == "absent":
            if bound is None:
                decision.case = "A13" if newest is None and kind in ("start", "LEGACY_IMPORT") else "A12t"
            else:
                decision.case = "A12"
        else:
            if strict is None or (newest is not None and newest_bytes is None):
                witness = self._witness("conversation_unreadable_unbound", self.clean_end, lineage)
                raise StartupStop("conversation_unreadable_unbound", witness, "A14")
            decision.case = "A14"
            # SV021-02: put the newest checkpoint's own (verified) bytes back,
            # so the file is bound again and .prev.json keeps its base; before
            # any checkpoint there is no such snapshot, only the replay.
            decision.restore = newest_bytes
        if decision.replay is None:
            decision.replay = lenient()
        return decision

    def _previous_base(self, p0, newest, state_n: SessionState, files, suffix, reader: dict):
        """A14's previous base (v2 1.4.4): replay through C_n, verify its hash, then the suffix.

        Returns (replay, C_n's bytes) or (None, None) when no file holds the named previous base.
        The interval runs on its own instance (`middle`); the returned replay
        holds only the suffix's work, the interval the newest threshold governs (SV026).
        """
        prev_info = newest.payload["prev"]
        if not prev_info:
            return None, None
        base = next((f for f in files if f.status == "ok" and f.sha == prev_info["conv_sha256"]), None)
        older = next((r for r in p0 if r.seq == prev_info["checkpoint_seq"] and r.type_name == "CHECKPOINT"), None)
        if base is None or older is None:
            return None, None
        state_p = SessionState.from_wire(older.payload["state"])
        interval = [r for r in p0 if prev_info["covers_seq"] < r.seq <= newest.payload["covers_seq"]]
        middle = _replay(json.loads(base.data), state_p, interval, **reader)
        middle_bytes = rp.conversation_bytes(middle.messages)
        if sha256(middle_bytes) != newest.payload["conv"]["sha256"]:
            raise StartupStop("replay_mismatch", {"at": newest.payload["covers_seq"]}, "A14")
        replay = Replay(middle.messages, state_n.copy(), **reader)
        for record in suffix:
            replay.apply(record)
        return replay, middle_bytes

    def _finish_case(self, session: Session, decision: _Decision, plan: cp.RecoveryPlan, core, after_core) -> None:
        """The base decision's records, then any recovery notices not yet durable."""
        if decision.case == "BP":
            self._complete_preserving(session, decision.preserving)
            return
        notices = list(plan.notices)
        case = decision.case
        state = session.state
        if case in ("A11", "A8"):
            conv = decision.conv
            if conv.status == "ok":
                folded_in = state.recap_folded if case == "A11" else (self.meta or {}).get("recap_folded", 0)
                folded_in = folded_in if rp.counter(folded_in) else 0
                messages, folded = self.repair(conv.messages, min(folded_in, len(conv.messages)))
                folded = min(folded, len(messages))
            else:
                messages, folded = [], 0
            entries = [(r.type_name, r.payload, r.seq) for r in decision.suffix]
            unmerged = _unmerged_notice(entries + [(name, payload, None) for name, payload in core])
            payload = {"epoch": state.history_epoch + 1, "conv_sha": conv.sha, "recap_folded": folded,
                       "notices": notices + ([unmerged[2]] if unmerged else [])}
            name = "EXTERNAL_EDIT" if case == "A11" else "LEGACY_REIMPORT"
            if case == "A8":
                payload["unmerged_suffix"] = [unmerged[0], unmerged[1]] if unmerged else None
                # SV021-10: the pending generations this original list already
                # shows, recorded with the reimport itself (not re-derived later
                # from whatever the list then holds).
                shown = {m.get("content") for m in messages if m.get("role") == "user"}
                foreign = []
                for entry in state.notes_pending:
                    data = session.read_blob(entry["blob"])
                    if data is not None and rp.NOTE_PREFIX + data.decode("utf-8") in shown:
                        foreign.append(entry["gen"])
                payload["foreign_gens"] = foreign
            if messages:
                data = rp.conversation_bytes(messages)
                session._commit(name, lambda blob: {**payload, "blob": blob}, blob=data)
            else:
                session._commit(name, payload)
            return
        if case == "A12":
            session._commit("EXTERNAL_DELETE", {"epoch": state.history_epoch + 1, "notices": notices})
            return
        if decision.carried:
            return  # the switch this recovery already wrote carried its notices
        if case == "A14":
            _quarantine_file(self.session_dir, "conversation", decision.conv.data or b"", self.quarantine, self.ops)
            if not any(r.type_name == "MSG_APPEND" and r.payload.get("text") == A14_NOTICE for r in decision.suffix):
                notices.append(A14_NOTICE)  # once per newest checkpoint, however often the start repeats
        written = 0
        for record in after_core:
            if record.type_name == "MSG_APPEND" and written < len(notices) and record.payload.get("text") == notices[written]:
                written += 1
        for text in notices[written:]:
            session._append("notice", text)
        if case == "A14":
            # Replace the unreadable file without rotating it into
            # conversation.prev.json, which still holds a bound base: with the
            # newest checkpoint's own bytes (the suffix replays on top), or,
            # before any checkpoint, with the replay.
            data = decision.restore if decision.restore is not None else rp.conversation_bytes(session.messages)
            # SV021-09: the runtime-installed file is the source binding from
            # now on -- recorded first, so a crash before the bytes land
            # re-enters A14 (still unreadable) and finds it already recorded.
            # It binds the file only; the logical conversation is unchanged.
            if not (decision.kind == "restored" and decision.bound == sha256(data)):
                session._commit("RECOVERY", {"kind": "conversation_restored", "detail": {"conv_sha": sha256(data)}})
            try:
                cp.write_bytes_durable(self.session_dir / "conversation.json", data, ops=self.ops)
            except cp.PersistenceFailure as error:
                session._fail(error)

    def _consume_ack(self, session: Session) -> None:
        """Transcribe the acknowledgement as RECOVERY_ACK once, make that receipt durable, then remove ACKNOWLEDGED.

        For every implemented pair (SV023-04), the carrier is retired only over
        exactly one receipt that matches it: reason, resolution and ack_id,
        plus, for TC4, the tail it was bound to (a witnessed receipt: its
        stop and evidence). The receipt's own segment is synced first, because
        it may be an earlier start's append that is readable but was never
        synced. A failed sync is a persistence failure, and the carrier stays.
        A TC4 receipt comes with its tail's recovery (`derive_core`); until it
        exists there is nothing to retire.
        """
        ack = self.ack
        if ack is None:
            return
        wanted = _wire(self.witnessed.receipt if self.witnessed is not None else ack)

        def matching() -> list:
            ledger = cp.scan_segments(cp.read_segments(self.session_dir / "ledger", ops=self.ops), session.lineage_id)
            return [r for r in ledger.records if r.type_name == "RECOVERY_ACK" and r.payload == wanted]

        found = matching()
        if not found and self.witnessed is None and ack["reason"] != "ledger_tail_ambiguous":
            session._commit("RECOVERY_ACK", wanted)
            found = matching()
        if not found:
            return
        if len(found) != 1:
            raise SessionInvariant(f"the acknowledgement receipt is recorded {len(found)} times, not once")
        _sync_record(self.session_dir, found[0], self.ops)
        _remove(self.session_dir, ACKNOWLEDGED, self.ops)


@dataclass
class _Decision:
    case: str
    replay: Replay | None
    conv: FileState
    newest: object
    suffix: list
    checkpoints: dict  # conversation sha -> the `prev` tuple of its newest CHECKPOINT
    carried: bool = False  # the binding switch is this recovery's own and carried its notices
    adopt: tuple | None = None  # A10: ("ADOPT", file bytes), written before the core
    restore: bytes | None = None  # A14: the newest checkpoint's bytes
    kind: str = ""  # the latest binding transition's kind and its file hash (None: absent)
    bound: str | None = None
    preserving: object = None  # SV-028: the BP decision's frozen plan


def _binding(records, newest):
    """(kind, bound sha or None for an absent file, the binding record) after the newest checkpoint."""
    covers = newest.payload["covers_seq"] if newest is not None else 0
    if newest is not None:
        kind, bound, binder = "checkpoint", newest.payload["conv"]["sha256"], newest
    else:
        kind, bound, binder = "start", None, None
    for record in records:
        if record.seq <= covers:
            continue
        name, payload = record.type_name, record.payload
        if name in SWITCH_TYPES:
            kind, bound, binder = name, payload.get("conv_sha"), record
        elif name == "EXTERNAL_DELETE":
            kind, bound, binder = name, None, record
        elif name == "RECOVERY" and payload.get("kind") == "conversation_adopted":
            kind, bound, binder = "adopted", payload["detail"].get("conv_sha"), record
        elif name == "RECOVERY" and payload.get("kind") == "conversation_restored":
            kind, bound, binder = "restored", payload["detail"].get("conv_sha"), record
    return kind, bound, binder


def _same_record(record, planned) -> bool:
    """Whether a record written after an intent is the planned one (an adoption by kind only)."""
    name, payload = planned
    if name == "ADOPT":
        return record.type_name == "RECOVERY" and record.payload.get("kind") == "conversation_adopted"
    return (record.type_name, record.payload) == (name, _wire(payload))


INTENT_KEYS = frozenset(
    {"lineage_id", "last_seq", "chain", "segment", "offset", "tail_sha256", "tail_bytes", "ack", "identity_reserved", "check"}
)


def _intent_check(body: dict) -> str:
    return sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())


def _sealed_intent(body: dict) -> dict:
    """RECOVERING's content with a SHA-256 over every other field (SV021-08)."""
    return {**body, "check": _intent_check(body)}


def _validated_intent(intent: dict, lineage: str) -> dict:
    """The frozen transaction input, or a stop before anything is used, copied or truncated.

    Every field is checked for its domain, and the checksum binds them all --
    the lineage, the prefix anchor (seq and chain), the original tail's place,
    size and hash, the acknowledgement and the reservation the outcome was
    derived from.
    """

    def bad(why: str):
        raise StartupStop("recovery_intent_invalid", {"field": why}, "intent")

    if set(intent) not in (INTENT_KEYS, INTENT_KEYS | {"witnessed"}):
        bad("keys")
    body = {key: value for key, value in intent.items() if key != "check"}
    if intent["check"] != _intent_check(body):
        bad("check")
    if intent["lineage_id"] != lineage:
        bad("lineage_id")
    if not (rp.counter(intent["last_seq"], minimum=1) and rp.is_hex64(intent["chain"])):
        bad("prefix anchor")
    if not (rp.counter(intent["segment"]) and intent["segment"] <= cp.MAX_SEGMENT_NO and rp.counter(intent["offset"])):
        bad("tail place")
    if not (rp.is_hex64(intent["tail_sha256"]) and rp.counter(intent["tail_bytes"], minimum=1)):
        bad("tail identity")
    reserved = intent["identity_reserved"]
    if reserved is not None and not rp.counter(reserved):
        bad("identity_reserved")
    ack = intent["ack"]
    if ack is not None and not (
        isinstance(ack, dict)
        and ack.get("reason") == "ledger_tail_ambiguous"
        and ack.get("resolution") == "continue-conservative"
        and isinstance(ack.get("ack_id"), str)
        and ack.get("tail_sha256") == intent["tail_sha256"]
    ):
        bad("ack")
    if "witnessed" in intent and (ack is not None or witnessed_context_problem(intent["witnessed"], intent["last_seq"])):
        bad("witnessed")
    return intent


RECEIPT_KEYS = frozenset({"reason", "resolution", "ack_id", "stop_id", "evidence_sha256"})


def witnessed_context_problem(context, last_seq: int) -> str | None:
    """Why an intent's `witnessed` context (SV023-03) is not this runtime's, or None.

    It names the witnessed transaction's receipt (exactly `receipt_payload`'s
    shape), that receipt's ack_id, and the witnessed end the intent's anchor
    cannot precede.
    """
    if not isinstance(context, dict):
        return "keys"
    receipt = context.get("receipt")
    if not (isinstance(receipt, dict) and set(receipt) == RECEIPT_KEYS):
        return "receipt keys"
    if not all(isinstance(receipt[key], str) for key in RECEIPT_KEYS):
        return "receipt types"
    pair = (receipt["reason"], receipt["resolution"])
    if pair not in STOP_WITNESS_RESOLUTIONS:
        return "pair"
    # SV-028: the preserving mechanism's context also carries its evidence (bounded, fixed keys).
    keys = {"ack_id", "receipt", "after_seq"} | ({"evidence"} if pair in PRESERVING_RESOLUTIONS else set())
    if set(context) != keys:
        return "keys"
    if not (isinstance(context["ack_id"], str) and HEX32.fullmatch(receipt["ack_id"]) and receipt["ack_id"] == context["ack_id"] and HEX32.fullmatch(receipt["stop_id"])):
        return "ack_id"
    if not rp.is_hex64(receipt["evidence_sha256"]):
        return "evidence_sha256"
    if not (rp.counter(context["after_seq"], minimum=1) and context["after_seq"] <= last_seq):
        return "after_seq"
    if pair in PRESERVING_RESOLUTIONS:
        problem = preserving_evidence_problem(context["evidence"])
        if problem:
            return problem
        if sha256(cp.canonical_body(context["evidence"])) != receipt["evidence_sha256"]:
            return "evidence digest"
    return None


def _replay(messages, state: SessionState, records, read_blob=None, *, lenient: bool = False, fetch_blob=None) -> Replay:
    """`read_blob` for verification replays (witness evidence); `fetch_blob` for the base decision's candidates (SV026)."""
    replay = Replay(messages, state, read_blob, lenient=lenient, fetch_blob=fetch_blob)
    for record in records:
        replay.apply(record)
    return replay


def _wire(payload: dict) -> dict:
    """A payload as it reads back from the ledger (key-sorted canonical JSON)."""
    return json.loads(cp.canonical_body(payload))


def _unmerged_notice(entries):
    """(first seq, last seq, notice) for message records after the last checkpoint, or None.

    `entries`: (type, payload, seq) for the suffix, then this recovery's own
    closure records (seq None), so a call it just closed shows its outcome.
    """
    material = [seq for name, _payload, seq in entries if name in MESSAGE_RECORDS and seq is not None]
    if not material:
        return None
    statuses = {}
    names = {}
    for name, payload, _seq in entries:
        if name == "TURN_RESPONSE":
            for call in payload["calls"]:
                key = (payload["turn_seq"], call["call_index"])
                names[key] = (call["wire_id"], call["name"])
                statuses[key] = "not run" if call["admit"] != "invoke" else "no outcome recorded"
        elif name == "DONE":
            statuses[(payload["turn_seq"], payload["call_index"])] = "ran"
        elif name in ("UNRUN", "SYNTH") and isinstance(payload["call_key"], list):
            statuses[tuple(payload["call_key"])] = "not run" if name == "UNRUN" else "outcome unknown"
    listed = [f"{names[key][0]} ({names[key][1]}): {statuses[key]}" for key in sorted(names)]
    calls = ""
    if listed:
        shown = listed[:UNMERGED_CALLS_SHOWN]
        more = len(listed) - len(shown)
        calls = "; its tool calls: " + ", ".join(shown) + (f", and {more} more" if more else "")
    last = max(seq for _name, _payload, seq in entries if seq is not None)
    return material[0], last, UNMERGED_NOTICE.format(first=material[0], last=last, calls=calls)


# ---------------------------------------------------------------------------
# The outcome records of a recovered tail (pure)
# ---------------------------------------------------------------------------
def derive_core(
    replay: Replay, plan: cp.RecoveryPlan, tail: cp.TailClass, scan0: cp.LedgerScan, ack, lineage: str,
    *, identity_reserved: int | None = None,
) -> list:
    """Closure of the open group, RECOVERY_ACK, then RECOVERY records -- deterministic in P, T and IDENTITY.

    Call outcomes are the accepted plan's (v2 1.3 classification). Request
    identity is derived from the replayed state rather than the plan's
    placeholder: a request with no recorded response is a possible spend
    once; a damaged REQUEST_SENT used `requests_next`. After hidden records
    (acknowledged TC4) the next turn is above the durable IDENTITY
    reservation (SV021-01): every request, hidden or not, reserved its turn
    there before its REQUEST_SENT, through any number of earlier recoveries.
    """
    core: list = []
    group = replay.group
    if group is not None:
        outcomes = {outcome.call_index: outcome for outcome in plan.calls}
        for call in group.calls[group.answered :]:
            if call["admit"] != "invoke":
                continue
            outcome = outcomes[call["call_index"]]
            key = [group.turn_seq, call["call_index"]]
            if outcome.status == "unknown":
                kind = "unknown_damaged_tail" if outcome.text == rp.DAMAGED_TAIL_TEXT else "unknown"
                core.append(("SYNTH", {"call_key": key, "kind": kind}))
            elif outcome.status == "unrun":
                core.append(("UNRUN", {"call_key": key, "reason": outcome.text}))
            else:
                raise ReplayMismatch(f"call {key} is open in replay but {outcome.status} in the plan")
    tail_sha = sha256(scan0.tail) if scan0.tail else None
    if ack is not None:
        core.append(("RECOVERY_ACK", {"reason": ack["reason"], "resolution": ack["resolution"], "ack_id": ack["ack_id"], "tail_sha256": tail_sha}))
    for item in plan.recovery_records:
        if item["kind"] == "possible_duplicate_spend":
            continue
        core.append(("RECOVERY", {"kind": item["kind"], "detail": {**item["detail"], "tail_sha256": tail_sha}}))
    state = replay.state
    last = state.requests_last
    nxt = dict(state.requests_next)
    spend_label = None
    if tail.kind == "TC4":
        if identity_reserved is None:
            raise ReplayMismatch("no valid IDENTITY reservation bounds the hidden requests")
        used = [r.payload["turn_seq"] for r in scan0.records if r.type_name == "REQUEST_SENT"]
        turn = max(state.requests_next["turn_seq"], identity_reserved + 1, *(t + 1 for t in used))
        nxt = {"turn_seq": turn, "attempt": 1}
        spend_label = "hidden"
    elif tail.kind == "TC2" and tail.declared_type == "REQUEST_SENT":
        spend_label = cp.request_label(lineage, nxt["turn_seq"], nxt["attempt"])
        nxt = {"turn_seq": nxt["turn_seq"], "attempt": nxt["attempt"] + 1}
    elif last is not None and last["outcome"] == "failed_unknown":
        spend_label = last["label"]
    if spend_label is not None:
        core.append(("RECOVERY", {"kind": "possible_duplicate_spend", "detail": {"label": spend_label, "next": nxt}}))
    return core
