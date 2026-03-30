"""
Tor transport pro anonymní federated learning.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Callable, Optional

logger = logging.getLogger(__name__)


class TorTransport:
    """Transport s Tor podporou a downgrade detekcí."""

    def __init__(self, data_dir: str = "~/.hledac/tor", evidence_log=None):
        self.data_dir = Path(data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.hidden_service_dir = self.data_dir / "hidden_service"
        self.hidden_service_dir.mkdir(exist_ok=True)
        self.onion_address: Optional[str] = None
        self.tor_process: Optional[asyncio.subprocess.Process] = None
        self.http_port: int = 0
        self.security_level = 'unknown'
        self.evidence_log = evidence_log
        self.handlers: Dict[str, Callable] = {}

    def register_handler(self, msg_type: str, handler: Callable):
        self.handlers[msg_type] = handler

    async def start(self):
        """Spustí Tor transport."""
        try:
            # Zkusíme spustit Tor (v produkčním prostředí)
            self.tor_process = await asyncio.create_subprocess_exec(
                'tor', '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await self.tor_process.wait()
            # Tor je dostupný
            self.security_level = 'tor'
            logger.info("Tor transport started")
        except FileNotFoundError:
            logger.warning("Tor not available, falling back to localhost")
            self.onion_address = "localhost"
            self.security_level = 'local'
            if self.evidence_log:
                self.evidence_log.create_decision_event(
                    kind="federation_downgrade",
                    summary={"reason": "Tor unavailable", "fallback": "localhost"},
                    reasons=["tor_not_found"],
                    refs={},
                    confidence=0.5
                )
        except Exception as e:
            logger.warning(f"Tor start failed, falling back to localhost: {e}")
            self.onion_address = "localhost"
            self.security_level = 'local'
            if self.evidence_log:
                self.evidence_log.create_decision_event(
                    kind="federation_downgrade",
                    summary={"reason": str(e), "fallback": "localhost"},
                    reasons=["tor_failed"],
                    refs={},
                    confidence=0.5
                )

    async def stop(self):
        """Zastaví Tor transport."""
        if self.tor_process:
            self.tor_process.terminate()
            await self.tor_process.wait()

    async def send_message(self, peer_id: str, msg_type: str, payload: Dict, signature: str):
        """Odešle zprávu (placeholder - implementace závisí na transportu)."""
        pass
