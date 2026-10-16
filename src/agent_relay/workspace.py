"""Private workspaces and identity-bound mailbox clients."""

import json
import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agent_relay.peers import configuration_lock, validate
from agent_relay.store import CourierError, Store


@dataclass(frozen=True)
class PeerSpec:
    runtime: str = "external"
    model: str | None = None
    allowed: tuple[str, ...] = ()
    api_key_env: str | None = None
    api_base: str | None = None
    timeout: float = 90
    executable: str | None = None


def _write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)


class Workspace:
    def __init__(self, path: Path | str) -> None:
        candidate = Path(path).expanduser().resolve()
        self._path = candidate / "config.json" if candidate.is_dir() else candidate
        self._config = json.loads(self._path.read_text(encoding="utf-8"))
        validate(self._config)

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def create(
        cls,
        directory: Path | str,
        peers: dict[str, PeerSpec],
        *,
        conversation_id: str = "discussion",
        max_messages: int = 32,
        limits: dict | None = None,
    ) -> "Workspace":
        definitions = {}
        for name, spec in peers.items():
            if not isinstance(spec, PeerSpec):
                raise TypeError("Peer definitions must be PeerSpec instances")
            definition = {
                "runtime": spec.runtime,
                "allowed": list(spec.allowed),
                "timeout": spec.timeout,
                "token": secrets.token_urlsafe(32),
            }
            for key in ("model", "api_key_env", "api_base", "executable"):
                value = getattr(spec, key)
                if value is not None:
                    definition[key] = value
            definitions[name] = definition
        config = {
            "peers": definitions,
            "conversation_id": conversation_id,
            "max_messages": max_messages,
        }
        if limits is not None:
            config["limits"] = limits
        validate(config)
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        _write_private(directory / "config.json", json.dumps(config, indent=2) + "\n")
        return cls(directory)

    def _identity(self, peer: str) -> dict:
        if peer not in self._config["peers"]:
            raise CourierError("Unknown peer identity")
        return self._config["peers"][peer]

    def register(self) -> Store:
        with configuration_lock(self.path):
            # Re-read under the same lock used by configuration editors.
            config = json.loads(self.path.read_text(encoding="utf-8"))
            validate(config)
            store = Store(self.path.parent / "mail.sqlite")
            store.register_workspace(config)
            self._config = config
            return store

    def client(self, peer: str) -> "PeerClient":
        self._identity(peer)
        store = self.register()
        return PeerClient(
            store, peer, self._identity(peer)["token"], self._config["conversation_id"]
        )

    def messages(self) -> list[dict]:
        database = self.path.parent / "mail.sqlite"
        if not database.exists():
            return []
        return Store.open_existing(database, read_only=True).messages(
            self._config["conversation_id"]
        )

    def mcp_config(self, peer: str, *, format: str = "json", output: Path | str) -> Path:
        self._identity(peer)
        if format not in {"json", "codex"}:
            raise ValueError("MCP format must be json or codex")
        # Keep the virtualenv executable symlink: resolving it loses installed packages.
        command = str(Path(sys.executable).absolute())
        args = ["-m", "agent_relay", "serve", str(self.path), "--peer", peer]
        if format == "json":
            text = (
                json.dumps(
                    {"mcpServers": {"agent_relay": {"command": command, "args": args}}}, indent=2
                )
                + "\n"
            )
        else:
            text = (
                "[mcp_servers.agent_relay]\ncommand = "
                + json.dumps(command, ensure_ascii=False)
                + "\nargs = "
                + json.dumps(args, ensure_ascii=False)
                + "\n"
            )
        destination = Path(output).expanduser().absolute()
        _write_private(destination, text)
        return destination


@dataclass(frozen=True)
class PeerClient:
    _store: Store = field(repr=False)
    _peer: str
    _token: str = field(repr=False)
    _conversation_id: str

    def peers(self) -> list[dict]:
        return self._store.peers(self._peer, self._token)

    def send(
        self,
        to: str,
        text: str,
        *,
        idempotency_key: str,
        reply_to: str | None = None,
        final: bool = False,
    ) -> dict:
        return self._store.send(
            self._peer,
            self._token,
            to,
            self._conversation_id,
            text,
            idempotency_key,
            reply_to,
            final,
        )

    def inbox(self, limit: int = 20) -> list[dict]:
        return self._store.inbox(self._peer, self._token, limit)

    def ack(self, id: str) -> dict:
        return self._store.ack(self._peer, self._token, id)

    def status(self, id: str) -> dict:
        return self._store.status(self._peer, self._token, id)
