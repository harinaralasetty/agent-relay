"""Qualify an installed wheel outside the source checkout, without provider calls.

Run with the Python interpreter from a fresh environment containing the built wheel.
"""

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory


def command(*args):
    result = subprocess.run(
        [sys.executable, "-m", "agent_relay", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=45,
        env={**os.environ, "PATH": ""},
    )
    if result.returncode:
        raise RuntimeError(f"Installed command failed: {args[0]} (exit {result.returncode})")
    return result.stdout


async def exercise_export(config):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async with stdio_client(StdioServerParameters(**config)) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            result = await client.call_tool("peer_list", {})
            if result.isError or len(json.loads(result.content[0].text)["peers"]) != 1:
                raise RuntimeError("Installed exported MCP configuration failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", action="store_true", help="Expect the optional models SDK")
    args = parser.parse_args()
    distribution = metadata.distribution("agent_relay")
    direct = distribution.read_text("direct_url.json")
    if direct and json.loads(direct).get("dir_info", {}).get("editable"):
        raise RuntimeError("Use a clean wheel installation, not the editable source environment")
    from agent_relay import PeerSpec, Workspace, __version__

    if distribution.version != __version__:
        raise RuntimeError("Version metadata differs from Python API")
    if (importlib.util.find_spec("litellm") is not None) != args.models:
        raise RuntimeError("Optional SDK installation differs from the selected extra")
    if "litellm" in sys.modules:
        raise RuntimeError("Public mailbox API imported the optional inference SDK")
    executable = Path(sys.executable).parent / "agent_relay"
    entrypoint = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "PATH": ""},
    )
    if entrypoint.returncode or __version__ not in entrypoint.stdout:
        raise RuntimeError("Installed console entry point failed")
    with TemporaryDirectory(prefix="agent-relay-wheel-") as temporary:
        os.chdir(temporary)
        if __version__ not in command("--version"):
            raise RuntimeError("Version command differs from metadata")
        check = json.loads(command("self-check"))
        if not check["ok"] or check["provider_calls"] != 0:
            raise RuntimeError("Installed local self-check failed")
        state = Path(temporary) / "state with spaces"
        command("init", state, "--peer", "alpha=external", "--peer", "beta=external")
        config = state / "config.json"
        if not json.loads(command("doctor", config))["ok"]:
            raise RuntimeError("Installed doctor failed")
        if json.loads(command("inspect", config)) != [] or (state / "mail.sqlite").exists():
            raise RuntimeError("Read-only inspection changed fresh workspace")
        export = state / "alpha.mcp.json"
        command("mcp-config", config, "--peer", "alpha", "--output", export)
        parameters = json.loads(export.read_text())["mcpServers"]["agent_relay"]
        asyncio.run(exercise_export(parameters))
        workspace = Workspace.create(
            Path(temporary) / "python-api",
            {"left": PeerSpec(allowed=("right",)), "right": PeerSpec(allowed=("left",))},
        )
        left, right = workspace.client("left"), workspace.client("right")
        sent = left.send("right", "hello", idempotency_key="hello")
        if right.inbox()[0]["id"] != sent["id"]:
            raise RuntimeError("Installed Python API exchange failed")
        right.ack(sent["id"])
        if not left.status(sent["id"])["acknowledged"]:
            raise RuntimeError("Installed Python API acknowledgment failed")
    print(
        json.dumps(
            {
                "ok": True,
                "version": __version__,
                "models_extra": args.models,
                "provider_calls": 0,
                "checks": [
                    "metadata",
                    "version",
                    "real-mcp-self-check",
                    "external-init",
                    "read-only-doctor-inspect",
                    "exported-mcp-startup",
                    "python-api",
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
