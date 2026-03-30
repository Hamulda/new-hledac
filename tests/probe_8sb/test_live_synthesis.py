"""D.13: Live synthesis test — requires model on disk."""
import asyncio
import sys
import time

sys.path.insert(0, ".")

from hledac.universal.brain.synthesis_runner import SynthesisRunner
from hledac.universal.brain.model_lifecycle import ModelLifecycle
from hledac.universal.core.resource_governor import sample_uma_status


async def test_live_synthesis():
    """Live MLX synthesis with Qwen2.5-0.5B or SmolLM2-135M."""
    s0 = sample_uma_status()
    runner = SynthesisRunner(ModelLifecycle())

    findings = [
        {
            "source_type": "cisa_kev",
            "confidence": 0.95,
            "text": "CVE-2026-1234 LockBit exploiting Windows SMB",
        },
        {
            "source_type": "clearnet",
            "confidence": 0.8,
            "text": "LockBit affiliate using Cobalt Strike beacon",
        },
    ]

    t = time.monotonic()
    report = await runner.synthesize_findings(
        "LockBit ransomware 2026", findings, force_synthesis=True
    )
    elapsed = time.monotonic() - t
    s1 = sample_uma_status()

    print(f"\nSynthesis: {elapsed:.1f}s | UMA: +{s1.rss_gib - s0.rss_gib:.2f}GiB")

    if report:
        print(f"Confidence: {getattr(report, 'confidence', 0):.2f}")
        print(f"Threat actors: {getattr(report, 'threat_actors', [])}")
        assert getattr(report, "confidence", 0) >= 0.3, "Confidence should be ≥ 0.3"
        print("SYNTHESIS LIVE: PASS ✅")
    else:
        print("SYNTHESIS SKIPPED (model not found or UMA guard)")
        print("NOTE: Run with model cached to verify live synthesis")

    await runner.close()


if __name__ == "__main__":
    asyncio.run(test_live_synthesis())
