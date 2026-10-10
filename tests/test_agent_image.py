"""The agent image, read as text: what goes into the seed, what stays outside it, and who runs it.

`/opt/agent` is the seed every agent boots from and every reseed restores, so what lands there is a
fact about the agent's world. These read `Dockerfile.agent` and `.dockerignore` the way the
reviewer of a change to them would, without building anything.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCKERFILE = (REPO / "Dockerfile.agent").read_text()

RUNTIME_FILES = [
    "agent.py",
    "chassis.py",
    "command_runtime.py",
    "watchdog.py",
    "system_prompt.txt",
    "user_prompt.txt",
]
MOUNTPOINTS = [
    "/work",
    "/state",
    "/shared",
    "/diode",
    "/pump",
    "/build",
    "/telemetry",
    "/llm/sock",
    "/llm/console",
    "/run/agent",
    "/home/agent",
]


def _instructions():
    """Dockerfile instructions with their continuation lines joined."""
    joined = re.sub(r"\\\n\s*", " ", DOCKERFILE)
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _copies():
    """Each COPY as (sources, destination), with any --chown flag dropped."""
    copies = []
    for line in _instructions():
        if not line.startswith("COPY "):
            continue
        words = [word for word in line.split()[1:] if not word.startswith("--")]
        copies.append((words[:-1], words[-1]))
    return copies


def _env():
    values = {}
    for line in _instructions():
        if line.startswith("ENV "):
            for name, value in re.findall(r"([A-Z_]+)=(\S+)", line):
                values[name] = value
    return values


def test_the_agent_image_copies_exactly_the_six_runtime_files_into_the_seed():
    seed = [(sources, dest) for sources, dest in _copies() if dest.rstrip("/") == "/opt/agent"]
    assert len(seed) == 1, seed
    assert seed[0][0] == [f"harness/{name}" for name in RUNTIME_FILES]


def test_the_seed_is_a_repository_with_baseline_and_rescue_tags_and_no_experimental():
    text = " ".join(_instructions())
    assert "git init" in text
    assert 'git config user.email "agent@localhost"' in text
    assert 'git config user.name "agent"' in text
    assert r"printf 'tombstones/\nsession_context.json\n' > .gitignore" in text
    assert "git tag baseline" in text
    assert "git tag rescue" in text
    assert "git tag experimental" not in text


def test_the_pump_and_the_recorder_ship_outside_the_seed():
    copies = _copies()
    assert (["pump/pump.py"], "/usr/local/bin/pump.py") in copies
    recorder = ["recorder/proxy.py", "recorder/recorder_streams.py", "recorder/core_caps.py"]
    assert (recorder, "/usr/local/lib/recorder/") in copies
    for sources, dest in copies:
        if dest.startswith("/opt/agent"):
            assert not any(s.startswith(("pump/", "recorder/")) for s in sources), sources


def test_the_image_runs_as_uid_and_gid_1000():
    text = " ".join(_instructions())
    assert "groupadd --gid 1000 agent" in text
    assert re.search(r"useradd [^&;]*--uid 1000 --gid 1000[^&;]* agent", text)
    users = [line for line in _instructions() if line.startswith("USER ")]
    assert users and all(line == "USER agent" for line in users)


def test_the_environment_keeps_agent_writable_files_off_every_image_owned_process():
    env = _env()
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["HOME"] == "/home/agent"
    assert env["CARGO_HOME"] == "/build/.cargo"
    assert env["CARGO_TARGET_DIR"] == "/build/target"
    assert env["XDG_CACHE_HOME"] == "/build/.cache"


def test_every_mountpoint_is_made_and_owned_by_the_agent():
    made = owned = ""
    for line in _instructions():
        if "mkdir -p" in line:
            made += " " + line
        if "chown" in line:
            owned += " " + line
    for path in MOUNTPOINTS:
        assert re.search(rf"\s{re.escape(path)}(\s|$)", made), f"{path} is not made"
        assert re.search(rf"\s{re.escape(path)}(\s|$)", owned), f"{path} is not owned"


def test_the_image_carries_no_aurora_world():
    for word in ("filigree", "books", "garden", "sense", "video"):
        assert not re.search(rf"\b{word}\b", DOCKERFILE, re.IGNORECASE), word


def test_the_dockerignore_keeps_test_leftovers_and_tests_out_of_the_image():
    lines = {
        line.strip()
        for line in (REPO / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for pattern in (
        "harness/tests/",
        "harness/session_context.json",
        "harness/tombstones/",
        "recorder/tests/",
        "pump/tests/",
    ):
        assert pattern in lines, pattern


def test_the_image_carries_only_the_operator_services():
    copies = [
        line for line in DOCKERFILE.splitlines() if line.startswith("COPY") and "services" in line
    ]
    assert len(copies) == 1, copies
    sources = copies[0].split()[1:-1]
    sources = [s for s in sources if not s.startswith("--")]
    assert sorted(sources) == sorted(
        f"services/{name}.py" for name in ("common", "health", "fleet_monitor", "review")
    )
    assert copies[0].split()[-1] == "/opt/services/"


def test_the_image_carries_no_agent_env():
    assert "agent.env" not in DOCKERFILE


def _stages():
    """The Dockerfile's stages as (name, base, instructions), split at each FROM, comments dropped."""
    stages = []
    for line in _instructions():
        match = re.fullmatch(r"FROM (\S+) AS (\S+)", line)
        if line.startswith("FROM "):
            assert match, f"every stage is named: {line}"
            stages.append((match[2], match[1], []))
        else:
            stages[-1][2].append(line)
    return stages


def _stage_copies(instructions):
    """Each COPY in a stage as (flags, sources, destination)."""
    copies = []
    for line in instructions:
        if line.startswith("COPY "):
            words = line.split()[1:]
            flags = [w for w in words if w.startswith("--")]
            paths = [w for w in words if not w.startswith("--")]
            copies.append((flags, paths[:-1], paths[-1]))
    return copies


BASE_COPY_SOURCES = sorted(
    [
        "requirements-agent.txt",
        *(f"harness/{name}" for name in RUNTIME_FILES),
        "pump/pump.py",
        "recorder/proxy.py",
        "recorder/recorder_streams.py",
        "recorder/core_caps.py",
        "llm_console_seed.json",
        "brief/",
        "services/common.py",
        "services/health.py",
        "services/fleet_monitor.py",
        "services/review.py",
        "containers/entrypoint.sh",
    ]
)


def test_the_agent_image_is_the_default_target_and_carries_nothing_of_the_vehicle():
    # John, 2026-10-10: no risk of information sharing. The agent image is the last stage, so a
    # bare `docker build` of this file is the agent image, and it adds nothing to the base.
    stages = _stages()
    assert [(name, base.split(":")[0].split("@")[0]) for name, base, _ in stages] == [
        ("base", "python"),
        ("vehicle", "base"),
        ("agent", "base"),
    ]
    assert stages[-1][2] == [], stages[-1][2]
    assert [name for name, base, _ in stages if "python:" in base] == ["base"]


def test_the_base_stage_copies_exactly_its_allow_list():
    base = _stages()[0][2]
    sources = sorted(s for _flags, paths, _dest in _stage_copies(base) for s in paths)
    assert sources == BASE_COPY_SOURCES
    assert not {".", "docs/", "containers/"} & set(sources)
    assert not [line for line in base if "/opt/vehicle" in line or "serve_vehicle" in line]


def test_the_vehicle_stage_adds_the_vehicle_and_its_entrypoint_only():
    name, _base, instructions = _stages()[1]
    assert name == "vehicle"
    copies = _stage_copies(instructions)
    assert copies == [
        (["--chown=agent:agent"], ["docs/deep_research/vehicle/"], "/opt/vehicle/"),
        (["--chmod=0755"], ["containers/serve_vehicle.sh"], "/usr/local/bin/serve_vehicle.sh"),
    ], copies
    assert 'ENTRYPOINT ["/usr/local/bin/serve_vehicle.sh"]' in instructions


def test_governance_never_reaches_an_image():
    # governance/ holds the design reasoning and the vehicle's records: the fleet must never see it.
    ignored = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "governance/" in ignored
    assert "governance" not in DOCKERFILE
