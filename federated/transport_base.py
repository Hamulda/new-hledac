"""
Transport base class pro federated learning.
"""

from abc import ABC, abstractmethod
from typing import Dict, Callable, Any, Optional
import asyncio
import inspect


class Transport(ABC):
    """Abstraktní transport pro federated learning."""

    def __init__(self):
        self.handlers: Dict[str, Callable] = {}
        self.security_level: str = 'unknown'

    def register_handler(self, msg_type: str, handler: Callable):
        """Registruje handler pro typ zprávy."""
        self.handlers[msg_type] = handler

    @abstractmethod
    async def send_message(self, peer_id: str, msg_type: str, payload: Dict, signature: str):
        """Odešle zprávu peerovi."""
        pass

    @abstractmethod
    async def start(self):
        """Spustí transport."""
        pass

    @abstractmethod
    async def stop(self):
        """Zastaví transport."""
        pass

    async def _dispatch(self, msg_type: str, data: Dict):
        """Dispečuje příchozí zprávu."""
        handler = self.handlers.get(msg_type)
        if handler:
            if inspect.iscoroutinefunction(handler):
                await handler(data)
            else:
                handler(data)
