import json
import subprocess
import sys

import pytest

from agent_relay.cli import initialize, load, make_runtimes, run
from agent_relay.store import CourierError, Store


def test_workspace_registration_is_atomic(tmp_path):
    path = initialize(tmp_path / "state", "model", "model")
    config = json.loads(path.read_text())
    store = Store(path.parent / "mail.sqlite")
    store.register("birch", "conflicting-identity", ["cedar"])
    with pytest.raises(CourierError, match="different identity"):
        store.register_workspace(config)
    with store.connect() as db:
        assert [row["id"] for row in db.execute("SELECT id FROM peers")] == ["birch"]
        assert db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0


def test_read_only_store_never_creates_or_changes_schema(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        Store.open_existing(path, read_only=True)
    assert not path.exists()
    store = Store(path)
    store.register("alpha", "secret", [])
    before = path.read_bytes()
    reader = Store.open_existing(path, read_only=True)
    assert reader.messages("demo") == []
    with pytest.raises(CourierError, match="read-only"):
        reader.register("beta", "another-secret", [])
    assert path.read_bytes() == before


def test_inspect_before_first_run_does_not_register_or_freeze(tmp_path):
    path = initialize(tmp_path / "state", "model", "model")
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "agent_relay", "inspect", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == []
    assert path.read_bytes() == before
    assert not (path.parent / "mail.sqlite").exists()
    assert not (path.parent / "config.json.lock").exists()


def test_external_peers_are_not_owned_runtimes(tmp_path):
    path = initialize(tmp_path / "state", "model", "model")
    config = json.loads(path.read_text())
    for definition in config["peers"].values():
        definition["runtime"] = "external"
        del definition["model"]
    path.write_text(json.dumps(config))
    config, store = load(path)
    assert make_runtimes(config, store) == {}


async def test_external_messages_remain_available_without_dispatch(tmp_path):
    path = initialize(tmp_path / "state", "model", "model")
    config = json.loads(path.read_text())
    for definition in config["peers"].values():
        definition["runtime"] = "external"
        del definition["model"]
    path.write_text(json.dumps(config))
    config, store = load(path)
    message = store.send(
        "cedar", config["peers"]["cedar"]["token"], "birch", "demo", "hello", "hello"
    )
    report = await run(path, None)
    assert report["errors"] == []
    assert report["external_pending_messages"] == [message["id"]]
    assert (
        store.status("cedar", config["peers"]["cedar"]["token"], message["id"])["status"]
        == "stored"
    )
    with pytest.raises(ValueError, match="managed runtime"):
        await run(path, {"cedar": "launch me"})


async def test_mixed_workspace_delivers_only_to_owned_peer(tmp_path, monkeypatch):
    from agent_relay import PeerSpec, Workspace
    from agent_relay.runtime import TurnResult

    workspace = Workspace.create(
        tmp_path / "mixed",
        {
            "owned": PeerSpec(runtime="codex", model="test-model", allowed=("outside",)),
            "outside": PeerSpec(allowed=("owned",)),
        },
    )
    outside = workspace.client("outside")
    question = outside.send("owned", "hello", idempotency_key="question")
    calls = []

    class LocalRuntime:
        def __init__(self, options):
            self.options = options
            self.session_id = "local-session"

        async def start(self):
            calls.append("start")

        async def turn(self, prompt):
            calls.append("turn")
            client = workspace.client("owned")
            message = client.inbox()[0]
            assert message["id"] == question["id"]
            client.ack(message["id"])
            client.send("outside", "reply", idempotency_key="reply", reply_to=message["id"])
            return TurnResult("done", self.session_id)

        async def close(self):
            calls.append("close")

    monkeypatch.setitem(
        __import__("agent_relay.cli", fromlist=["RUNTIMES"]).RUNTIMES, "codex", LocalRuntime
    )
    report = await run(workspace.path, None)
    assert report["errors"] == []
    assert calls == ["start", "turn", "close"]
    assert report["turns"] == {"owned": 1}
    assert outside.status(question["id"])["status"] == "completed"
    assert outside.status(question["id"])["acknowledged"]
    reply = outside.inbox()[0]
    assert reply["reply_to"] == question["id"]
    assert reply["status"] == "stored"
    assert report["external_pending_messages"] == [reply["id"]]
