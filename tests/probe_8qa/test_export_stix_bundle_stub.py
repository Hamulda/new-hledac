"""Sprint 8QA: export_stix_bundle stub test."""

import asyncio
import tempfile

import pytest

from hledac.universal.knowledge.ioc_graph import IOCGraph


@pytest.mark.asyncio
async def test_export_stix_bundle_stub():
    """After inserting 3 IOC nodes, export_stix_bundle returns list of length 3."""
    with tempfile.TemporaryDirectory() as d:
        g = IOCGraph(db_path=f"{d}/graph")
        await g.initialize()

        await g.upsert_ioc("cve", "CVE-2026-1")
        await g.upsert_ioc("ip", "1.2.3.4")
        await g.upsert_ioc("malware", "lockbit")

        bundle = await g.export_stix_bundle()
        assert len(bundle) == 3
        for item in bundle:
            assert item["type"] == "indicator"
            assert item["spec_version"] == "2.1"
            assert "id" in item
            assert "value" in item
            assert "ioc_type" in item
        await g.close()
