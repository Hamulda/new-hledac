"""
Universal Tools - Lightweight and Memory-Efficient

Tools optimized for M1 8GB RAM with minimal memory footprint.
"""

from .reranker import (
    LightweightReranker,
    RerankResult,
    RerankRequest,
    RerankerConfig,
    RerankerFactory,
    create_reranker
)
from .content_miner import (
    RustMiner,
    MiningResult,
    create_rust_miner
)

# Sprint 80: OSINT adapters
from .commoncrawl_adapter import CommonCrawlAdapter, RawFinding
from .wayback_adapter import WaybackAdapter

__all__ = [
    # Reranker
    'LightweightReranker',
    'RerankResult',
    'RerankRequest',
    'RerankerConfig',
    'RerankerFactory',
    'create_reranker',
    # Miner
    'RustMiner',
    'MiningResult',
    'create_rust_miner',
    # Sprint 80: OSINT adapters
    'CommonCrawlAdapter',
    'WaybackAdapter',
    'RawFinding',
]
