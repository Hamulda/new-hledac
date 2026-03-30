"""
In-memory transport pro testování federated learning.
"""

import asyncio
import inspect
from typing import Dict, Callable, Any
from collections import defaultdict

from .transport_base import Transport


class InMemoryTransport(Transport):
    """In-memory transport pro lokální testování."""

    def __init__(self, node_id: str):
        super().__init__()
        self.node_id = node_id
        self.peers: Dict[str, 'InMemoryTransport'] = {}
        self._queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._running = False

    def add_peer(self, peer: 'InMemoryTransport'):
        """Přidá peera."""
        self.peers[peer.node_id] = peer
        peer.peers[self.node_id] = self

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def send_message(self, peer_id: str, msg_type: str, payload: Dict, signature: str):
        """Odešle zprávu do fronty peera."""
        if peer_id not in self.peers:
            return

        peer = self.peers[peer_id]
        message = {
            'sender': self.node_id,
            'type': msg_type,
            'payload': payload,
            'signature': signature
        }
        await peer._queues[self.node_id].put(message)

    async def receive(self) -> Dict:
        """Přijme zprávu z fronty."""
        queue = self._queues.get(self.node_id)
        if queue:
            return await queue.get()
        return {}

    async def poll_once(self):
        """Zpracuje jednu příchozí zprávu."""
        try:
            msg = await asyncio.wait_for(self.receive(), timeout=0.01)
            if msg:
                msg_type = msg.get('type')
                if msg_type in self.handlers:
                    handler = self.handlers[msg_type]
                    if inspect.iscoroutinefunction(handler):
                        await handler(msg)
                    else:
                        handler(msg)
        except asyncio.TimeoutError:
            pass
