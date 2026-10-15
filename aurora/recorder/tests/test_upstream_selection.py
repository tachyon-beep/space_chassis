import httpx
import pytest

import chassis
import proxy


@pytest.fixture
def clean_env(monkeypatch):
    for var in (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "STREAM_UPSTREAM_URL",
        "STREAM_BASE_URL",
        "STREAM_API_KEY",
        "HOST_LLM_BASE_URL",
        "HOST_LLM_API_KEY",
        "HOST_OPENROUTER_KEY_SET",
        "HOST_STREAM_BASE_URL",
        "HOST_STREAM_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    # An empty value selects the direct upstream, which is what the existing
    # provider-selection tests below are about.
    monkeypatch.setenv("LLM_SOCKET_PATH", "")
    return monkeypatch


def test_proxy_upstream_defaults_to_openrouter(clean_env):
    assert proxy.upstream_url() == "https://openrouter.ai/api/v1/chat/completions"


def test_proxy_upstream_honors_llm_base_url(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1")
    assert proxy.upstream_url() == "http://host.docker.internal:5000/v1/chat/completions"


def test_proxy_upstream_strips_trailing_slash(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1/")
    assert proxy.upstream_url() == "http://host.docker.internal:5000/v1/chat/completions"


def test_proxy_key_is_openrouter_key_by_default(clean_env):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-real")
    assert proxy.upstream_api_key() == "sk-real"


def test_proxy_key_is_llm_key_when_llm_base_url_set(clean_env):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-real")
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1")
    clean_env.setenv("LLM_API_KEY", "sk-local-key")
    assert proxy.upstream_api_key() == "sk-local-key"


def test_proxy_key_empty_for_no_auth_local_server(clean_env):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-real")
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1")
    assert proxy.upstream_api_key() == ""


def test_stream_upstream_defaults_to_openrouter(clean_env):
    assert proxy.stream_upstream_url() == "https://openrouter.ai/api/v1/chat/completions"


def test_stream_upstream_ignores_llm_base_url(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1")
    assert proxy.stream_upstream_url() == "https://openrouter.ai/api/v1/chat/completions"


def test_stream_upstream_override_reaims_declared_streams(clean_env):
    # The verify harness aims declared streams at its stub with this variable;
    # it is not an operator-facing knob.
    clean_env.setenv("STREAM_UPSTREAM_URL", "http://verify-stub:8199/v1/")
    assert proxy.stream_upstream_url() == "http://verify-stub:8199/v1/chat/completions"


def test_upstream_for_core_follows_the_configured_upstream(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1")
    clean_env.setenv("LLM_API_KEY", "sk-local-key")
    clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    assert proxy.upstream_for("core") == (
        "http://host.docker.internal:5000/v1/chat/completions",
        "sk-local-key",
    )


def test_upstream_for_streams_pins_openrouter_and_its_key(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1")
    clean_env.setenv("LLM_API_KEY", "sk-local-key")
    clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    assert proxy.upstream_for("aux") == (
        "https://openrouter.ai/api/v1/chat/completions",
        "sk-or",
    )


def test_stream_upstream_honors_its_own_base_url(clean_env):
    # Declared streams may be aimed at any OpenAI-compatible upstream, not
    # only OpenRouter.
    clean_env.setenv("STREAM_BASE_URL", "https://api.deepseek.com/v1")
    assert proxy.stream_upstream_url() == "https://api.deepseek.com/v1/chat/completions"


def test_stream_upstream_still_ignores_the_core_upstream(clean_env):
    # A stream upstream is never inherited from core.sock's: pointing both at
    # one place is an operator decision stated twice, never a silent default.
    clean_env.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    clean_env.setenv("LLM_API_KEY", "sk-core")
    assert proxy.stream_upstream_url() == "https://openrouter.ai/api/v1/chat/completions"


def test_the_verify_override_still_wins_over_the_operator_setting(clean_env):
    clean_env.setenv("STREAM_BASE_URL", "https://api.deepseek.com/v1")
    clean_env.setenv("STREAM_UPSTREAM_URL", "http://verify-stub:8199/v1/")
    assert proxy.stream_upstream_url() == "http://verify-stub:8199/v1/chat/completions"


def test_upstream_for_streams_uses_its_own_key_when_aimed_elsewhere(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://host.docker.internal:5000/v1")
    clean_env.setenv("LLM_API_KEY", "sk-local-key")
    clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    clean_env.setenv("STREAM_BASE_URL", "https://api.deepseek.com/v1")
    clean_env.setenv("STREAM_API_KEY", "sk-stream")
    assert proxy.upstream_for("aux") == (
        "https://api.deepseek.com/v1/chat/completions",
        "sk-stream",
    )


def test_a_stream_upstream_may_take_no_key_at_all(clean_env):
    # Mirrors core.sock: an explicit upstream with no key is a no-auth local
    # server, not a misconfiguration.
    clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    clean_env.setenv("STREAM_BASE_URL", "http://host.docker.internal:5000/v1")
    assert proxy.upstream_for("aux") == (
        "http://host.docker.internal:5000/v1/chat/completions",
        "",
    )


def test_chassis_requires_a_key_without_llm_base_url(clean_env):
    with pytest.raises(SystemExit):
        chassis.build_client()


def test_chassis_openrouter_mode(clean_env):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-real")
    clean_env.setenv("LLM_MODEL", "some/model")
    client, model = chassis.build_client()
    assert model == "some/model"
    assert str(client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"


def test_chassis_llm_mode_without_key(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://localhost:5000/v1")
    clean_env.setenv("LLM_MODEL", "local-model")
    client, model = chassis.build_client()
    assert model == "local-model"
    assert str(client.base_url).rstrip("/") == "http://localhost:5000/v1"


def test_chassis_model_defaults_when_llm_model_is_unset(clean_env):
    clean_env.setenv("LLM_BASE_URL", "http://localhost:5000/v1")
    _, model = chassis.build_client()
    assert model == "deepseek/deepseek-v4-pro"


def test_unset_socket_path_selects_socket_mode(clean_env, tmp_path, monkeypatch):
    # The container case: an unset variable must not fall back to a network the
    # container does not have.
    monkeypatch.delenv("LLM_SOCKET_PATH", raising=False)
    clean_env.setenv("OPENROUTER_API_KEY", "sk-real")
    monkeypatch.setattr(chassis, "SOCKET_WAIT_SECONDS", 0)

    with pytest.raises(chassis.EnvironmentFailure):
        chassis.build_client()


def test_present_socket_builds_a_uds_client(clean_env, tmp_path):
    path = tmp_path / "core.sock"
    path.write_bytes(b"")
    clean_env.setenv("OPENROUTER_API_KEY", "sk-real")
    clean_env.setenv("LLM_MODEL", "some/model")
    clean_env.setenv("LLM_SOCKET_PATH", str(path))

    client, model = chassis.build_client()

    assert model == "some/model"
    assert str(client.base_url).rstrip("/") == "http://localhost/api/v1"
    # The wiring under test is the UDS transport itself, not just the base_url,
    # which stays the same string regardless of whether the transport used it.
    transport = client._client._transport
    assert isinstance(transport, httpx.HTTPTransport)
    assert transport._pool._uds == str(path)


def test_absent_socket_raises_environment_failure(clean_env, tmp_path, monkeypatch):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-real")
    clean_env.setenv("LLM_SOCKET_PATH", str(tmp_path / "missing.sock"))
    monkeypatch.setattr(chassis, "SOCKET_WAIT_SECONDS", 0)

    with pytest.raises(chassis.EnvironmentFailure):
        chassis.build_client()


def test_wait_for_socket_returns_true_once_the_path_exists(tmp_path):
    path = tmp_path / "core.sock"
    calls = []

    def fake_sleep(seconds):
        calls.append(seconds)
        path.write_bytes(b"")

    assert chassis.wait_for_socket(str(path), timeout=5, sleep=fake_sleep) is True
    assert len(calls) == 1


def test_wait_for_socket_gives_up_at_the_timeout(tmp_path):
    assert (
        chassis.wait_for_socket(str(tmp_path / "never"), timeout=0, sleep=lambda s: None) is False
    )


def test_wait_for_socket_returns_true_immediately_when_already_present(tmp_path):
    # The container cold-start case: the socket can already exist by the time the
    # chassis checks, even with no time budget to wait for it.
    path = tmp_path / "core.sock"
    path.write_bytes(b"")

    assert chassis.wait_for_socket(str(path), timeout=0, sleep=lambda s: None) is True


def _global_pairs(env):
    env.setenv("LLM_BASE_URL", "https://core.example/v1")
    env.setenv("LLM_API_KEY", "sk-core")
    env.setenv("STREAM_BASE_URL", "https://stream.example/v1")
    env.setenv("STREAM_API_KEY", "sk-stream")
    env.setenv("OPENROUTER_API_KEY", "sk-or")


def test_host_llm_pair_replaces_the_global_pair(clean_env):
    _global_pairs(clean_env)
    clean_env.setenv("HOST_LLM_BASE_URL", "https://host.example/v1/")
    clean_env.setenv("HOST_LLM_API_KEY", "sk-host")
    assert proxy.upstream_for("core") == ("https://host.example/v1/chat/completions", "sk-host")
    assert proxy.upstream_for("aux") == ("https://stream.example/v1/chat/completions", "sk-stream")


def test_host_llm_url_without_a_host_key_sends_no_key(clean_env):
    _global_pairs(clean_env)
    clean_env.setenv("HOST_LLM_BASE_URL", "https://host.example/v1")
    assert proxy.upstream_for("core") == ("https://host.example/v1/chat/completions", "")


def test_no_host_llm_url_uses_the_global_pair(clean_env):
    _global_pairs(clean_env)
    assert proxy.upstream_for("core") == ("https://core.example/v1/chat/completions", "sk-core")
    clean_env.delenv("LLM_BASE_URL")
    assert proxy.upstream_for("core") == (
        "https://openrouter.ai/api/v1/chat/completions",
        "sk-or",
    )


def test_host_llm_key_without_a_host_url_is_ignored(clean_env):
    _global_pairs(clean_env)
    clean_env.setenv("HOST_LLM_API_KEY", "sk-host")
    assert proxy.upstream_for("core") == ("https://core.example/v1/chat/completions", "sk-core")


def test_host_stream_pair_replaces_the_global_stream_pair(clean_env):
    _global_pairs(clean_env)
    clean_env.setenv("HOST_STREAM_BASE_URL", "https://hoststream.example/v1")
    clean_env.setenv("HOST_STREAM_API_KEY", "sk-hs")
    assert proxy.upstream_for("aux") == ("https://hoststream.example/v1/chat/completions", "sk-hs")
    assert proxy.upstream_for("core") == ("https://core.example/v1/chat/completions", "sk-core")


def test_host_stream_url_without_a_host_key_sends_no_key(clean_env):
    _global_pairs(clean_env)
    clean_env.setenv("HOST_STREAM_BASE_URL", "https://hoststream.example/v1")
    assert proxy.upstream_for("aux") == ("https://hoststream.example/v1/chat/completions", "")


def test_host_stream_key_without_a_host_url_is_ignored(clean_env):
    _global_pairs(clean_env)
    clean_env.setenv("HOST_STREAM_API_KEY", "sk-hs")
    assert proxy.upstream_for("aux") == ("https://stream.example/v1/chat/completions", "sk-stream")


def test_neither_kind_of_socket_carries_the_other_kinds_key(clean_env):
    clean_env.setenv("HOST_LLM_BASE_URL", "https://host.example/v1")
    clean_env.setenv("HOST_LLM_API_KEY", "sk-host-core")
    clean_env.setenv("LLM_API_KEY", "sk-core")
    assert proxy.upstream_for("aux")[1] == ""
    clean_env.setenv("HOST_STREAM_BASE_URL", "https://hoststream.example/v1")
    clean_env.setenv("HOST_STREAM_API_KEY", "sk-host-stream")
    assert proxy.upstream_for("core")[1] == "sk-host-core"
    assert proxy.upstream_for("aux")[1] == "sk-host-stream"


def test_the_verify_override_still_wins_over_the_host_stream_url(clean_env):
    clean_env.setenv("HOST_STREAM_BASE_URL", "https://hoststream.example/v1")
    clean_env.setenv("STREAM_UPSTREAM_URL", "http://verify-stub:8199/v1/")
    assert proxy.stream_upstream_url() == "http://verify-stub:8199/v1/chat/completions"


def test_the_recorder_starts_on_the_host_pair_alone(clean_env, capsys):
    clean_env.setenv("HOST_LLM_BASE_URL", "https://host.example/v1")
    clean_env.setattr(proxy.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(StopIteration()))
    with pytest.raises(StopIteration):
        proxy.main()
    err = capsys.readouterr()
    assert "error: set" not in err.out
    assert "host upstream configured without a key" in err.err


def test_no_warning_when_the_host_pair_has_its_key(clean_env, capsys):
    clean_env.setenv("HOST_LLM_BASE_URL", "https://host.example/v1")
    clean_env.setenv("HOST_LLM_API_KEY", "sk-host")
    clean_env.setattr(proxy.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(StopIteration()))
    with pytest.raises(StopIteration):
        proxy.main()
    assert "without a key" not in capsys.readouterr().err


def test_the_stream_host_url_without_a_key_warns(clean_env, capsys):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-global")
    clean_env.setenv("HOST_STREAM_BASE_URL", "https://hoststream.example/v1")
    clean_env.setattr(proxy.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(StopIteration()))
    with pytest.raises(StopIteration):
        proxy.main()
    err = capsys.readouterr().err
    assert "warning: host upstream configured without a key (HOST_STREAM_BASE_URL)" in err
    assert "HOST_LLM_BASE_URL" not in err


@pytest.mark.parametrize("kind", ["LLM", "STREAM"])
def test_a_host_key_without_its_url_warns(clean_env, capsys, kind):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-global")
    clean_env.setenv(f"HOST_{kind}_API_KEY", "sk-host")
    clean_env.setattr(proxy.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(StopIteration()))
    with pytest.raises(StopIteration):
        proxy.main()
    err = capsys.readouterr().err
    assert f"warning: host key configured without an upstream (HOST_{kind}_API_KEY)" in err
    assert len([line for line in err.splitlines() if "warning:" in line]) == 1


def test_no_host_key_warning_when_the_pair_is_complete_or_absent(clean_env, capsys):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-global")
    clean_env.setenv("HOST_LLM_BASE_URL", "https://host.example/v1")
    clean_env.setenv("HOST_LLM_API_KEY", "sk-host")
    clean_env.setenv("HOST_STREAM_API_KEY", "   ")
    clean_env.setattr(proxy.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(StopIteration()))
    with pytest.raises(StopIteration):
        proxy.main()
    assert "without an upstream" not in capsys.readouterr().err


SHARED_KEY_WARNING = "warning: this host's core upstream key is shared with the first host"


def _start_and_capture_stderr(clean_env, capsys):
    clean_env.setattr(proxy.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(StopIteration()))
    with pytest.raises(StopIteration):
        proxy.main()
    return capsys.readouterr().err


@pytest.mark.parametrize("host_url", [None, "https://host.example/v1"])
@pytest.mark.parametrize("global_url", [None, "https://global.example/v1"])
@pytest.mark.parametrize("key_set", [None, "", "1"])
def test_shared_core_key_warning_matrix(clean_env, capsys, host_url, global_url, key_set):
    clean_env.setenv("OPENROUTER_API_KEY", "sk-global")
    if host_url:
        clean_env.setenv("HOST_LLM_BASE_URL", host_url)
        clean_env.setenv("HOST_LLM_API_KEY", "sk-host")
    if global_url:
        clean_env.setenv("LLM_BASE_URL", global_url)
    if key_set is not None:
        clean_env.setenv("HOST_OPENROUTER_KEY_SET", key_set)
    err = _start_and_capture_stderr(clean_env, capsys)
    expected = key_set is not None and not host_url and (bool(global_url) or key_set == "")
    assert (SHARED_KEY_WARNING in err) is expected
    assert err.count(SHARED_KEY_WARNING) <= 1
