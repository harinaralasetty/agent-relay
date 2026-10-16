"""Read-only host diagnostics and an isolated, provider-free protocol exercise."""

import asyncio
import json
import os
import platform
import secrets
import shutil
import stat
import sys
from contextlib import AsyncExitStack
from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory


def doctor(config_path: Path | None = None) -> dict:
    """Inspect prerequisites without launching providers or creating mailbox state."""
    checks = []

    def record(name, good, message, *, warning=False):
        checks.append(
            {
                "name": name,
                "status": "ok" if good else ("warning" if warning else "error"),
                "message": message,
            }
        )

    record(
        "python",
        sys.version_info >= (3, 12),
        f"Python {platform.python_version()}; requires 3.12 or newer",
    )
    record("os", sys.platform in {"darwin", "linux"}, "Supported systems: macOS and Linux")

    def dependency(name):
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            record(name, False, f"{name} is not installed")
        else:
            record(name, True, f"{name} version {version}")

    dependency("mcp")
    if config_path is None:
        record("config", False, "No configuration selected; runtime checks skipped", warning=True)
    else:
        from agent_relay.peers import validate

        path = Path(config_path).expanduser()
        try:
            config = json.loads(path.read_text())
            validate(config)
        except (OSError, ValueError, TypeError, KeyError):
            record("config", False, "Configuration cannot be read or is invalid")
        else:
            record("config", True, "Configuration is valid")
            if any(p["runtime"] == "litellm" for p in config["peers"].values()):
                dependency("litellm")
            for peer, definition in config["peers"].items():
                runtime = definition["runtime"]
                if runtime in {"codex", "claude"}:
                    found = shutil.which(definition.get("executable") or runtime) is not None
                    record(
                        f"executable:{peer}",
                        found,
                        f"{runtime} executable "
                        + ("found" if found else "missing")
                        + "; authentication and model availability are untested",
                    )
            names = sorted(
                {p["api_key_env"] for p in config["peers"].values() if p.get("api_key_env")}
            )
            for name in names:
                found = bool(os.environ.get(name))
                record(
                    f"api_key:{name}",
                    found,
                    "Named API environment variable is " + ("set" if found else "missing"),
                )
            record(
                "config_permissions",
                stat.S_IMODE(path.stat().st_mode) & 0o077 == 0,
                "Private configuration should be accessible only to its owner",
                warning=True,
            )
        try:
            mode = stat.S_IMODE(path.parent.stat().st_mode)
            record(
                "state_permissions",
                mode & 0o077 == 0,
                "State directory should be accessible only to its owner",
                warning=True,
            )
        except OSError:
            record("state_permissions", False, "State directory is unavailable", warning=True)
    return {"ok": not any(c["status"] == "error" for c in checks), "checks": checks}


async def self_check() -> dict:
    """Exercise two real authenticated stdio sessions in temporary local state."""
    checks = []

    def require(name, condition):
        checks.append(
            {
                "name": name,
                "status": "ok" if condition else "error",
                "message": "Passed" if condition else "Protocol check failed",
            }
        )
        if not condition:
            raise RuntimeError("Protocol check failed")

    async def run():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        from agent_relay.store import Store

        with TemporaryDirectory(prefix="agent-relay-check-") as directory:
            path = Path(directory) / "mail.sqlite"
            store = Store(path)
            tokens = {peer: secrets.token_urlsafe(32) for peer in ("alpha", "beta")}
            store.register("alpha", tokens["alpha"], ["beta"])
            store.register("beta", tokens["beta"], ["alpha"])
            store.conversation("check", ["alpha", "beta"])
            with open(os.devnull, "w") as errors:
                async with AsyncExitStack() as stack:
                    sessions = {}
                    for peer in tokens:
                        parameters = StdioServerParameters(
                            command=sys.executable,
                            args=["-m", "agent_relay.mcp_server"],
                            env={
                                "AGENT_RELAY_DB": str(path),
                                "AGENT_RELAY_PEER": peer,
                                "AGENT_RELAY_TOKEN": tokens[peer],
                            },
                        )
                        read, write = await stack.enter_async_context(
                            stdio_client(parameters, errlog=errors)
                        )
                        session = await stack.enter_async_context(ClientSession(read, write))
                        await session.initialize()
                        sessions[peer] = session
                    alpha, beta = sessions["alpha"], sessions["beta"]
                    expected = {"peer_list", "peer_send", "peer_inbox", "peer_ack", "peer_status"}
                    tool_sets = []
                    for session in sessions.values():
                        tool_sets.append({t.name for t in (await session.list_tools()).tools})
                    require("tools", all(names == expected for names in tool_sets))

                    async def call(session, tool, arguments):
                        result = await session.call_tool(tool, arguments)
                        if result.isError:
                            raise RuntimeError("Tool failed")
                        return json.loads(result.content[0].text)

                    peers = await call(alpha, "peer_list", {})
                    require("identity", [p["id"] for p in peers["peers"]] == ["beta"])
                    args = {
                        "to": "beta",
                        "conversation_id": "check",
                        "text": "ping",
                        "idempotency_key": "ping",
                    }
                    sent = await call(alpha, "peer_send", args)
                    require("send", sent["sender"] == "alpha" and sent["recipient"] == "beta")
                    inbox = await call(beta, "peer_inbox", {})
                    require("inbox", [m["id"] for m in inbox["messages"]] == [sent["id"]])
                    again = await call(alpha, "peer_send", args)
                    require(
                        "idempotency",
                        again["id"] == sent["id"]
                        and len((await call(beta, "peer_inbox", {}))["messages"]) == 1,
                    )
                    denied = await alpha.call_tool("peer_ack", {"message_id": sent["id"]})
                    require("unauthorized_ack", bool(denied.isError))
                    denied_route = await alpha.call_tool(
                        "peer_send", {**args, "to": "alpha", "idempotency_key": "denied-route"}
                    )
                    require("unauthorized_route", bool(denied_route.isError))
                    conflict = await alpha.call_tool("peer_send", {**args, "text": "changed"})
                    require("conflicting_idempotency", bool(conflict.isError))
                    before = await call(alpha, "peer_status", {"message_id": sent["id"]})
                    require(
                        "status_before_ack",
                        not before["acknowledged"] and before["status"] == "stored",
                    )
                    ack = await call(beta, "peer_ack", {"message_id": sent["id"]})
                    after = await call(alpha, "peer_status", {"message_id": sent["id"]})
                    require(
                        "recipient_ack",
                        ack["acknowledged"]
                        and after["acknowledged"]
                        and not (await call(beta, "peer_inbox", {}))["messages"],
                    )
                    reply = await call(
                        beta,
                        "peer_send",
                        {
                            "to": "alpha",
                            "conversation_id": "check",
                            "text": "pong",
                            "idempotency_key": "pong",
                            "reply_to": sent["id"],
                        },
                    )
                    require(
                        "reply",
                        reply["reply_to"] == sent["id"]
                        and reply["hop"] == 1
                        and (await call(alpha, "peer_inbox", {}))["messages"][0]["id"]
                        == reply["id"],
                    )
                    await call(alpha, "peer_ack", {"message_id": reply["id"]})
                    final = await call(
                        alpha,
                        "peer_send",
                        {
                            "to": "beta",
                            "conversation_id": "check",
                            "text": "done",
                            "idempotency_key": "done",
                            "reply_to": reply["id"],
                            "final": True,
                        },
                    )
                    closed = await beta.call_tool(
                        "peer_send",
                        {
                            "to": "alpha",
                            "conversation_id": "check",
                            "text": "late",
                            "idempotency_key": "late",
                        },
                    )
                    require("closure", final["final"] and bool(closed.isError))
                    await call(beta, "peer_ack", {"message_id": final["id"]})
                    require(
                        "all_recipients_acked",
                        all(message["acknowledged"] for message in store.messages("check")),
                    )

    try:
        async with asyncio.timeout(30):
            await run()
    except Exception:
        # Exception strings can contain configuration, subprocess output, or credentials.
        checks.append(
            {
                "name": "execution",
                "status": "error",
                "message": "Local protocol exercise failed or timed out",
            }
        )
    return {
        "ok": all(c["status"] == "ok" for c in checks),
        "checks": checks,
        "kind": "local-protocol",
        "provider_calls": 0,
    }
