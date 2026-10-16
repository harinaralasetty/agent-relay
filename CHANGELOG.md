# Changelog

## 0.3.0a1 — local adoption draft

- Public `Workspace`, `PeerSpec`, and `PeerClient` Python API for authenticated local mailboxes.
- Explicit external peers, generic named-peer initialization, per-peer stdio serving,
  and token-free JSON/TOML client configuration exports.
- Provider-free real MCP self-check and read-only setup diagnostics.
- Atomic topology registration; transcript inspection no longer registers a fresh workspace.
- External messages remain available to their client and are reported separately from owned queues.
- Single-source package version, typing marker, clean-wheel qualification, and manual release preparation.

Codex CLI, Claude Code, and optional LiteLLM support remain available. This alpha
is published as source on GitHub only; it has not been published to PyPI.
