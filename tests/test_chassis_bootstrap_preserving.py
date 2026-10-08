"""SV-028: `bootstrap-preserving` for a witnessed `conversation_unreadable_unbound` stop (W1).

Evidence kinds, kept apart:

* **In-process simulation** (most of this file), on temporary roots, as in
  `test_chassis_acknowledgements`. A "crash" raises `Crash` before an injected
  filesystem call -- process death: completed calls stay (M-1) -- and a
  "restart" calls the command or `open_session` again. Host loss (M-2) is only
  *simulated*, by `PreserveOps`/`host_loss_names`: segment bytes no returned
  fsync covered are cut back, and namespace changes (created directories and
  files, renames of files and directories, unlinks) that no returned fsync of
  their containing directory covered are undone, newest first. Pending names
  are keyed by the containing directory's identity, so they follow an
  ancestor rename (`<ack>.partial` -> `<ack>`), and every undo re-resolves
  identities (SV028-06, L6). Each restart carries the previous process's
  watermarks (`PreserveOps(root, previous)`).
* **One real CLI section** (`test_sv028_cli_*`): the real recorder, a local
  stub upstream and real `services/chassis.py` processes, including the
  actual `--acknowledge-stop … --resolution bootstrap-preserving` command.

The fixtures use the production layout (`session_dir = home_dir/session`,
`chassis.py:610–612`), so the command is called with its unchanged signature
and HANDOFF.md is found where the chassis writes it. The declared inventory a
test compares against is computed here, independently of the runtime's
selector. Not a power-loss, kernel or storage experiment; no provider; no real
session.
"""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import chassis
import chassis_gc as gc
import chassis_persistence as cp
import chassis_replay as rp
import chassis_session as cs
import chassis_startup as st
import pytest
from test_chassis_durability import Crash
from test_chassis_gc import HEADER, CutOps, append_record, note, tool_turn
from test_chassis_gc import begin as gc_begin
from test_chassis_recovery_live import LINEAGE, Root, establish, partial_turn, respond, resume

A14 = "conversation_unreadable_unbound"
CK5 = "run_json_unreadable"
BP = "bootstrap-preserving"
CFB = "continue-from-bound"
DAMAGED = b"\x00not a conversation"
DAMAGED_PREV = b"\x00not one either"
X = b"\x00a later damage"  # what a later A14 quarantines over the planted Y
Y = b"planted: not the quarantine copy of X"
CORRUPT_Y = f"corrupt/conversation-{hashlib.sha256(X).hexdigest()[:16]}"
ACK_TEMP = ".ACKNOWLEDGED.0123456789abcdef.tmp"  # temp-shaped, pre-existing: evidence, not ownership
LEAF_FILE = "planted-only.bin"
SERVICES = Path(__file__).resolve().parent.parent / "services"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# The namespace-capable fault model (SV028-06, L6)
# ---------------------------------------------------------------------------
class PreserveOps(CutOps):
    """CutOps (segment byte watermarks, crash points, injected errors) plus pending names by directory identity.

    Each pending change is recorded against its containing directory's
    (st_dev, st_ino) and cleared only by a returned `sync_dir` of that same
    directory, whatever its path is by then. `trace` mirrors `log` with paths
    relative to the root; `created` lists the paths this process created.
    """

    def __init__(self, root: Path, previous: PreserveOps | None = None) -> None:
        super().__init__(durable=previous.durable if previous is not None else None)
        self.root = Path(root)
        self.pending: list[tuple] = list(previous.pending) if previous is not None else []
        self.trace: list[tuple] = []
        self.created: list[str] = []
        self.usage_log: list[tuple] | None = None

    def rel(self, path) -> str:
        try:
            return Path(path).relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    @staticmethod
    def _identity(path) -> tuple:
        status = os.stat(path)
        return status.st_dev, status.st_ino

    def _step(self, call, path, frame=None) -> None:
        count = len(self.log)
        try:
            super()._step(call, path, frame)
        finally:
            if len(self.log) > count:
                self.trace.append((call, self.rel(path), frame))

    def _record(self, parent, change) -> None:
        self.pending.append((self._identity(parent), change))

    def _measure(self) -> None:
        """(trace position of the call just completed + 1, files, bytes) under preserved/."""
        if self.usage_log is not None:
            self.usage_log.append((len(self.trace), *usage(self.root / "session")))

    def open(self, path, flags, mode=0o644):
        new = bool(flags & os.O_CREAT) and not os.path.lexists(path)
        fd = super().open(path, flags, mode)
        if new:
            self._record(Path(path).parent, ("new", Path(path).name))
            self.created.append(self.rel(path))
        self._measure()
        return fd

    def write(self, fd, data):
        written = super().write(fd, data)
        self._measure()
        return written

    def mkdir(self, path):
        super().mkdir(path)
        self._record(Path(path).parent, ("new", Path(path).name))
        self.created.append(self.rel(path))
        self._measure()

    def rename(self, source, target):
        source, target = Path(source), Path(target)
        assert source.parent == target.parent, "the model covers same-directory renames only"
        is_dir = source.is_dir()
        before = target.read_bytes() if target.is_file() else None
        super().rename(source, target)
        self._record(target.parent, ("rename", source.name, target.name, before, is_dir))
        self._measure()

    def unlink(self, path):
        data = Path(path).read_bytes() if Path(path).is_file() else None
        super().unlink(path)
        self._record(Path(path).parent, ("unlink", Path(path).name, data))
        self._measure()

    def sync_dir(self, path):
        super().sync_dir(path)
        identity = self._identity(path)
        self.pending = [entry for entry in self.pending if entry[0] != identity]

    def abandon(self) -> None:
        for fd in list(self.paths):
            with contextlib.suppress(OSError):
                os.close(fd)
        self.paths.clear()


def _resolve(root: Path, identity: tuple) -> Path | None:
    """The current path of a directory identity under `root`, re-resolved on every call (L6)."""
    for directory, _subdirs, _files in os.walk(root):
        try:
            status = os.stat(directory)
        except OSError:
            continue
        if (status.st_dev, status.st_ino) == identity:
            return Path(directory)
    return None


def host_loss_names(ops: PreserveOps) -> None:
    """Simulated M-2: unsynced segment bytes are cut back; pending namespace changes are undone, newest first.

    A change whose directory no longer resolves (removed with an unfenced
    ancestor) is skipped: nothing is resurrected under a removed directory.
    """
    for path, size in ops.durable.items():
        if os.path.exists(path) and os.path.getsize(path) > size:
            os.truncate(path, size)
    for identity, change in reversed(ops.pending):
        directory = _resolve(ops.root, identity)
        if directory is None:
            continue
        kind = change[0]
        if kind == "new":
            target = directory / change[1]
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
        elif kind == "rename":
            _kind, source, name, before, is_dir = change
            target = directory / name
            if is_dir:
                if target.exists():
                    os.rename(target, directory / source)
            elif before is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(before)
        elif kind == "unlink":
            _kind, name, data = change
            if data is not None:
                (directory / name).write_bytes(data)
    ops.pending = []


def usage(session_dir: Path) -> tuple[int, int]:
    """(files, logical bytes) under session/preserved/."""
    preserved = Path(session_dir) / "preserved"
    files = total = 0
    if preserved.is_dir():
        for path in preserved.rglob("*"):
            if path.is_file() and not path.is_symlink():
                files += 1
                total += path.lstat().st_size
    return files, total


class NoSyncOps(cp.DurableOps):
    """For building a fixture only: no durability is claimed for these appends."""

    def fsync(self, fd):
        pass

    def sync_dir(self, path):
        pass


# ---------------------------------------------------------------------------
# Fixtures: an actual witnessed A14-unbound stop in the production layout
# ---------------------------------------------------------------------------
class HomeRoot(Root):
    """`session = home/session` (chassis.py:610–612): the command's default home is right."""

    def __init__(self, path) -> None:
        super().__init__(path)
        self.home = Path(path)


@dataclass
class Ctx:
    root: HomeRoot
    variant: str
    state: dict  # C_n's state (= the state at the stop), wire form, next_seq normalized to 1
    epoch: int
    witness: dict
    stopped_bytes: bytes
    effects: tuple
    saved_prev: bytes | None
    cb_tuple: dict | None = None

    @property
    def session_dir(self) -> Path:
        return self.root.session_dir

    @property
    def ack_id(self) -> str:
        return sha(self.stopped_bytes + f"\n{A14}\n{BP}".encode())[:32]

    @property
    def sealed(self) -> Path:
        return self.session_dir / "preserved" / self.ack_id

    @property
    def partial(self) -> Path:
        return self.session_dir / "preserved" / f"{self.ack_id}.partial"

    def rel(self, path: Path) -> str:
        return Path(path).relative_to(self.root.path).as_posix()

    def acknowledge(self, ops=None, reason=A14, resolution=BP):
        return st.acknowledge(self.session_dir, reason, resolution, **({"ops": ops} if ops is not None else {}))

    def clone(self, path: Path) -> Ctx:
        shutil.copytree(self.root.path, path, symlinks=True)
        return dataclasses.replace(self, root=HomeRoot(path))


def wire(state: rp.SessionState) -> dict:
    return state.to_wire(next_seq=1)


def effects(root: Root) -> tuple:
    types = root.types()
    return types.count("REQUEST_SENT"), types.count("INVOKING")


def receipts(root: Root) -> list:
    return [r.payload for r in root.records() if r.type_name == "RECOVERY_ACK"]


def build(path: Path, variant: str = "run-end", *, pending_note: bool = True, suffix: str | None = None, extra_run_ends: int = 0):
    """C_n, a state-neutral suffix (unless `suffix` says otherwise), no damage yet."""
    path.mkdir(parents=True, exist_ok=True)
    root = HomeRoot(path)
    cb_tuple = cb_bytes = None
    if variant == "collected-and-rotated":
        session = gc_begin(root)
    elif variant == "older-known-prev":
        opening = root.start()
        opening.session.writer.segment_max = 1  # many small segments; no collection while building
        session = resume(opening)
        respond(session, content="ok")
        session.checkpoint()
        cb_bytes = root.file("conversation.json")
        cb_tuple = gc.checkpoint_tuple([r for r in root.records() if r.type_name == "CHECKPOINT"][-1])
    else:
        session = establish(root)
    if pending_note:
        session.write_note("N1", header=HEADER)
    if variant == "collected-and-rotated":
        tool_turn(session, "r0")
        tool_turn(session, "r1")
    else:
        partial_turn(session, 6)
        if variant == "failed-unknown-request":
            session.send(lambda: None)  # a request with no recorded response: outcome failed_unknown
        session.checkpoint()
        if variant == "older-known-prev":
            session.append_message("user", "more")
            session.checkpoint()
    newest = [r for r in root.records() if r.type_name == "CHECKPOINT"][-1]
    if suffix == "partial-turn":
        partial_turn(session, 4)
    elif suffix == "message":
        session.append_message("user", "after the checkpoint")
    elif suffix == "note-written":
        session.write_note("N2", header=HEADER)
    session.record_run_end(0, "main_returned")
    state, epoch = wire(session.state), session.state.history_epoch
    session.close()
    if suffix == "earlier-receipt":
        append_record(root, "RECOVERY_ACK", {"reason": "x", "resolution": "y"})
    if extra_run_ends:
        scan = cp.scan_segments(cp.read_segments(root.session_dir / "ledger"), LINEAGE)
        writer = cp.LedgerWriter.continue_after(root.session_dir, LINEAGE, scan, ops=NoSyncOps())
        for _ in range(extra_run_ends):
            writer.append("RUN_END", {"exit": 0, "reason": "main_returned"})
        writer.close()
    if variant == "collected-and-rotated":
        later = [r for r in root.records() if r.seq > newest.seq]
        assert any(r.type_name == "GC_INTENT" and r.payload["segments"] for r in later), "non-vacuous: a collection after C_n"
        assert any(r.type_name == "LEDGER_HEADER" for r in later), "non-vacuous: a rotation after C_n"
    return root, state, epoch, cb_tuple, cb_bytes


def plant(root: HomeRoot, *, planted: bool, corrupt_leaf: bool) -> None:
    session_dir = root.session_dir
    if planted:
        (session_dir / "agent-notes.txt").write_bytes(b"an agent's own file X")
        (session_dir / "recap.md").write_bytes(b"an old recap\n")
        (session_dir / ACK_TEMP).write_bytes(b"pre-existing bytes of unproven origin")
        (session_dir / "corrupt").mkdir(exist_ok=True)
        (session_dir / CORRUPT_Y).write_bytes(Y)
    if corrupt_leaf:
        (session_dir / "corrupt").mkdir(exist_ok=True)
        (session_dir / "corrupt" / LEAF_FILE).write_bytes(b"the only entry of its leaf")


def take_stop(root: HomeRoot) -> tuple[bytes, dict]:
    before = root.snapshot()
    opening = root.start()
    assert (opening.stop, opening.classification) == (A14, "A14"), opening
    after = root.snapshot()
    changed = {n for n in set(before) | set(after) if before.get(n) != after.get(n)}
    assert changed == {"session/STOPPED"}, f"the stop changed {changed}"
    stopped = (root.session_dir / "STOPPED").read_bytes()
    witness = json.loads(stopped)["detail"]["witness"]
    assert st.witness_problem(witness, A14) is None
    return stopped, witness


def make(path: Path, variant: str = "run-end", *, pending_note=True, planted=False, corrupt_leaf=False, suffix=None, extra_run_ends=0) -> Ctx:
    root, state, epoch, cb_tuple, cb_bytes = build(path, variant, pending_note=pending_note, suffix=suffix, extra_run_ends=extra_run_ends)
    saved_prev = root.file("conversation.prev.json") if (root.session_dir / "conversation.prev.json").exists() else None
    plant(root, planted=planted, corrupt_leaf=corrupt_leaf)
    (root.session_dir / "conversation.json").write_bytes(DAMAGED)
    (root.session_dir / "conversation.prev.json").write_bytes(cb_bytes if variant == "older-known-prev" else DAMAGED_PREV)
    counts = effects(root)
    stopped, witness = take_stop(root)
    return Ctx(root, variant, state, epoch, witness, stopped, counts, saved_prev, cb_tuple)


def declared(session_dir: Path, home: Path) -> dict:
    """The independent declared inventory, taken before the command: {path: (bytes, (st_dev, st_ino))}.

    Every regular file under session/ outside preserved/, plus HANDOFF.md. No
    name is excluded: snapshot timing alone leaves out what the command creates.
    """
    found = {}
    for path in sorted(Path(session_dir).rglob("*")):
        rel = path.relative_to(session_dir)
        if rel.parts[0] == "preserved" or path.is_symlink() or not path.is_file():
            continue
        status = path.stat()
        found[f"session/{rel.as_posix()}"] = (path.read_bytes(), (status.st_dev, status.st_ino))
    handoff = Path(home) / "HANDOFF.md"
    if handoff.is_file() and not handoff.is_symlink():
        status = handoff.stat()
        found["home/HANDOFF.md"] = (handoff.read_bytes(), (status.st_dev, status.st_ino))
    return found


def inventory_of(ctx: Ctx) -> dict:
    return declared(ctx.session_dir, ctx.root.home)


def set_files(set_dir: Path) -> dict:
    return {p.relative_to(set_dir).as_posix(): p for p in set_dir.rglob("*") if p.is_file()}


def assert_preserved(set_dir: Path, inventory: dict, *, inodes: bool = True) -> None:
    """Exactly the declared files, at their declared bytes, as independent inodes."""
    files = set_files(set_dir)
    assert set(files) - {"MANIFEST"} == set(inventory), sorted(set(files) ^ (set(inventory) | {"MANIFEST"}))
    before = {identity for _data, identity in inventory.values()}
    for rel, (data, _identity) in inventory.items():
        assert files[rel].read_bytes() == data, f"{rel}: preserved bytes differ"
        if inodes:
            status = files[rel].stat()
            assert status.st_nlink == 1 and (status.st_dev, status.st_ino) not in before, f"{rel}: not an independent copy"


def owned(ctx: Ctx) -> list:
    last = ctx.witness["ledger"]["last_seq"]
    return [r for r in ctx.root.records() if r.seq > last and r.type_name != "LEDGER_HEADER"]


def plan_types(ctx: Ctx) -> list[str]:
    return ["RECOVERY_ACK", *(["RECOVERY"] if ctx.variant == "failed-unknown-request" else []), "EXTERNAL_DELETE"]


def expected_state(ctx: Ctx) -> dict:
    state = json.loads(json.dumps(ctx.state))
    state["history_epoch"] = ctx.epoch + 1
    state["recap_folded"] = 0
    if ctx.variant == "failed-unknown-request":
        state["requests"]["last"]["outcome"] = "possible_duplicate_spend"
    return state


def assert_activated(ctx: Ctx, session=None, *, torn: bool = False) -> None:
    """Exactly the frozen plan Π (+ T), the §11 state, nothing left pending, no effect."""
    own = owned(ctx)
    expected = plan_types(ctx) + (["RECOVERY"] if torn else [])
    assert [r.type_name for r in own] == expected, [r.type_name for r in own]
    after = [r for r in ctx.root.records() if r.seq > ctx.witness["ledger"]["last_seq"]]
    assert after[0].seq == ctx.witness["ledger"]["last_seq"] + 1, "physical continuity after the witnessed end"
    receipt = own[0].payload
    assert (receipt["reason"], receipt["resolution"], receipt["ack_id"]) == (A14, BP, ctx.ack_id)
    assert receipt["stop_id"] == ctx.witness["stop_id"]
    manifest = (ctx.sealed / "MANIFEST").read_bytes()
    activation = own[len(plan_types(ctx)) - 1].payload
    assert activation == {
        "epoch": ctx.epoch + 1, "notices": [], "cause": "bootstrap_preserving", "ack_id": ctx.ack_id, "manifest_sha256": sha(manifest),
    }
    if ctx.variant == "failed-unknown-request":
        spend = own[1].payload
        assert spend["kind"] == "possible_duplicate_spend" and spend["detail"]["label"] == ctx.state["requests"]["last"]["label"]
        assert [r.payload.get("kind") for r in own].count("possible_duplicate_spend") == 1, "exactly one spend"
    if torn:
        assert own[-1].payload["kind"] == "torn_incomplete"
    for name in ("STOPPED", "ACKNOWLEDGED", "RECOVERING", "FSYNC_FAILED"):
        assert not (ctx.session_dir / name).exists(), name
    assert effects(ctx.root) == ctx.effects, "no request or tool"
    opened = None
    if session is None:
        opened = ctx.root.start()
        session = opened.session
    try:
        assert wire(session.state) == expected_state(ctx), "§11: every retained fact, one epoch step"
        nxt = ctx.state["requests"]["next"]
        assert session.next_label() == f"{LINEAGE}:{nxt['turn_seq']}:{nxt['attempt']}"
    finally:
        if opened is not None:
            opened.session.close()


def converge(ctx: Ctx, previous: PreserveOps | None = None):
    """Repeat the command while STOPPED is present; start; a second start writes nothing."""
    ops = PreserveOps(ctx.root.path, previous) if previous is not None else None
    if (ctx.session_dir / "STOPPED").exists():
        assert json.loads(ctx.root.file("STOPPED"))["reason"] == A14, ctx.root.stopped()
        ctx.acknowledge(ops)
    opening = ctx.root.start(**({"ops": ops} if ops is not None else {}))
    assert opening.stop is None, opening
    opening.session.close()
    count = len(ctx.root.records())
    again = ctx.root.start()
    assert again.stop is None and again.classification == "A12t", again
    assert len(ctx.root.records()) == count, "the second start wrote records"
    again.session.close()
    return opening


def snapshot_unchanged(ctx: Ctx, call, match: str) -> None:
    before = ctx.root.snapshot()
    with pytest.raises(cp.LedgerError, match=match):
        call()
    assert ctx.root.snapshot() == before, f"{match}: the refused command changed the store"


def armed(ctx: Ctx, previous: PreserveOps | None = None) -> PreserveOps:
    ops = PreserveOps(ctx.root.path, previous)
    ops.armed = True
    return ops


def crash(ctx: Ctx, ops: PreserveOps, action) -> None:
    with pytest.raises(Crash):
        action(ops)
    ops.abandon()


def start_with(ctx: Ctx):
    return lambda ops: ctx.root.start(ops=ops)


def frames(ctx: Ctx, carrier: dict) -> list[bytes]:
    """The exact own frames Π after the witnessed end, for torn-prefix traces."""
    last = ctx.root.records()[-1]
    planned = [("RECOVERY_ACK", st.receipt_payload(carrier))]
    if ctx.variant == "failed-unknown-request":
        last_request = ctx.state["requests"]["last"]
        planned.append(("RECOVERY", {"kind": "possible_duplicate_spend", "detail": {"label": last_request["label"], "next": ctx.state["requests"]["next"]}}))
    manifest = (ctx.sealed / "MANIFEST").read_bytes()
    planned.append(("EXTERNAL_DELETE", {"epoch": ctx.epoch + 1, "notices": [], "cause": "bootstrap_preserving", "ack_id": ctx.ack_id, "manifest_sha256": sha(manifest)}))
    out, seq, chain = [], last.seq + 1, last.chain
    for name, payload in planned:
        frame, chain = cp.encode_frame(seq, name, payload, chain)
        out.append(frame)
        seq += 1
    return out


def append_bytes(ctx: Ctx, data: bytes) -> None:
    with open(ctx.root.segment(), "ab") as handle:
        handle.write(data)


def reseal(value: dict, **changes) -> dict:
    body = {k: v for k, v in value.items() if k != "check"}
    for key, item in changes.items():
        if "." in key:
            outer, inner = key.split(".")
            body[outer] = {**body[outer], inner: item}
        else:
            body[key] = item
    return st._sealed(body)


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def is_temp(name: str) -> bool:
    return name.startswith(".") and name.endswith(".tmp")


# ===========================================================================
# N1–N3: one new epoch, A12's duty-visible path, preservation across later replacement
# ===========================================================================
@pytest.mark.parametrize("variant", ["run-end", "collected-and-rotated", "failed-unknown-request"])
def test_sv028_bootstrap_preserving_starts_exactly_one_new_epoch(tmp_path, variant):
    ctx = make(tmp_path, variant)
    inventory = inventory_of(ctx)
    carrier = ctx.acknowledge()  # the unchanged runtime refuses here ("not implemented")
    assert not (ctx.session_dir / "STOPPED").exists() and (ctx.session_dir / "ACKNOWLEDGED").exists()
    assert carrier["ack_id"] == ctx.ack_id and carrier["witness"] == ctx.witness
    assert receipts(ctx.root) == [] and effects(ctx.root) == ctx.effects, "the command writes no record and sends nothing"
    assert ctx.root.file("conversation.json") == DAMAGED, "Phase A never removes the live conversation"
    assert not ctx.partial.exists()
    assert_preserved(ctx.sealed, inventory)
    # Phase B with live STOPPED absent: the preserved STOPPED binds the stop (L2).
    opening = ctx.root.start()
    assert (opening.classification, opening.stop) == ("BP", None), opening
    assert_activated(ctx, opening.session)
    assert opening.session.messages == []
    opening.session.close()
    assert_preserved(ctx.sealed, inventory)
    count = len(ctx.root.records())
    again = ctx.root.start()
    assert again.classification == "A12t" and len(ctx.root.records()) == count, again
    again.session.close()


@pytest.mark.parametrize("notes", ["pending-note", "no-pending-note"])
def test_sv028_resume_after_activation_matches_the_same_state_a12_path(tmp_path, notes):
    pending = notes == "pending-note"
    ctx = make(tmp_path / "bp", pending_note=pending)
    ctx.acknowledge()
    bp = resume(ctx.root.start())
    bp_messages = list(bp.messages)
    bp.close()
    control, *_rest = build(tmp_path / "a12", pending_note=pending)
    (control.session_dir / "conversation.json").unlink()  # the same state, deleted rather than damaged
    opening = control.start()
    assert opening.classification == "A12", opening
    a12 = resume(opening)
    a12_messages = list(a12.messages)
    a12.close()
    assert bp_messages == a12_messages, "the duty sees exactly what A12 shows"
    assert [m["content"] for m in bp_messages] == ([note("N1")] if pending else ["OPENING"]), (
        "a pending note makes the list nonempty and preempts the opening; without one, the opening runs"
    )


def test_sv028_every_declared_pre_resolution_file_survives_later_ordinary_replacement(tmp_path):
    ctx = make(tmp_path, planted=True)
    inventory = inventory_of(ctx)
    for name in ("session/agent-notes.txt", f"session/{CORRUPT_Y}", f"session/{ACK_TEMP}", "home/HANDOFF.md", "session/recap.md"):
        assert name in inventory, name
    ctx.acknowledge()
    opening = ctx.root.start(collect=True)
    assert opening.classification == "BP", opening
    activation_seq = owned(ctx)[-1].seq
    session = resume(opening)  # the note adopted; checkpoint 1
    session.write_note("N2", header=HEADER)  # replaces the HANDOFF mirror
    chassis.Carried(ctx.session_dir, ctx.root.home).append_recap(["a later fold"])  # replaces recap.md
    session.append_message("user", "later")
    session.checkpoint()  # checkpoint 2: run.json replaced, the conversation rotated into .prev.json
    session.append_message("user", "later still")
    session.checkpoint()  # checkpoint 3
    session.close()
    records = ctx.root.records()
    assert any(r.type_name == "GC_INTENT" and r.seq > activation_seq for r in records), "non-vacuous: an ordinary collection"
    for rel in ("home/HANDOFF.md", "session/recap.md", "session/run.json", "session/conversation.prev.json"):
        live = ctx.root.home / "HANDOFF.md" if rel.startswith("home/") else ctx.session_dir / rel.split("/", 1)[1]
        assert live.read_bytes() != inventory[rel][0], f"{rel} was replaced by ordinary operation"
    (ctx.session_dir / "conversation.json").write_bytes(X)
    again = ctx.root.start(collect=True)
    assert (again.classification, again.stop) == ("A14", None), again
    again.session.close()
    assert (ctx.session_dir / CORRUPT_Y).read_bytes() == X, "the quarantine replaced the planted destination"
    assert_preserved(ctx.sealed, inventory)


def test_sv028_an_older_known_previous_file_is_retained_and_collection_follows_the_reference_graph(tmp_path):
    ctx = make(tmp_path, "older-known-prev")
    inventory = inventory_of(ctx)
    ctx.acknowledge()
    opening = ctx.root.start(collect=True)
    assert opening.classification == "BP", opening
    session = opening.session
    activation_seq = owned(ctx)[-1].seq
    session.append_message("user", "after activation")
    session.checkpoint()
    session.close()
    records = ctx.root.records()
    first = [r for r in records if r.type_name == "CHECKPOINT" and r.seq > activation_seq][0]
    assert first.payload["prev"] == ctx.cb_tuple, "the older known checkpoint in .prev.json is kept and named"
    (intent,) = [r for r in records if r.type_name == "GC_INTENT" and r.seq > first.seq][:1]
    payload = intent.payload
    assert payload["checkpoint_seq"] == first.seq and payload["records_through"] == ctx.cb_tuple["covers_seq"]
    assert payload["segments"], "non-vacuous: whole pre-activation segments were eligible at the first checkpoint"
    for number in payload["segments"]:
        assert not (ctx.session_dir / "ledger" / cp.segment_name(number)).exists()
    floor = payload["records_through"]
    previous = next(r for r in records if r.seq == ctx.cb_tuple["checkpoint_seq"])
    retained = set(first.payload["state"]["blobs_live"]) | set(previous.payload["state"]["blobs_live"])
    for record in records:
        if record.seq > floor:
            retained |= rp.record_refs(record)
    assert not set(payload["blobs"]) & retained, "only blobs outside the reference graph were named"
    assert_preserved(ctx.sealed, inventory)


# ===========================================================================
# N4: pure refusals change nothing
# ===========================================================================
def _readable(ctx):
    (ctx.session_dir / "conversation.json").write_text(json.dumps([{"role": "user", "content": "NEW"}], indent=2) + "\n")


def _previous_base(ctx):
    (ctx.session_dir / "conversation.prev.json").write_bytes(ctx.saved_prev)


def _rewrite_stop(ctx, detail):
    (ctx.session_dir / "STOPPED").write_text(json.dumps({"reason": A14, "detail": detail}, sort_keys=True))


def _drop_note_blob(ctx):
    (blob,) = [entry["blob"] for entry in ctx.state["notes"]["pending"]]
    (ctx.session_dir / "blobs" / blob).unlink()


def _pending_collection(ctx):
    intent = append_record(ctx.root, "GC_INTENT", {"records_through": 0, "checkpoint_seq": 1, "segments": [], "blobs": ["0" * 64]})
    scan = cp.scan_segments(cp.read_segments(ctx.session_dir / "ledger"), LINEAGE)
    _rewrite_stop(ctx, {"witness": reseal(ctx.witness, **{"ledger.last_seq": intent.seq, "ledger.last_chain": intent.chain, "ledger.end_offset": scan.tail_offset})})


ENVELOPE = [
    # (case, fixture kwargs, mutation, call override, token)
    ("suffix-partial-turn", {"suffix": "partial-turn"}, None, {}, "suffix_not_neutral"),
    ("suffix-message", {"suffix": "message"}, None, {}, "suffix_not_neutral"),
    ("suffix-note-written", {"suffix": "note-written"}, None, {}, "suffix_not_neutral"),
    ("suffix-earlier-receipt", {"suffix": "earlier-receipt"}, None, {}, "suffix_not_neutral"),
    ("conversation-readable", {}, _readable, {}, "conversation_readable"),
    ("conversation-absent", {}, lambda ctx: (ctx.session_dir / "conversation.json").unlink(), {}, "conversation_absent"),
    ("conversation-over-bound", {}, "over-bound", {}, "conversation_over_bound"),
    ("previous-base-available", {}, _previous_base, {}, "previous_base_available"),
    ("no-witness", {}, lambda ctx: _rewrite_stop(ctx, None), {}, "no valid witness"),
    ("damaged-witness", {}, lambda ctx: _rewrite_stop(ctx, {"witness": {**ctx.witness, "identity_reserved": 1}}), {}, "no valid witness"),
    ("appended-record", {}, lambda ctx: append_record(ctx.root, "RUN_END", {"exit": 0, "reason": "x"}), {}, "ledger_not_witnessed"),
    ("garbage-tail", {}, lambda ctx: append_bytes(ctx, b"SVL1 0000"), {}, "ledger_not_witnessed"),
    ("identity", {}, lambda ctx: (ctx.session_dir / "IDENTITY").write_bytes(cs.identity_bytes(LINEAGE, ctx.witness["identity_reserved"] + 1)), {}, "identity_not_witnessed"),
    ("state-blob", {}, _drop_note_blob, {}, "state_blob_missing"),
    ("run-json", {}, lambda ctx: (ctx.session_dir / "run.json").write_text(json.dumps(json.loads(ctx.root.file("run.json")))), {}, "run_json_not_witnessed"),
    ("pending-collection", {}, _pending_collection, {}, "collection_pending_or_unauthorized"),
    ("recovering-open", {}, lambda ctx: (ctx.session_dir / "RECOVERING").write_text("{}"), {}, "transaction_open"),
    ("fsync-failed", {}, lambda ctx: (ctx.session_dir / "FSYNC_FAILED").write_text("{}"), {}, "transaction_open"),
    ("foreign-carrier", {}, lambda ctx: (ctx.session_dir / "ACKNOWLEDGED").write_text(json.dumps({"reason": "x"})), {}, "another acknowledgement is pending"),
    ("pair-run-json", {}, None, {"reason": CK5}, "not implemented"),
    ("pair-tail", {}, None, {"reason": "ledger_tail_ambiguous"}, "not implemented"),
    ("pair-ledger-missing", {}, None, {"reason": "ledger_missing"}, "not implemented"),
]


def test_sv028_every_envelope_refusal_names_its_reason_and_changes_nothing(tmp_path):
    for case, kwargs, mutate, call, token in ENVELOPE:
        ctx = make(tmp_path / case, **kwargs)
        with pytest.MonkeyPatch.context() as patch:
            if mutate == "over-bound":
                patch.setattr(st, "CONVERSATION_READ_MAX", len(DAMAGED) - 1)  # [injected]
            elif mutate is not None:
                mutate(ctx)
            snapshot_unchanged(ctx, lambda: ctx.acknowledge(**call), token)


def _own_set_mid_transaction(ctx, predicate):
    ops = armed(ctx)
    ops.crash_when = predicate
    crash(ctx, ops, ctx.acknowledge)
    return ops


SHAPES = [
    ("symlink", lambda ctx: os.symlink("run.json", ctx.session_dir / "link"), "preservation_unsupported_shape"),
    ("ledger-subdirectory", lambda ctx: (ctx.session_dir / "ledger" / "sub").mkdir(), "preservation_unsupported_shape"),
    ("blobs-subdirectory", lambda ctx: (ctx.session_dir / "blobs" / "sub").mkdir(), "preservation_unsupported_shape"),
    ("corrupt-subdirectory", lambda ctx: (ctx.session_dir / "corrupt" / "sub").mkdir(parents=True), "preservation_unsupported_shape"),
    ("unknown-directory", lambda ctx: (ctx.session_dir / "extra").mkdir(), "preservation_unsupported_shape"),
    ("fifo", lambda ctx: os.mkfifo(ctx.session_dir / "fifo"), "preservation_unsupported_shape"),
    ("bad-name", lambda ctx: (ctx.session_dir / "bad name").write_bytes(b"x"), "preservation_unsupported_name"),
    ("symlinked-handoff", lambda ctx: ((ctx.root.home / "HANDOFF.md").unlink(), os.symlink("session/run.json", ctx.root.home / "HANDOFF.md")), "preservation_unsupported_shape"),
    ("foreign-preserved-shape", lambda ctx: (ctx.session_dir / "preserved" / "not-a-set").mkdir(parents=True), "preservation_unsupported_shape"),
    ("both-own-names", lambda ctx: ((ctx.sealed).mkdir(parents=True), ctx.partial.mkdir()), "preserved_set_mismatch"),
]


def test_sv028_every_unsupported_shape_is_refused_before_any_mutation(tmp_path):
    for case, mutate, token in SHAPES:
        ctx = make(tmp_path / case)
        mutate(ctx)
        snapshot_unchanged(ctx, ctx.acknowledge, token)
    # A damaged sealed own set is refused untouched: never repaired or rewritten.
    ctx = make(tmp_path / "damaged-sealed")
    _own_set_mid_transaction(ctx, lambda call, path, frame: call == "open" and Path(path).name.startswith(".ACKNOWLEDGED."))
    assert ctx.sealed.is_dir() and not (ctx.session_dir / "ACKNOWLEDGED").exists()
    target = ctx.sealed / "session" / "run.json"
    target.write_bytes(target.read_bytes()[:-1] + b"#")
    snapshot_unchanged(ctx, ctx.acknowledge, "preserved_set_mismatch")
    # A file in the own unfinished set that the ownership rule does not cover.
    ctx = make(tmp_path / "unowned-scratch")
    _own_set_mid_transaction(ctx, lambda call, path, frame: call == "mkdir" and Path(path).name == "session" and ".partial" in str(path))
    assert (ctx.partial / "MANIFEST").exists()
    (ctx.partial / "random.txt").write_bytes(b"not this transaction's")
    snapshot_unchanged(ctx, ctx.acknowledge, "preserved_scratch_unowned")


# ===========================================================================
# N5: the order of every step and fence
# ===========================================================================
def _index(trace, predicate, start=0) -> int:
    for position in range(start, len(trace)):
        if predicate(trace[position]):
            return position
    raise AssertionError("no such call in the trace")


def test_sv028_the_command_and_the_activation_are_ordered_and_fenced(tmp_path):
    ctx = make(tmp_path)
    inventory = inventory_of(ctx)
    ops = armed(ctx)
    ctx.acknowledge(ops)
    trace = list(ops.trace)
    P, Q, S = "session/preserved", ctx.rel(ctx.partial), ctx.rel(ctx.sealed)
    mkdir_q = _index(trace, lambda t: t[:2] == ("mkdir", Q))
    assert trace[mkdir_q + 1][:2] == ("sync_dir", P), "the set's name is fenced before it is used"
    manifest = _index(trace, lambda t: t[:2] == ("rename", f"{Q}/MANIFEST"))
    assert trace[manifest + 1][:2] == ("sync_dir", Q), "the inventory boundary is the MANIFEST's returned fence"
    first_child = _index(trace, lambda t: t[0] == "mkdir" and t[1].startswith(f"{Q}/"))
    assert manifest < first_child, "the inventory precedes every child directory and copy"
    copies = [i for i, t in enumerate(trace) if t[0] == "rename" and t[1].startswith(f"{Q}/") and t[1] != f"{Q}/MANIFEST"]
    assert {trace[i][1][len(Q) + 1:] for i in copies} == set(inventory)
    for i in copies:
        assert trace[i + 1] == ("sync_dir", trace[i][1].rsplit("/", 1)[0], None), "each copy's name is fenced in its leaf"
    seal = _index(trace, lambda t: t[:2] == ("rename", S))
    window = trace[copies[-1] + 2:seal]  # after the last copy's own leaf fence: E alone
    e_files = {t[1] for t in window if t[0] == "fsync"}
    assert {f"{Q}/{rel}" for rel in [*inventory, "MANIFEST"]} <= e_files, "E fsyncs every set file, reused or new"
    e_dirs = [t[1] for t in window if t[0] == "sync_dir"]
    leaves = [f"{Q}/session/ledger", f"{Q}/session/blobs", f"{Q}/session", f"{Q}/home", Q, P, "session"]
    assert [d for d in e_dirs if d in leaves] == leaves, f"E fences leaves first, then parents: {e_dirs}"
    assert trace[seal + 1][:2] == ("sync_dir", P)
    carrier = _index(trace, lambda t: t[:2] == ("rename", "session/ACKNOWLEDGED"))
    assert seal < carrier and trace[carrier + 1][:2] == ("sync_dir", "session")
    unstop = _index(trace, lambda t: t[:2] == ("unlink", "session/STOPPED"))
    assert carrier < unstop and trace[unstop + 1][:2] == ("sync_dir", "session")
    assert not [t for t in trace if t[0] == "link"], "never a hard link"
    # Phase B.
    ops = armed(ctx)
    ctx.root.start(ops=ops).session.close()
    trace = list(ops.trace)
    fence = _index(trace, lambda t: t[:2] == ("sync_dir", "session"))
    receipt = _index(trace, lambda t: t[0] == "write" and t[2] == "10")
    activation = _index(trace, lambda t: t[0] == "write" and t[2] == "14")
    assert fence < receipt < activation and trace[receipt + 1][0] == "fsync" and trace[activation + 1][0] == "fsync"
    b3 = _index(trace, lambda t: t[:2] == ("sync_dir", "session/ledger"), activation)
    assert any(t[0] == "fsync" and t[1].endswith(".svl") for t in trace[activation + 2:b3]), "B3 fsyncs the owned segment"
    unlink = _index(trace, lambda t: t[:2] == ("unlink", "session/conversation.json"))
    assert b3 < unlink and trace[unlink + 1][:2] == ("sync_dir", "session"), "B3 before the live conversation is removed"
    retire = _index(trace, lambda t: t[:2] == ("unlink", "session/ACKNOWLEDGED"))
    assert unlink < retire and trace[retire - 1][0] == "fsync" and trace[retire + 1][:2] == ("sync_dir", "session")
    identity = [i for i, t in enumerate(trace) if t[1].startswith("session/.IDENTITY.") or t[1] == "session/IDENTITY"]
    assert all(i > retire for i in identity), "no reservation before the carrier is retired"
    assert not [t for t in trace if t[0] == "link"]


# ===========================================================================
# N6–N8: every cut, second interruptions, partial own prefixes
# ===========================================================================
def source_of(ctx: Ctx, rel: str) -> Path:
    return ctx.root.home / "HANDOFF.md" if rel == "home/HANDOFF.md" else ctx.session_dir / rel.split("/", 1)[1]


def cut_invariants(ctx: Ctx, inventory: dict, label: str) -> None:
    """§10, checked immediately after a cut (and after simulated host loss), before any convergence."""
    if not (ctx.session_dir / "conversation.json").exists():
        assert "EXTERNAL_DELETE" in [r.type_name for r in owned(ctx)], f"{label}: the conversation is gone without a durable activation"
    if (ctx.session_dir / "ACKNOWLEDGED").exists():
        assert ctx.sealed.is_dir(), f"{label}: a carrier without its sealed set"
        assert_preserved(ctx.sealed, inventory, inodes=False)
    for rel, (data, _identity) in inventory.items():
        live = source_of(ctx, rel)
        copies = [d / rel for d in (ctx.sealed, ctx.partial) if (d / rel).is_file()]
        assert (live.is_file() and live.read_bytes() == data) or any(c.read_bytes() == data for c in copies), f"{label}: {rel} lost its last copy"


def both_phases(ctx: Ctx):
    def run(ops):
        ctx.acknowledge(ops)
        ctx.root.start(ops=ops).session.close()

    return run


@pytest.mark.parametrize("loss", ["process-death", "host-loss"])
def test_sv028_every_cut_converges_to_one_receipt_and_one_activation(tmp_path, loss):
    base = make(tmp_path / "base", planted=True)
    probe = base.clone(tmp_path / "probe")
    ops = armed(probe)
    both_phases(probe)(ops)
    calls = len(ops.log)
    assert calls > 50, "non-vacuous: both phases were logged"
    for cut in range(calls):
        ctx = base.clone(tmp_path / f"cut-{cut}")
        inventory = inventory_of(ctx)
        ops = armed(ctx)
        ops.crash_at = cut
        crash(ctx, ops, both_phases(ctx))
        label = f"cut {cut} before {ops.log[-1] if ops.log else '-'} ({loss})"
        if loss == "host-loss":
            host_loss_names(ops)
        cut_invariants(ctx, inventory, label)
        try:
            converge(ctx, ops)
            assert_activated(ctx)
            assert_preserved(ctx.sealed, inventory)
        except (AssertionError, cp.LedgerError) as error:
            raise AssertionError(f"{label}: {error}") from error
        shutil.rmtree(ctx.root.path)


def _after_unlink_fence(ops):
    return lambda call, path, frame: (
        len(ops.trace) >= 2 and ops.trace[-1][:2] == ("sync_dir", "session") and ops.trace[-2][:2] == ("unlink", "session/conversation.json")
    )


def activation_readable_then_second_death(ctx: Ctx) -> PreserveOps:
    """SV028-01: P1 dies on the activation's fsync; P2 writes nothing, establishes it (B3), unlinks, fences, dies."""
    ctx.acknowledge()
    p1 = armed(ctx)
    p1.crash_when = lambda call, path, frame: call == "fsync" and frame == "14"
    crash(ctx, p1, start_with(ctx))
    assert "EXTERNAL_DELETE" in [r.type_name for r in owned(ctx)] and ctx.root.file("conversation.json") == DAMAGED
    p2 = armed(ctx, p1)
    p2.crash_when = _after_unlink_fence(p2)
    crash(ctx, p2, start_with(ctx))
    assert not (ctx.session_dir / "conversation.json").exists()
    assert not [t for t in p2.trace if t[0] == "write" and t[1].endswith(".svl")], "the restart wrote no core record"
    host_loss_names(p2)
    return p2


SECOND = {
    "receipt-unsynced/activation-write": (
        "B", lambda ops: lambda call, path, frame: call == "fsync" and frame == "10",
        lambda ops: lambda call, path, frame: call == "write" and frame == "14",
    ),
    "archive-directory-unfenced/inventory-write": (
        "A", lambda ops: lambda call, path, frame: call == "sync_dir" and ops.rel(path) == "session/preserved" and ops.trace and ops.trace[-1][0] == "mkdir",
        lambda ops: lambda call, path, frame: call == "rename" and ops.rel(path).endswith(".partial/MANIFEST"),
    ),
    "conversation-unlink-unfenced/carrier-unlink": (
        "B", lambda ops: _after_unlink_fence_first(ops),
        lambda ops: lambda call, path, frame: call == "unlink" and ops.rel(path) == "session/ACKNOWLEDGED",
    ),
}


def _after_unlink_fence_first(ops):
    """The sync_dir(session) right after the conversation's unlink (the fence itself is the cut)."""
    return lambda call, path, frame: call == "sync_dir" and ops.rel(path) == "session" and ops.trace and ops.trace[-1][:2] == ("unlink", "session/conversation.json")


@pytest.mark.parametrize(
    "cuts",
    ["activation-readable/after-unlink-fence", "receipt-unsynced/activation-write",
     "archive-directory-unfenced/inventory-write", "conversation-unlink-unfenced/carrier-unlink"],
)
def test_sv028_a_second_interruption_then_host_loss_still_converges(tmp_path, cuts):
    ctx = make(tmp_path / "ctx", planted=True)
    inventory = inventory_of(ctx)
    if cuts == "activation-readable/after-unlink-fence":
        p2 = activation_readable_then_second_death(ctx)
        assert "EXTERNAL_DELETE" in [r.type_name for r in owned(ctx)], "B3 returned before the unlink: the activation is durable"
    else:
        phase, first, second = SECOND[cuts]
        if phase == "B":
            ctx.acknowledge()
        action = ctx.acknowledge if phase == "A" else start_with(ctx)
        p1 = armed(ctx)
        p1.crash_when = first(p1)
        crash(ctx, p1, action)
        p2 = armed(ctx, p1)
        p2.crash_when = second(p2)
        crash(ctx, p2, action)
        host_loss_names(p2)
    cut_invariants(ctx, inventory, cuts)
    converge(ctx, p2)
    assert_activated(ctx)
    assert_preserved(ctx.sealed, inventory)


@pytest.mark.parametrize("trace", ["receipt-torn", "spend-torn", "spend-readable", "activation-torn", "carrier-absent-recovering-present"])
def test_sv028_an_own_partial_prefix_composes_with_the_frozen_plan(tmp_path, trace):
    variant = "failed-unknown-request" if trace.startswith("spend") else "run-end"
    ctx = make(tmp_path / "ctx", variant)
    inventory = inventory_of(ctx)
    carrier = ctx.acknowledge()
    own = frames(ctx, carrier)
    torn = trace != "spend-readable"
    if trace in ("receipt-torn", "carrier-absent-recovering-present"):
        fragment = own[0][:70]
        append_bytes(ctx, fragment)
    elif trace == "spend-torn":
        fragment = own[1][:70]
        append_bytes(ctx, own[0] + fragment)
    elif trace == "spend-readable":
        append_bytes(ctx, own[0] + own[1])  # readable, never synced: applied once, never re-derived away
    else:
        fragment = own[-1][:70]
        append_bytes(ctx, own[0] + fragment)
    if trace == "carrier-absent-recovering-present":
        p1 = armed(ctx)
        p1.crash_when = lambda call, path, frame: call == "unlink" and p1.rel(path) == "session/RECOVERING"
        crash(ctx, p1, start_with(ctx))
        assert not (ctx.session_dir / "ACKNOWLEDGED").exists() and (ctx.session_dir / "RECOVERING").exists()
        count = len(ctx.root.records())
        opening = ctx.root.start()  # carrier-free: authenticated by the sealed context alone
        assert (opening.classification, opening.stop) == ("BP", None), opening
        assert len(ctx.root.records()) == count, "the carrier-free start wrote nothing"
        opening.session.close()
    else:
        opening = ctx.root.start()
        assert (opening.classification, opening.stop) == ("BP", None), opening
        opening.session.close()
    assert not (ctx.session_dir / "RECOVERING").exists()
    assert_activated(ctx, torn=torn)
    if torn:
        recovery = owned(ctx)[-1].payload
        assert recovery["detail"]["tail_sha256"] == sha(fragment) and recovery["detail"]["bytes"] == len(fragment)
        assert [n for n in ctx.root.corrupt() if n.startswith("ledger-")], "the torn bytes are kept in corrupt/"
    count = len(ctx.root.records())
    again = ctx.root.start()
    assert again.classification == "A12t" and len(ctx.root.records()) == count
    again.session.close()
    assert_preserved(ctx.sealed, {k: v for k, v in inventory.items()})


# ===========================================================================
# N9–N11: stale permission, conflicts, the real CLI
# ===========================================================================
def test_sv028_stale_or_conflicting_acknowledgements_grant_nothing(tmp_path):
    base = make(tmp_path / "base")
    # Another transaction's carrier is pending: never replaced.
    ctx = base.clone(tmp_path / "other-carrier")
    (ctx.session_dir / "ACKNOWLEDGED").write_text(json.dumps({"reason": "fsync_failed_previous_run", "resolution": CFB, "ack_id": "0" * 32}))
    snapshot_unchanged(ctx, ctx.acknowledge, "another acknowledgement is pending")
    # This carrier pending (STOPPED still present), then the other resolution: refused.
    ctx = base.clone(tmp_path / "this-carrier")
    _own_set_mid_transaction(ctx, lambda call, path, frame: call == "unlink" and Path(path).name == "STOPPED")
    assert (ctx.session_dir / "ACKNOWLEDGED").exists() and (ctx.session_dir / "STOPPED").exists()
    snapshot_unchanged(ctx, lambda: st.acknowledge(ctx.session_dir, A14, CFB), "pending")
    # Repeated after STOPPED's removal: the same carrier, only a fence.
    ctx = base.clone(tmp_path / "repeat")
    first = ctx.acknowledge()
    before = ctx.root.snapshot()
    assert ctx.acknowledge() == first and ctx.root.snapshot() == before
    # Consumed, then repeated: nothing to acknowledge.
    old = (ctx.session_dir / "ACKNOWLEDGED").read_bytes()
    ctx.root.start().session.close()
    snapshot_unchanged(ctx, ctx.acknowledge, "no readable STOPPED")
    # An old carrier over a later stop with the same reason.
    session = resume(ctx.root.start())
    session.close()
    (ctx.session_dir / "conversation.json").write_bytes(DAMAGED)
    stopped, witness = take_stop(ctx.root)
    assert witness["stop_id"] != ctx.witness["stop_id"]
    (ctx.session_dir / "ACKNOWLEDGED").write_bytes(old)
    snapshot_unchanged(ctx, ctx.acknowledge, "another acknowledgement is pending")
    (ctx.session_dir / "STOPPED").unlink()
    count = len(receipts(ctx.root))
    assert ctx.root.start().stop == "acknowledgement_unverified" and len(receipts(ctx.root)) == count
    # Changed between the command and the start: nothing is activated.
    changes = {
        "conversation-repaired": _readable,
        "record-appended": lambda c: append_record(c.root, "RUN_END", {"exit": 0, "reason": "x"}),
        "sealed-byte-flipped": lambda c: (c.sealed / "session" / "IDENTITY").write_bytes(b"{}"),
        "manifest-byte-flipped": lambda c: (c.sealed / "MANIFEST").write_bytes((c.sealed / "MANIFEST").read_bytes()[:-1] + b" "),
        "preserved-stop-binding": _rebound_preserved_stop,
    }
    for name, change in changes.items():
        ctx = base.clone(tmp_path / name)
        ctx.acknowledge()
        change(ctx)
        opening = ctx.root.start()
        assert (opening.stop, opening.classification) == ("acknowledgement_unverified", "ACK"), (name, opening)
        assert receipts(ctx.root) == [] and (ctx.session_dir / "ACKNOWLEDGED").exists(), name
        if name != "conversation-repaired":
            assert ctx.root.file("conversation.json") == DAMAGED, name
        if name == "preserved-stop-binding":
            assert "stop" in opening.detail["problem"], opening.detail
    # An independent FSYNC_FAILED keeps A1's authority; the A1 acknowledgement is refused while this carrier is pending.
    ctx = base.clone(tmp_path / "fsync-failed")
    ctx.acknowledge()
    (ctx.session_dir / "FSYNC_FAILED").write_text("{}")
    assert ctx.root.start().classification == "A1"
    snapshot_unchanged(ctx, lambda: st.acknowledge(ctx.session_dir, "fsync_failed_previous_run", CFB), "pending")


def _rebound_preserved_stop(ctx: Ctx) -> None:
    """The preserved STOPPED replaced, with the MANIFEST entry and the carrier's digest made consistent: only the stop binding is false (L2)."""
    other = json.loads(ctx.stopped_bytes)
    other["reason"] = CK5
    data = json.dumps(other, sort_keys=True).encode()
    (ctx.sealed / "session" / "STOPPED").write_bytes(data)
    manifest = json.loads((ctx.sealed / "MANIFEST").read_bytes())
    for entry in manifest["entries"]:
        if entry["path"] == "session/STOPPED":
            entry.update(bytes=len(data), sha256=sha(data))
    manifest["totals"]["bytes"] = sum(entry["bytes"] for entry in manifest["entries"])
    body = canonical(reseal(manifest))
    (ctx.sealed / "MANIFEST").write_bytes(body)
    carrier = json.loads(ctx.root.file("ACKNOWLEDGED"))
    carrier = reseal(carrier, **{"evidence.manifest_sha256": sha(body)})
    (ctx.session_dir / "ACKNOWLEDGED").write_text(json.dumps(carrier, sort_keys=True))


def test_sv028_a_conflict_after_activation_fails_closed(tmp_path):
    ctx = make(tmp_path)
    ctx.acknowledge()
    p1 = armed(ctx)
    p1.crash_when = lambda call, path, frame: call == "unlink" and p1.rel(path) == "session/conversation.json"
    crash(ctx, p1, start_with(ctx))
    assert "EXTERNAL_DELETE" in [r.type_name for r in owned(ctx)]
    _readable(ctx)
    listed = ctx.root.file("conversation.json")
    opening = ctx.root.start()
    assert (opening.stop, opening.classification) == ("acknowledgement_unverified", "ACK"), opening
    assert "conversation_changed" in opening.detail["problem"], opening.detail
    assert ctx.root.file("conversation.json") == listed, "nothing was unlinked"
    assert (ctx.session_dir / "ACKNOWLEDGED").exists(), "the carrier is kept"


def test_sv028_cli_bootstrap_preserving_behind_the_first_request_barrier():
    from stub_model import Reply  # noqa: PLC0415
    from test_chassis_correlation import Loop, assert_stripped  # noqa: PLC0415

    world = Loop([Reply(text="fine", repeat=100)])
    try:
        world.finish(world.popen(ASKS="1"))
        lineage = json.loads((world.session_dir / "run.json").read_text())["lineage_id"]
        assert world.sent() == [f"{lineage}:1:1"]
        (world.session_dir / "conversation.json").write_bytes(DAMAGED)
        (world.session_dir / "conversation.prev.json").write_bytes(DAMAGED_PREV)
        stopped_run = world.popen(ASKS="1")
        out, err = stopped_run.communicate(timeout=60)
        assert stopped_run.returncode == 44, out[-2000:] + err[-2000:]
        stopped = (world.session_dir / "STOPPED").read_bytes()
        record = json.loads(stopped)
        assert record["reason"] == A14 and st.witness_problem(record["detail"]["witness"], A14) is None
        witness_end = record["detail"]["witness"]["ledger"]["last_seq"]
        inventory = declared(world.session_dir, world.world.home)
        traffic = (len(world.opens()), len(world.stub.bodies))
        ack = subprocess.run(
            [sys.executable, str(SERVICES / "chassis.py"), "--acknowledge-stop", A14, "--resolution", BP],
            cwd=str(world.world.work), env=world.env(), capture_output=True, text=True, timeout=60,
        )
        assert ack.returncode == 0, ack.stdout + ack.stderr
        assert (len(world.opens()), len(world.stub.bodies)) == traffic, "the command contacted nothing"
        process, release = world.behind_a_barrier(ASKS="1")
        assert (len(world.opens()), len(world.stub.bodies)) == traffic, "acknowledgement and activation contacted nothing"
        assert not (world.session_dir / "ACKNOWLEDGED").exists() and not (world.session_dir / "STOPPED").exists()
        own = [r for r in world.records() if r.seq > witness_end and r.type_name not in ("LEDGER_HEADER",)]
        assert [r.type_name for r in own][:2] == ["RECOVERY_ACK", "EXTERNAL_DELETE"], [r.type_name for r in own]
        assert own[1].payload["cause"] == "bootstrap_preserving"
        release.touch()
        world.finish(process)
        label = world.sent()[-1]
        assert label == f"{lineage}:2:1", "the next permitted identity"
        assert world.opens()[-1]["client_label"] == label and not world.opens()[-1].get("label_seen_before")
        ack_id = sha(stopped + f"\n{A14}\n{BP}".encode())[:32]
        assert_preserved(world.session_dir / "preserved" / ack_id, inventory)
        assert_stripped(world)
    finally:
        world.close()


# ===========================================================================
# N12–N14: mutation controls, the registry, B3's failure
# ===========================================================================
@pytest.mark.parametrize("mutation", ["hardlinked-copies", "no-neutral-suffix-check", "no-pre-unlink-sync", "plan-from-mutated-replay"])
def test_sv028_mutation_control(tmp_path, mutation, monkeypatch):
    if mutation == "hardlinked-copies":
        ctx = make(tmp_path)
        inventory = inventory_of(ctx)
        monkeypatch.setattr(st, "_write_copy", lambda source, dest, data, ops: os.link(source, dest))
        ctx.acknowledge()
        monkeypatch.undo()
        ctx.root.start().session.close()  # the ordinary append to the active segment
        segment = f"session/ledger/{cp.segment_name(0)}"
        assert (ctx.sealed / segment).read_bytes() != inventory[segment][0], "the linked 'copy' moved with the live file"
        with pytest.raises(AssertionError):
            assert_preserved(ctx.sealed, inventory)
    elif mutation == "no-neutral-suffix-check":
        ctx = make(tmp_path, suffix="message")
        snapshot_unchanged(ctx, ctx.acknowledge, "suffix_not_neutral")
        monkeypatch.setattr(st, "_suffix_problem", lambda records: None)
        with pytest.raises(pytest.fail.Exception):
            with pytest.raises(cp.LedgerError):
                ctx.acknowledge()  # the protecting refusal no longer happens
        opening = ctx.root.start()
        assert opening.classification == "BP" and opening.session.messages == [], "the suffix memory was dropped"
        assert "MSG_APPEND" in [r.type_name for r in ctx.root.records() if r.seq <= ctx.witness["ledger"]["last_seq"]]
        opening.session.close()
    elif mutation == "no-pre-unlink-sync":
        ctx = make(tmp_path)
        monkeypatch.setattr(st._Context, "_establish_owned_durability", lambda self, session, preserving: None)
        p2 = activation_readable_then_second_death(ctx)
        monkeypatch.undo()
        assert not (ctx.session_dir / "conversation.json").exists()
        assert "EXTERNAL_DELETE" not in [r.type_name for r in owned(ctx)], "without B3 the activation was lost"
        with pytest.raises(AssertionError):
            converge(ctx, p2)
    else:
        ctx = make(tmp_path, "failed-unknown-request")
        carrier = ctx.acknowledge()
        own = frames(ctx, carrier)
        append_bytes(ctx, own[0] + own[1])
        real = st.preserving_continuation

        def mutated(newest, suffix, head, **kwargs):
            extra = [r for r in ctx.root.records() if r.seq > head[-1].seq and r.type_name != "LEDGER_HEADER"]
            return real(newest, [*suffix, *extra], head, **kwargs)

        monkeypatch.setattr(st, "preserving_continuation", mutated)
        opening = ctx.root.start()
        assert (opening.stop, opening.classification) == ("acknowledgement_unverified", "ACK"), opening
        assert "own_prefix" in opening.detail["problem"], opening.detail
        with pytest.raises(AssertionError):
            assert_activated(ctx)


def test_sv028_the_registry_is_one_truthful_union(tmp_path):
    from test_chassis_acknowledgements import OTHER_REASONS  # noqa: PLC0415

    expected = {
        ("ledger_tail_ambiguous", "continue-conservative"): "tail",
        ("fsync_failed_previous_run", CFB): "plain",
        ("corrupt_quarantine_full", CFB): "plain",
        (A14, CFB): "witnessed",
        (CK5, CFB): "witnessed",
        (A14, BP): "preserving",
    }
    assert st.RESOLUTION_MECHANISM == expected
    assert st.IMPLEMENTED_RESOLUTIONS == set(expected)
    assert st.WITNESSED_RESOLUTIONS == {(A14, CFB), (CK5, CFB)}
    assert st.PRESERVING_RESOLUTIONS == {(A14, BP)}
    assert st.STOP_WITNESS_RESOLUTIONS == {(A14, CFB), (CK5, CFB), (A14, BP)}
    assert st.WITNESSED_REASONS == {A14, CK5}
    root = HomeRoot(tmp_path)
    establish(root).close()
    refused = 0
    for reason in OTHER_REASONS:
        for resolution in (CFB, BP, "continue-conservative"):
            if (reason, resolution) in expected:
                continue
            (root.session_dir / "STOPPED").write_text(json.dumps({"reason": reason, "detail": None}))
            before = root.snapshot()
            with pytest.raises(cp.LedgerError, match="not implemented"):
                st.acknowledge(root.session_dir, reason, resolution)
            assert root.snapshot() == before, (reason, resolution)
            refused += 1
    assert refused == len(OTHER_REASONS) * 3 - len(expected)


def test_sv028_a_failed_pre_unlink_sync_leaves_the_conversation_and_takes_the_persistence_boundary(tmp_path):
    ctx = make(tmp_path)
    ctx.acknowledge()
    p1 = armed(ctx)
    p1.crash_when = lambda call, path, frame: call == "fsync" and frame == "14"
    crash(ctx, p1, start_with(ctx))
    p2 = armed(ctx, p1)
    p2.fail_when = lambda call, path, frame: OSError(errno.EIO, "injected") if call == "fsync" and frame == "14" else None
    with pytest.raises(cp.PersistenceFailure):
        ctx.root.start(ops=p2)
    p2.abandon()
    assert ctx.root.file("conversation.json") == DAMAGED, "B3 failed: the live conversation is untouched"
    assert (ctx.session_dir / "FSYNC_FAILED").exists()
    assert ctx.root.start().classification == "A1"


# ===========================================================================
# N15: capacity and serialization bounds
# ===========================================================================
def _copy_temp_fsync(ops):
    return lambda call, path, frame: call == "fsync" and ".partial/" in str(path) and is_temp(Path(path).name) and not Path(path).name.startswith(".MANIFEST.")


@pytest.mark.parametrize(
    "case", ["repeated-copy-temp-crashes", "rewrite-peak", "manifest-exact-limit", "manifest-over-limit", "long-neutral-suffix", "cap-boundary"]
)
def test_sv028_capacity_and_serialization_bounds(tmp_path, case, monkeypatch):
    if case == "long-neutral-suffix":
        short = make(tmp_path / "one")
        long_ = make(tmp_path / "many", extra_run_ends=2000)
        small, large = short.acknowledge(), long_.acknowledge()
        assert large["evidence"]["suffix"]["count"] == small["evidence"]["suffix"]["count"] + 2000
        size_small, size_large = (len(json.dumps(c, sort_keys=True)) for c in (small, large))
        assert abs(size_large - size_small) <= 16 and size_large <= cp.MAX_MARKER_READ, (
            "the carrier's size is independent of the suffix length (count and digest), up to decimal width"
        )
        return
    base = make(tmp_path / "base", planted=True)
    inventory_size = None
    if case in ("manifest-exact-limit", "manifest-over-limit", "cap-boundary"):
        probe = base.clone(tmp_path / "probe")
        probe.acknowledge()
        manifest_size = len((probe.sealed / "MANIFEST").read_bytes())
        final = usage(probe.session_dir)
        inventory_size = (manifest_size, final)
    if case == "repeated-copy-temp-crashes":
        ctx = base.clone(tmp_path / "ctx")
        samples = []
        previous = None
        for _death in range(5):
            ops = armed(ctx, previous)
            ops.usage_log = samples
            ops.crash_when = _copy_temp_fsync(ops)
            crash(ctx, ops, ctx.acknowledge)
            temps = [p for p in ctx.partial.rglob("*") if p.is_file() and is_temp(p.name)]
            assert len(temps) == 1, f"each death leaves only its own in-flight temp: {temps}"
            previous = ops
        ops = PreserveOps(ctx.root.path, previous)
        ops.usage_log = samples
        ctx.acknowledge(ops)
        final = usage(ctx.session_dir)
        assert max(f for _p, f, _b in samples) <= final[0] and max(b for _p, _f, b in samples) <= final[1], "never above the computed peak"
        converge(ctx)
    elif case == "rewrite-peak":
        ctx = base.clone(tmp_path / "ctx")
        _own_set_mid_transaction(ctx, lambda call, path, frame: call == "rename" and Path(path).name == ctx.ack_id)
        copy = ctx.partial / "session" / "agent-notes.txt"
        copy.write_bytes(copy.read_bytes()[:-1] + b"#")  # same size: F == U
        before = usage(ctx.session_dir)
        ops = armed(ctx)
        ops.usage_log = []
        ctx.acknowledge(ops)
        rel = ctx.rel(copy)
        removed = _index(ops.trace, lambda t: t[:2] == ("unlink", rel))
        written = _index(ops.trace, lambda t: t[0] == "open" and t[1].startswith(rel.rsplit("/", 1)[0] + "/.agent-notes.txt."))
        assert removed < written, "the mismatching destination is deleted before its replacement's temp"
        assert max(f for _p, f, _b in ops.usage_log) <= before[0] and max(b for _p, _f, b in ops.usage_log) <= before[1]
        converge(ctx)
    elif case == "manifest-exact-limit":
        ctx = base.clone(tmp_path / "ctx")
        monkeypatch.setattr(st, "MANIFEST_READ_MAX", inventory_size[0])  # [injected]
        ctx.acknowledge()
        converge(ctx)
    elif case == "manifest-over-limit":
        ctx = base.clone(tmp_path / "ctx")
        monkeypatch.setattr(st, "MANIFEST_READ_MAX", inventory_size[0] - 1)  # [injected]
        snapshot_unchanged(ctx, ctx.acknowledge, "preserved_manifest_too_large")
    else:
        files, total = inventory_size[1]
        ctx = base.clone(tmp_path / "exact")
        monkeypatch.setattr(st, "PRESERVED_MAX_BYTES", total)
        ctx.acknowledge()
        ctx = base.clone(tmp_path / "minus-one")
        monkeypatch.setattr(st, "PRESERVED_MAX_BYTES", total - 1)
        snapshot_unchanged(ctx, ctx.acknowledge, "preserved_capacity:bytes")
        # L4: pre-existing over-cap usage that admitted owned cleanup reduces before any allocation.
        monkeypatch.setattr(st, "PRESERVED_MAX_BYTES", total)
        ctx = base.clone(tmp_path / "over-cap")
        _own_set_mid_transaction(ctx, _copy_temp_fsync(None))
        big = ctx.partial / "session" / ".agent-notes.txt.ffffffffffffffff.tmp"
        big.write_bytes(b"\x00" * (total + 1))  # owned-shaped scratch: its live source verifies
        start = usage(ctx.session_dir)
        assert start[1] > total, "U is above the cap"
        ops = armed(ctx)
        ops.usage_log = []
        ctx.acknowledge(ops)
        first_alloc = next(i for i, t in enumerate(ops.trace) if t[0] == "open" and ".partial/" in t[1] and is_temp(Path(t[1]).name))
        cleanup = [i for i, t in enumerate(ops.trace) if t[0] == "unlink" and ".partial/" in t[1]]
        assert len(cleanup) == 2 and max(cleanup) < first_alloc, "every deletion precedes every allocation"
        during = [b for position, _f, b in ops.usage_log if position - 1 < first_alloc]
        assert during == sorted(during, reverse=True), "monotone reduction before any allocation"
        after = [b for position, _f, b in ops.usage_log if position - 1 >= first_alloc]
        assert after and all(b <= total for b in after), "no allocation above the admitted post-cleanup bound"
        final = usage(ctx.session_dir)[1]
        assert max([start[1], *during, *after]) == max(start[1], final) == start[1], "the invocation peak is max(U, F)"
        assert final <= total


# ===========================================================================
# N16–N19: dependency fences, the model, the durable inventory, exact reuse
# ===========================================================================
@pytest.mark.parametrize("case", ["reused-leaf-converges", "omit-reuse-fence-mutation", "eio-before-seal"])
def test_sv028_a_reused_copy_is_fenced_before_the_seal(tmp_path, case, monkeypatch):
    ctx = make(tmp_path / "ctx", corrupt_leaf=True)
    inventory = inventory_of(ctx)
    assert [k for k in inventory if k.startswith("session/corrupt/")] == [f"session/corrupt/{LEAF_FILE}"], "one entry in the leaf"
    leaf = f"{ctx.rel(ctx.partial)}/session/corrupt"
    p1 = armed(ctx)
    p1.crash_when = lambda call, path, frame: call == "sync_dir" and p1.rel(path) == leaf
    crash(ctx, p1, ctx.acknowledge)
    assert (ctx.partial / "session" / "corrupt" / LEAF_FILE).is_file(), "renamed, its leaf fence never returned"
    p2 = armed(ctx, p1)
    if case == "eio-before-seal":
        p2.fail_when = lambda call, path, frame: OSError(errno.EIO, "injected") if call == "sync_dir" and p2.rel(path) == leaf else None
        with pytest.raises(cp.PersistenceFailure):
            ctx.acknowledge(p2)
        assert not ctx.sealed.exists() and not (ctx.session_dir / "ACKNOWLEDGED").exists()
        assert (ctx.session_dir / "STOPPED").exists() and ctx.root.file("conversation.json") == DAMAGED
        assert (ctx.session_dir / "FSYNC_FAILED").exists(), "the best-effort marker was written"
        snapshot_unchanged(ctx, ctx.acknowledge, "transaction_open")
        return
    if case == "omit-reuse-fence-mutation":
        real = st._establish_set

        def omit(set_dir, entries, session_dir, ops):
            original = ops.sync_dir
            ops.sync_dir = lambda path: None if str(path).endswith("/session/corrupt") else original(path)
            try:
                return real(set_dir, entries, session_dir, ops)
            finally:
                del ops.sync_dir

        monkeypatch.setattr(st, "_establish_set", omit)
    ctx.acknowledge(p2)
    monkeypatch.undo()
    assert not [p for p in p2.created if p.startswith(leaf + "/")], "the reuse branch: no new file in that leaf"
    assert not [t for t in p2.trace if t[0] in ("write", "rename") and t[1].startswith(leaf + "/")], "no incidental later write there"
    p3 = armed(ctx, p2)
    opening = ctx.root.start(ops=p3)
    assert opening.classification == "BP", opening
    opening.session.close()
    pending_in_leaf = [_resolve(ctx.root.path, identity) for identity, change in p3.pending if change[0] == "rename" and change[2] == LEAF_FILE]
    host_loss_names(p3)
    entry = ctx.sealed / "session" / "corrupt" / LEAF_FILE
    if case == "reused-leaf-converges":
        assert not pending_in_leaf, "E fenced the reused entry's leaf before the seal"
        assert entry.is_file() and entry.read_bytes() == inventory[f"session/corrupt/{LEAF_FILE}"][0]
        assert_preserved(ctx.sealed, inventory, inodes=False)
        converge(ctx)
    else:
        assert pending_in_leaf and all(str(p).startswith(str(ctx.sealed)) for p in pending_in_leaf), "the pending name followed the ancestor rename"
        assert ctx.sealed.is_dir(), "the seal itself was fenced"
        with pytest.raises(AssertionError):
            assert entry.is_file(), "the reused entry under the sealed name"


def test_sv028_preserve_ops_carries_pending_child_names_across_an_ancestor_rename(tmp_path):
    def setup(root: Path) -> PreserveOps:
        root.mkdir()
        ops = PreserveOps(root)
        ops.mkdir(root / "a")
        ops.mkdir(root / "a" / "b")
        ops.sync_dir(root)
        ops.sync_dir(root / "a")
        fd = ops.open(root / "a" / "b" / "f", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        ops.write(fd, b"data")
        ops.fsync(fd)
        ops.close(fd)  # its name is pending in b
        return ops

    # 1. The ancestor rename is fenced; the child's name is not: it is lost under the new path.
    ops = setup(tmp_path / "fenced-rename")
    ops.rename(tmp_path / "fenced-rename" / "a", tmp_path / "fenced-rename" / "c")
    ops.sync_dir(tmp_path / "fenced-rename")
    host_loss_names(ops)
    assert (tmp_path / "fenced-rename" / "c" / "b").is_dir() and not (tmp_path / "fenced-rename" / "c" / "b" / "f").exists()
    # 2. The child's directory fenced too: it survives.
    ops = setup(tmp_path / "child-fenced")
    ops.rename(tmp_path / "child-fenced" / "a", tmp_path / "child-fenced" / "c")
    ops.sync_dir(tmp_path / "child-fenced")
    ops.sync_dir(tmp_path / "child-fenced" / "c" / "b")
    host_loss_names(ops)
    assert (tmp_path / "child-fenced" / "c" / "b" / "f").read_bytes() == b"data"
    # 3. An unfenced ancestor rename is reversed; the pending child is re-resolved under the old path (L6).
    ops = setup(tmp_path / "reversed")
    ops.rename(tmp_path / "reversed" / "a", tmp_path / "reversed" / "c")
    host_loss_names(ops)
    assert not (tmp_path / "reversed" / "c").exists() and (tmp_path / "reversed" / "a" / "b").is_dir()
    assert not (tmp_path / "reversed" / "a" / "b" / "f").exists()
    # 4. A removed, unfenced directory takes its fenced descendants with it; nothing is resurrected there.
    root = tmp_path / "removed"
    root.mkdir()
    ops = PreserveOps(root)
    ops.mkdir(root / "d")  # d's name is never fenced in root
    ops.mkdir(root / "d" / "e")
    ops.sync_dir(root / "d")
    fd = ops.open(root / "d" / "e" / "g", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    ops.write(fd, b"x")
    ops.fsync(fd)
    ops.close(fd)
    ops.sync_dir(root / "d" / "e")
    ops.unlink(root / "d" / "e" / "g")  # pending in e: its undo restores g, then d's undo removes all of it
    host_loss_names(ops)
    assert not (root / "d").exists(), "d's own name was never fenced"


def _cut_before_e(ctx: Ctx):
    """The command dies at E's first fsync of a set file: every copy done, nothing established or sealed."""
    _own_set_mid_transaction(
        ctx, lambda call, path, frame: call == "fsync" and ".partial" in str(path) and not is_temp(Path(path).name)
    )
    assert (ctx.partial / "MANIFEST").exists() and not ctx.sealed.exists()


@pytest.mark.parametrize(
    "case",
    ["source-changed-after-copy", "source-missing", "domain-gained-file", "inventory-corrupt", "inventory-foreign-binding",
     "inventory-missing-with-copies", "corrupted-copy-with-verified-source", "pre-existing-acknowledged-temp-preserved",
     "owned-copy-temp-cleanup", "owned-inventory-temp-cleanup"],
)
def test_sv028_the_durable_inventory_binds_every_retry(tmp_path, case):
    ctx = make(tmp_path / "ctx", planted=True)
    inventory = inventory_of(ctx)
    notes = ctx.session_dir / "agent-notes.txt"
    if case in ("source-changed-after-copy", "source-missing", "domain-gained-file", "inventory-corrupt", "inventory-foreign-binding"):
        _cut_before_e(ctx)
        copied = (ctx.partial / "session" / "agent-notes.txt").read_bytes()
        assert copied == inventory["session/agent-notes.txt"][0]
        if case == "source-changed-after-copy":
            notes.write_bytes(b"Y: changed after its copy")
            token = "preserved_source_changed"
        elif case == "source-missing":
            notes.unlink()
            token = "preserved_source_missing"
        elif case == "domain-gained-file":
            (ctx.session_dir / "new-file.txt").write_bytes(b"added later")
            token = "preserved_domain_changed"
        elif case == "inventory-corrupt":
            manifest = ctx.partial / "MANIFEST"
            manifest.write_bytes(manifest.read_bytes()[:-2] + b"0}")
            token = "preserved_inventory_invalid"
        else:
            manifest = ctx.partial / "MANIFEST"
            (ctx.partial / "MANIFEST").write_bytes(canonical(reseal(json.loads(manifest.read_bytes()), stop_sha256="0" * 64)))
            token = "preserved_inventory_invalid"
        snapshot_unchanged(ctx, ctx.acknowledge, token)
        assert (ctx.partial / "session" / "agent-notes.txt").read_bytes() == copied, "the copied original X is kept"
        assert not (ctx.session_dir / "ACKNOWLEDGED").exists() and (ctx.session_dir / "STOPPED").exists()
        assert ctx.root.file("conversation.json") == DAMAGED
        return
    if case == "inventory-missing-with-copies":
        (ctx.partial / "session").mkdir(parents=True)
        (ctx.partial / "session" / "agent-notes.txt").write_bytes(notes.read_bytes())
        snapshot_unchanged(ctx, ctx.acknowledge, "preserved_inventory_missing")
        return
    if case == "corrupted-copy-with-verified-source":
        _cut_before_e(ctx)
        copy = ctx.partial / "session" / "agent-notes.txt"
        copy.write_bytes(b"damaged copy")
        ctx.acknowledge()
    elif case == "pre-existing-acknowledged-temp-preserved":
        ctx.acknowledge()
        manifest = json.loads((ctx.sealed / "MANIFEST").read_bytes())
        assert f"session/{ACK_TEMP}" in [entry["path"] for entry in manifest["entries"]], "inventoried as evidence"
    elif case == "owned-copy-temp-cleanup":
        _own_set_mid_transaction(ctx, lambda call, path, frame: call == "rename" and ".partial/" in str(path) and Path(path).name != "MANIFEST")
        (temp,) = [p for p in ctx.partial.rglob("*") if p.is_file() and is_temp(p.name)]
        ops = armed(ctx)
        ctx.acknowledge(ops)
        assert ("unlink", ctx.rel(temp)) in [t[:2] for t in ops.trace] and not temp.exists(), "exactly the owned temp was removed"
    else:
        _own_set_mid_transaction(ctx, lambda call, path, frame: call == "rename" and Path(path).name == "MANIFEST")
        assert [p.name for p in ctx.partial.iterdir()] and all(p.name.startswith(".MANIFEST.") for p in ctx.partial.iterdir())
        (temp,) = list(ctx.partial.iterdir())
        ops = armed(ctx)
        ctx.acknowledge(ops)
        assert ("unlink", ctx.rel(temp)) in [t[:2] for t in ops.trace] and not temp.exists()
    converge(ctx)
    assert_activated(ctx)
    assert_preserved(ctx.sealed, inventory)
    if case == "pre-existing-acknowledged-temp-preserved":
        assert (ctx.session_dir / ACK_TEMP).read_bytes() == inventory[f"session/{ACK_TEMP}"][0], "never deleted live"


@pytest.mark.parametrize("state", ["complete-partial-before-rename", "rename-unfenced-then-host-loss", "sealed-after-rename-fence"])
def test_sv028_an_equal_manifest_retry_allocates_nothing_at_cap_u(tmp_path, state, monkeypatch):
    ctx = make(tmp_path / "cut", planted=True)
    inventory = inventory_of(ctx)
    ops = armed(ctx)
    if state == "complete-partial-before-rename":
        ops.crash_when = lambda call, path, frame: call == "rename" and Path(path).name == ctx.ack_id
    elif state == "rename-unfenced-then-host-loss":
        ops.crash_when = lambda call, path, frame: call == "sync_dir" and ops.rel(path) == "session/preserved" and ops.trace and ops.trace[-1][:2] == ("rename", ctx.rel(ctx.sealed))
    else:
        # The carrier's own temp in session/ -- not E's read-only open of the planted temp-shaped file's copy.
        ops.crash_when = lambda call, path, frame: (
            call == "open" and Path(path).parent == ctx.session_dir and Path(path).name.startswith(".ACKNOWLEDGED.")
        )
    crash(ctx, ops, ctx.acknowledge)
    if state == "rename-unfenced-then-host-loss":
        host_loss_names(ops)
        assert ctx.partial.is_dir() and not ctx.sealed.exists(), "the unfenced seal was reversed"
    elif state == "sealed-after-rename-fence":
        assert ctx.sealed.is_dir()
    else:
        assert ctx.partial.is_dir() and (ctx.partial / "MANIFEST").exists()
    files, total = usage(ctx.session_dir)
    companions = {name: ctx.clone(tmp_path / name) for name in ("bytes-minus-one", "files-minus-one")}
    monkeypatch.setattr(st, "PRESERVED_MAX_FILES", files)
    monkeypatch.setattr(st, "PRESERVED_MAX_BYTES", total)
    retry = armed(ctx, ops)
    retry.usage_log = []
    ctx.acknowledge(retry)
    assert not [p for p in retry.created if p.startswith("session/preserved/")], "no allocation under preserved/ (no MANIFEST temp)"
    assert not [t for t in retry.trace if t[0] == "write" and t[1].startswith("session/preserved/")]
    assert retry.usage_log and all(sample[1:] == (files, total) for sample in retry.usage_log), "usage stayed exactly U"
    converge(ctx)
    assert_preserved(ctx.sealed, inventory)
    monkeypatch.setattr(st, "PRESERVED_MAX_BYTES", total - 1)
    snapshot_unchanged(companions["bytes-minus-one"], companions["bytes-minus-one"].acknowledge, "preserved_capacity:bytes")
    monkeypatch.setattr(st, "PRESERVED_MAX_BYTES", total)
    monkeypatch.setattr(st, "PRESERVED_MAX_FILES", files - 1)
    snapshot_unchanged(companions["files-minus-one"], companions["files-minus-one"].acknowledge, "preserved_capacity:files")


# ===========================================================================
# L1, L3: the inherited inventory's fence; late failures keep their actual prefix
# ===========================================================================
def test_sv028_a_readable_inherited_inventory_is_established_before_archive_mutation(tmp_path):
    base = make(tmp_path / "base", planted=True)
    for second in ("before-establishment-returns", "after-establishment"):
        ctx = base.clone(tmp_path / second)
        inventory = inventory_of(ctx)
        Q = ctx.rel(ctx.partial)
        p1 = armed(ctx)
        p1.crash_when = lambda call, path, frame: call == "sync_dir" and p1.rel(path) == Q and p1.trace and p1.trace[-1][:2] == ("rename", f"{Q}/MANIFEST")
        crash(ctx, p1, ctx.acknowledge)
        inventory_bytes = (ctx.partial / "MANIFEST").read_bytes()
        p2 = armed(ctx, p1)
        if second == "before-establishment-returns":
            p2.crash_when = lambda call, path, frame: call == "sync_dir" and p2.rel(path) == Q
        else:
            p2.crash_when = lambda call, path, frame: (
                p2.trace and p2.trace[-1][:2] == ("sync_dir", "session") and ("sync_dir", Q) in [t[:2] for t in p2.trace]
            )
        crash(ctx, p2, ctx.acknowledge)
        established = [i for i, t in enumerate(p2.trace) if t[:2] in (("fsync", f"{Q}/MANIFEST"), ("sync_dir", Q))]
        mutations = [i for i, t in enumerate(p2.trace) if t[0] in ("mkdir", "unlink") and t[1].startswith(f"{Q}/")]
        assert established, "the establishment ran"
        assert not mutations or min(mutations) > max(established), "no cleanup or child mkdir before the inventory is established"
        assert not mutations, "the cut came before any archive mutation"
        host_loss_names(p2)
        if second == "after-establishment":
            assert (ctx.partial / "MANIFEST").read_bytes() == inventory_bytes, "the established inventory survives the host loss"
        else:
            assert not [p for p in p2.created if p.startswith(f"{Q}/")], "nothing was created before the establishment returned"
        converge(ctx, p2)
        assert_activated(ctx)
        assert_preserved(ctx.sealed, inventory)


@pytest.mark.parametrize("fence", ["seal-fence", "carrier-fence", "stop-retirement-fence"])
def test_sv028_late_phase_a_io_failure_preserves_the_completed_prefix(tmp_path, fence):
    ctx = make(tmp_path, planted=True)
    inventory = inventory_of(ctx)
    ops = armed(ctx)
    fired = []
    previous = {
        "seal-fence": (("rename", ctx.rel(ctx.sealed)), "session/preserved"),
        "carrier-fence": (("rename", "session/ACKNOWLEDGED"), "session"),
        "stop-retirement-fence": (("unlink", "session/STOPPED"), "session"),
    }[fence]

    def fail(call, path, frame):
        if not fired and call == "sync_dir" and ops.rel(path) == previous[1] and ops.trace and ops.trace[-1][:2] == previous[0]:
            fired.append(len(ops.trace))
            return OSError(errno.EIO, "injected")
        return None

    ops.fail_when = fail
    with pytest.raises(cp.PersistenceFailure):
        ctx.acknowledge(ops)
    ops.abandon()
    later = ops.trace[fired[0] + 1:]
    for call, rel, _frame in later:
        assert "FSYNC_FAILED" in rel or rel == "session" or Path(rel).name.startswith(".ACKNOWLEDGED."), (
            f"only the marker attempt and helper cleanup follow the failure: {call} {rel}"
        )
    assert ctx.sealed.is_dir() and not ctx.partial.exists(), "the completed seal rename stays visible"
    assert_preserved(ctx.sealed, inventory)
    carrier = (ctx.session_dir / "ACKNOWLEDGED").exists()
    stopped = (ctx.session_dir / "STOPPED").exists()
    assert (carrier, stopped) == {"seal-fence": (False, True), "carrier-fence": (True, True), "stop-retirement-fence": (True, False)}[fence]
    assert ctx.root.file("conversation.json") == DAMAGED, "Phase A never removes the live conversation"
    assert (ctx.session_dir / "FSYNC_FAILED").exists(), "the best-effort marker's own write returned here"
    assert receipts(ctx.root) == [] and effects(ctx.root) == ctx.effects


def test_sv028_a_source_change_during_copy_keeps_the_published_inventory_and_prior_copies(tmp_path):
    ctx = make(tmp_path, planted=True)
    inventory = inventory_of(ctx)
    ops = PreserveOps(ctx.root.path)
    real = ops.rename
    stop_copy = f"{ctx.rel(ctx.partial)}/session/STOPPED"

    def rename(source, target):
        real(source, target)
        if ops.rel(target) == stop_copy:
            (ctx.session_dir / "agent-notes.txt").write_bytes(b"changed during the copy")

    ops.rename = rename
    with pytest.raises(cp.LedgerError, match="preserved_source_changed"):
        ctx.acknowledge(ops)
    manifest = (ctx.partial / "MANIFEST").read_bytes()
    paths = [entry["path"] for entry in json.loads(manifest)["entries"]]
    assert "session/agent-notes.txt" in paths and sha(inventory["session/agent-notes.txt"][0]) in manifest.decode()
    earlier = [p for p in paths if p < "session/agent-notes.txt"]
    assert "session/STOPPED" in earlier
    for rel in earlier:
        assert (ctx.partial / rel).read_bytes() == inventory[rel][0], f"{rel}: an earlier copy is kept"
    assert not (ctx.partial / "session" / "agent-notes.txt").exists()
    assert not (ctx.session_dir / "ACKNOWLEDGED").exists() and (ctx.session_dir / "STOPPED").exists()
    assert ctx.root.file("conversation.json") == DAMAGED and receipts(ctx.root) == []
    snapshot_unchanged(ctx, ctx.acknowledge, "preserved_source_changed")
    assert (ctx.partial / "MANIFEST").read_bytes() == manifest, "the published inventory is never rewritten"
