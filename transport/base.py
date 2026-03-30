from abc import ABC, abstractmethod
from typing import Dict, Callable, Any

class Transport(ABC):
    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def wait_ready(self):
        pass

    @abstractmethod
    def register_handler(self, msg_type: str, handler: Callable):
        pass

    @abstractmethod
    async def send_message(self, target: str, msg_type: str, payload: Dict[str, Any], signature: str, msg_id: str = None):
        pass
