import json
import stat
import tomllib

import pytest

from agent_relay.store import CourierError
from agent_relay.workspace import PeerSpec, Workspace


def make_workspace(tmp_path):
    return Workspace.create(
        tmp_path / 'workspace "with spaces" 📨',
        {
            "alice": PeerSpec(allowed=("bob",)),
            "bob": PeerSpec(allowed=("alice",)),
            "observer": PeerSpec(),
        },
    )


def test_private_creation_and_read_only_inspection(tmp_path):
    workspace = make_workspace(tmp_path)
    assert stat.S_IMODE(workspace.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(workspace.path.parent.stat().st_mode) == 0o700
    before = {p.name: p.read_bytes() for p in workspace.path.parent.iterdir()}
    assert Workspace(workspace.path).messages() == []
    assert {p.name: p.read_bytes() for p in workspace.path.parent.iterdir()} == before
    with pytest.raises(FileExistsError):
        make_workspace(tmp_path)
    assert {p.name: p.read_bytes() for p in workspace.path.parent.iterdir()} == before


def test_unknown_identity_has_no_side_effects(tmp_path):
    workspace = make_workspace(tmp_path)
    before = set(workspace.path.parent.iterdir())
    with pytest.raises(CourierError):
        workspace.client("missing")
    with pytest.raises(CourierError):
        workspace.mcp_config("missing", output=tmp_path / "mcp.json")
    assert set(workspace.path.parent.iterdir()) == before
    assert not (tmp_path / "mcp.json").exists()


def test_identity_bound_round_trip(tmp_path):
    workspace = make_workspace(tmp_path)
    alice, bob = workspace.client("alice"), workspace.client("bob")
    observer = workspace.client("observer")
    assert [p["id"] for p in alice.peers()] == ["bob"]
    assert observer.peers() == []
    token = json.loads(workspace.path.read_text())["peers"]["alice"]["token"]
    assert token not in repr(alice)
    assert not hasattr(alice, "messages")
    initial = alice.send("bob", "hello", idempotency_key="hello")
    assert alice.send("bob", "hello", idempotency_key="hello") == initial
    with pytest.raises(CourierError, match="Conflicting"):
        alice.send("bob", "changed", idempotency_key="hello")
    with pytest.raises(CourierError):
        observer.status(initial["id"])
    with pytest.raises(CourierError):
        alice.ack(initial["id"])
    with pytest.raises(CourierError):
        alice.send("observer", "blocked", idempotency_key="blocked")
    assert bob.inbox() == [initial]
    bob.ack(initial["id"])
    assert bob.inbox() == []
    reply = bob.send(
        "alice", "goodbye", idempotency_key="reply", reply_to=initial["id"], final=True
    )
    assert reply["hop"] == 1
    assert reply["reply_to"] == initial["id"]
    with pytest.raises(CourierError, match="closed"):
        alice.send("bob", "more", idempotency_key="more")
    database = workspace.path.parent / "mail.sqlite"
    before = {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in workspace.path.parent.iterdir()
    }
    assert len(workspace.messages()) == 2
    assert {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in workspace.path.parent.iterdir()
    } == before
    assert database.exists()


@pytest.mark.parametrize("format", ["json", "codex"])
def test_private_mcp_exports_without_registration(tmp_path, format):
    workspace = make_workspace(tmp_path)
    output = tmp_path / ("mcp." + format)
    assert workspace.mcp_config("alice", format=format, output=output) == output
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    content = output.read_text()
    if format == "json":
        entry = json.loads(content)["mcpServers"]["agent_relay"]
    else:
        entry = tomllib.loads(content)["mcp_servers"]["agent_relay"]
    assert entry["args"] == ["-m", "agent_relay", "serve", str(workspace.path), "--peer", "alice"]
    assert entry["command"].startswith("/")
    for peer in json.loads(workspace.path.read_text())["peers"].values():
        assert peer["token"] not in content
    assert set(p.name for p in workspace.path.parent.iterdir()) == {"config.json"}
    with pytest.raises(FileExistsError):
        workspace.mcp_config("alice", format=format, output=output)
    assert output.read_text() == content


def test_invalid_creation_does_not_create_directory(tmp_path):
    destination = tmp_path / "invalid"
    with pytest.raises(ValueError):
        Workspace.create(destination, {"alice": PeerSpec(allowed=("missing",)), "bob": PeerSpec()})
    assert not destination.exists()


def test_existing_directory_permissions_unchanged_on_refusal(tmp_path):
    workspace = make_workspace(tmp_path)
    workspace.path.parent.chmod(0o755)
    before = workspace.path.read_bytes()
    with pytest.raises(FileExistsError):
        make_workspace(tmp_path)
    assert stat.S_IMODE(workspace.path.parent.stat().st_mode) == 0o755
    assert workspace.path.read_bytes() == before
