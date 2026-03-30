"""
Network Analysis Module
=======================

Network-based OSINT and threat detection capabilities:
- DNS Tunneling Detector: Cascade detection with entropy, N-gram, and MLX LSTM
- PCAP streaming analysis with constant memory

M1 8GB Optimized: Streaming algorithms, <1GB memory regardless of PCAP size
"""

# Lazy loading for optional components
DNS_TUNNEL_DETECTOR_AVAILABLE = False
try:
    from .dns_tunnel_detector import (
        DNSTunnelDetector,
        DNSTunnelConfig,
        TunnelingFinding,
        NGramScore,
        create_dns_tunnel_detector,
    )
    DNS_TUNNEL_DETECTOR_AVAILABLE = True
except ImportError:
    DNSTunnelDetector = None  # type: ignore
    DNSTunnelConfig = None  # type: ignore
    TunnelingFinding = None  # type: ignore
    NGramScore = None  # type: ignore
    create_dns_tunnel_detector = None  # type: ignore

__all__ = [
    "DNS_TUNNEL_DETECTOR_AVAILABLE",
]

if DNS_TUNNEL_DETECTOR_AVAILABLE:
    __all__.extend([
        "DNSTunnelDetector",
        "DNSTunnelConfig",
        "TunnelingFinding",
        "NGramScore",
        "create_dns_tunnel_detector",
    ])
