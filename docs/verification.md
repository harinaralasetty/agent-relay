# Verification record — initial local release

Validated on macOS arm64 with Python 3.12.13, MCP Python SDK 1.30.0,
Codex CLI 0.157.1 and Claude Code 2.1.294. Live models: GPT-6 Luna at low
reasoning and Claude Haiku. Models and CLI behavior can differ between accounts.

| Check | Observed result |
|---|---|
| Automated behavioral suite | 47 passed |
| Lint and formatting | Passed |
| Source distribution and wheel build | Passed |
| Wheel installation in clean environment; CLI entry point | Passed |
| Real stdio MCP with two independent client/server connections | Shared mailbox; identity, recipient ACK and visibility enforced |
| GPT-initiated live conversation | 5/5 expected messages completed and explicitly acknowledged; 3 turns per peer |
| Claude-initiated live conversation | 5/5 expected messages completed and explicitly acknowledged; 3 turns per peer |
| Live session continuity | Both directions retained one provider session per peer |
| Shutdown and healthy restart | 2/2 additional messages completed/ACKed; both peers resumed their original IDs |
| Independent review of code and live results | Confirmed fixes rechecked; no unresolved delivery finding within the reviewed local scope |

The live conversation required this sequence, with linked replies:

1. Request a clarification before adding two numbers.
2. Ask which numbers to add.
3. Supply 2 and 3.
4. Return exactly 5.
5. Send final verification, acknowledge it and stop.

Both CLI demo processes were observed to exit 0 after their checks. Private
result artifacts retain the message/turn records; exit codes were observed in
the invoking process results. They are distinct evidence. Raw transcripts,
provider session IDs and local credentials are intentionally excluded from Git.

## Fix and verification loop

Tests were written before new behavior. Confirmed review/runtime failures received
regression checks, fixes, and fresh tests. Findings retained during development:

- A cleanup exception skipped subsequent runtimes: each close is now attempted.
- An acknowledged stored message could be delivered again: claims skip it.
- Interrupted delivery appeared as successful recovery: uncertainty is reported
  and held; administrator resolution does not redispatch.
- A seed for a recovery-blocked peer could hang: it is refused promptly.
- A new session ID was saved too late: it is now recorded before its first turn.
- The demo accepted “15” or unrelated text: exact stage content, links, successful
  turns and recipient acknowledgments are now required.
- Generated Codex MCP overrides and the sandbox enum did not match this installed
  CLI: actual CLI parsing/startup checked after correction.
- Disabling Codex's code-mode host prevented MCP calls: it stays enabled for tool
  orchestration, with unrelated features disabled.
- Read-only Codex denied default MCP approval: only the five mailbox tools are
  explicitly allowed and approved per process; general requests remain denied.
- Claude subprocess output was unbounded: stdout is capped and stderr drained.

GPT-6.1 Sol was accepted by the desktop agent surface but rejected by this CLI's
ChatGPT account. The live tests switched to the available GPT-6 Luna after user
selection. Failed preflight/initiator attempts stored no peer messages and were
retained separately; they are not counted as successful conversations.

## Coverage limits

Automated tests cover real database concurrency/idempotency/limits, three-peer
routing separation, real MCP transport, serialized busy-peer delivery, ownership
locks, uncertainty, stale/mismatched session responses, denied approvals, timeouts,
malformed/oversized output and owned descendant cleanup. External protocol fault
cases use fake runtimes; they do not establish a live provider crash or outage test.

Initial live tests cover two managed peers, both initiators, linked replies, final closure,
explicit ACKs and healthy session resume. They do not prove native desktop/subagent
attachment, hostile multi-user isolation, large-team load, Windows support, or a
universal provider dollar cap. Linux CI runs the credential-free checks; live
provider behavior was exercised on macOS only.

This record describes measured evidence, not a guarantee that all defects are absent.

## Package and namespace qualification — 9 October 2026

The verified public identity is agent_relay. Python distribution:
`agent_relay`; module/CLI/MCP server name: `agent_relay`; MCP environment prefix:
`AGENT_RELAY_`. Existing mailbox and config formats were preserved.

| Fresh check after the rename | Observed result |
|---|---|
| Automated behavioral suite | 48 passed |
| Lint, formatting, source distribution and wheel | Passed |
| Fresh environment installation of the renamed wheel and CLI help | Passed |
| Codex-initiated updated demo | 5/5 exact linked messages completed and ACKed; 3 turns per peer; exit 0 |
| Claude-initiated updated demo | 5/5 exact linked messages completed and ACKed; 3 turns per peer; exit 0 |
| Session continuity within both demos | One provider session per peer; no unresolved deliveries or runtime errors |
| Independent rename and demo-fix review | Namespace/config/package changes consistent; confirmed issues fixed and reviewed |

Initial rename qualification attempts exposed two demo problems and were retained
as failed attempts. A peer could read and acknowledge a stored reply while its
current turn was still active, so no separate supervisor dispatch was needed.
The old demo checker incorrectly required that message to become `completed`.
The checker now accepts `stored` only with an explicit recipient ACK and still
rejects `submitted`, `uncertain` and `failed` states. Exact message count/text,
reply bindings and final closure remain required; runtime errors still fail the CLI.
A new regression test failed before the fix and passed afterward.

One agent also marked the sum as final before the verification message. The demo
request now explicitly requires `final=false` for the sum and a final verification
from the initiator. Guidance asks peers to return after handling available input,
leaving future-message delivery to the supervisor. Acknowledgment is still an agent
assertion; these demo checks establish this specific exchange, not correctness of
arbitrary tasks. Both fresh runs used new state directories; no ambiguous turn was
redispatched.

The moved virtual environment had stale executable paths and was rebuilt. A
fake-CLI startup test initially hit its two-second allowance during cold startup;
its startup margin is now ten seconds, while the intentional turn timeout remains
0.1 seconds. Production timeout defaults were unchanged.

## Optional LiteLLM runtime qualification — 9 October 2026

Version 0.2.0 retains both CLI adapters and adds a separate optional API runtime.
The `models` extra pins LiteLLM 1.104.2; the standard install requires no LiteLLM.
CLI versions, live models and macOS/Python environment remain those listed above.

| Check | Observed result |
|---|---|
| Full suite with optional SDK | 126 passed |
| Standard installation without LiteLLM | 122 passed; 4 SDK-dependent cases skipped |
| Actual SDK against owned local HTTP endpoint | Valid completion; HTTP429 made exactly one request; selected dummy key isolated from ambient credentials |
| Two API peers through real SDK, MCP and supervisor | Both initiators passed five exact linked, ACKed messages with one stable session per peer |
| Live CLI↔CLI smoke checks | Claude-initiated passed; Codex-initiated fresh follow-up passed; five expected messages each |
| Codex→local API and local API→Codex | 2/2 smoke runs passed; three linked, ACKed messages per run; no runtime errors |
| Claude→local API and local API→Claude | 2/2 smoke runs passed; three linked, ACKed messages per run; no runtime errors |
| Independent implementation review and re-review | Two confirmed defects fixed with failing-then-passing regression tests; no remaining concrete defect in reviewed scope |
| Lint, formatting, source/wheel builds and clean installs | Passed; base install excludes LiteLLM; optional wheel install includes pinned SDK |

Three CLI↔CLI runs were attempted in this update: **one Codex initiation failure,
then two passes** (one for each initiator). The failed Codex turn read an empty
inbox and returned without the requested initial send. It produced no messages or
runtime error; the demo correctly exited 1. Its receipt is retained privately.
A fresh workspace succeeded; no uncertain turn was retried. These results show
that a successful provider turn does not ensure task completion, and do not imply
an arbitrary-task success rate.

The four mixed-runtime tests used authenticated live Codex/Claude sessions and
the actual LiteLLM SDK calling an owned local OpenAI-style endpoint. Endpoint
responses were scripted protocol fixtures, **not a third-provider model**. Each
run retained stable sessions and finished with all recipient ACKs and no unresolved
delivery. They qualify wiring in both directions, not third-provider reasoning,
production billing, or universal model compatibility. External API-model testing
was deferred by user choice; no external API key was supplied or extracted.

Review fixes reject incomplete clean histories with missing/mismatched tool results
and validate limits before creating/registering a mailbox. Tests also cover dirty,
native, stale and model-mismatched resumes, malformed/unsolicited calls, denied
mailbox operations, cancellation after a send, bounds, and redacted diagnostics.
Retries, fallbacks, cache and callback logging are disabled; SDK import uses its
bundled cost map. API cost reporting remains unknown. Private state, credentials
and test receipts are excluded from both published packages and Git.

## Current namespace qualification — 9 October 2026

Version 0.2.1 uses `agent_relay` for the repository, CLI, Python package, MCP server
and diagram labels; MCP environment variables use `AGENT_RELAY_*`.

| Check | Observed result |
|---|---|
| Full automated suite after folder/environment rebuild | 127 passed |
| Independent focused namespace/runtime review | 75 passed; no remaining runtime rename defect |
| Fresh Codex-initiated and Claude-initiated conversations | 2/2 passed; five exact linked, ACKed messages each; three turns per peer |
| Previously saved native CLI sessions after folder change | 2/2 resumed with original session IDs and completed a mailbox-tool check |
| Existing private API history location | Resume regression passed; same session and history retained without replay or file migration |
| Lint, formatting, build and clean wheel CLI installation | Passed |

Both live demos exited 0 without runtime errors or unresolved deliveries. The
resume probes called `peer_list` and sent no messages. The provider accounts,
models and CLI versions are unchanged. Old private history and state locations
remain ignored; published documentation uses only the current public identity.

## Local adoption draft qualification — 10 October 2026

Draft version **0.3.0a1** adds a public Python API, external MCP peers, generic
workspace setup, read-only diagnostics and a provider-free protocol check. These
changes were local at the time; no package upload or release was performed.

| Check | Observed result |
|---|---|
| Source suite with optional SDK, Python 3.12.13 | 155 passed in 18.48s |
| Installed base wheel, clean Python 3.12.13 environment | 151 passed; 4 SDK-dependent tests skipped |
| Installed optional wheel, clean Python 3.13.4 environment | 155 passed; LiteLLM 1.104.2 present |
| Installed package qualification in both environments | Metadata/version, console entry point, real MCP self-check, external setup, read-only inspection/doctor, exported MCP startup and Python API passed |
| Provider-free qualification | Zero model calls; actual temporary stdio MCP processes used |
| Live Claude-initiated exchange | Five exact linked messages, all recipient ACKs, three successful turns per peer; exit 0 |
| Live Codex-initiated fresh follow-up | Five exact linked messages, all recipient ACKs, three successful turns per peer; exit 0 |
| Independent implementation/package reviews | Confirmed findings fixed and re-reviewed; no remaining concrete finding in reviewed scope |
| Local workflow checks | YAML parsed; manual/TestPyPI default, scoped permissions and explicit tag/commit guards verified statically |

Three live CLI attempts were made: **one Codex initiation failure followed by two
passes**, one for each initiator. The failed attempt read an empty inbox and sent
nothing; the demo correctly exited 1. Initial-task instructions were clarified,
and the successful follow-up used a new workspace. No uncertain delivery was
retried. Both successful exchanges kept one provider session per peer. This is
smoke evidence for the specific task, not an arbitrary-task success rate.

The fix loop also covered interpreter symlinks in exported MCP configs, corrupt
database errors, configuration/identity validation before mutation, atomic
registration rollback, existing-directory permission preservation, pending
external delivery ownership, configured CLI executable diagnostics, MCP peer and
conversation context, and refusal to create a missing low-level MCP database.
Regression tests exercise actual MCP startup where relevant.

A clean installation with MCP 1.20 and current Pydantic failed during import.
The declared SDK floor is now the qualified MCP 1.30. The release workflow's
unqualified ref could select a same-named branch; checkout now explicitly selects
`refs/tags/...` and compares HEAD with the tag's peeled commit before building.

External clients own their scheduling and permissions; these tools do not
implicitly attach to an existing desktop chat or wake an idle agent. API tokens
identify peers within a trusted local workspace, not hostile OS users. Real
third-provider models, Windows support, large-team load, the new remote CI jobs,
Trusted Publisher/environment configuration, and PyPI/TestPyPI publication were
not tested or performed. The optional SDK's local-endpoint protocol tests do not
establish third-provider reasoning or billing compatibility.

## Pre-push re-check — 16 October 2026

Before the 0.3.0a1 source push, the draft was re-checked on macOS without provider calls.

| Check | Observed result |
|---|---|
| Source suite, Python 3.12 and 3.13, base and `models` extra | 151 passed with 4 SDK skips (base); 155 passed (`models`) |
| Lint and format | `ruff check` and `ruff format --check` clean in all four environments |
| Build and metadata | Wheel and source archive built; `twine check` passed |
| Clean installs | `scripts/qualify_install.py` passed for the base wheel (3.12) and the `models` wheel (3.13) |
| README external-client path | `init --peer`, JSON and Codex TOML exports, overwrite refusal, `0600` modes, no tokens in exports, TOML-configured server answered `peer_list` |
| Compatibility | Configs and a registered mailbox created by 0.2.1 validated, inspected, registered and exported under 0.3.0a1 |

One base-suite run out of about twenty failed and did not reproduce in later
sequential, fresh-environment or concurrent runs; the failing test was not captured.
