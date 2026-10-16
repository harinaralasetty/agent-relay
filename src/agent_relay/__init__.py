"""agent_relay: durable local agent messaging.

Workspace owns configuration and registration. PeerClient exposes the five
authenticated mailbox operations without starting a model or runtime.
"""

from agent_relay.workspace import PeerClient, PeerSpec, Workspace

__version__ = "0.3.0a1"
__all__ = ["PeerClient", "PeerSpec", "Workspace", "__version__"]
