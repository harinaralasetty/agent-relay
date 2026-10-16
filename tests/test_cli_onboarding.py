import json
import os
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_relay import __version__


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "agent_relay", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=40,
    )


def test_generic_cli_init_and_read_only_diagnosis(tmp_path):
    directory = tmp_path / "state"
    result = cli(
        "init",
        directory,
        "--peer",
        "alpha=external",
        "--peer",
        "beta=external",
        "--conversation-id",
        "review",
        "--max-messages",
        "16",
    )
    assert result.returncode == 0, result.stderr
    config = directory / "config.json"
    definitions = json.loads(config.read_text())
    assert definitions["conversation_id"] == "review"
    assert definitions["peers"]["alpha"]["allowed"] == ["beta"]
    assert "model" not in definitions["peers"]["alpha"]
    assert cli("inspect", config).stdout.strip() == "[]"
    doctor = cli("doctor", config)
    assert doctor.returncode == 0, doctor.stderr
    assert json.loads(doctor.stdout)["ok"]
    assert not (directory / "mail.sqlite").exists()
    assert __version__ in cli("--version").stdout


def test_invalid_init_creates_no_state_and_does_not_echo_token(tmp_path):
    for specification in ("alpha=external:unused", "alpha=codex", "alpha=unknown:x"):
        directory = tmp_path / specification.replace(":", "-")
        result = cli("init", directory, "--peer", specification, "--peer", "beta=external")
        assert result.returncode != 0
        assert not directory.exists()


async def test_exported_config_starts_real_mcp_sessions_and_is_private(tmp_path):
    directory = tmp_path / "workspace with spaces"
    assert (
        cli("init", directory, "--peer", "alpha=external", "--peer", "beta=external").returncode
        == 0
    )
    config = directory / "config.json"
    exports = {}
    for peer in ("alpha", "beta"):
        destination = directory / f"{peer}.json"
        result = cli("mcp-config", config, "--peer", peer, "--output", destination)
        assert result.returncode == 0, result.stderr
        assert os.stat(destination).st_mode & 0o777 == 0o600
        exports[peer] = json.loads(destination.read_text())["mcpServers"]["agent_relay"]
        for identity in json.loads(config.read_text())["peers"].values():
            assert identity["token"] not in destination.read_text() + result.stdout + result.stderr
    assert not (directory / "mail.sqlite").exists()
    async with stdio_client(StdioServerParameters(**exports["alpha"])) as (ar, aw):
        async with ClientSession(ar, aw) as alpha:
            await alpha.initialize()
            sent = await alpha.call_tool(
                "peer_send",
                {
                    "to": "beta",
                    "conversation_id": "discussion",
                    "text": "hello",
                    "idempotency_key": "hello",
                },
            )
            assert not sent.isError
            message = json.loads(sent.content[0].text)
            async with stdio_client(StdioServerParameters(**exports["beta"])) as (br, bw):
                async with ClientSession(br, bw) as beta:
                    await beta.initialize()
                    received = await beta.call_tool("peer_inbox", {})
                    assert (
                        json.loads(received.content[0].text)["messages"][0]["id"] == message["id"]
                    )
                    acknowledged = await beta.call_tool("peer_ack", {"message_id": message["id"]})
                    assert not acknowledged.isError
    unknown = cli("serve", config, "--peer", "unknown")
    assert unknown.returncode == 1
    assert "Unknown peer identity" in unknown.stderr


def test_corrupt_mailbox_is_reported_without_traceback_or_mutation(tmp_path):
    directory = tmp_path / "state"
    assert (
        cli("init", directory, "--peer", "alpha=external", "--peer", "beta=external").returncode
        == 0
    )
    database = directory / "mail.sqlite"
    database.write_bytes(b"not a database")
    before = database.read_bytes()
    result = cli("inspect", directory / "config.json")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "database" in result.stderr
    assert database.read_bytes() == before


async def test_configured_mcp_advertises_its_peer_and_conversation_without_secrets(tmp_path):
    directory = tmp_path / "context"
    assert (
        cli(
            "init",
            directory,
            "--peer",
            "alpha=external",
            "--peer",
            "beta=external",
            "--conversation-id",
            "review",
        ).returncode
        == 0
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent_relay", "serve", str(directory / "config.json"), "--peer", "alpha"],
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            response = await session.initialize()
            assert "alpha" in response.instructions
            assert "review" in response.instructions
            for definition in json.loads((directory / "config.json").read_text())["peers"].values():
                assert definition["token"] not in response.instructions
