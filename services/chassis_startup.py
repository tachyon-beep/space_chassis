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
`RECOVERING` intent names the valid prefix's end and the tail's hash; a
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
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import chassis_envelope as envelope
import chassis_gc as gc
import chassis_persistence as cp
import chassis_replay as rp
from chassis_replay import Replay, ReplayMismatch, SessionState
from chassis_session import BLOB_READ_MAX, Session, checkpoint_tuple, read_identity

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

# Resolutions this runtime can carry out. The others named by SV-013/v2
# (bootstrap-preserving; continue-from-bound for a damaged or missing ledger)
# are refused rather than half-performed: they remain deferred.
IMPLEMENTED_RESOLUTIONS = {
    ("ledger_tail_ambiguous", "continue-conservative"),
    ("fsync_failed_previous_run", "continue-from-bound"),
    ("corrupt_quarantine_full", "continue-from-bound"),
}

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
def acknowledge(session_dir: Path, reason: str, resolution: str, *, ops: cp.DurableOps | None = None) -> dict:
    """Make the acknowledgement durable, then lift the stop: ACKNOWLEDGED -> (FSYNC_FAILED) -> STOPPED.

    A crash before ACKNOWLEDGED is durable changes nothing; after it, STOPPED
    still stops every start (A0) until it is removed last, so no crash cut
    grants permission that was not durably given. Repeating the command is
    harmless. It adds no evidence about what any damaged bytes held.
    """
    ops = ops or cp.DurableOps()
    session_dir = Path(session_dir)
    if (reason, resolution) not in IMPLEMENTED_RESOLUTIONS:
        raise cp.LedgerError(f"{resolution!r} for {reason!r} is not implemented by this runtime; nothing was changed")
    ack = cp.acknowledge_stop(session_dir, reason, resolution, ops=ops)
    stopped = ops.read(str(session_dir / STOPPED), cp.MAX_MARKER_READ)
    ack["ack_id"] = sha256(stopped + f"\n{reason}\n{resolution}".encode())[:32]
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


def _read_ack(session_dir: Path, ops) -> dict | None:
    status, ack = _read_json_object(ops, session_dir / ACKNOWLEDGED, cp.MAX_MARKER_READ)
    if status != "ok":
        return None
    if (ack.get("reason"), ack.get("resolution")) not in IMPLEMENTED_RESOLUTIONS or not isinstance(ack.get("ack_id"), str):
        return None
    return ack


def _remove(session_dir: Path, name: str, ops) -> None:
    try:
        if (session_dir / name).exists():
            ops.unlink(str(session_dir / name))
            ops.sync_dir(str(session_dir))
    except OSError as error:
        raise cp.PersistenceFailure(f"{name} could not be removed durably: {error}") from error


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
        self.ack = _read_ack(session_dir, self.ops)
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
            raise StartupStop("run_json_unreadable", None, "CK5")
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
            session._commit("LEGACY_IMPORT", lambda blob: {**payload, "blob": blob}, blob=data, replay_bytes=len(data))
        else:
            session._commit("LEGACY_IMPORT", payload)
        self._consume_ack(session, ())
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
        read_blob = lambda sha: blobs.get(sha, BLOB_READ_MAX)  # noqa: E731
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
        # What IDENTITY is carried forward as: never below either checked value.
        high_water = max((v for v in (live, identity) if v is not None), default=None)
        tail_ack = ack if ack and ack.get("reason") == "ledger_tail_ambiguous" else None
        tail = cp.classify_tail(scan0)
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

        decision = self._classify_base(p0, extra, format2, lineage, read_blob)
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

        # Set the tail aside only under a durable intent (see the module docstring).
        if scan0.tail and intent is None:
            intent = _sealed_intent({
                "lineage_id": lineage, "last_seq": scan0.last_seq, "chain": scan0.last_chain,
                "segment": scan0.tail_segment, "offset": scan0.tail_offset,
                "tail_sha256": sha256(scan0.tail), "tail_bytes": len(scan0.tail), "ack": tail_ack,
                "identity_reserved": identity,
            })
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
        session.since_records = decision.suffix_records + len(extra)
        for type_name, payload in core[len(extra):]:
            if type_name == "ADOPT":
                data = payload
                session._commit(
                    "RECOVERY",
                    lambda blob: {"kind": "conversation_adopted", "detail": {"conv_sha": sha256(data), "blob": blob}},
                    blob=data,
                    replay_bytes=len(data),
                )
            else:
                session._commit(type_name, payload)
        after_core = extra[len(core):]
        self._finish_case(session, decision, plan, core, after_core)
        _remove(session_dir, RECOVERING, ops)
        self._consume_ack(session, now.records)
        # SV021-01: the reservation now covers every turn this ledger used and
        # the next one, durably, before the duty can cause any request.
        used = [r.payload["turn_seq"] for r in now.records if r.type_name == "REQUEST_SENT"]
        target = max([*used, session.state.requests_next["turn_seq"], high_water or 0])
        session.identity_reserved = live  # what the file actually holds: rewrite it if missing or lower
        session.reserve_turns(target, exact=True)
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
    def _classify_base(self, p0, extra, format2: bool, lineage: str, read_blob) -> _Decision:
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
                strict = _replay([], SessionState(lineage), p0, read_blob)
                state_n = None
            else:
                state_n = SessionState.from_wire(newest.payload["state"])
                base = next((f for f in (conv, prev) if f.status == "ok" and f.sha == newest.payload["conv"]["sha256"]), None)
                if base is not None:
                    newest_bytes = base.data
                    strict = _replay(json.loads(base.data), state_n.copy(), suffix, read_blob)
                else:
                    strict, newest_bytes = self._previous_base(p0, newest, state_n, (conv, prev), suffix, read_blob)
        except rp.StateError as error:
            raise StartupStop("checkpoint_state_invalid", {"error": str(error)[:200]}) from error
        except ReplayMismatch as error:
            raise StartupStop("replay_mismatch", {"error": str(error)[:200]}) from error

        def lenient() -> Replay:
            try:
                return _replay([], state_n.copy(), suffix, read_blob, lenient=True)
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
        decision = _Decision("", strict, conv, newest, suffix, known, len(suffix), carried=carried, kind=kind, bound=bound)
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
                raise StartupStop("conversation_unreadable_unbound", None, "A14")
            decision.case = "A14"
            # SV021-02: put the newest checkpoint's own (verified) bytes back,
            # so the file is bound again and .prev.json keeps its base; before
            # any checkpoint there is no such snapshot, only the replay.
            decision.restore = newest_bytes
        if decision.replay is None:
            decision.replay = lenient()
        return decision

    def _previous_base(self, p0, newest, state_n: SessionState, files, suffix, read_blob):
        """A14's previous base (v2 1.4.4): replay through C_n, verify its hash, then the suffix.

        Returns (replay, C_n's bytes) or (None, None) when no file holds the named previous base.
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
        middle = _replay(json.loads(base.data), state_p, interval, read_blob)
        middle_bytes = rp.conversation_bytes(middle.messages)
        if sha256(middle_bytes) != newest.payload["conv"]["sha256"]:
            raise StartupStop("replay_mismatch", {"at": newest.payload["covers_seq"]}, "A14")
        replay = Replay(middle.messages, state_n.copy(), read_blob)
        for record in suffix:
            replay.apply(record)
        return replay, middle_bytes

    def _finish_case(self, session: Session, decision: _Decision, plan: cp.RecoveryPlan, core, after_core) -> None:
        """The base decision's records, then any recovery notices not yet durable."""
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
                session._commit(name, lambda blob: {**payload, "blob": blob}, blob=data, replay_bytes=len(data))
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

    def _consume_ack(self, session: Session, records) -> None:
        """Transcribe a non-tail acknowledgement as RECOVERY_ACK once; then remove ACKNOWLEDGED."""
        ack = self.ack
        if ack is None:
            return
        done = any(r.type_name == "RECOVERY_ACK" and r.payload.get("ack_id") == ack["ack_id"] for r in records)
        done = done or any(
            r.type_name == "RECOVERY_ACK" and r.payload.get("ack_id") == ack["ack_id"]
            for r in cp.scan_segments(cp.read_segments(self.session_dir / "ledger", ops=self.ops), session.lineage_id).records
        )
        if not done and ack["reason"] != "ledger_tail_ambiguous":
            session._commit("RECOVERY_ACK", {"reason": ack["reason"], "resolution": ack["resolution"], "ack_id": ack["ack_id"]})
            done = True
        if done:
            _remove(self.session_dir, ACKNOWLEDGED, self.ops)


@dataclass
class _Decision:
    case: str
    replay: Replay | None
    conv: FileState
    newest: object
    suffix: list
    checkpoints: dict  # conversation sha -> the `prev` tuple of its newest CHECKPOINT
    suffix_records: int
    carried: bool = False  # the binding switch is this recovery's own and carried its notices
    adopt: tuple | None = None  # A10: ("ADOPT", file bytes), written before the core
    restore: bytes | None = None  # A14: the newest checkpoint's bytes
    kind: str = ""  # the latest binding transition's kind and its file hash (None: absent)
    bound: str | None = None


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

    if set(intent) != INTENT_KEYS:
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
    return intent


def _replay(messages, state: SessionState, records, read_blob, *, lenient: bool = False) -> Replay:
    replay = Replay(messages, state, read_blob, lenient=lenient)
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
