import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional
import hashlib
import random

from hledac.universal.core.resource_governor import ResourceGovernor, Priority

logger = logging.getLogger(__name__)

MAX_ITEM_BYTES = 256 * 1024  # 256KB hard cap


class KademliaNode:
    def __init__(
        self,
        node_id: str,
        governor: ResourceGovernor,
        bootstrap_nodes: Optional[List[str]] = None,
        k: int = 20,
        alpha: int = 3,
    ):
        self.node_id = node_id
        self.governor = governor
        self.bootstrap_nodes = bootstrap_nodes or []
        self.k = k
        self.alpha = alpha

        self.routing_table: Dict[int, List[Dict[str, Any]]] = {}
        self.data_store: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        self.data_store_max = 10_000
        self.data_store_ttl = 3600

        self._running = True
        self._refresh_task: Optional[asyncio.Task] = None
        self._transport = None

        self._pending_rpcs: Dict[str, asyncio.Future] = {}

    def set_transport(self, transport):
        self._transport = transport
        transport.register_handler("dht_ping", self._handle_ping)
        transport.register_handler("dht_pong", self._handle_pong)
        transport.register_handler("dht_store", self._handle_store)
        transport.register_handler("dht_find_value", self._handle_find_value)
        transport.register_handler("dht_find_value_resp", self._handle_find_value_resp)

    async def start(self):
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        for peer in self.bootstrap_nodes:
            if peer == self.node_id:
                continue
            await self._ping(peer)

    async def stop(self):
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

    def _distance(self, key1: str, key2: str) -> int:
        h1 = int(hashlib.sha256(key1.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha256(key2.encode()).hexdigest(), 16)
        return h1 ^ h2

    def _bucket_index(self, key: str) -> int:
        dist = self._distance(key, self.node_id)
        if dist == 0:
            return 0
        return min(dist.bit_length() - 1, 255)

    def _update_routing(self, peer_id: str, peer_info: Optional[Dict[str, Any]] = None):
        if peer_id == self.node_id:
            return
        peer_info = peer_info or {}
        b = self._bucket_index(peer_id)
        bucket = self.routing_table.setdefault(b, [])
        bucket = [p for p in bucket if p.get("id") != peer_id]
        bucket.append({"id": peer_id, **peer_info, "last_seen": time.time()})
        if len(bucket) > self.k:
            bucket = bucket[-self.k:]
        self.routing_table[b] = bucket

    def _find_closest_nodes(self, key: str, count: int) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        b = self._bucket_index(key)
        for i in range(max(0, b - 5), min(256, b + 6)):
            candidates.extend(self.routing_table.get(i, []))
        candidates.sort(key=lambda n: self._distance(n["id"], key))
        return candidates[:count]

    def _local_put(self, key: str, value: Any):
        self.data_store[key] = (value, time.time())
        self.data_store.move_to_end(key)
        if len(self.data_store) > self.data_store_max:
            self.data_store.popitem(last=False)

    def _local_get(self, key: str) -> Optional[Any]:
        if key not in self.data_store:
            return None
        value, ts = self.data_store[key]
        if time.time() - ts > self.data_store_ttl:
            del self.data_store[key]
            return None
        self.data_store.move_to_end(key)
        return value

    async def store(self, key: str, value: Any):
        self._local_put(key, value)

        closest = self._find_closest_nodes(key, self.k)
        tasks = [self._send_store(p["id"], key, value) for p in closest if p["id"] != self.node_id]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def find_value(self, key: str) -> Optional[Any]:
        local = self._local_get(key)
        if local is not None:
            return local

        queried = set()
        shortlist = self._find_closest_nodes(key, self.alpha)

        while shortlist:
            rpc_ids: List[str] = []
            send_tasks: List[asyncio.Task] = []

            for peer in shortlist[: self.alpha]:
                pid = peer["id"]
                if pid in queried or pid == self.node_id:
                    continue
                queried.add(pid)

                rpc_id = str(uuid.uuid4())
                rpc_ids.append(rpc_id)
                fut = asyncio.get_running_loop().create_future()
                self._pending_rpcs[rpc_id] = fut
                send_tasks.append(asyncio.create_task(self._send_find_value(pid, key, rpc_id)))

            if not rpc_ids:
                break

            # wait for responses (futures)
            futures = [self._pending_rpcs[rid] for rid in rpc_ids if rid in self._pending_rpcs]
            if not futures:
                break

            done, pending = await asyncio.wait(futures, timeout=3.0)
            # cleanup pending
            for fut in pending:
                fut.cancel()

            # remove all rpcs
            for rid in rpc_ids:
                self._pending_rpcs.pop(rid, None)

            for fut in done:
                if fut.cancelled():
                    continue
                try:
                    res = fut.result()
                except Exception:
                    continue

                if isinstance(res, dict) and "value" in res:
                    self._local_put(key, res["value"])
                    return res["value"]
                if isinstance(res, dict) and "nodes" in res:
                    for n in res["nodes"]:
                        if n.get("id") and n["id"] not in queried:
                            shortlist.append(n)

            shortlist.sort(key=lambda n: self._distance(n["id"], key))
            shortlist = shortlist[: self.k]

        return None

    async def _ping(self, peer_id: str) -> bool:
        if not self._transport:
            return False
        rpc_id = str(uuid.uuid4())
        fut = asyncio.get_running_loop().create_future()
        self._pending_rpcs[rpc_id] = fut
        await self._transport.send_message(peer_id, "dht_ping", {"rpc_id": rpc_id}, "")
        try:
            ok = await asyncio.wait_for(fut, timeout=2.0)
            self._update_routing(peer_id)
            return bool(ok)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_rpcs.pop(rpc_id, None)

    async def _send_store(self, peer_id: str, key: str, value: Any):
        if not self._transport:
            return
        # hard cap (best-effort): odmítnout příliš velké hodnoty
        try:
            import orjson
            approx = len(orjson.dumps(value))
            if approx > MAX_ITEM_BYTES:
                logger.warning("DHT store skipped: value too large")
                return
        except Exception:
            pass

        await self._transport.send_message(peer_id, "dht_store", {"key": key, "value": value}, "")
        self._update_routing(peer_id)

    async def _send_find_value(self, peer_id: str, key: str, rpc_id: str):
        if not self._transport:
            return
        await self._transport.send_message(peer_id, "dht_find_value", {"key": key, "rpc_id": rpc_id}, "")
        self._update_routing(peer_id)

    # Handlers
    async def _handle_ping(self, data: Dict[str, Any]):
        sender = data.get("sender")
        payload = data.get("payload", {})
        rpc_id = payload.get("rpc_id")
        if sender and rpc_id and self._transport:
            self._update_routing(sender)
            await self._transport.send_message(sender, "dht_pong", {"rpc_id": rpc_id}, "")

    async def _handle_pong(self, data: Dict[str, Any]):
        sender = data.get("sender")
        payload = data.get("payload", {})
        rpc_id = payload.get("rpc_id")
        if sender:
            self._update_routing(sender)
        fut = self._pending_rpcs.get(rpc_id)
        if fut and not fut.done():
            fut.set_result(True)

    async def _handle_store(self, data: Dict[str, Any]):
        sender = data.get("sender")
        payload = data.get("payload", {})
        if sender:
            self._update_routing(sender)
        key = payload.get("key")
        value = payload.get("value")
        if key is None:
            return
        self._local_put(key, value)

    async def _handle_find_value(self, data: Dict[str, Any]):
        sender = data.get("sender")
        payload = data.get("payload", {})
        key = payload.get("key")
        rpc_id = payload.get("rpc_id")
        if not (sender and key and rpc_id and self._transport):
            return

        self._update_routing(sender)

        value = self._local_get(key)
        if value is not None:
            await self._transport.send_message(sender, "dht_find_value_resp", {"rpc_id": rpc_id, "value": value}, "")
            return

        closest = self._find_closest_nodes(key, self.k)
        await self._transport.send_message(sender, "dht_find_value_resp", {"rpc_id": rpc_id, "nodes": closest}, "")

    async def _handle_find_value_resp(self, data: Dict[str, Any]):
        sender = data.get("sender")
        payload = data.get("payload", {})
        rpc_id = payload.get("rpc_id")
        if sender:
            self._update_routing(sender)
        fut = self._pending_rpcs.get(rpc_id)
        if fut and not fut.done():
            fut.set_result(payload)

    async def _refresh_loop(self):
        while self._running:
            await asyncio.sleep(300)
            bucket_idx = random.randint(0, 255)
            bucket = list(self.routing_table.get(bucket_idx, []))
            for peer in bucket:
                pid = peer.get("id")
                if pid:
                    ok = await self._ping(pid)
                    if not ok:
                        self.routing_table[bucket_idx] = [p for p in self.routing_table.get(bucket_idx, []) if p.get("id") != pid]
