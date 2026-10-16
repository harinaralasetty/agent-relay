# Python API

Install the source project or a built wheel in Python 3.12+ on macOS/Linux. The
public imports are `Workspace`, `PeerSpec`, and `PeerClient` from `agent_relay`.
These mailbox APIs do not call a model or import the optional LiteLLM SDK.

## Workspace and peer definitions

```python
from agent_relay import PeerSpec, Workspace

relay = Workspace.create(
    ".agent_relay/my-review",
    {
        "alpha": PeerSpec(allowed=("beta",)),
        "beta": PeerSpec(allowed=("alpha",)),
    },
    conversation_id="review",
    max_messages=32,
)
```

`PeerSpec` defaults to runtime `external`, with no model. Set `runtime="codex"`,
`"claude"`, or `"litellm"` and a nonempty `model` to use an owned adapter. CLI peers
can select an `executable`; API peers can select `api_key_env` (a variable name,
never its value) and `api_base`. `timeout` applies to managed runtime turns.
Only `allowed` recipients may receive messages; there is no implicit route in the
Python API. Include at least two peers and use 1–64 character names composed of
letters, digits, underscore, or hyphen. The CLI's generic init convenience creates
mutual routes; use this API or edit fresh config for narrower routes.

Creation validates everything before writing `config.json`. New state directories
use `0700`, config files `0600`; existing files are never overwritten. Existing
directory permissions are preserved, so choose a private directory and check it
with `doctor`. Peer tokens stay in that private config and only their hashes enter
the mailbox database. This is trusted local software, not process isolation from
the same OS user.

Creation and `Workspace(CONFIG_OR_DIRECTORY)` do not create a database.
`relay.register()` deliberately freezes the identity/routes and conversation in one
transaction. `relay.client("alpha")` registers on first use and returns an
identity-bound `PeerClient`. Reopening with the same topology is idempotent;
changing registered routes, tokens, or conversation definitions is refused.

## Mailbox operations

| Method | Result |
|---|---|
| `client.peers()` | Permitted peers and their runtime state |
| `client.send(to, text, idempotency_key=..., reply_to=None, final=False)` | Stored message with generated ID |
| `client.inbox(limit=20)` | This peer's unacknowledged messages; no implicit ACK |
| `client.ack(message_id)` | Recipient's explicit acknowledgment |
| `client.status(message_id)` | Authenticated delivery state and acknowledgment |

Reuse a send's idempotency key only for an identical logical message. Reuse with
changed content, recipient, or reply/final fields raises `ValueError`. A reply must
point to a message in the same conversation and reverse its sender/recipient pair.
Permission and validation failures also raise `ValueError`; Filesystem failures raise
`OSError`; database failures can raise `sqlite3.Error`. Client representation excludes its token.

```python
alpha, beta = relay.client("alpha"), relay.client("beta")
question = alpha.send("beta", "What should we check?", idempotency_key="question-1")
beta.ack(question["id"])
answer = beta.send(
    "alpha", "Check the input boundary.", idempotency_key="answer-1", reply_to=question["id"]
)
alpha.ack(answer["id"])
final = alpha.send("beta", "Thanks.", idempotency_key="done-1", reply_to=answer["id"], final=True)
beta.ack(final["id"])
```

`final=True` closes the **entire conversation**, including other participants.
Already-stored messages remain deliverable; new messages are refused. Gather all
outstanding replies before closing. Reading or successful runtime completion does
not establish an ACK, and an ACK does not establish answer correctness.

`relay.messages()` returns an administrative transcript. Before registration it
returns `[]` without changing topology. On an existing database it uses a read-only
connection. Transcript text is private task data, even though it contains no peer
tokens; redact it before sharing.

## Configure external MCP clients

```python
relay.mcp_config("alpha", output=".agent_relay/my-review/alpha.mcp.json")
relay.mcp_config("beta", format="codex", output=".agent_relay/my-review/beta.mcp.toml")
```

`format="json"` writes the Claude-style `mcpServers` structure. `format="codex"`
writes a TOML stanza. Exports contain absolute interpreter/workspace paths and a
`serve CONFIG --peer ID` command, without token values. Keep the installation in
place; regenerate config after moving it. Output files use `0600`, refuse
replacement, and never alter your client's global config. Export alone does not
register the workspace; server startup does.

An external client runs its own MCP loop, polls its inbox when appropriate, and
keeps its own tool permissions. The mailbox does not wake existing apps. Owned
runtimes remain available through `agent_relay run CONFIG --watch` in a mixed
workspace; they do not claim messages addressed to external peers. Finite runs
report those messages as `external_pending_messages` and drain only owned queues.

Run `examples/python_exchange.py` for a complete temporary local exchange. See the
[architecture contract](architecture.md) for delivery failures, uncertainty and
runtime boundaries.
