"""The vehicle's referee moved to its own repository; these are the assertions that could not.

`docs/deep_research/vehicle` is a git submodule of the vehicle's own repository now
(`CRITERION-4-PLAN.md`, option A). The ~311 fixture-breaking tests went with it — they copy the
vehicle folder into a temp directory and break one thing, and the linter must not read anything
outside that folder, so they belong where the folder lives.

What stays here is the residue: the assertions about files that are *space_chassis's* and that the
vehicle's suite is not allowed to reach for.

  * the frozen corpus (`docs/deep_research/*.md`) — the vehicle must not read it, and a test that
    checks the vehicle agrees with a citation has to stand on this side;
  * `contract/diode_probe.py`, the operator side's instrument;
  * the reconciliation README, whose rows are assertions about this repository's files;
  * `docker-compose.yml`, `Dockerfile.agent`, `.dockerignore` and `containers/serve_vehicle.sh` —
    how the vehicle is *served*, which is this repository's business.

The harness below is a copy rather than an import, deliberately: importing the vehicle's test module
would make this suite depend on the submodule's internal shape, and the linter-must-not-read-outside
rule exists precisely to keep the two halves apart.

Run it with the submodule checked out: `git submodule update --init` then `python3 -m pytest -q`.
"""

from __future__ import annotations

import contextlib
import fnmatch
import itertools
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[1]
VEHICLE = REPO / "docs" / "deep_research" / "vehicle"
LINTER = VEHICLE / "tools" / "check_vehicle.py"
FILES = (
    "vehicle.yaml",
    "mission.yaml",
    "coupling.yaml",
    "channels.yaml",
    "presentation.yaml",
)


def run_linter(vehicle_dir: Path, strict: bool = False) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(LINTER), "--dir", str(vehicle_dir)]
    if strict:
        argv.append("--strict")
    return subprocess.run(argv, capture_output=True, text=True, check=False)


_FIXTURE_COUNTER = itertools.count()


def fixture_dir(tmp_path: Path, prefix: str) -> Path:
    """A directory for one broken-copy fixture, unique within the run.

    Nine helpers in this file named their fixture `abs(hash((old, new))) % 10000`, and that is a
    directory named by a *randomised* function: `hash` of a string is salted per process unless
    `PYTHONHASHSEED` is set, and ten thousand buckets for fourteen fixtures collide about once in a
    hundred runs. Two that collide share a destination and the second `shutil.copytree` raises
    `FileExistsError` — which is not a wrong answer about the vehicle, it is a test that cannot
    run, and it was recorded twice as an unreproduced flake before the traceback was caught. A
    counter has no buckets and no salt, and it keeps the prefix a reader greps for.
    """
    return tmp_path / f"{prefix}{next(_FIXTURE_COUNTER)}"


def copy_definition(destination: Path) -> Path:
    """A writable copy of the definition, without the tooling or the prose.

    The domains come too: by round 2 the definition is four top-level files plus one
    directory per landed domain, and a fixture that copied only the first four would let a
    test pass while the thing it claims to test was never read.

    **And the prose comes too, for the same reason, one round later.** The linter now holds the
    folder's own status board against the files it describes (`check_readme_figures`), the method
    table in `plant.md` against `METHODS`, and the fault scheduler's docstring against the domains'
    fault policies (`check_tool_docstrings`). A fixture that copied only the YAML would make every
    one of those checks refuse for absence in every test in this file — which is the same defect
    the domains clause above records, arriving in the fixture that clause was written for. So the
    fixture copies what the linter reads and nothing else: the two prose files and the one tool
    whose docstring makes a claim, not the 750 KB `check_vehicle.py` the fixture is *running*.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy(VEHICLE / name, destination / name)
    for name in ("README.md", "plant.md"):
        shutil.copy(VEHICLE / name, destination / name)
    (destination / "tools").mkdir(exist_ok=True)
    shutil.copy(VEHICLE / "tools" / "faults.py", destination / "tools" / "faults.py")
    domains = VEHICLE / "domains"
    if domains.is_dir():
        shutil.copytree(domains, destination / "domains")
    return destination



def _in_words(n: int) -> str:
    """Enough of a number-to-words conversion for a count in the low hundreds.

    Written rather than imported because the alternative is a dependency the operator-side services
    are not allowed to have, and because the range is small and known: this file's test count, in
    the hundreds, spelled the way the reconciliation README spells it.
    """
    units = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    )
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
    if n < 20:
        return units[n]
    if n < 100:
        return tens[n // 10] + (f"-{units[n % 10]}" if n % 10 else "")
    # **The hundreds digit, which this dropped.** The first version returned a bare "hundred" for a
    # round hundred and the caller prefixed a hard-coded "One", so 200 and 100 spelled the same —
    # and this file reached exactly 200 tests, which is when an ambiguity stops being theoretical.
    # The caller no longer prefixes anything and the digit is spelled here.
    head = f"{units[n // 100]} hundred"
    if n % 100 == 0:
        return head
    return f"{head} {_in_words(n % 100)}"




def _docker_ignores(relative: str) -> str | None:
    """The last `.dockerignore` line that decides `relative`, or None for "nothing does".

    Docker's rule is last-match-wins over ordered patterns, with a leading `!` re-including. This
    reads the file the way the builder does rather than searching it for a substring, which is the
    difference between testing the exclusion and testing that someone typed the path.
    """
    verdict = None
    parts = Path(relative).parts
    for raw in (REPO / ".dockerignore").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line.lstrip("!").rstrip("/")
        if not pattern:
            continue
        # A pattern matches the path itself or any directory above it: `docs/` excludes everything
        # under `docs`, and `!docs/deep_research/vehicle/` is the only way back in.
        candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        if any(
            fnmatch.fnmatchcase(candidate, pattern)
            or fnmatch.fnmatchcase(candidate, pattern + "/**")
            for candidate in candidates
        ):
            verdict = "excluded" if not negated else "included"
    return verdict




def test_the_vehicle_passes_the_contract_probe(tmp_path):
    """The window is frozen, shared, and this is the only thing that proves the vehicle meets it.

    `contract/diode_probe.py` is the repository's instrument for the far side of the wall, and
    until `tools/console.py` existed there was nothing to point it at: the vehicle declared a
    conformance table for §9's twelve checks and had never been walked through one of them. The
    probe is deliberately blind to physics — "it only answers: does the window behave the way the
    world is built to expect?" — so a console that claims batches, writes one result per command,
    republishes its state every cycle and advances telemetry on its own is exactly what it tests.

    The assertion is `0 failed` rather than "exit 0", because the probe exits 0 with skips and the
    skip here is real: no deferring verb is reachable at this phase, so §9 check 9 has nothing to
    test. A test that demanded zero skips would be demanding the probe lie.
    """
    diode = tmp_path / "diode"
    console = subprocess.Popen(
        [
            sys.executable,
            str(VEHICLE / "tools" / "console.py"),
            "--diode-dir",
            str(diode),
            "--slug",
            "probe_target",
            "--poll",
            "0.05",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # **Unbounded, and killed in the `finally`, because a cycle count is a clock and this test
        # needs a vehicle.** The first version ran `--cycles 600`, which is a race: the probe takes
        # about a minute, each cycle costs a fraction of a second, and a console that finishes first
        # leaves the probe doctoring a `state.json` nothing will rewrite and waiting for a result file
        # nothing will write. That is the shape of the one failure this test has ever reported —
        # *"an unknown verb is refused with a result file"* — and it is a test that cannot run rather
        # than a window that is wrong.
        #
        # Wait for everything the window is supposed to contain, because the probe reads the
        # vocabulary from `state.json` and the gates from `HELP.md` *and* `state.json` — and the
        # console announces itself by writing `console.json` **last**, so that a reader attaching
        # at any instant finds a vehicle that can already answer. The first version of the console
        # created the console first and published on its first cycle, and a probe attaching in that
        # gap reported "HELP.md and state.json named none" for a vehicle about to name 226 gates.
        window = diode / "probe_target"
        expected = ("console.json", "state.json", "HELP.md", "pending.json")
        deadline = time.time() + 20
        while time.time() < deadline:
            if all((window / name).exists() for name in expected):
                break
            time.sleep(0.1)
        for name in expected:
            assert (window / name).exists(), f"the console never published {name}"

        probe = subprocess.run(
            [
                sys.executable,
                str(REPO / "contract" / "diode_probe.py"),
                "--diode-dir",
                str(diode),
                "--slug",
                "probe_target",
                "--poll-seconds",
                "0.3",
                "--timeout",
                "15",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode == 0, probe.stdout[-2500:]
        assert "0 failed" in probe.stdout, probe.stdout[-2500:]
        assert "an unknown verb is refused by name" in probe.stdout
        assert "variables survive the claim" in probe.stdout
        # The gate set the probe reads must be the *instantiated* one and nothing else: 226 names,
        # not 58 templates and not 58 verbs mistaken for gates because HELP.md listed them in the
        # form the probe scans.
        gates = re.search(r"gate variables are published\n\s+found (\d+):", probe.stdout)
        assert gates, probe.stdout[-1500:]
        assert int(gates.group(1)) > 200, (
            f"the probe found {gates.group(1)} gate variables; the templates did not expand"
        )
    finally:
        console.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            console.wait(timeout=10)

def test_the_crews_error_model_is_a_distribution(tmp_path):
    """The crew can be wrong, and the model of how was read by nothing — including by arithmetic.

    `display_contract.wrongness` is the vehicle's statement of how a crew report can be wrong: the
    mode the whole crew-as-an-instrument design turns on, since a person who says "it's cold in
    here" when the coldplate is fine is the one sensor that can be wrong without being broken. It
    declares four kinds with a weight each and a note saying one of the four cannot happen here.

    **Nothing read it, and the arithmetic did not survive being read.** 0.4 + 0.3 + 0.2 + 0.1 is
    0.9999999999999999 in binary floating point, and the only reason it is anywhere near one is the
    0.1 attached to `wrong_module` — the kind the note says this vehicle cannot produce. The three
    that can fire summed to 0.9, so the model was not a distribution over anything: a sampler either
    drew the forbidden mode one time in ten, which is the leak the note forbids, or drew the other
    three and left a tenth of the mass unallocated. Which of those the corpus meant was nowhere
    written, because nothing had ever read the numbers.

    The citation was wrong too, and that is the one claim here a test can settle outright by reading
    the document: the four modes are `simulator-design.md`:362-371's crew-as-instrument table, and
    the `source` field named `crew_diode.md`, which carries none of the four names. A linter cannot
    look up whether a source says a thing; a test can, for the citations it knows.

    The rule is three clauses: every kind says whether this vehicle can produce it; the seedable
    weights sum to one; and a kind that cannot happen carries no weight, because a share of the
    distribution spent on an outcome nothing can draw is a share subtracted from the ones that can.
    """
    crew = yaml.safe_load((VEHICLE / "domains" / "crew" / "components.yaml").read_text())
    model = crew["display_contract"]["wrongness"]
    kinds = {str(k["id"]): k for k in model["kinds"]}
    assert len(kinds) == 4, sorted(kinds)
    seedable = {i: k for i, k in kinds.items() if k.get("seedable")}
    assert sorted(seedable) == ["forgot", "misattributed", "misheard"], sorted(seedable)
    total = sum(float(k["weight"]) for k in seedable.values())
    assert total == 1.0, f"the seedable weights sum to {total!r}, not one"
    assert kinds["wrong_module"]["seedable"] is False
    assert "weight" not in kinds["wrong_module"], (
        "the unreachable mode carries a share, which is mass no sampler can spend"
    )

    # The citation, read against the document it names. The frozen specs are inputs: this asserts
    # the corpus points at the right one, not that the spec is right.
    source = str(model["provenance"]["source"])
    assert "simulator-design.md:" in source, source[:120]
    assert "crew_diode.md" not in source, "the source field should name one document, not two"
    design = (REPO / "docs" / "deep_research" / "integration" / "simulator-design.md").read_text()
    assert "forgot, misheard, misattributed, wrong module" in design
    assert "misheard" not in (REPO / "docs" / "deep_research" / "crew_diode.md").read_text()

    # Break a copy: put the forbidden mode's share back into the three that can fire, which is the
    # defect exactly as it stood.
    fixture = copy_definition(fixture_dir(tmp_path, "wrongness_"))
    path = fixture / "domains" / "crew" / "components.yaml"
    doc = yaml.safe_load(path.read_text())
    weights = {"misheard": 0.4, "misattributed": 0.3, "forgot": 0.2}
    for kind in doc["display_contract"]["wrongness"]["kinds"]:
        if kind["id"] in weights:
            kind["weight"] = weights[kind["id"]]
    path.write_text(yaml.safe_dump(doc, sort_keys=False, width=100))

    result = run_linter(fixture)
    assert result.returncode == 1, result.stdout[-1200:]
    assert "summing to 0.9" in result.stdout
    assert "display_contract.wrongness.kinds" in result.stdout

    def rewrite(weights: dict[str, float], forbidden_weight: float | None = None) -> None:
        """Set the model's weights and write the fixture back, for the cases below."""
        doc = yaml.safe_load(path.read_text())
        for kind in doc["display_contract"]["wrongness"]["kinds"]:
            kind.pop("weight", None)
            if kind["id"] in weights:
                kind["weight"] = weights[kind["id"]]
            elif forbidden_weight is not None:
                kind["weight"] = forbidden_weight
        path.write_text(yaml.safe_dump(doc, sort_keys=False, width=100))

    # The other two ways a declared distribution stops being one: a total above one, and a share
    # given back to the mode nothing can draw.
    for weights, forbidden, needle in (
        ({"misheard": 0.5, "misattributed": 0.4, "forgot": 0.3}, None, "summing to 1.2"),
        ({"misheard": 0.4445, "misattributed": 0.3333, "forgot": 0.2222}, 0.1, "cannot produce"),
    ):
        rewrite(weights, forbidden)
        result = run_linter(fixture)
        assert result.returncode == 1, result.stdout[-800:]
        assert needle in result.stdout, result.stdout[-800:]

    # A rounded set is not a structural gap: 0.9999 is what four-place renormalisation gives, and
    # the tolerance exists so the rule catches 0.9 rather than arithmetic the corpus already did.
    rewrite({"misheard": 0.4444, "misattributed": 0.3333, "forgot": 0.2222})
    assert run_linter(fixture).returncode == 0, "a rounded set of weights was refused"

def test_the_changelog_row_for_the_linter_is_held_against_the_linter():
    """A row of prose about the linter, and four of its five countable figures were stale.

    `integration/reconciliation/README.md` carries one row per file, and the row for
    `vehicle/tools/check_vehicle.py` states what the tool is: **294** declared debts, **661**
    `report.refuse` call sites, a **41**-node tick order, **138** severity declarations, and **41**
    named channels with **3** described categories withheld. Counted against the tools, they were
    263, 767, 57, 142 and 38 with none — four stale figures in the sentence a reader uses to size
    the tool, and nothing read any of them. That is this folder's oldest finding (*a declaration no
    tool reads has already drifted*) arriving in the one file the vehicle's README cannot hold: it
    is one directory away, and when the vehicle moves to its own repository it stays behind.

    **So the reader is here rather than in the linter**, which is the same choice this test file
    already makes for that README's test count: the linter must not depend on a file that is not
    part of the vehicle. Every figure is derived rather than repeated — the debts and the node count
    from the linter's own output, the call sites from the tool's source, the severities and the
    withheld split from the corpus — and the reader is exercised against a stale row per figure, so
    a rule that matched nothing could not pass by accident.
    """
    row = next(
        (
            line
            for line in (
                REPO / "docs" / "deep_research" / "integration" / "reconciliation" / "README.md"
            ).read_text().splitlines()
            if line.startswith("| `../../vehicle/tools/check_vehicle.py`")
        ),
        None,
    )
    assert row is not None, "the changelog carries no row for the linter"

    lint = run_linter(VEHICLE)
    assert lint.returncode == 0, lint.stdout[-900:]
    debts = re.search(r"with (\d+) declared debt", lint.stdout).group(1)
    nodes = re.search(r"the node schedule is (\d+) nodes", lint.stdout).group(1)
    calls = str((VEHICLE / "tools" / "check_vehicle.py").read_text().count("report.refuse("))
    thresholds = sum(
        len((yaml.safe_load(path.read_text()) or {}).get("thresholds") or [])
        for path in sorted((VEHICLE / "domains").glob("*/profiles.yaml"))
    )
    named = described = 0
    for path in sorted((VEHICLE / "domains").glob("*/points.yaml")):
        for entry in (yaml.safe_load(path.read_text()) or {}).get("not_published") or []:
            if isinstance(entry, dict) and entry.get("channel"):
                named += 1
            else:
                described += 1

    def stated(text: str) -> dict[str, str]:
        return {
            "debts": re.search(r"(\d+) declared debts?", text).group(1),
            "calls": re.search(r"(\d+) `report\.refuse` call sites", text).group(1),
            "nodes": re.search(r"(\d+)-node tick order", text).group(1),
            "severities": re.search(r"\((\d+) severity declarations", text).group(1),
            "withheld": "/".join(
                re.search(r"(\d+) named channels and (\d+) described categories", text).groups()
            ),
        }

    live = {
        "debts": debts,
        "calls": calls,
        "nodes": nodes,
        "severities": str(thresholds),
        "withheld": f"{named}/{described}",
    }
    assert stated(row) == live, (stated(row), live)

    # And the reader itself, one stale figure at a time: each is replaced by what the row said
    # before this round, and the reader has to notice.
    for key, old, stale in (
        ("debts", f"{debts} declared debts", "294 declared debts"),
        ("calls", f"{calls} `report.refuse` call sites", "661 `report.refuse` call sites"),
        ("nodes", f"{nodes}-node tick order", "41-node tick order"),
        ("severities", f"({thresholds} severity declarations", "(138 severity declarations"),
        (
            "withheld",
            f"{named} named channels and {described} described categories",
            "41 named channels and 3 described categories",
        ),
    ):
        assert old in row, old
        mutated = stated(row.replace(old, stale, 1))
        assert mutated[key] != live[key], f"the reader did not see the stale {key}: {mutated[key]}"

def test_the_vehicle_is_servable_from_the_compose_file(tmp_path):
    """Criterion 3d: the far side of the window has to be a thing the stack can actually run.

    `docker-compose.yml`'s `diode` service is a *slot* — "the implementation is mounted in by
    whoever builds the vehicle" — and for fifty-five rounds nobody built one, so the reference stack
    served nothing and every agent read its own empty directory. This round adds a `vehicle` service
    carrying the console this repository has, and this test is the referee for the four ways that can
    be a working implementation of nothing:

      1. the service is declared but the image cannot contain the vehicle, because `.dockerignore`
         excludes `docs/` and the `COPY` therefore fails — which it did, on the first build;
      2. the window lands beside the agents' mount instead of inside it, so everything works and
         nobody can read it;
      3. the service gets a route to the model network, which is the one hard rule in AGENTS.md;
      4. it serves one slug of its own name while the fleet's ten agents were each handed a
         different one, which is the failure the roster sweep exists to prevent.

    The fourth is checked by *running the script* against a stub vehicle rather than by reading it.
    A grep for `FLEET_` in a shell script proves a string is present and nothing about which
    directories get created; the run above produces exactly the set of windows the fleet would find.
    """
    import os

    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    assert "vehicle" in compose["services"], "the vehicle has no service to run it"
    service = compose["services"]["vehicle"]
    reference = compose["services"]["diode"]

    # **The image can carry it.** Both halves are needed and neither is sufficient: `!docs/...` in
    # the ignore file, and a `COPY` that names the same path. A build that fails is better than a
    # service that runs without a vehicle, but only if somebody runs it.
    assert _docker_ignores("docs/deep_research/vehicle/tools/console.py") != "excluded", (
        "`.dockerignore` keeps the vehicle out of the build context, so the image's COPY fails"
    )
    assert _docker_ignores("docs/deep_research/integration/review-findings.md") == "excluded", (
        "the rest of the corpus is evidence, not runtime, and does not belong in an image"
    )
    dockerfile = (REPO / "Dockerfile.agent").read_text()
    assert "COPY --chown=agent:agent docs/deep_research/vehicle/ /opt/vehicle/" in dockerfile
    assert "containers/serve_vehicle.sh /usr/local/bin/serve_vehicle.sh" in dockerfile
    assert service["entrypoint"] == ["/usr/local/bin/serve_vehicle.sh"], service.get("entrypoint")
    assert service["image"] == reference["image"], "a second image is a second vehicle"
    assert service["profiles"] == ["vehicle"], (
        "a bare `docker compose up` is the cheap one-agent stack; the window must not join it"
    )

    # **The same directory the agents read, and nothing else.** `diode` is the slot and this is the
    # implementation, so the mount list is identical on purpose; the comparison is to the file rather
    # than to a literal, because an agent's own mount moving is exactly the change that would leave
    # this service publishing into an orphan.
    assert service["volumes"] == reference["volumes"], (
        "the window must appear inside the agents' own diode mount, not beside it"
    )
    assert [v for v in service["volumes"] if v.endswith(":/diode")], service["volumes"]
    assert service["networks"] == ["worknet"], (
        "agents join worknet and nothing else; the vehicle obeys the same rule"
    )
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]

    # **The scenario, the seed, and the fallback to the roster.** The service's own environment is
    # where a compose file states a default, and the two that matter are the run's identity and the
    # slug list. `FLEET_SLUGS` rather than one `FLEET_N_SLUG`, because a service that picked agent
    # 1's name would serve exactly one of the ten.
    env = service["environment"]
    assert "nominal" in env["VEHICLE_SCENARIO"] and "VEHICLE_SCENARIO" in env["VEHICLE_SCENARIO"]
    assert env["VEHICLE_SEED"].endswith("-0}")
    assert "FLEET_SLUGS" in env["VEHICLE_SLUGS"], (
        "the default must be the roster, or nine of ten agents read an empty directory"
    )
    assert env["VEHICLE_DIR"] == "/opt/vehicle" and env["DIODE_DIR"] == "/diode"
    assert "restart" in service and service["restart"] == "unless-stopped", (
        "a publisher that exits takes the window down with it"
    )

    # **And the script, run.** A stub vehicle stands in for `/opt/vehicle`: the real console needs
    # PyYAML and the whole corpus, and neither is what is under test here. The stub records its own
    # arguments and then *waits*, because the script's last line is `wait` and a console that exited
    # immediately would make this test prove the opposite of what it claims — that the service
    # returns as soon as its children do.
    vehicle = tmp_path / "opt" / "vehicle"
    (vehicle / "tools").mkdir(parents=True)
    (vehicle / "tools" / "console.py").write_text(
        "import json, os, sys, time\n"
        "argv = sys.argv[1:]\n"
        "slug = argv[argv.index('--slug') + 1]\n"
        "diode = argv[argv.index('--diode-dir') + 1]\n"
        "with open(os.path.join(diode, slug, 'args.json'), 'w') as handle:\n"
        "    json.dump(argv, handle)\n"
        "time.sleep(2)\n"
    )
    diode = tmp_path / "diode"
    (diode / "mackerel").mkdir(parents=True)
    (diode / "not_a_directory").write_text("")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DIODE_", "VEHICLE_", "FLEET_"))
    }
    env.update(
        DIODE_DIR=str(diode),
        VEHICLE_DIR=str(vehicle),
        VEHICLE_SCENARIO="crisis",
        VEHICLE_SEED="7",
        DIODE_POLL_SECONDS="0.05",
        VEHICLE_RING_SLOTS="12",
        FLEET_1_SLUG="mackerel",
        FLEET_2_SLUG="cinnabar",
        FLEET_10_SLUG="scabious",
    )
    process = subprocess.Popen(
        ["sh", str(REPO / "containers" / "serve_vehicle.sh")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        deadline = time.time() + 20
        served = set()
        while time.time() < deadline:
            served = {path.parent.name for path in diode.glob("*/args.json")}
            if len(served) >= 4:
                break
            time.sleep(0.05)
        # The roster's ten names are swept from the environment, the directory that already exists
        # is swept from the mount, and a file in the diode directory is not an agent.
        assert served == {"mackerel", "cinnabar", "scabious", "vehicle"}, (
            f"the sweep served {sorted(served)} for a roster of three and one live directory"
        )
    finally:
        process.terminate()
        process.communicate(timeout=10)
    assert process.returncode is not None

    # Every window's arguments, and the scenario reaching each of them: one console per slug with
    # the run's identity and the ring bound the operator set.
    for slug in ("mackerel", "scabious", "vehicle"):
        argv = json.loads((diode / slug / "args.json").read_text())
        assert argv[argv.index("--slug") + 1] == slug
        assert argv[argv.index("--scenario") + 1] == "crisis", argv
        assert argv[argv.index("--seed") + 1] == "7", argv
        assert argv[argv.index("--ring-slots") + 1] == "12", argv
        assert argv[argv.index("--poll") + 1] == "0.05", argv
        assert argv[argv.index("--cycles") + 1] == "0", (
            "the service must not exit after a fixed number of cycles"
        )

    # An explicit list wins over the roster, which is how an operator serves one window on purpose.
    for path in diode.glob("*/args.json"):
        path.unlink()
    env["VEHICLE_SLUGS"] = "pelican"
    started = time.time()
    served = subprocess.run(
        ["sh", str(REPO / "containers" / "serve_vehicle.sh")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    elapsed = time.time() - started
    # And it *waited*. The stub holds its window open for two seconds, which is the only reason this
    # can tell `wait` from a fork: "a service that forked and returned would be a service whose
    # container exits while its workers keep running", and that is exactly what a script ending in
    # `console.py … &` without the `wait` would do -- return 0 in a tenth of a second with two
    # orphaned consoles still publishing into a volume nothing supervises.
    assert served.returncode == 0, served.stderr
    assert elapsed >= 1.5, f"the script returned in {elapsed:.2f}s without waiting on its consoles"
    assert {path.parent.name for path in diode.glob("*/args.json")} == {"pelican", "vehicle"}, (
        "VEHICLE_SLUGS is an explicit answer and must not be widened by the roster"
    )


def test_the_vehicle_s_presentation_references_resolve_in_this_repository():
    """The vehicle *cites* the contract, the probe and the corpus; this side proves they exist.

    `presentation.yaml` names the frozen contract and the probe that tests it, and `coupling.yaml`
    names the corpus document it was generated from and the design section that fixes its
    provenance rule. Every one of those lives in *this* repository, outside the vehicle's root —
    and the vehicle's own suite may not stat them, which it used to do while the two halves shared
    a root. The boundary moved, so the assertion did: the vehicle asserts the four are named, and
    this asserts the names point at something. A citation that resolves to nothing is the folder's
    oldest finding — *a declaration no tool reads has already drifted* — arriving in the one place
    the vehicle cannot look.
    """
    presentation = yaml.safe_load((VEHICLE / "presentation.yaml").read_text())
    coupling = yaml.safe_load((VEHICLE / "coupling.yaml").read_text())
    for value in (
        presentation["contract"],
        presentation["contract_probe"],
        coupling["generated_from"],
        coupling["provenance_rules"],
    ):
        assert (REPO / str(value).split("#", 1)[0]).exists(), value


def test_the_reconciliation_readme_states_the_vehicle_suite_s_test_count():
    """The one figure about the vehicle's suite that has to be read from *this* side.

    `integration/reconciliation/README.md` carries a row per file, and the row for the vehicle's
    referee states how many tests it holds. That sentence is a claim about the vehicle — and the
    reader of it cannot live in the vehicle, because the reconciliation README is one directory away
    and the vehicle's suite may not read outside its own folder. So this is the residue's job: count
    the tests in the submodule's referee and hold the sentence to it. It said one hundred
    twenty-six while the file held a hundred and thirty-four once, and it was wrong for eight
    rounds; the number is derived here rather than repeated, so adding a test and forgetting the
    sentence fails here rather than in a reader's estimate of the folder.
    """
    reconciliation = (
        REPO / "docs" / "deep_research" / "integration" / "reconciliation" / "README.md"
    ).read_text()
    suite = (VEHICLE / "tests" / "test_vehicle_config.py").read_text()
    mine = len(re.findall(r"^def test_", suite, re.M))
    assert mine > 100, f"the self-count found {mine} tests, which is not this suite's shape"
    # Sentence-initial in the README, so the first letter is capitalised here rather than the
    # helper returning a capital it would have to un-capitalise everywhere else.
    needle = f"{_in_words(mine).capitalize()} tests"
    assert needle in reconciliation, (
        f"the reconciliation README does not say {needle!r} about the vehicle's suite, "
        f"which holds {mine}"
    )
