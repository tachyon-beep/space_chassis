"""The generated docker-compose.yml: every agent bound to its own surfaces and nothing else.

scripts/build_compose.py writes the whole file from the volume manifest, and the committed file is
exactly what it writes. These read it through tests/compose_text.py, Aurora's PyYAML-free reader
for the subset the generator emits, so they hold where Docker is not installed.
"""

import re
import sys
from pathlib import Path

import compose_text
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_compose  # noqa: E402

COUNT = 10
TEXT = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
SERVICES = compose_text.services(TEXT)
ROOT_PLACEHOLDER = "${SPACE_VOLUMES_DIR:-./volumes}"
SLUG_VARIABLE = re.compile(r"\$\{FLEET_(\d+)_SLUG:-agent_(\d+)\}")
VENDOR = {"./vendor/registry", "./vendor/cargo-config.toml"}


def _slug(n: int) -> str:
    return f"${{FLEET_{n}_SLUG:-agent_{n}}}"


def _mounts(service: str):
    return compose_text.mount_flags(SERVICES[service])


# ---------- the reader understands both mount syntaxes (Aurora's) ----------


def test_the_reader_parses_a_long_syntax_mount_and_its_bind_options() -> None:
    text = (
        "services:\n"
        "  a:\n"
        "    volumes:\n"
        "      - type: bind\n"
        "        source: ${SPACE_VOLUMES_DIR:-./volumes}/llm_sock_x/data\n"
        "        target: /llm/sock\n"
        "        read_only: true\n"
        "        bind:\n"
        "          create_host_path: false\n"
        "      # a comment between items\n"
        "      - ./vendor/registry:/vendor/registry:ro\n"
        "    tmpfs:\n"
        "      - /work:size=1g,uid=1000,gid=1000\n"
        "    ports:\n"
        '      - "127.0.0.1:${PORT:-8090}:8090"\n'
    )
    body = compose_text.services(text)["a"]

    assert body["volumes"] == [
        {
            "type": "bind",
            "source": "${SPACE_VOLUMES_DIR:-./volumes}/llm_sock_x/data",
            "target": "/llm/sock",
            "read_only": "true",
            "bind": {"create_host_path": "false"},
        },
        "./vendor/registry:/vendor/registry:ro",
    ]
    assert body["tmpfs"] == ["/work:size=1g,uid=1000,gid=1000"]
    assert body["ports"] == ["127.0.0.1:${PORT:-8090}:8090"]
    assert compose_text.mount_flags(body) == [
        ("${SPACE_VOLUMES_DIR:-./volumes}/llm_sock_x/data", "/llm/sock", True),
        ("./vendor/registry", "/vendor/registry", True),
    ]


def test_the_reader_keeps_a_short_named_volume_a_scalar() -> None:
    text = "services:\n  a:\n    volumes:\n      - state:/state\n      - pump:/pump:ro\n"
    body = compose_text.services(text)["a"]

    assert body["volumes"] == ["state:/state", "pump:/pump:ro"]
    assert compose_text.mount_flags(body) == [("state", "/state", False), ("pump", "/pump", True)]


def test_the_reader_attaches_eight_space_keys_to_list_items_alone() -> None:
    text = (
        "services:\n"
        "  a:\n"
        "    build:\n"
        "      args:\n"
        '        X: "2"\n'
        "    volumes:\n"
        "      - type: bind\n"
        "        target: /x\n"
    )
    body = compose_text.services(text)["a"]

    assert body["build"] == {"args": ""}
    assert body["volumes"] == [{"type": "bind", "target": "/x"}]


# ---------- the generated file ----------


def test_the_committed_compose_is_exactly_what_the_generator_writes() -> None:
    assert build_compose.build_text(COUNT) == TEXT


def test_the_fleet_is_ten_agents_and_ten_recorders_beside_the_operator_and_window_services() -> (
    None
):
    expected = {f"agent_{n}" for n in range(1, COUNT + 1)}
    expected |= {f"recorder_{n}" for n in range(1, COUNT + 1)}
    expected |= {"fleet_monitor", "review", "diode", "vehicle"}
    assert set(SERVICES) == expected
    assert re.search(r"^name: space-chassis$", TEXT, re.M)


def test_no_agent_mounts_another_agents_surface() -> None:
    for n in range(1, COUNT + 1):
        for source, target, _read_only in _mounts(f"agent_{n}"):
            for found in SLUG_VARIABLE.findall(source + target):
                assert found == (str(n), str(n)), (n, source, target)
            if source in VENDOR:
                continue
            assert SLUG_VARIABLE.search(source) or source in {f"{ROOT_PLACEHOLDER}/shared/data"}, (
                n,
                source,
            )


def test_only_recorders_mount_the_ledger() -> None:
    for name in SERVICES:
        holds = any("/fleet_ledger/" in source for source, _t, _r in _mounts(name))
        assert holds == name.startswith("recorder_"), name


def test_every_bounded_mount_binds_an_image_data_directory_that_must_exist() -> None:
    image = re.compile(
        r"\$\{SPACE_VOLUMES_DIR:-\./volumes\}/[a-z_]+(_\$\{FLEET_\d+_SLUG:-agent_\d+\})?"
        r"/data(/\$\{FLEET_\d+_SLUG:-agent_\d+\})?"
    )
    for name, body in SERVICES.items():
        for entry in body.get("volumes") or []:
            if isinstance(entry, str):
                continue
            assert image.fullmatch(entry["source"]), (name, entry["source"])
            assert entry["type"] == "bind"
            assert entry["bind"] == {"create_host_path": "false"}, (name, entry)


def test_only_the_read_only_vendor_mounts_and_the_window_services_short_binds_are_outside_the_image_scheme() -> (
    None
):
    for name, body in SERVICES.items():
        for entry in body.get("volumes") or []:
            if not isinstance(entry, str):
                continue
            if name in {"diode", "vehicle"}:
                assert entry == f"{ROOT_PLACEHOLDER}/diode/data:/diode", (name, entry)
            else:
                assert entry.endswith(":ro") and entry.split(":")[0] in VENDOR, (name, entry)


def test_agents_join_only_worknet_and_recorders_only_modelnet() -> None:
    for n in range(1, COUNT + 1):
        assert SERVICES[f"agent_{n}"]["networks"] == ["worknet"]
        assert SERVICES[f"recorder_{n}"]["networks"] == ["modelnet"]


def test_the_agent_runs_read_only_with_its_tmpfs_and_limits() -> None:
    for n in range(1, COUNT + 1):
        body = SERVICES[f"agent_{n}"]
        assert body["read_only"] == "true"
        assert body["init"] == "true"
        assert body["cap_drop"] == ["ALL"]
        assert body["security_opt"] == ["no-new-privileges:true"]
        assert body["tmpfs"] == [
            "/tmp",
            "/work:size=1g,uid=1000,gid=1000",
            "/home/agent:size=256m,uid=1000,gid=1000",
            "/run/agent:size=64m,uid=1000,gid=1000",
        ]
        assert body["mem_limit"] == "${AGENT_MEM:-3g}"
        assert body["cpus"] == "${AGENT_CPUS:-1.0}"
        assert body["pids_limit"] == "1024"


CREDENTIAL = re.compile(r"\$\{[A-Z0-9_]*(API_KEY|_KEY|SECRET|PASSWORD)[A-Z0-9_]*(:-[^}]*)?\}")


def test_the_credential_pattern_separates_limits_from_keys() -> None:
    assert CREDENTIAL.search("${OPENROUTER_API_KEY:-}")
    assert CREDENTIAL.search("${LLM_API_KEY}")
    assert not CREDENTIAL.search("${CONTEXT_WINDOW_TOKENS:-200000}")
    assert not CREDENTIAL.search("${RECORDER_TOKEN_HOURLY_MAX:-1}")


def test_the_agent_environment_carries_no_credential_and_the_dummy_key() -> None:
    for n in range(1, COUNT + 1):
        environment = SERVICES[f"agent_{n}"]["environment"]
        assert environment["OPENROUTER_API_KEY"] == "sk-dummy"
        for name, value in environment.items():
            assert not CREDENTIAL.search(value), (n, name, value)
        assert "LLM_BASE_URL" not in environment


def test_the_recorder_upstream_defaults_empty_so_the_openrouter_key_is_used() -> None:
    for n in range(1, COUNT + 1):
        environment = SERVICES[f"recorder_{n}"]["environment"]
        assert environment["LLM_BASE_URL"] == "${LLM_BASE_URL:-}"
        assert environment["OPENROUTER_API_KEY"] == "${OPENROUTER_API_KEY:-}"
        assert environment["AGENT_SLUG"] == _slug(n)
        assert environment["FLEET_LEDGER_PATH"] == "/ledger/ledger.jsonl"
        assert environment["TRANSCRIPT_DIR"] == "/transcripts"
        assert environment["LLM_SOCKET_PATH"] == "/llm/sock/core.sock"
        assert environment["LLM_CONSOLE_FILE"] == "/llm/console/console.json"
        assert SERVICES[f"recorder_{n}"]["entrypoint"] == [
            "python",
            "/usr/local/lib/recorder/proxy.py",
        ]


def test_each_agent_depends_on_its_own_recorder() -> None:
    for n in range(1, COUNT + 1):
        assert SERVICES[f"agent_{n}"]["depends_on"] == [f"recorder_{n}"]


def test_agents_and_recorders_past_the_first_are_in_the_fleet_profile() -> None:
    for n in range(1, COUNT + 1):
        for name in (f"agent_{n}", f"recorder_{n}"):
            if n == 1:
                assert "profiles" not in SERVICES[name], name
            else:
                assert SERVICES[name]["profiles"] == ["fleet"], name
    assert SERVICES["diode"]["profiles"] == ["diode"]
    assert SERVICES["vehicle"]["profiles"] == ["vehicle"]


def test_every_agent_and_recorder_restarts_unless_stopped() -> None:
    for name, body in SERVICES.items():
        assert body["restart"] == "unless-stopped", name


def test_the_image_is_built_once() -> None:
    builders = [name for name, body in SERVICES.items() if "build" in body]
    assert builders == ["agent_1"]
    assert all(body["image"] == "space-chassis-agent" for body in SERVICES.values())


def test_every_service_logs_with_a_bounded_json_file() -> None:
    for name, body in SERVICES.items():
        assert body["logging"] == {
            "driver": "json-file",
            "options": {"max-size": "10m", "max-file": "5"},
        }, name


def test_the_override_example_is_a_pointer_to_the_generated_smoke_stack() -> None:
    text = (ROOT / "docker-compose.override.example.yml").read_text(encoding="utf-8")
    assert "live/stack.py" in text
    assert compose_text.services(text) == {}


def test_the_window_binds_its_image_data_not_its_mount_point() -> None:
    assert SERVICES["diode"]["volumes"] == [f"{ROOT_PLACEHOLDER}/diode/data:/diode"]


@pytest.mark.parametrize("count", [1, 3])
def test_the_generator_scales_to_a_smaller_fleet(count: int) -> None:
    services = compose_text.services(build_compose.build_text(count))
    assert {name for name in services if name.startswith("agent_")} == {
        f"agent_{n}" for n in range(1, count + 1)
    }


def test_the_recorders_carry_the_plan_4b_settings_with_their_defaults() -> None:
    expected = {
        "RESPONSE_MAX_BYTES": "${RESPONSE_MAX_BYTES:-16777216}",
        "RECORDER_MIN_FREE_BYTES": "${RECORDER_MIN_FREE_BYTES:-67108864}",
        "RECORDER_CLIENT_TIMEOUT": "${RECORDER_CLIENT_TIMEOUT:-600}",
        "RECORDER_DEADLINE_MARGIN": "${RECORDER_DEADLINE_MARGIN:-30}",
        "RECORDER_UPSTREAM_DEADLINE": "${RECORDER_UPSTREAM_DEADLINE:-540}",
        "RECORDER_LATEST_START": "${RECORDER_LATEST_START:-480}",
        "RECORDER_OPERATION_TIMEOUT": "${RECORDER_OPERATION_TIMEOUT:-60}",
    }
    for name, body in SERVICES.items():
        if name.startswith("recorder_"):
            environment = body["environment"]
            for key, value in expected.items():
                assert environment.get(key) == value, (name, key)


def test_the_env_example_documents_every_recorder_setting() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in (
        "REQUEST_MAX_BYTES",
        "RESPONSE_MAX_BYTES",
        "RECORDER_MIN_FREE_BYTES",
        "RECORDER_CLIENT_TIMEOUT",
        "RECORDER_DEADLINE_MARGIN",
        "RECORDER_UPSTREAM_DEADLINE",
        "RECORDER_LATEST_START",
        "RECORDER_OPERATION_TIMEOUT",
    ):
        assert f"{key}=" in text, key
