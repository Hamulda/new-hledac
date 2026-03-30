"""
OSINT-friendly sketches pro federated learning:
- Count-Min sketch pro frekvenční odhad
- MinHash sketch pro odhad podobnosti
- SimHash sketch pro near-duplicate detection
"""

import hashlib
import numpy as np
from typing import Optional, List, Dict, Any

try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    mx = None
    MLX_AVAILABLE = False


class CountMinSketch:
    """Count-Min sketch s per-session salting."""

    def __init__(self, width: int = 10000, depth: int = 5, salt: Optional[bytes] = None):
        self.width = width
        self.depth = depth
        self.salt = salt or b''
        self.table = np.zeros((depth, width), dtype=np.int32)

    def _hash(self, item: str, seed: int) -> int:
        """Hash s použitím salt."""
        salted = self.salt + item.encode() + str(seed).encode()
        return int(hashlib.sha256(salted).hexdigest(), 16) % self.width

    def add(self, item: str, count: int = 1):
        """Přidá item do sketch."""
        for i in range(self.depth):
            idx = self._hash(item, i)
            self.table[i, idx] += count

    def estimate(self, item: str) -> int:
        """Odhadne count pro item (minimum přes všechny hash funkce)."""
        return min(self._hash(item, i) for i in range(self.depth))

    def to_bytes(self) -> bytes:
        """Serializace."""
        return self.table.tobytes()

    @classmethod
    def from_bytes(cls, data: bytes, width: int = 10000, depth: int = 5) -> 'CountMinSketch':
        """Deserializace."""
        sketch = cls(width=width, depth=depth)
        sketch.table = np.frombuffer(data, dtype=np.int32).reshape((depth, width))
        return sketch


class MinHashSketch:
    """MinHash sketch pro Jaccard podobnost."""

    def __init__(self, num_hashes: int = 128, salt: Optional[bytes] = None):
        self.num_hashes = num_hashes
        self.salt = salt or b''
        self.signature = np.full(num_hashes, np.iinfo(np.uint64).max, dtype=np.uint64)

    def _hash(self, item: str, seed: int) -> np.uint64:
        """Hash funkce pro MinHash."""
        salted = self.salt + item.encode() + str(seed).encode()
        h = hashlib.sha256(salted).digest()
        # Použijeme pouze 8 bajtů (64 bitů)
        return np.uint64(int.from_bytes(h[:8], 'big'))

    def add(self, item: str):
        """Přidá item do sketch (set)."""
        for i in range(self.num_hashes):
            h = self._hash(item, i)
            if h < self.signature[i]:
                self.signature[i] = h

    def jaccard_estimate(self, other: 'MinHashSketch') -> float:
        """Odhad Jaccard podobnosti."""
        return float(np.mean(self.signature == other.signature))

    def to_bytes(self) -> bytes:
        """Serializace."""
        return self.signature.tobytes()

    @classmethod
    def from_bytes(cls, data: bytes, num_hashes: int = 128) -> 'MinHashSketch':
        """Deserializace."""
        sketch = cls(num_hashes=num_hashes)
        sketch.signature = np.frombuffer(data, dtype=np.uint64)
        return sketch


class SimHashSketch:
    """SimHash pro near-duplicate detection."""

    def __init__(self, dim: int = 64, salt: Optional[bytes] = None):
        self.dim = dim
        self.salt = salt or b''
        self.fingerprint = np.zeros(dim, dtype=np.float32)

    def _hash_features(self, features: List[str]) -> np.ndarray:
        """Hashuje features na vektor."""
        vectors = []
        for f in features:
            salted = self.salt + f.encode()
            h = int(hashlib.sha256(salted).hexdigest(), 16)
            # Převod na bitový vektor
            v = np.array([1 if (h >> i) & 1 else -1 for i in range(self.dim)], dtype=np.float32)
            vectors.append(v)
        return np.mean(vectors, axis=0) if vectors else np.zeros(self.dim, dtype=np.float32)

    def add_features(self, features: List[str]):
        """Přidá features a aktualizuje fingerprint."""
        self.fingerprint = self._hash_features(features)

    def hamming_distance(self, other: 'SimHashSketch') -> int:
        """Hammingova vzdálenost."""
        return int(np.sum(self.fingerprint != other.fingerprint))

    def to_bytes(self) -> bytes:
        """Serializace."""
        return self.fingerprint.tobytes()

    @classmethod
    def from_bytes(cls, data: bytes, dim: int = 64) -> 'SimHashSketch':
        """Deserializace."""
        sketch = cls(dim=dim)
        sketch.fingerprint = np.frombuffer(data, dtype=np.float32)
        return sketch
