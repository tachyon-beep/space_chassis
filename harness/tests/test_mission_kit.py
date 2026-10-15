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


def test_read_path_bounds_what_it_returns_not_only_what_it_reads(tmp_path):
    # Line numbers and replacement characters expand the text; the bound is on the output.
    for name, data in (("lines.txt", b"\n" * 70_000), ("blob.bin", b"\xff" * 70_000)):
        p = tmp_path / name
        p.write_bytes(data)
        out = agent.read_path(str(p))
        assert len(out.encode()) < agent.MISSION_KIT_OUTPUT_LIMIT + 200, name
        assert out.endswith(
            f"[file is 70000 bytes; output stops at {agent.MISSION_KIT_OUTPUT_LIMIT}]"
        ), name


def test_read_path_reads_a_numbered_line_anywhere_in_a_large_file(tmp_path):
    p = tmp_path / "long.txt"
    p.write_text("".join(f"line {i}\n" for i in range(1, 100_001)))
    assert agent.read_path(str(p), 50_000) == "50000: line 50000\n"


def test_read_path_counts_every_line_when_one_is_out_of_range(tmp_path):
    p = tmp_path / "long.txt"
    p.write_text("".join(f"line {i}\n" for i in range(1, 100_001)))
    assert agent.read_path(str(p), 100_001) == (
        "error: line 100001 is out of range; the file has 100000 lines"
    )


def test_read_path_bounds_a_single_numbered_line(tmp_path):
    p = tmp_path / "wide.txt"
    p.write_text("y" * 200_000 + "\n")
    out = agent.read_path(str(p), 1)
    assert len(out.encode()) < agent.MISSION_KIT_OUTPUT_LIMIT + 200
    assert out.endswith(f"[line is longer; output stops at {agent.MISSION_KIT_OUTPUT_LIMIT}]")


def test_write_path_refuses_an_unknown_mode_and_leaves_the_file_alone(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("keep")
    assert agent.write_path(str(p), "x", mode="add") == (
        "error: unknown mode 'add'; use overwrite or append"
    )
    assert p.read_text() == "keep"
