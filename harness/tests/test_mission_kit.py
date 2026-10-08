import agent


def test_read_path_reads_a_file_outside_the_harness_with_line_numbers(tmp_path):
    p = tmp_path / "brief.md"
    p.write_text("one\ntwo\n")
    assert agent.read_path(str(p)) == "1: one\n2: two\n"
    assert agent.read_path(str(p), 2) == "2: two\n"


def test_read_path_bounds_a_large_file_and_says_where_it_stopped(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 200_000)
    out = agent.read_path(str(p))
    assert len(out.encode()) < agent.MISSION_KIT_OUTPUT_LIMIT + 200
    assert out.endswith(
        f"[file is 200000 bytes; output stops at {agent.MISSION_KIT_OUTPUT_LIMIT}]"
    )


def test_read_path_decodes_bytes_that_are_not_utf8(tmp_path):
    p = tmp_path / "raw.bin"
    p.write_bytes(b"ok\xff\xfe\n")
    assert agent.read_path(str(p)).startswith("1: ok")


def test_read_path_on_a_missing_file_is_an_error_string(tmp_path):
    assert agent.read_path(str(tmp_path / "absent")).startswith("error reading ")


def test_write_path_overwrites_then_appends(tmp_path):
    p = tmp_path / "note.txt"
    assert agent.write_path(str(p), "a") == f"wrote 1 bytes to {p}"
    agent.write_path(str(p), "b", mode="append")
    assert p.read_text() == "ab"


def test_write_path_into_a_missing_directory_is_an_error_string(tmp_path):
    out = agent.write_path(str(tmp_path / "no" / "such" / "f"), "x")
    assert out.startswith("error writing ")


def test_run_reports_status_exit_and_both_streams():
    out = agent.run("echo out; echo err >&2; exit 3")
    assert out.splitlines()[:2] == ["status: completed", "exit: 3"]
    assert "stdout:\nout\n" in out
    assert "stderr:\nerr\n" in out


def test_run_reports_a_timeout_and_returns():
    out = agent.run("sleep 30", timeout=1)
    assert out.startswith("status: timeout after 1 s")


def test_run_caps_the_timeout_at_120_seconds(monkeypatch):
    # The cap is command_runtime's COMMAND_TIMEOUT_SECONDS (120), read at call time;
    # lowering it to 1 shows a 900-second request stopping at the cap.
    import command_runtime

    monkeypatch.setattr(command_runtime, "COMMAND_TIMEOUT_SECONDS", 1)
    out = agent.run("sleep 30", timeout=900)
    assert out.startswith("status: timeout after 1 s")


def test_run_rejects_a_timeout_that_is_not_positive():
    assert agent.run("true", timeout=0).startswith("error: timeout must be")


def test_run_marks_truncated_output():
    out = agent.run(f"head -c {agent.MISSION_KIT_OUTPUT_LIMIT + 10} /dev/zero | tr '\\0' x")
    assert "[stdout truncated]" in out


def test_git_works_through_run(tmp_path):
    out = agent.run(f"git init -q {tmp_path} && git -C {tmp_path} status --short")
    assert out.splitlines()[:2] == ["status: completed", "exit: 0"]
