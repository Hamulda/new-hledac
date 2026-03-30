"""Sprint 8RB — STIX bundle validates: export_stix_bundle() → stix2.Bundle → stix2.parse() passes."""
import asyncio
import tempfile
import time
from pathlib import Path
import kuzu
import stix2


def test_stix_bundle_validates():
    """Multiple IOCs → export_stix_bundle() → stix2.Bundle() → stix2.parse() does not crash."""
    from hledac.universal.knowledge.ioc_graph import IOCGraph

    with tempfile.TemporaryDirectory() as tmpdir:
        g = IOCGraph(db_path=Path(tmpdir) / "test_bundle")
        g._db = kuzu.Database(str(Path(tmpdir) / "test_bundle"))
        g._conn = kuzu.Connection(g._db)
        g._init_schema_sync()

        now = time.time()
        # Insert multiple IOC types
        for ioc_type, value in [
            ("ip", "10.0.0.1"),
            ("domain", "example.com"),
            ("cve", "CVE-2026-9999"),
            ("hash_sha256", "a" * 64),
        ]:
            g._conn.execute(
                "CREATE (:IOC {id: $id, ioc_type: $t, value: $v, "
                "first_seen: $ts, last_seen: $ts, confidence: $c})",
                {"id": f"{ioc_type}:{value}", "t": ioc_type, "v": value, "ts": now, "c": 0.9},
            )

        result = asyncio.run(g.export_stix_bundle())

        # stix2.parse() must not raise
        try:
            bundle = stix2.Bundle(objects=result)
            stix2.parse(bundle.serialize())
            validation_passed = True
        except Exception as e:
            validation_passed = False
            raise AssertionError(f"stix2.parse() failed: {e}") from e

        assert validation_passed
        g._close_sync()


if __name__ == "__main__":
    test_stix_bundle_validates()
    print("test_stix_bundle_validates: PASS")
