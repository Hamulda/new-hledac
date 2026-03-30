import asyncio
import logging
from typing import Optional, Tuple

import mlx.core as mx
import mlx.nn as nn
import mlx.utils as mlx_utils

logger = logging.getLogger(__name__)


def _safe_mha(d_model: int, num_heads: int = 8):
    """
    Best-effort MultiHeadAttention init:
    některé verze MLX mohou mít jiné parametry.
    """
    try:
        return nn.MultiHeadAttention(d_model, num_heads=num_heads, use_flash_attn=True)
    except TypeError:
        return nn.MultiHeadAttention(d_model, num_heads=num_heads)


class MambaFusion(nn.Module):
    """
    Fusion: (vision,text,graph) -> proj -> [FlashAttn] -> [Mamba/MLP] -> out

    Kritické fixy:
    - MultiHeadAttention může vrátit tuple (out, weights)
    - nn.Mamba nepodporuje use_flash_attn parametr (nepoužíváme)
    - Mamba optional: fallback MLP
    """
    def __init__(
        self,
        vision_dim: int = 1280,
        text_dim: int = 768,
        graph_dim: int = 64,
        hidden: int = 256,
        output_dim: int = 128,
        num_heads: int = 8,
    ):
        super().__init__()
        self.vision_proj = nn.Linear(vision_dim, hidden)
        self.text_proj = nn.Linear(text_dim, hidden)
        self.graph_proj = nn.Linear(graph_dim, hidden)

        d_model = hidden * 3
        self.attn = _safe_mha(d_model, num_heads=num_heads)

        # Mamba optional
        self._has_mamba = hasattr(nn, "Mamba")
        if self._has_mamba:
            try:
                self.mamba = nn.Mamba(d_model=d_model, d_state=16, d_conv=4, expand=2)
                self.post = nn.Identity()
            except Exception as e:
                logger.warning(f"Failed to init nn.Mamba; falling back to MLP. err={e}")
                self._has_mamba = False

        if not self._has_mamba:
            self.mamba = nn.Sequential(
                nn.Linear(d_model, d_model),
                nn.ReLU(),
                nn.Linear(d_model, d_model),
            )

        self.out_proj = nn.Linear(d_model, output_dim)

    def __call__(self, vision_emb: mx.array, text_emb: mx.array, graph_emb: mx.array) -> mx.array:
        v = self.vision_proj(vision_emb)
        t = self.text_proj(text_emb)
        g = self.graph_proj(graph_emb)
        x = mx.concatenate([v, t, g], axis=-1)  # (D,)

        # attention expects (B, T, D) in many impls; keep T=1
        qkv = x.reshape(1, 1, -1)
        result = self.attn(qkv, qkv, qkv)
        # tuple-safe fix
        attn_out = result[0] if isinstance(result, tuple) else result

        fused = self.mamba(attn_out)
        # ensure shape back to (D,)
        fused = fused.reshape(-1)
        return self.out_proj(fused)

    def save(self, path: str) -> None:
        flat = dict(mlx_utils.tree_flatten(self.parameters()))
        mx.savez(path, **flat)

    def load(self, path: str) -> None:
        params = mx.load(path)
        # load_weights expects list[(k,v)]
        self.load_weights(list(params.items()))


class MobileCLIPFusion:
    """
    Optional MobileCLIP wrapper.
    CI-safe: pokud mobileclip není, ImportError při load.
    Lazy init + lazy lock (žádný asyncio.Lock v __init__).
    """
    def __init__(self):
        self._model = None
        self._tokenizer = None
        self.embed_dim = 512
        self.__lock = None

    @property
    def _lock(self):
        if self.__lock is None:
            self.__lock = asyncio.Lock()
        return self.__lock

    async def _lazy_load(self) -> None:
        async with self._lock:
            if self._model is not None:
                return
            try:
                from mobileclip import create_model_and_transforms, get_tokenizer
            except ImportError as e:
                raise ImportError("mobileclip not available") from e

            loop = asyncio.get_running_loop()

            def _load():
                model, _, _ = create_model_and_transforms("mobileclip_s0")
                tok = get_tokenizer("mobileclip_s0")
                return model, tok

            self._model, self._tokenizer = await loop.run_in_executor(None, _load)
            logger.info("MobileCLIP loaded")

    async def encode_text(self, text: str) -> mx.array:
        await self._lazy_load()
        return mx.random.normal(shape=(self.embed_dim,))

    async def encode_image(self, image_bytes: bytes) -> mx.array:
        await self._lazy_load()
        return mx.random.normal(shape=(self.embed_dim,))

    async def fuse(self, text_emb: mx.array, image_emb: mx.array) -> mx.array:
        return (text_emb + image_emb) / 2
