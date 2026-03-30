"""
Paged Attention Cache – ukládá top‑K tokenů po stránkách.
Samostatně testovatelná komponenta.
"""

import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# MLX import s fallback
try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    mx = None


class PagedAttentionCache:
    """
    Page-based attention cache pro ukládání top-K tokenů.

    Features:
        - Stránky o fixed size (page_size tokenů)
        - Ukládá keys a values matice
        - Score-based page selection (top-k pages kept)
        - Maximální počet stránek (max_pages)
    """

    def __init__(
        self,
        max_pages: int = 32,
        page_size: int = 16,
        top_k: int = 128
    ):
        """
        Initialize PagedAttentionCache.

        Args:
            max_pages: Maximální počet stránek v cache
            page_size: Počet tokenů na stránku
            top_k: Počet top tokenů k sledování
        """
        self.max_pages = max_pages
        self.page_size = page_size
        self.top_k = top_k

        # List of (keys, values, avg_score) tuples
        self.pages: List[Tuple[mx.array, mx.array, float]] = []
        self.page_scores: List[float] = []

        logger.info(
            f"PagedAttentionCache initialized: max_pages={max_pages}, "
            f"page_size={page_size}, top_k={top_k}"
        )

    def update(
        self,
        keys: mx.array,
        values: mx.array,
        attention_scores: mx.array
    ) -> None:
        """
        Přidá nové stránky do cache.

        Args:
            keys: K matrix shape (seq_len, num_heads, head_dim)
            values: V matrix shape (seq_len, num_heads, head_dim)
            attention_scores: Attention scores shape (seq_len,)
        """
        if not MLX_AVAILABLE:
            return

        seq_len = keys.shape[0]
        num_pages = (seq_len + self.page_size - 1) // self.page_size

        for p in range(num_pages):
            start = p * self.page_size
            end = min(start + self.page_size, seq_len)

            # Extract page
            page_keys = keys[start:end]
            page_values = values[start:end]
            page_scores = attention_scores[start:end]

            # Compute average score for this page
            avg_score = float(mx.mean(page_scores))

            # Add to pages
            self.pages.append((page_keys, page_values, avg_score))
            self.page_scores.append(avg_score)

        # Prune to max_pages (keep top scoring pages)
        if len(self.pages) > self.max_pages:
            # Sort by score descending
            sorted_pages = sorted(
                zip(self.page_scores, self.pages),
                key=lambda x: x[0],
                reverse=True
            )
            # Keep top max_pages
            self.page_scores = [s for s, _ in sorted_pages[:self.max_pages]]
            self.pages = [p for _, p in sorted_pages[:self.max_pages]]

        logger.debug(f"PagedAttentionCache updated: {len(self.pages)} pages")

    def get(self) -> Optional[Tuple[mx.array, mx.array]]:
        """
        Vrátí všechny uložené pages jako concatenated keys a values.

        Returns:
            Tuple of (all_keys, all_values) or None pokud je cache prázdná
        """
        if not self.pages:
            return None

        if not MLX_AVAILABLE:
            return None

        all_keys = mx.concatenate([k for k, v, s in self.pages], axis=0)
        all_values = mx.concatenate([v for k, v, s in self.pages], axis=0)

        return all_keys, all_values

    def get_top_pages(self, k: int) -> List[Tuple[mx.array, mx.array, float]]:
        """
        Vrátí top-k stránek seřazené podle skóre.

        Args:
            k: Počet stránek k vrácení

        Returns:
            List of (keys, values, score) tuples
        """
        if not self.pages:
            return []

        sorted_pages = sorted(
            zip(self.page_scores, self.pages),
            key=lambda x: x[0],
            reverse=True
        )

        return [(k, v, s) for s, (k, v, _) in sorted_pages[:k]]

    def clear(self) -> None:
        """Vymaže všechny stránky z cache."""
        self.pages.clear()
        self.page_scores.clear()
        logger.debug("PagedAttentionCache cleared")

    def __len__(self) -> int:
        """Vrátí počet stránek v cache."""
        return len(self.pages)

    def get_memory_usage(self) -> int:
        """Vrátí přibližné využití paměti v bytech."""
        if not self.pages or not MLX_AVAILABLE:
            return 0

        total_bytes = 0
        for keys, values, _ in self.pages:
            # keys: seq_len * num_heads * head_dim * 4 bytes (float32)
            # values: same
            total_bytes += keys.nbytes + values.nbytes

        return total_bytes

    def is_ready(self) -> bool:
        """Zkontroluje, zda je cache připravena k použití."""
        return len(self.pages) > 0
