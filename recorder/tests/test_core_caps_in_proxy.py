import email.message
import io
import json
import threading
import urllib.error

import core_caps
import httpx
import proxy
import pytest
import recorder_streams
from recorder_streams import estimate_prompt_tokens

REPLY = {
    "choices": [{"message": {"content": "hi"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
}


@pytest.fixture(autouse=True)
def stream_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-stream-test")
    monkeypatch.delenv("STREAM_UPSTREAM_URL", raising=False)


@pytest.fixture
def transcripts(tmp_path, monkeypatch):
    monkeypatch.setattr(proxy, "TRANSCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(proxy, "TRANSCRIPT_FILE", str(tmp_path / "transcript.jsonl"))
    monkeypatch.setattr(proxy, "PLAIN_TRANSCRIPT_FILE", str(tmp_path / "transcript.txt"))
    monkeypatch.setattr(proxy, "EVENTS_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(proxy, "_active_bindings", set(), raising=False)
    return tmp_path


class _Response:
    status = 200

    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def getheaders(self):
        return [("Content-Type", "application/json")]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def upstream(monkeypatch):
    """A fake upstream that counts its calls and can run a probe while it answers."""
    calls = []

    def forward_open(*args, **kwargs):
        calls.append(args)
        if upstream.during is not None:
            upstream.during()
        return _Response(json.dumps(REPLY).encode("utf-8"))

    upstream.calls = calls
    upstream.during = None
    monkeypatch.setattr(proxy, "forward_open", forward_open)
    return upstream


def _serve(tmp_path, name, **attributes):
    path = str(tmp_path / f"{name}.sock")
    instance = proxy.UnixHTTPServer(path, proxy.ProxyHTTPRequestHandler)
    instance.stream_name = name
    for key, value in attributes.items():
        setattr(instance, key, value)
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    return path, instance


def _post(path, payload):
    transport = httpx.HTTPTransport(uds=path)
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        return client.post("/api/v1/chat/completions", json=payload, timeout=10)


def _stop(instance):
    instance.shutdown()
    instance.server_close()


def test_the_core_socket_refuses_with_429_once_its_hour_is_spent(tmp_path, transcripts, upstream):
    path, instance = _serve(tmp_path, "core", core_caps=core_caps.CoreCaps(1, 10**9))
    try:
        assert _post(path, {"model": "m", "messages": []}).status_code == 200
        refused = _post(path, {"model": "m", "messages": []})
        assert refused.status_code == 429
        assert "request(s) per hour" in refused.json()["error"]["message"]
    finally:
        _stop(instance)
    record = (transcripts / "transcript.jsonl").read_text(encoding="utf-8")
    assert len(record.strip().splitlines()) == 2
    assert "sk-stream-test" not in record
    assert "authorization" not in record.lower()


def test_a_core_refusal_never_reaches_the_upstream(tmp_path, transcripts, upstream):
    path, instance = _serve(tmp_path, "core", core_caps=core_caps.CoreCaps(1, 10**9))
    try:
        _post(path, {"model": "m", "messages": []})
        _post(path, {"model": "m", "messages": []})
    finally:
        _stop(instance)
    assert len(upstream.calls) == 1


def test_the_core_settles_the_reported_usage(tmp_path, transcripts, upstream):
    caps = core_caps.CoreCaps(10, 10**9)
    path, instance = _serve(tmp_path, "core", core_caps=caps)
    try:
        _post(path, {"model": "m", "messages": []})
    finally:
        _stop(instance)
    assert caps.used()["tokens"] == 8


def test_an_upstream_error_settles_the_core_at_zero(tmp_path, transcripts, monkeypatch):
    def refused(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://upstream", 500, "boom", email.message.Message(), io.BytesIO(b"{}")
        )

    monkeypatch.setattr(proxy, "forward_open", refused)
    caps = core_caps.CoreCaps(10, 10**9)
    path, instance = _serve(tmp_path, "core", core_caps=caps)
    try:
        assert _post(path, {"model": "m", "messages": []}).status_code == 500
    finally:
        _stop(instance)
    assert caps.used() == {"requests": 1, "tokens": 0}


def test_a_fleet_refusal_of_a_declared_stream_spends_nothing_of_the_stream_s_hour(
    tmp_path, transcripts, upstream
):
    ledger_path = str(tmp_path / "ledger.jsonl")
    core_caps.FleetLedger(ledger_path, "other", 100).reserve(100)
    registry = recorder_streams.StreamRegistry()
    registry.apply({"aux": {"budget": 10, "token_budget": 5000}}, {})
    fleet = core_caps.FleetLedger(ledger_path, "a", 100)
    path, instance = _serve(tmp_path, "aux", registry=registry, fleet=fleet)
    try:
        response = _post(path, {"model": "m", "messages": []})
    finally:
        _stop(instance)
    assert response.status_code == 429
    assert "across the fleet" in response.json()["error"]["message"]
    stream = registry.state()["streams"]["aux"]
    assert stream["tokens"]["used"] == 0
    assert stream["budget"]["used"] == 0
    assert upstream.calls == []


def test_a_declared_stream_reserves_its_own_allowance_on_the_fleet_ledger(
    tmp_path, transcripts, upstream
):
    registry = recorder_streams.StreamRegistry()
    registry.apply({"aux": {"budget": 10, "token_budget": 5000}}, {})
    fleet = core_caps.FleetLedger(str(tmp_path / "ledger.jsonl"), "a", 10**12)
    held = []
    upstream.during = lambda: held.append(fleet.used())
    payload = {"model": "m", "messages": []}
    path, instance = _serve(tmp_path, "aux", registry=registry, fleet=fleet)
    try:
        assert _post(path, payload).status_code == 200
    finally:
        _stop(instance)
    body = json.dumps(payload).encode("utf-8")
    assert held and 0 < held[0] <= estimate_prompt_tokens(body) + 5000 + 64
    assert fleet.used() == 8


def test_without_caps_the_core_socket_behaves_as_aurora_s(tmp_path, transcripts, upstream):
    path, instance = _serve(tmp_path, "core")
    try:
        first = _post(path, {"model": "m", "messages": []})
        second = _post(path, {"model": "m", "messages": []})
    finally:
        _stop(instance)
    assert first.status_code == second.status_code == 200
    assert len(upstream.calls) == 2
    assert len((transcripts / "transcript.jsonl").read_text().strip().splitlines()) == 2


def test_a_ledger_failure_at_admission_is_a_recorded_503(tmp_path, transcripts, upstream):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.mkdir()
    ledger = core_caps.FleetLedger(str(ledger_path), "a", 10**9)
    caps = core_caps.CoreCaps(10, 10**9, ledger=ledger)
    path, instance = _serve(tmp_path, "core", core_caps=caps, fleet=ledger)
    try:
        response = _post(path, {"model": "m", "messages": []})
    finally:
        _stop(instance)
    assert response.status_code == 503
    assert upstream.calls == []
    assert len((transcripts / "transcript.jsonl").read_text().strip().splitlines()) == 1


def test_a_ledger_failure_after_the_upstream_answered_still_records_the_exchange(
    tmp_path, transcripts, upstream
):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = core_caps.FleetLedger(str(ledger_path), "a", 10**9)
    caps = core_caps.CoreCaps(10, 10**9, ledger=ledger)

    def break_the_ledger():
        ledger_path.unlink()
        ledger_path.mkdir()

    upstream.during = break_the_ledger
    path, instance = _serve(tmp_path, "core", core_caps=caps, fleet=ledger)
    try:
        response = _post(path, {"model": "m", "messages": []})
    finally:
        _stop(instance)
    assert response.status_code == 200
    assert len((transcripts / "transcript.jsonl").read_text().strip().splitlines()) == 1
    assert caps.used()["tokens"] == 8


def test_a_declared_stream_s_fleet_reservation_is_the_composed_one(tmp_path, transcripts, upstream):
    # The stream's declaration, not the agent's request, decides what goes upstream, so the
    # fleet must hold what the stream holds: the composed body's reservation.
    registry = recorder_streams.StreamRegistry()
    registry.apply({"aux": {"budget": 10, "token_budget": 10**6, "max_tokens": 50000}}, {})
    fleet = core_caps.FleetLedger(str(tmp_path / "ledger.jsonl"), "a", 10**12)
    held = []
    upstream.during = lambda: held.append(
        (fleet.used(), registry.state()["streams"]["aux"]["tokens"]["used"])
    )
    path, instance = _serve(tmp_path, "aux", registry=registry, fleet=fleet)
    try:
        assert _post(path, {"model": "m", "messages": [], "max_tokens": 1}).status_code == 200
    finally:
        _stop(instance)
    assert held[0][0] == held[0][1]
    assert held[0][0] > 50000
