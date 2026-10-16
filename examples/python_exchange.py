"""A local mailbox exchange with no model, account, or network request."""

from tempfile import TemporaryDirectory

from agent_relay import PeerSpec, Workspace

with TemporaryDirectory(prefix="agent-relay-example-") as directory:
    relay = Workspace.create(
        directory,
        {
            "alpha": PeerSpec(allowed=("beta",)),
            "beta": PeerSpec(allowed=("alpha",)),
        },
    )
    alpha, beta = relay.client("alpha"), relay.client("beta")
    question = alpha.send("beta", "What does an ACK tell us?", idempotency_key="question")
    beta.ack(question["id"])
    reply = beta.send(
        "alpha",
        "The recipient explicitly acknowledged the message.",
        idempotency_key="answer",
        reply_to=question["id"],
    )
    alpha.ack(reply["id"])
    final = alpha.send("beta", "Thanks.", idempotency_key="done", reply_to=reply["id"], final=True)
    beta.ack(final["id"])
    for message in relay.messages():
        print(
            f"{message['sender']} → {message['recipient']}: {message['text']} "
            f"[ACK={message['acknowledged']}, final={message['final']}]"
        )
