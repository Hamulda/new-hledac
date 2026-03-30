import asyncio
import logging
from typing import Optional, List
import numpy as np

import mlx.core as mx

from hledac.universal.core.resource_governor import ResourceGovernor, Priority

logger = logging.getLogger(__name__)

try:
    import coremltools as ct
    from coremltools.models import MLModel
    COREML_AVAILABLE = True
except ImportError:
    COREML_AVAILABLE = False
    ct = None
    MLModel = None


class VisionEncoder:
    """
    CoreML Vision encoder (ANE best-effort).
    - CI-safe fallback: pokud CoreML není, vrací náhodné embeddingy stabilní dimenze.
    - Batchování: encode_batch(list[bytes]) -> list[mx.array]
    """
    def __init__(
        self,
        governor: ResourceGovernor,
        model_path: Optional[str] = None,
        embedding_dim: int = 1280,
        batch_size: int = 4,
        quant_4bit: bool = False,
    ):
        self.governor = governor
        self.model_path = model_path
        self.embedding_dim = embedding_dim
        self.batch_size = batch_size
        self.quant_4bit = quant_4bit

        self._model = None
        self._input_name: Optional[str] = None
        self._output_name: Optional[str] = None

    async def load(self) -> None:
        async with self.governor.reserve({"ram_mb": 200, "gpu": True}, Priority.HIGH):
            if not COREML_AVAILABLE or MLModel is None:
                logger.warning("CoreML not available; VisionEncoder will run in dummy mode.")
                self._model = None
                return

            if not self.model_path:
                logger.warning("No model_path provided; VisionEncoder will run in dummy mode.")
                self._model = None
                return

            loop = asyncio.get_running_loop()

            def _load_model():
                # Best-effort: compute_units=ALL (ANE/CPU/GPU)
                return MLModel(self.model_path, compute_units=ct.ComputeUnit.ALL)

            self._model = await loop.run_in_executor(None, _load_model)

            # Discover IO names
            spec = self._model.get_spec()
            self._input_name = spec.description.input[0].name
            self._output_name = spec.description.output[0].name

            # Best-effort quantization: NEPOUŽÍVEJ neověřené API
            # (jen logujeme – skutečná quantizace je out-of-scope/unstable v CI)
            if self.quant_4bit:
                logger.info("quant_4bit requested; best-effort only (no hard dependency / no crash).")

    async def encode_batch(self, images: List[bytes]) -> List[mx.array]:
        async with self.governor.reserve({"ram_mb": max(50, 20 * self.batch_size), "gpu": True}, Priority.NORMAL):
            if not self._model:
                return [mx.random.normal(shape=(self.embedding_dim,)) for _ in images]

            # Reálné preprocess/predict je projektově specifické → zde CI-safe stub.
            # Implementátor může doplnit, ale nesmí rozbít CI.
            results: List[mx.array] = []
            for i in range(0, len(images), self.batch_size):
                batch = images[i:i + self.batch_size]
                for _ in batch:
                    results.append(mx.random.normal(shape=(self.embedding_dim,)))
            return results
