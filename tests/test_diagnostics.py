import json

from agent_relay.diagnostics import doctor, self_check


async def test_self_check_exercises_real_protocol():
    result = await self_check()
    assert result["ok"], result
    assert result["kind"] == "local-protocol"
    assert result["provider_calls"] == 0
    assert all(check["status"] == "ok" for check in result["checks"])
    assert {"tools", "reply", "unauthorized_ack", "closure"} <= {
        check["name"] for check in result["checks"]
    }


def test_doctor_invalid_config_does_not_echo_secrets_or_create_state(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"token":"secret-canary"}')
    before = sorted(tmp_path.iterdir())
    result = doctor(path)
    assert not result["ok"]
    assert "secret-canary" not in json.dumps(result)
    assert sorted(tmp_path.iterdir()) == before


def test_doctor_checks_selected_runtime_without_running_it(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "conversation_id": "test",
                "peers": {
                    "a": {
                        "runtime": "litellm",
                        "model": "x",
                        "token": "a",
                        "allowed": ["b"],
                        "api_key_env": "RELAY_TEST_MISSING_KEY",
                    },
                    "b": {"runtime": "codex", "model": "x", "token": "b", "allowed": ["a"]},
                },
            }
        )
    )
    monkeypatch.delenv("RELAY_TEST_MISSING_KEY", raising=False)
    looked_up = []
    monkeypatch.setattr(
        "agent_relay.diagnostics.shutil.which", lambda name: looked_up.append(name) or None
    )
    result = doctor(path)
    assert not result["ok"]
    assert looked_up == ["codex"]
    assert any(
        c["name"] == "api_key:RELAY_TEST_MISSING_KEY" and c["status"] == "error"
        for c in result["checks"]
    )
    assert not (tmp_path / "mail.sqlite").exists()


async def test_self_check_failure_is_sanitized_and_temporary_state_removed(monkeypatch):
    directories = []

    def broken_register(store, *args):
        directories.append(store.path.parent)
        raise RuntimeError("secret-canary")

    monkeypatch.setattr("agent_relay.store.Store.register", broken_register)
    result = await self_check()
    assert not result["ok"]
    assert "secret-canary" not in json.dumps(result)
    assert directories and not directories[0].exists()


def test_doctor_no_config_is_warning_and_json_friendly():
    result = doctor()
    json.dumps(result)
    assert next(c for c in result["checks"] if c["name"] == "config")["status"] == "warning"


def test_doctor_external_requires_no_provider_and_reports_private_state(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    config = {
        "conversation_id": "test",
        "peers": {
            "a": {"runtime": "external", "token": "a", "allowed": ["b"]},
            "b": {"runtime": "external", "token": "b", "allowed": ["a"]},
        },
    }
    path.write_text(json.dumps(config))
    tmp_path.chmod(0o700)
    monkeypatch.setattr(
        "agent_relay.diagnostics.shutil.which",
        lambda name: (_ for _ in ()).throw(AssertionError(name)),
    )
    result = doctor(path)
    assert result["ok"], result
    assert next(c for c in result["checks"] if c["name"] == "state_permissions")["status"] == "ok"
    assert not (tmp_path / "mail.sqlite").exists()


def test_doctor_warns_about_shared_directory(tmp_path):
    tmp_path.chmod(0o755)
    result = doctor(tmp_path / "missing.json")
    check = next(c for c in result["checks"] if c["name"] == "state_permissions")
    assert check["status"] == "warning"
    assert not result["ok"]


async def test_self_check_success_removes_temporary_state(monkeypatch):
    from tempfile import TemporaryDirectory

    directories = []

    def track(*args, **kwargs):
        temporary = TemporaryDirectory(*args, **kwargs)
        directories.append(temporary.name)
        return temporary

    monkeypatch.setattr("agent_relay.diagnostics.TemporaryDirectory", track)
    result = await self_check()
    assert result["ok"], result
    from pathlib import Path

    assert directories and all(not Path(directory).exists() for directory in directories)


def test_doctor_checks_configured_executable_and_private_config_mode(tmp_path, monkeypatch):
    from agent_relay.cli import initialize

    path = initialize(tmp_path / "state", "model", "model")
    config = json.loads(path.read_text())
    config["peers"]["cedar"]["executable"] = "missing-custom-codex"
    path.write_text(json.dumps(config))
    path.chmod(0o644)
    monkeypatch.setattr(
        "agent_relay.diagnostics.shutil.which",
        lambda name: "/fake/bin/" + name if name in {"codex", "claude"} else None,
    )
    result = doctor(path)
    assert not result["ok"]
    assert any(c["name"] == "executable:cedar" and c["status"] == "error" for c in result["checks"])
    assert any(
        c["name"] == "config_permissions" and c["status"] == "warning" for c in result["checks"]
    )
    assert "missing-custom-codex" not in json.dumps(result)
