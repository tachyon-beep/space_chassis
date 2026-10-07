"""The session owner: every format-2 mutation of a chassis session, in one place.

Standard library only. Contracts: SV-015 v2 sections 1.2-1.4 and 2.3, SV-013
sections 2.2.2-2.2.5 as retained there. Built on the accepted SV-020
foundation (`chassis_persistence`) and the pure reducer (`chassis_replay`).

**One owner, one rule.** A `Session` changes the conversation, the notes, the
request identity and the checkpoint only by appending one synced ledger record
and then applying `chassis_replay.Replay.apply` to that same record -- the
function recovery applies to the records it reads back. There is no second
path that edits `messages` directly, so what the next start replays is what
this run held.

* **Effect gates.** `send` appends REQUEST_SENT and calls its effect only after
  the frame's fsync returned; `invoke` does the same with INVOKING. A failed
  append or sync means the effect is never called.
* **Blobs first.** DONE, MSG_APPEND (long text), NOTE_WRITTEN, HISTORY_REPLACED
  and retained originals are durable blobs before the record that names them.
* **One failure boundary.** Any persistence failure -- the writer's, a blob's,
  the conversation install, run.json -- breaks the session: it attempts the
  FSYNC_FAILED marker once (never recursively, v2 1.4.9) and refuses every
  later mutation and effect.
* **CKG.** `checkpoint` refuses while a tool group is open or messages are
  queued: there is no mid-group checkpoint.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import chassis_envelope as envelope
import chassis_persistence as cp
import chassis_replay as rp
from chassis_replay import Replay, SessionState

FORMAT = 2
WRITER = "chassis-2"

# [CM] v2 1.4.6 values; RECOVERY_* are v2 1.4.7's defaults.
INLINE_TEXT_BYTES = 4096  # MSG_APPEND carries text inline up to this, else a blob
DIRECT_MESSAGE_MAX_E = 1024 * 1024
SET_HISTORY_MAX = 16 * 1024 * 1024
RECOVERY_RECORDS_MAX = 256
RECOVERY_BYTES_MAX = 8 * 1024 * 1024
HANDOFF_READ_MAX = 1024 * 1024  # local read bound for an agent-edited HANDOFF.md [CM]
# Blob read bound [CM]: a base-switch blob holds a whole adopted conversation,
# which today's reader accepts up to 64 MiB; every other blob kind is smaller.
BLOB_READ_MAX = 64 * 1024 * 1024

PersistenceFailure = cp.PersistenceFailure

# The request-identity reservation (SV021-01). A request's turn is reserved in
# IDENTITY, durably, before its REQUEST_SENT -- so every turn any request ever
# used, including requests in ledger bytes later found damaged, is <= the
# reservation. It lives outside the ledger because a damaged ledger suffix is
# exactly what it must outlive. Reserved in blocks to save syncs.
IDENTITY = "IDENTITY"
RESERVE_BLOCK = 64


class SessionInvariant(RuntimeError):
    """The runtime asked for a mutation its own state machine forbids. A defect, never a guess."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity_bytes(lineage_id: str, reserved: int) -> bytes:
    body = {"lineage_id": lineage_id, "turns_reserved_through": reserved}
    check = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
    return json.dumps({**body, "check": check}, sort_keys=True).encode()


def read_identity(session_dir: Path, lineage_id: str, ops: cp.DurableOps | None = None) -> int | None:
    """The valid reservation for this lineage, or None (absent, unreadable, damaged, foreign)."""
    ops = ops or cp.DurableOps()
    try:
        value = json.loads(ops.read(str(Path(session_dir) / IDENTITY), cp.MAX_MARKER_READ).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(value, dict) or set(value) != {"lineage_id", "turns_reserved_through", "check"}:
        return None
    reserved = value["turns_reserved_through"]
    if value["lineage_id"] != lineage_id or not rp.counter(reserved):
        return None
    return reserved if identity_bytes(lineage_id, reserved) == json.dumps(value, sort_keys=True).encode() else None


def file_sha(path: Path, ops: cp.DurableOps) -> str | None:
    try:
        return sha256(ops.read(str(path), BLOB_READ_MAX))
    except OSError:
        return None


def checkpoint_tuple(record) -> dict:
    """The `prev` tuple that names a CHECKPOINT record."""
    return {
        "covers_seq": record.payload["covers_seq"],
        "conv_sha256": record.payload["conv"]["sha256"],
        "conv_bytes": record.payload["conv"]["bytes"],
        "checkpoint_seq": record.seq,
    }


class Session:
    """The one owner of a format-2 session's mutations."""

    def __init__(
        self,
        session_dir: Path,
        home_dir: Path,
        writer: cp.LedgerWriter,
        replay: Replay,
        *,
        ops: cp.DurableOps | None = None,
        caps: envelope.Caps = envelope.DEFAULT_CAPS,
        checkpoints: dict | None = None,
        identity_reserved: int | None = None,
        records_max: int = RECOVERY_RECORDS_MAX,
        bytes_max: int = RECOVERY_BYTES_MAX,
        lifecycle=None,
        install=None,
        meta_source=None,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.home_dir = Path(home_dir)
        self.handoff_path = self.home_dir / "HANDOFF.md"
        self.writer = writer
        self.replay = replay
        self.ops = ops or cp.DurableOps()
        self.caps = caps
        # Conversation SHA-256 -> the `prev` tuple of the newest CHECKPOINT that
        # bound those bytes (SV021-02): `prev` names what the retained file holds.
        self.checkpoints: dict[str, dict] = dict(checkpoints or {})
        self.identity_reserved = identity_reserved
        self.records_max = records_max
        self.bytes_max = bytes_max
        self.since_records = 0
        self.since_bytes = 0
        self.queue: list[tuple[str, str]] = []
        self.broken = False
        self.marker_written: bool | None = None
        self.lifecycle = lifecycle or (lambda event, **fields: None)
        # CK2-CK4. `install(messages, data, rotate) -> sha256`; the chassis
        # routes it through `Carried.save_conversation` so its tests can fail it.
        self.install = install or (
            lambda _messages, data, rotate: cp.install_conversation(self.session_dir, data, ops=self.ops, rotate=rotate)
        )
        # The legacy run.json keys (agent, name, run, turn, ...); CK5 adds the rest.
        self.meta_source = meta_source or dict

    @classmethod
    def start_fresh(cls, session_dir: Path, home_dir: Path, lineage_id: str, *, ops: cp.DurableOps | None = None, **kwargs) -> Session:
        """A new lineage: ledger/, segment 0 and an empty IDENTITY reservation. Writes no record."""
        ops = ops or cp.DurableOps()
        try:
            writer = cp.LedgerWriter.create(session_dir, lineage_id, ops=ops)
            # Before any request can exist: an ambiguous tail later found in this
            # lineage is then always covered by a valid reservation.
            cp.write_bytes_durable(Path(session_dir) / IDENTITY, identity_bytes(lineage_id, 0), ops=ops)
        except cp.PersistenceFailure as error:
            # create() attempts the marker only for failures after it began
            # writing; a failed mkdir is still a session persistence failure.
            cp.mark_fsync_failed(session_dir, f"{type(error).__name__}: {error}", ops=ops)
            raise
        replay = Replay([], SessionState(lineage_id), lambda sha: writer.blobs.get(sha, BLOB_READ_MAX))
        return cls(session_dir, home_dir, writer, replay, ops=ops, identity_reserved=0, **kwargs)

    # -- views ---------------------------------------------------------------
    @property
    def messages(self) -> list:
        return self.replay.messages

    @property
    def state(self) -> SessionState:
        return self.replay.state

    @property
    def lineage_id(self) -> str:
        return self.state.lineage_id

    @property
    def group(self):
        return self.replay.group

    def read_blob(self, sha: str) -> bytes | None:
        return self.writer.blobs.get(sha, BLOB_READ_MAX)

    # -- the failure boundary --------------------------------------------------
    def _usable(self) -> None:
        if self.broken:
            raise PersistenceFailure("the session failed earlier and accepts nothing more")

    def _fail(self, error: BaseException):
        """Break the session; attempt FSYNC_FAILED once unless the writer already did."""
        self.broken = True
        self.writer.broken = True
        if self.writer.marker_written is not None:
            self.marker_written = self.writer.marker_written
        elif self.marker_written is None:
            self.marker_written = cp.mark_fsync_failed(self.session_dir, f"{type(error).__name__}: {error}", ops=self.ops)
        raise PersistenceFailure(f"{type(error).__name__}: {error}") from error

    def _commit(self, type_name: str, payload, *, blob: bytes | None = None, replay_bytes: int = 0) -> cp.Record:
        """Append one synced record (its blob first), then apply the reducer to it."""
        self._usable()
        try:
            if blob is None:
                record = self.writer.append(type_name, payload)
            else:
                record = self.writer.append_with_blob(type_name, blob, payload)
        except cp.PersistenceFailure as error:
            self._fail(error)
        try:
            self.replay.apply(record)
        except rp.ReplayMismatch as error:
            # Durable, but not a record this state could have produced: stop
            # here; the next start's replay refuses it the same way.
            self.broken = True
            raise SessionInvariant(f"{type_name}: {error}") from error
        self.since_records += 1
        self.since_bytes += record.length + replay_bytes
        return record

    def _put_blob(self, data: bytes) -> str:
        self._usable()
        try:
            return self.writer.blobs.put(data)
        except cp.PersistenceFailure as error:
            self._fail(error)

    def _require_boundary(self, what: str) -> None:
        self._usable()  # a broken session refuses as a persistence failure first
        if self.replay.group is not None:
            raise SessionInvariant(f"{what} inside the open tool group of turn {self.replay.group.turn_seq}")

    # -- requests (REQUEST_SENT gate) ------------------------------------------
    def next_label(self) -> str:
        identity = self.state.requests_next
        return cp.request_label(self.lineage_id, identity["turn_seq"], identity["attempt"])

    def reserve_turns(self, through: int, *, exact: bool = False) -> None:
        """Make IDENTITY cover `through` (durably, before anything that uses it); never lowers it."""
        self._usable()
        if self.identity_reserved is not None and through <= self.identity_reserved:
            return
        reserved = through if exact else min(through + RESERVE_BLOCK - 1, rp.MAX_COUNTER)
        if not rp.counter(reserved, minimum=through):
            raise cp.LedgerError(f"turn {through} is outside the identity domain")
        try:
            cp.write_bytes_durable(self.session_dir / IDENTITY, identity_bytes(self.lineage_id, reserved), ops=self.ops)
        except cp.PersistenceFailure as error:
            self._fail(error)
        self.identity_reserved = reserved

    def send(self, effect):
        """IDENTITY covers the turn, REQUEST_SENT (synced), then `effect()` -- the only way a request is sent."""
        self._require_boundary("a request")
        identity = self.state.requests_next
        label = cp.request_label(self.lineage_id, identity["turn_seq"], identity["attempt"])
        self.reserve_turns(identity["turn_seq"])
        self._commit("REQUEST_SENT", {"turn_seq": identity["turn_seq"], "attempt": identity["attempt"], "label": label})
        return effect()

    def adopt(self, adoption: envelope.Adoption) -> None:
        """TURN_RESPONSE (originals first, FIFO-retained), or RESPONSE_REFUSED.

        Both carry their notice (the refusal; the omitted calls), which the
        reducer appends -- the refusal at once, the omission when the group's
        last call is answered -- so no crash can separate a durable response
        from the notice it owes (SV021-06).
        """
        last = self.state.requests_last
        if last is None or last["outcome"] != "failed_unknown" or last["turn_seq"] != adoption.turn_seq:
            raise SessionInvariant(f"a response for turn {adoption.turn_seq} without its request")
        if adoption.refused:
            self._commit("RESPONSE_REFUSED", adoption.refusal_payload())
            return
        retained = []
        for original in adoption.originals:
            if len(original.data) > rp.ORIGINAL_MAX_ITEM:
                self.lifecycle("original_not_retained", field=original.field, bytes=len(original.data))
                continue
            retained.append(
                {"sha256": self._put_blob(original.data), "bytes": len(original.data), "kind": original.kind, "field": original.field}
            )
        before = [entry["sha256"] for entry in self.state.originals] + [entry["sha256"] for entry in retained]
        self._commit("TURN_RESPONSE", adoption.turn_response_payload(retained))
        kept = {entry["sha256"] for entry in self.state.originals}
        for sha in dict.fromkeys(sha for sha in before if sha not in kept):
            self._commit("ORIGINAL_EVICTED", {"sha": sha})

    # -- tools (INVOKING gate, DONE) -------------------------------------------
    def _frontier(self, call: envelope.StoredCall) -> int:
        self._usable()
        group = self.replay.group
        if group is None or group.next_call() is None or group.next_call()["call_index"] != call.index:
            raise SessionInvariant(f"call {call.index} is not the frontier call")
        return group.turn_seq

    def invoke(self, call: envelope.StoredCall, effect):
        """INVOKING (synced), then the tool body. Never for a call with admit != invoke."""
        if call.admit != "invoke":
            raise SessionInvariant(f"call {call.index} was admitted as {call.admit}, not invoke")
        turn = self._frontier(call)
        self._commit("INVOKING", {"turn_seq": turn, "call_index": call.index})
        return effect()

    def record_result(self, call: envelope.StoredCall, outcome: str, text) -> None:
        """The stored result: normalized and capped, a durable blob, then DONE."""
        turn = self._frontier(call)
        stored, info = envelope.stored_result(text, self.caps.result)
        data = stored.encode("utf-8")
        self._commit(
            "DONE",
            lambda blob: {
                "turn_seq": turn,
                "call_index": call.index,
                "outcome": outcome,
                "blob": blob,
                "original_bytes": info["original_bytes"],
                "stored_E": info["escaped_units"],
                "truncated": info["truncated"],
                "replaced_chars": info["replaced_chars"],
            },
            blob=data,
            replay_bytes=len(data),
        )

    def end_group(self, call: envelope.StoredCall, stop: BaseException, *, ended_text: str, how: str, termination=None) -> None:
        """Answer the call a run ended in and every later call, before the exception goes on.

        A typed end first records TERMINATION; then KeyboardInterrupt ->
        SYNTH{unknown}, anything else -> DONE{raised:<T>} with `ended_text`. Every later invokable
        call -> UNRUN "not run: the run ended <how>in call <wire id>"; later
        calls with admit != invoke keep their admission answer. A broken
        session writes nothing: recovery derives the rest from the ledger.
        """
        if self.broken or self.replay.group is None:
            return
        turn = self._frontier(call)
        if termination is not None:
            # While the call is still open: its answer may close the group
            # (it can be the last call), and a TERMINATION names an open call.
            kind, note_gen = termination
            self.record_termination(kind, note_gen, call_key=[turn, call.index])
        if isinstance(stop, KeyboardInterrupt):
            self._commit("SYNTH", {"call_key": [turn, call.index], "kind": "unknown"})
        else:
            self.record_result(call, f"raised:{type(stop).__name__}", ended_text)
        while self.replay.group is not None:
            later = self.replay.group.next_call()
            self._commit(
                "UNRUN",
                {"call_key": [turn, later["call_index"]], "reason": f"not run: the run ended {how}in call {call.wire_id}"},
            )

    def record_termination(self, kind: str, note_gen, call_key="direct") -> None:
        payload = {"call_key": call_key, "kind": kind}
        if note_gen is not None:
            payload["note_gen"] = note_gen
        self._commit("TERMINATION", payload)

    # -- messages ----------------------------------------------------------------
    def _append(self, kind: str, text: str, **extra) -> None:
        data = text.encode("utf-8")
        payload = {"kind": kind, "epoch": self.state.history_epoch, **extra}
        if len(data) <= INLINE_TEXT_BYTES:
            self._commit("MSG_APPEND", {**payload, "text": text})
        else:
            self._commit("MSG_APPEND", lambda blob: {**payload, "blob": blob}, blob=data, replay_bytes=len(data))

    def append_message(self, kind: str, text) -> None:
        """A direct say/note/notice: one MSG_APPEND unit (<= 1 MiB escaped, v2 1.4.6)."""
        if not isinstance(text, str):
            raise ValueError("a message must be text")
        self._require_boundary("a direct message")
        normalized, _replaced = envelope.normalize_text(text)
        units = envelope.escaped_units(normalized)
        if units > DIRECT_MESSAGE_MAX_E:
            raise ValueError(f"a message is at most {DIRECT_MESSAGE_MAX_E} escaped units; this one is {units}")
        self._append(kind, normalized)
        self.unit_end()

    def queue_message(self, kind: str, normalized: str) -> None:
        """Hold an already-admitted message until the group's flush (in memory only)."""
        self.queue.append((kind, normalized))

    def flush(self) -> None:
        """After the group's last answer: the omitted-calls notice, then the queue, in order."""
        self._require_boundary("a queue flush")
        queued, self.queue = self.queue, []
        for kind, text in queued:
            self._append(kind, text)

    def discard_queue(self) -> int:
        """A broken session cannot flush: what was queued is lost, and the count is reported."""
        lost = len(self.queue)
        self.queue = []
        return lost

    # -- notes (D13 2.2.5 with v2 1.4.2-1.4.4) --------------------------------------
    def write_note(self, note, *, header: str) -> int | None:
        """NOTE_WRITTEN{runtime} (blob first), then the HANDOFF.md mirror. None if dropped.

        The 17th unadopted note is not stored (v2 1.4.6): a
        RECOVERY{note_dropped_pending_limit} records the drop so the next
        resume reports it, even if the run dies before its next checkpoint.
        """
        if not isinstance(note, str):
            raise ValueError("a handoff note must be text")
        if len(self.state.notes_pending) >= rp.MAX_PENDING_NOTES:
            self._drop_note(len(note.encode("utf-8", "replace")))
            return None
        text, _info = envelope.truncate_marked(note.strip(), self.caps.note)
        file_text = f"{header}\n\n{text}\n"
        data = file_text.encode("utf-8")
        gen = self.state.notes_next_gen
        mirror = sha256(data)
        self._commit(
            "NOTE_WRITTEN",
            lambda blob: {"gen": gen, "blob": blob, "bytes": len(data), "sha256": blob, "source": "runtime", "mirror_sha256": mirror},
            blob=data,
        )
        try:
            # The legacy mirror: no authority, so its failure is reported, not fatal.
            from common import write_text_atomic  # noqa: PLC0415 -- the shared helper the chassis already uses

            write_text_atomic(self.handoff_path, file_text)
        except OSError as error:
            self.lifecycle("handoff_mirror_failed", error=f"{type(error).__name__}: {error}"[:300])
        if self.replay.group is None:
            self.unit_end()
        return gen

    def _drop_note(self, size: int) -> None:
        self._commit("RECOVERY", {"kind": "note_dropped_pending_limit", "detail": {"bytes": size}})
        self.lifecycle("note_dropped_pending_limit", pending=len(self.state.notes_pending), bytes=size)

    def adopt_file_edit(self) -> int | None:
        """HANDOFF.md bytes the runtime did not write and has not processed: one new generation.

        A file whose SHA-256 is the last processed one, or any recorded mirror
        (pending generations and the newest adopted), is runtime-written and
        never adopted. [X] An identical rewrite is undetectable (D13 rule 4).
        """
        try:
            data = self.ops.read(str(self.handoff_path), HANDOFF_READ_MAX)
        except FileNotFoundError:
            return None
        except OSError as error:
            self.lifecycle("handoff_unreadable", error=f"{type(error).__name__}: {error}"[:300])
            return None
        digest = sha256(data)
        if digest == self.state.handoff_md_sha256 or digest in self.state.mirror_sha256s():
            return None
        if len(self.state.notes_pending) >= rp.MAX_PENDING_NOTES:
            self._drop_note(len(data))
            return None
        stored, _info = envelope.truncate_marked(data.decode("utf-8", "replace"), self.caps.note)
        blob = stored.encode("utf-8")
        gen = self.state.notes_next_gen
        self._commit(
            "NOTE_WRITTEN",
            lambda key: {"gen": gen, "blob": key, "bytes": len(blob), "sha256": key, "source": "file_edit", "mirror_sha256": digest},
            blob=blob,
        )
        return gen

    def adopt_notes(self) -> list[int]:
        """Append every pending generation once, in order; then any drop notice.

        A generation a LEGACY_REIMPORT found already in an older runtime's list
        carries a durable `foreign` mark (SV021-10): it advances the watermark
        without being appended again (`adopted_by_foreign_runtime`). The mark
        is per generation, never by text, so a later generation with equal
        text is still appended.
        """
        self._require_boundary("note adoption")
        adopted = []
        for entry in list(self.state.notes_pending):
            foreign = entry.get("foreign") is True
            payload = {"kind": "note", "gen": entry["gen"], "blob": entry["blob"], "epoch": self.state.history_epoch}
            if foreign:
                payload["foreign"] = True
            self._commit("MSG_APPEND", payload, replay_bytes=0 if foreign else entry["bytes"])
            if not foreign:
                adopted.append(entry["gen"])
        if self.state.notes_dropped:
            self._append("notice", rp.DROPPED_NOTE_NOTICE.format(count=rp.MAX_PENDING_NOTES), reports="note_dropped_pending_limit")
        return adopted

    # -- history and recap -----------------------------------------------------------
    def replace_history(self, messages) -> None:
        """HISTORY_REPLACED (the new list as a blob first), then a checkpoint at once."""
        self._require_boundary("set_history")
        if not isinstance(messages, list) or not all(
            isinstance(message, dict) and isinstance(message.get("role"), str) for message in messages
        ):
            raise ValueError("history must be a list of messages, each a dict with a string role")
        try:
            data = rp.conversation_bytes(messages)
        except (TypeError, ValueError, RecursionError) as error:
            raise ValueError(f"history must be JSON-serializable: {type(error).__name__}") from error
        if len(data) > SET_HISTORY_MAX:
            raise ValueError(f"history is at most {SET_HISTORY_MAX} bytes serialized; this one is {len(data)}")
        epoch, count, digest = self.state.history_epoch + 1, len(messages), sha256(data)
        self._commit(
            "HISTORY_REPLACED",
            lambda blob: {"epoch": epoch, "new_blob": blob, "new_count": count, "new_sha256": digest},
            blob=data,
            replay_bytes=len(data),
        )
        self.checkpoint()

    def record_fold(self, start: int, end: int, lines: int) -> None:
        """RECAP_FOLD after recap.md was appended: a crash between repeats lines, never loses them."""
        self._require_boundary("a recap fold")
        if start != self.state.recap_folded or not start < end <= len(self.messages):
            raise SessionInvariant(f"a fold {start}->{end} does not continue {self.state.recap_folded}")
        self._commit("RECAP_FOLD", {"from": start, "to": end, "lines": lines})

    # -- checkpoints (CK1-CK6), thresholds and rotation -----------------------------
    def unit_end(self) -> None:
        """After a unit: checkpoint on the v2 1.4.1 threshold, else rotate a full segment."""
        if self.broken or self.replay.group is not None or self.queue:
            return
        if self.since_records >= self.records_max or self.since_bytes >= self.bytes_max:
            self.checkpoint()
        else:
            self._rotate()

    def _rotate(self) -> None:
        try:
            self.writer.rotate_if_full()
        except cp.PersistenceFailure as error:
            self._fail(error)

    def _retained_prev(self) -> tuple[bool, dict | None]:
        """CK3's choice (SV021-02): keep a bound snapshot as conversation.prev.json, and name it.

        The current conversation.json is rotated aside unless that would
        replace a bound snapshot in .prev.json with something older or unbound
        -- after A10, A14 or an external edit .prev.json can be the only bound
        base. (With nothing bound in .prev.json the current file is kept, as
        D13 2.2.9 keeps a pre-ledger list at the first checkpoint.) `prev`
        names the newest checkpoint whose bytes the retained file holds, or
        nothing.
        """
        current = self.checkpoints.get(file_sha(self.session_dir / "conversation.json", self.ops))
        kept = self.checkpoints.get(file_sha(self.session_dir / "conversation.prev.json", self.ops))
        if kept is not None and (current is None or current["checkpoint_seq"] < kept["checkpoint_seq"]):
            return False, dict(kept)
        return True, dict(current) if current is not None else None

    def checkpoint(self, ended: dict | None = None) -> cp.Record:
        """CK1 serialize; CK2-CK4 install (a bound prev kept); CK5 run.json; CK6 CHECKPOINT."""
        self._usable()
        if self.replay.group is not None or self.queue:
            raise SessionInvariant("a checkpoint is never written inside a tool group or with queued messages (CKG)")
        data = rp.conversation_bytes(self.messages)
        rotate, prev = self._retained_prev()
        try:
            conv_sha = self.install(self.messages, data, rotate)
        except OSError as error:
            self._fail(error)
        if conv_sha != sha256(data):
            self.broken = True
            raise SessionInvariant("the installed conversation is not the serialized list")
        covers = self.writer.next_seq - 1
        conv = {"sha256": conv_sha, "bytes": len(data)}
        meta = dict(self.meta_source())
        meta.update(
            {
                "format": FORMAT,
                "writer": WRITER,
                "lineage_id": self.lineage_id,
                "recap_folded": self.state.recap_folded,
                "history_epoch": self.state.history_epoch,
                "checkpoint": {"covers_seq": covers, "conv": conv, "prev": prev, "epoch": self.state.history_epoch},
            }
        )
        if ended is not None:
            meta["ended"] = ended
        run_bytes = (json.dumps(meta, indent=2) + "\n").encode("ascii")
        try:
            cp.write_bytes_durable(self.session_dir / "run.json", run_bytes, ops=self.ops)
        except cp.PersistenceFailure as error:
            self._fail(error)
        payload = {
            "covers_seq": covers,
            "chain_at_cover": self.writer.chain,
            "conv": conv,
            "prev": prev,
            "run_sha256": sha256(run_bytes),
            "state": self.state.to_wire(next_seq=covers + 2),
        }
        record = self._commit("CHECKPOINT", payload)
        self.checkpoints[conv_sha] = checkpoint_tuple(record)
        self.since_records = self.since_bytes = 0
        self._rotate()
        return record

    def record_run_end(self, exit_code: int, reason: str) -> None:
        """RUN_END, best-effort (v2 1.2): a failure here changes no exit."""
        if self.broken:
            return
        with contextlib.suppress(PersistenceFailure, cp.LedgerError):
            self._commit("RUN_END", {"exit": exit_code, "reason": reason})

    def close(self) -> None:
        self.writer.close()
