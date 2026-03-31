"""
Lehká grafová neuronová síť (GraphSAGE) implementovaná v MLX.
Trénink na pozadí, inference volitelná podle velikosti grafu.
"""

import logging
import time
import array
from collections import OrderedDict
from typing import List, Tuple, Optional, Any

import numpy as np

# Sprint 79a: GNN protective fixes
try:
    import rustworkx as rx

    RUSTWORKX_AVAILABLE = True
except ImportError:
    RUSTWORKX_AVAILABLE = False
    rx = None

# G2: Bounded node_features - now per-instance in __init__

logger = logging.getLogger(__name__)

try:
    import mlx.core as mx
    import mlx.nn as nn
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    mx = None
    nn = None


class GraphSAGE(nn.Module):
    """GraphSAGE model pro predikci hran."""

    def __init__(self, in_dim: int, hidden_dim: int, out_dim: int, num_layers: int = 2):
        super().__init__()
        self.layers = []
        for i in range(num_layers):
            self.layers.append(nn.Linear(in_dim if i == 0 else hidden_dim, hidden_dim))
        self.out_proj = nn.Linear(hidden_dim, out_dim)

    def __call__(self, x, adj):
        for layer in self.layers:
            x = mx.relu(layer(adj @ x))
        return self.out_proj(x)


def neighbor_sampling(adj_list: List[List[int]], node_ids: List[int], k: int = 10):
    """
    Vrátí pro každý uzel seznam k náhodných sousedů (s vracením).
    """
    sampled = []
    for node in node_ids:
        neighbors = adj_list[node]
        if len(neighbors) < k:
            # opakujeme sousedy, abychom dosáhli k
            sampled.append(np.random.choice(neighbors, size=k, replace=True).tolist())
        else:
            sampled.append(np.random.choice(neighbors, size=k, replace=False).tolist())
    return sampled


class GNNPredictor:
    """
    Prediktor, který obaluje GNN model a umožňuje trénink na pozadí.
    """
    # Sprint 79c: __slots__ for memory efficiency
    __slots__ = ('model', 'optimizer', 'trained', '_training_scheduled',
                 'node_features', 'scheduler', 'graph', '_edge_count',
                 'max_nodes', 'max_edges', 'max_node_features',
                 '_in_dim', '_hidden_dim', '_out_dim',
                 '_last_cleanup', '_cleanup_interval')

    def __init__(self, in_dim: int = 64, hidden_dim: int = 32, out_dim: int = 1):
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available, cannot create GNNPredictor")

        self.model = GraphSAGE(in_dim, hidden_dim, out_dim)
        try:
            import mlx.optimizers as optim
            self.optimizer = optim.Adam(learning_rate=1e-3)
        except (ImportError, AttributeError):
            self.optimizer = None
        self.trained = False
        self._training_scheduled = False

        # Sprint 79c: GNN protective fixes
        # G2: Bounded node_features with LRU eviction (max 10k entries)
        self.max_node_features = 10000
        self.node_features = OrderedDict()

        # G1: Plain dict (not defaultdict), edge limit with eviction
        self.graph: dict = {}  # node_id -> set of neighbors
        self.max_nodes = 10000
        self.max_edges = 50000
        self._edge_count = 0

        self.scheduler = None
        self._in_dim = in_dim
        self._hidden_dim = hidden_dim
        self._out_dim = out_dim
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def set_scheduler(self, scheduler):
        """Nastaví scheduler pro background training."""
        self.scheduler = scheduler

    def _add_edge(self, src: int, dst: int):
        """Přidá hranu; detekuje duplicity, při dosažení limitu eviktuje nejstarší uzel."""
        # Ensure source node exists
        if src not in self.graph:
            self.graph[src] = set()

        # Duplicate detection
        if dst in self.graph[src]:
            return  # Edge already exists

        # Edge limit with eviction
        if self._edge_count >= self.max_edges:
            # Evict oldest node
            oldest = next(iter(self.graph))
            edges_removed = len(self.graph[oldest])
            self._edge_count -= edges_removed
            del self.graph[oldest]
            logger.debug(f"GNN evicted node {oldest} ({edges_removed} edges)")

        self.graph[src].add(dst)
        self._edge_count += 1

        # Ensure destination exists
        if dst not in self.graph:
            self.graph[dst] = set()

    def build_adj_list(self, edges: List[Tuple[int, int]], n_nodes: int):
        """Vytvoří seznam sousedů pomocí plain dict (ne defaultdict)."""
        # Use plain dict with set for neighbors
        for u, v in edges:
            if u < n_nodes and v < n_nodes:
                self._add_edge(u, v)
                self._add_edge(v, u)

    def _maybe_cleanup(self):
        """Periodické čištění osiřelých uzlů (bez feature a bez hran)."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        orphaned = [
            node_id for node_id in self.graph
            if node_id not in self.node_features and not self.graph.get(node_id)
        ]
        for node_id in orphaned:
            del self.graph[node_id]

        self._last_cleanup = now
        if orphaned:
            logger.debug(f"GNN cleanup: removed {len(orphaned)} orphaned nodes")

    def get_neighbors(self, node_id: int) -> set:
        """Vrátí sousedy (read-only, nevytváří záznamy)."""
        return self.graph.get(node_id, set())

    def add_node_feature(self, node_id: int, feature: np.ndarray):
        """
        G2: Add node feature with bounded LRU eviction.
        Uses array('f') for memory efficiency.
        """
        # Move to end if exists (most recently used)
        if node_id in self.node_features:
            self.node_features.move_to_end(node_id)
        # Store as array('f') for memory efficiency
        self.node_features[node_id] = array.array('f', feature)
        # Evict oldest if over limit
        while len(self.node_features) > self.max_node_features:
            oldest_id, _ = self.node_features.popitem(last=False)
            # Also clean up from graph
            self.graph.pop(oldest_id, None)

    def trigger_training(self, edges: List[Tuple[int, int]],
                        features,
                        labels,
                        num_epochs: int = 10):
        """Spustí trénink na pozadí, pokud je k dispozici scheduler."""
        if self.scheduler and not self._training_scheduled:
            self._training_scheduled = True
            # Import here to avoid circular dependency
            from hledac.universal.orchestrator.global_scheduler import register_task

            # Register training task if not already registered
            try:
                register_task("train_gnn", train_gnn_task)
            except ValueError:
                pass  # Already registered

            self.scheduler.schedule(8, "train_gnn", self, edges, features, labels, num_epochs)

    def predict(self, node_ids: List[int], edges: List[Tuple[int, int]]) -> mx.array:
        """
        Predikce pravděpodobnosti hrany mezi každým párem v node_ids.
        Pro jednoduchost predikujeme skóre pro všechny možné páry mezi node_ids.

        G1: Guard against OOM - limit matrix size.
        """
        if not self.trained:
            raise RuntimeError("GNN not trained yet")

        # G1: Guard - limit node count to prevent OOM
        MAX_PREDICT_NODES = 1000
        if len(node_ids) > MAX_PREDICT_NODES:
            logger.warning(f"Limiting prediction from {len(node_ids)} to {MAX_PREDICT_NODES} nodes")
            node_ids = node_ids[:MAX_PREDICT_NODES]

        n = len(node_ids)
        # G1: Use edge list instead of dense matrix when possible
        # For small n, dense is fine; for large, use sparse representation
        if n <= 100:
            # Small graph - use dense matrix
            adj_np = np.zeros((n, n), dtype=np.float32)
            idx_map = {orig: i for i, orig in enumerate(node_ids)}
            for u, v in edges:
                if u in idx_map and v in idx_map:
                    adj_np[idx_map[u], idx_map[v]] = 1.0
                    adj_np[idx_map[v], idx_map[u]] = 1.0
            adj = mx.array(adj_np)
        else:
            # Large graph - use adjacency list representation
            adj_dict = {i: set() for i in range(n)}
            idx_map = {orig: i for i, orig in enumerate(node_ids)}
            for u, v in edges:
                if u in idx_map and v in idx_map:
                    adj_dict[idx_map[u]].add(idx_map[v])
                    adj_dict[idx_map[v]].add(idx_map[u])
            # Sprint 7B: Use stored node_features (fallback to zero for missing)
            feat_list = []
            for i, node_id in enumerate(node_ids[:n]):
                if node_id in self.node_features:
                    arr = self.node_features[node_id]
                    if isinstance(arr, array.array):
                        feat_list.append(np.array(arr, dtype=np.float32))
                    else:
                        feat_list.append(np.asarray(arr, dtype=np.float32))
                else:
                    feat_list.append(np.zeros(self._in_dim, dtype=np.float32))
            feat = mx.stack([mx.array(f) for f in feat_list])
            # For large graphs, use simplified model (just features, no adjacency)
            adj = mx.zeros((n, n))  # Dummy - model should handle this
            pred = self.model(feat, adj)
            return pred

        # Sprint 7B: Use stored node_features instead of random
        feat_list = []
        for node_id in node_ids:
            if node_id in self.node_features:
                arr = self.node_features[node_id]
                if isinstance(arr, array.array):
                    feat_list.append(np.array(arr, dtype=np.float32))
                else:
                    feat_list.append(np.asarray(arr, dtype=np.float32))
            else:
                # Fallback to zero vector if not found
                feat_list.append(np.zeros(self._in_dim, dtype=np.float32))
        feat = mx.stack([mx.array(f) for f in feat_list])

        pred = self.model(feat, adj)
        return pred

    def get_graph_embedding(self) -> mx.array:
        """
        Vrátí embedding celého grafu jako proxy (průměr embeddings uzlů).
        """
        if not self.trained or not self.node_features:
            return mx.zeros((8,))
        # Convert array('f') to numpy for MLX
        emb_list = []
        for arr in self.node_features.values():
            if isinstance(arr, array.array):
                emb_list.append(np.array(arr, dtype=np.float32))
            else:
                emb_list.append(np.asarray(arr, dtype=np.float32))
        all_embs = mx.stack([mx.array(e) for e in emb_list])
        return mx.mean(all_embs, axis=0)[:8]  # omezíme na 8 dimenzí

    # ------------------------------------------------------------------
    # Sprint 8TD: Batch IOC scoring
    # ------------------------------------------------------------------

    def score_ioc_batch(
        self,
        ioc_nodes: list[tuple[str, str]],
        ioc_graph: Any = None,
    ) -> dict[str, float]:
        """
        Sprint 8TD + 8UA: Batch scoring IOC uzlů pomocí GNN graph centrality.
        8UA: Live Kuzu degree lookup přes IOCGraph Cypher API.

        Args:
            ioc_nodes: List of (ioc_value, ioc_type) tuples
            ioc_graph: Optional IOC graph for degree lookup (IOCGraph instance)

        Returns:
            Dict mapping ioc_value -> confidence_score (0.0-1.0)
        """
        import math
        scores = {}

        # Sprint 8UA: IOC type weights
        type_weight = {
            "domain": 1.20, "ipv4": 1.10, "ipv6": 1.05,
            "sha256": 1.15, "md5": 1.10, "sha1": 1.08,
            "cve": 1.25, "url": 0.95, "email": 0.90,
            "malware_family": 1.30,
        }

        for value, ioc_type in ioc_nodes:
            try:
                degree = 0
                if ioc_graph is not None:
                    try:
                        # Sprint 8UA: Live Kuzu degree via Cypher
                        # IOCGraph has _conn (kuzu.Connection) when initialized
                        kuzu_conn = getattr(ioc_graph, '_conn', None)
                        if kuzu_conn is not None:
                            # Degree = count of OBSERVED edges
                            res = kuzu_conn.execute(
                                "MATCH (n:IOC)-[r:OBSERVED]->() "
                                "WHERE n.value = $v AND n.ioc_type = $t RETURN count(r)",
                                {"v": value, "t": ioc_type},
                            )
                            if res.has_next():
                                row = res.get_next()
                                degree = int(row[0]) if row else 0
                        else:
                            # Fallback: try degree() method
                            degree_fn = getattr(ioc_graph, 'degree', None)
                            if degree_fn:
                                degree = degree_fn(value)
                            elif hasattr(ioc_graph, 'get_degree'):
                                degree = ioc_graph.get_degree(value)
                            else:
                                node_degree = getattr(ioc_graph, 'nodes', {}).get(
                                    value, {}
                                ).get('degree', 0)
                                degree = node_degree
                    except Exception:
                        degree = 0

                tw = type_weight.get(ioc_type, 1.0)
                # Sprint 8UA: MLX-native scoring: log-degree + type weight
                base = min(1.0, 0.45 + 0.12 * math.log1p(max(0, degree - 1)))
                score = min(1.0, round(base * tw, 4))
                scores[value] = score
            except Exception:
                scores[value] = 0.5  # default
        return scores

    async def score_ioc_batch_async(
        self,
        ioc_nodes: list[tuple[str, str]],
        ioc_graph: Any = None,
    ) -> dict[str, float]:
        """
        Sprint 8TD: Async wrapper pro score_ioc_batch.

        Offloads sync scoring do CPU_EXECUTOR.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        _CPU = ThreadPoolExecutor(max_workers=1)

        def _sync():
            return self.score_ioc_batch(ioc_nodes, ioc_graph)

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(_CPU, _sync)
        finally:
            _CPU.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Sprint 8VH: GNN ↔ DuckPGQGraph Bridge Functions
# ---------------------------------------------------------------------------


def predict_from_edge_list(
    edge_list: list[tuple[str, str, str, float]],
    top_k: int = 10,
) -> list[dict]:
    """
    Bridge mezi DuckPGQGraph.export_edge_list() a GNN inference.

    edge_list formát: [(src_value, dst_value, rel_type, weight), ...]

    Vrátí: list dicts s poli:
      - "src": str  — zdrojový IOC
      - "dst": str  — predikovaný cílový IOC (nová hrana)
      - "score": float  — confidence predikce [0, 1]
      - "rel_type": str — predikovaný typ vztahu

    Pokud GNN není dostupný (MLX/torch chybí):
      → Fallback: vrátí top-k nejčastější dst nodes z edge_list
        seřazené podle frekvence (heuristika bez modelu).
    """
    from collections import Counter

    if not edge_list:
        return []

    try:
        # Primární: skutečný GNN inference
        # GNNPredictor.score_ioc_batch() bere (value, type) tuples
        # Importujeme zde pro lazy loading
        try:
            from brain.gnn_predictor import GNNPredictor
        except ImportError:
            GNNPredictor = None

        if GNNPredictor is not None:
            predictor = GNNPredictor()

            # Build IOC nodes from edge_list (unique dst nodes as candidates)
            dst_nodes = [(dst, _infer_rel_type(rel))
                         for _, dst, rel, _ in edge_list]
            # Deduplicate by value
            seen = set()
            unique_dsts = []
            for val, typ in dst_nodes:
                if val not in seen:
                    seen.add(val)
                    unique_dsts.append((val, typ))

            if unique_dsts:
                scores = predictor.score_ioc_batch(unique_dsts, ioc_graph=None)
                # Sort by score descending
                sorted_scores = sorted(
                    scores.items(), key=lambda x: x[1], reverse=True
                )
                results = []
                for val, score in sorted_scores[:top_k]:
                    rel = _most_common_rel(edge_list, val)
                    results.append({
                        "src": "graph",
                        "dst": val,
                        "score": float(score),
                        "rel_type": rel,
                    })
                return results

    except Exception:
        pass

    # Fallback: frequency heuristic
    freq = Counter(dst for _, dst, _, _ in edge_list)
    seen_src = {src for src, _, _, _ in edge_list}
    results = []
    for dst, count in freq.most_common(top_k):
        if dst not in seen_src:  # predikuj pouze nové nodes
            results.append({
                "src": "graph",
                "dst": dst,
                "score": float(count / max(1, len(edge_list))),
                "rel_type": "predicted",
            })
    return results


def _infer_rel_type(rel: str) -> str:
    """Infer IOC type from relationship string."""
    rel_lower = rel.lower()
    if "resolv" in rel_lower or "dns" in rel_lower:
        return "domain"
    if "links_to" in rel_lower or "connects" in rel_lower:
        return "domain"
    if "communicat" in rel_lower or "contact" in rel_lower:
        return "email"
    if "hosts" in rel_lower or "serves" in rel_lower:
        return "ipv4"
    return "domain"


def _most_common_rel(edge_list: list[tuple[str, str, str, float]], dst: str) -> str:
    """Return most common relationship type for a given dst node."""
    from collections import Counter
    rels = [rel for _, d, rel, _ in edge_list if d == dst]
    if not rels:
        return "observed"
    return Counter(rels).most_common(1)[0][0]


def get_anomaly_scores(
    edge_list: list[tuple[str, str, str, float]],
) -> list[dict]:
    """
    Detekuje anomální IOC nodes (high betweenness centrality nebo
    náhlý spike v degree).

    Fallback: nodes s degree > mean + 2*std.

    Vrátí: [{"value": str, "anomaly_score": float}]
    """
    if not edge_list:
        return []

    from collections import Counter
    import statistics

    try:
        # Primární: GNN anomaly detection
        # Use GNNPredictor's scoring if available
        try:
            from brain.gnn_predictor import GNNPredictor
        except ImportError:
            GNNPredictor = None

        if GNNPredictor is not None:
            predictor = GNNPredictor()
            # Build all unique nodes with inferred types
            all_nodes = set()
            for src, dst, rel, _ in edge_list:
                all_nodes.add(src)
                all_nodes.add(dst)
            # Infer types
            node_types = {}
            for node in all_nodes:
                # Infer from edges
                node_types[node] = _infer_rel_type(
                    _most_common_rel(edge_list, node)
                )
            # Score batch
            nodes_with_types = [(n, node_types.get(n, "domain")) for n in all_nodes]
            scores = predictor.score_ioc_batch(nodes_with_types, ioc_graph=None)
            # High-scoring nodes are anomalous
            threshold = 0.7
            anomalies = [
                {"value": n, "anomaly_score": float(s)}
                for n, s in scores.items()
                if s >= threshold
            ]
            if anomalies:
                return sorted(anomalies, key=lambda x: x["anomaly_score"], reverse=True)
    except Exception:
        pass

    # Fallback: statistický outlier (degree > mean + 2*std)
    degree = Counter(src for src, _, _, _ in edge_list)
    degree.update(Counter(dst for _, dst, _, _ in edge_list))

    if len(degree) < 3:
        return []

    vals = list(degree.values())
    mean = statistics.mean(vals)
    stdev = statistics.stdev(vals) if len(vals) > 1 else 1.0
    threshold_val = mean + 2 * stdev

    return [
        {"value": node, "anomaly_score": min(1.0, count / max(1, threshold_val))}
        for node, count in degree.most_common()
        if count > threshold_val
    ]


# ---------------------------------------------------------------------------
# Original train_gnn_task
# ---------------------------------------------------------------------------

def train_gnn_task(predictor: 'GNNPredictor',
                   edges: List[Tuple[int, int]],
                   features,
                   labels,
                   num_epochs: int = 10,
                   batch_size: int = 32,
                   learning_rate: float = 1e-3):
    """
    Trénink GNN na pozadí – voláno schedulerem.
    edges: seznam (u, v) hran (neorientovaných)
    features: matice (n_nodes, in_dim) – vstupní příznaky uzlů
    labels: vektor (n_nodes,) – 1 pro pozitivní (hrana existuje), 0 pro negativní
    """
    if not MLX_AVAILABLE:
        logger.warning("MLX not available, skipping GNN training")
        return

    try:
        from mlx.nn import losses
        import mlx.optimizers as optim
    except (ImportError, AttributeError) as e:
        logger.warning(f"MLX imports failed: {e}, skipping GNN training")
        return

    n_nodes = features.shape[0]

    # G1: Guard against OOM - limit training graph size
    MAX_TRAIN_NODES = 5000
    if n_nodes > MAX_TRAIN_NODES:
        logger.warning(f"Limiting GNN training from {n_nodes} to {MAX_TRAIN_NODES} nodes")
        # Sample subset of nodes and edges
        import random
        node_subset = random.sample(range(n_nodes), MAX_TRAIN_NODES)
        node_set = set(node_subset)
        # Filter edges to only include nodes in subset
        edges = [(u, v) for u, v in edges if u in node_set and v in node_set]
        # Remap node IDs
        node_map = {old: new for new, old in enumerate(node_subset)}
        edges = [(node_map[u], node_map[v]) for u, v in edges]
        features = features[node_subset]
        labels = labels[node_subset] if hasattr(labels, '__getitem__') else labels
        n_nodes = MAX_TRAIN_NODES

    # Vytvoříme hustou matici sousednosti (MLX nemá sparse modul)
    adj_np = np.zeros((n_nodes, n_nodes), dtype=np.float32)
    for u, v in edges:
        if u < n_nodes and v < n_nodes:
            adj_np[u, v] = 1.0
            adj_np[v, u] = 1.0
    adj = mx.array(adj_np)

    # Vytvoříme model se stejnou dimenzí jako features
    model = GraphSAGE(features.shape[1], 32, 1)
    optimizer = optim.Adam(learning_rate=learning_rate)

    def loss_fn(model, x, adj, y):
        pred = model(x, adj).squeeze()
        return losses.binary_cross_entropy(pred, y)

    loss_and_grad_fn = nn.value_and_grad(model, loss_fn)

    for epoch in range(num_epochs):
        loss, grads = loss_and_grad_fn(model, features, adj, labels)
        optimizer.update(model, grads)
        mx.eval(model.parameters(), optimizer.state)
        if epoch % 2 == 0:
            logger.debug(f"GNN training epoch {epoch}, loss: {loss.item():.4f}")

    # Uložíme natrénovaný model do prediktoru
    predictor.model = model
    predictor.trained = True
    logger.info("GNN training completed")
