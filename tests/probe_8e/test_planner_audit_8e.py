"""
Sprint 8E: Planner Read-Only Audit Probe
=========================================
Validates PLANNER_AUDIT_8E.md exists and meets all mandatory requirements.

Run: pytest tests/probe_8e/ -v
Duration: <5 seconds (read-only, no execution)
"""

import os
from pathlib import Path

import pytest


# Root of the universal package
UNIVERSAL_ROOT = Path(__file__).parent.parent.parent.resolve()


class TestAuditDocumentExists:
    """Verify audit document exists."""

    def test_audit_doc_exists(self):
        """Verify PLANNER_AUDIT_8E.md exists."""
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        assert audit_path.exists(), f"Audit doc not found at {audit_path}"

    def test_audit_doc_is_readable(self):
        """Verify audit doc is readable."""
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        content = audit_path.read_text()
        assert len(content) > 100, "Audit doc is too short to be valid"


class TestAuditMandatorySections:
    """Verify all mandatory sections are present."""

    @pytest.fixture
    def audit_content(self):
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        return audit_path.read_text()

    def test_section_scope_and_methodology(self, audit_content):
        """Section 1: Scope a metodika."""
        assert "Scope" in audit_content or "scope" in audit_content.lower()

    def test_section_inventory(self, audit_content):
        """Section 2: Ground-truth inventory."""
        assert "inventory" in audit_content.lower() or "Inventory" in audit_content

    def test_section_top_10_by_size(self, audit_content):
        """Section 3: Top 10 souboru podle velikosti."""
        assert "Top 10" in audit_content or "top 10" in audit_content.lower()

    def test_section_ao_coupling_matrix(self, audit_content):
        """Section 4: AO coupling matrix."""
        assert "AO coupling" in audit_content or "coupling" in audit_content.lower()

    def test_section_runtime_storage_model_coupling(self, audit_content):
        """Section 5: Runtime/storage/model coupling matrix."""
        assert "runtime" in audit_content.lower() or "Runtime" in audit_content

    def test_section_tier_map(self, audit_content):
        """Section 6: Tier 1 / Tier 2 / Tier 3 patch map."""
        assert "Tier 1" in audit_content or "Tier 2" in audit_content
        assert "Tier 3" in audit_content or "FORBIDDEN" in audit_content

    def test_section_first_insertion_point(self, audit_content):
        """Section 7: Prvni realisticky non-AO insertion point."""
        assert "insertion point" in audit_content.lower() or "Insertion" in audit_content

    def test_section_safe_sequence(self, audit_content):
        """Section 8: Navrh bezpecne posloupnosti."""
        assert "posloupnosti" in audit_content.lower() or "sequence" in audit_content.lower()

    def test_section_forbidden(self, audit_content):
        """Section 9: Co je explicitne zakazano."""
        assert "ZAKAZ" in audit_content or "FORBIDDEN" in audit_content or "Forbidden" in audit_content

    def test_section_recommended_sprint(self, audit_content):
        """Section 10: Doporuceny dalsi implementacni sprint."""
        assert "Sprint 8" in audit_content or "doporuceni" in audit_content.lower() or "recommended" in audit_content.lower()


class TestTierClassification:
    """Verify Tier classification is correct."""

    @pytest.fixture
    def audit_content(self):
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        return audit_path.read_text()

    def test_tier_1_not_empty(self, audit_content):
        """Tier 1 must not be empty."""
        # Look for Tier 1 section
        assert "Tier 1" in audit_content or "SAFE-TO-TOUCH" in audit_content
        # Should mention at least search.py or htn_planner or cost_model
        assert (
            "search.py" in audit_content
            or "htn_planner.py" in audit_content
            or "cost_model.py" in audit_content
            or "task_cache.py" in audit_content
        )

    def test_tier_1_files_exist(self, audit_content):
        """All files mentioned as Tier 1 must exist."""
        planning_dir = UNIVERSAL_ROOT / "planning"

        # Check for each potential Tier 1 file
        tier1_files = [
            "search.py",
            "task_cache.py",
            "htn_planner.py",
            "cost_model.py",
        ]
        for fname in tier1_files:
            if fname in audit_content:
                fpath = planning_dir / fname
                assert fpath.exists(), f"Tier 1 file {fname} does not exist at {fpath}"

    def test_no_autonomous_orchestrator_in_tier_1(self, audit_content):
        """autonomous_orchestrator.py must NOT be in Tier 1."""
        # Find Tier 1 section (between Tier 1 and Tier 2 headers)
        tier1_section = ""
        lines = audit_content.split("\n")
        in_tier1 = False
        for line in lines:
            if "Tier 1" in line or "SAFE-TO-TOUCH" in line:
                in_tier1 = True
            elif "Tier 2" in line or "PATCHNUTELNE" in line:
                in_tier1 = False
            if in_tier1:
                tier1_section += line + "\n"

        # If we have a Tier 1 section, check it doesn't contain autonomous_orchestrator
        if tier1_section.strip():
            assert "autonomous_orchestrator" not in tier1_section, (
                "autonomous_orchestrator.py must NOT be in Tier 1"
            )


class TestAOCouplingSection:
    """Verify explicit AO coupling section exists."""

    @pytest.fixture
    def audit_content(self):
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        return audit_path.read_text()

    def test_ao_coupling_section_exists(self, audit_content):
        """Audit must have explicit AO coupling section."""
        assert "AO coupling" in audit_content or "autonomous_orchestrator" in audit_content

    def test_ao_coupling_result_documented(self, audit_content):
        """AO coupling result must be documented (found or not found)."""
        assert "ZADNA" in audit_content or "ZÁDNÁ" in audit_content or "Zadne" in audit_content or "Z žádná" in audit_content or "No matches" in audit_content or "NONE" in audit_content


class TestRecommendedNextSprint:
    """Verify recommended next sprint is documented."""

    @pytest.fixture
    def audit_content(self):
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        return audit_path.read_text()

    def test_recommended_sprint_mentioned(self, audit_content):
        """Recommended next sprint must be explicitly mentioned."""
        assert "8F" in audit_content or "doporuceny" in audit_content.lower() or "recommended" in audit_content.lower()


class TestPlannerFilesIntegrity:
    """Verify planner files exist and are consistent."""

    def test_planning_directory_exists(self):
        """Verify planning/ directory exists."""
        planning_dir = UNIVERSAL_ROOT / "planning"
        assert planning_dir.exists(), f"planning/ dir not found at {planning_dir}"

    def test_planning_init_exists(self):
        """Verify planning/__init__.py exists."""
        init_path = UNIVERSAL_ROOT / "planning" / "__init__.py"
        assert init_path.exists(), f"__init__.py not found at {init_path}"

    def test_all_planner_modules_exist(self):
        """Verify all expected planner modules exist."""
        expected = [
            "cost_model.py",
            "htn_planner.py",
            "search.py",
            "slm_decomposer.py",
            "task_cache.py",
        ]
        planning_dir = UNIVERSAL_ROOT / "planning"
        for fname in expected:
            fpath = planning_dir / fname
            assert fpath.exists(), f"Expected planner module {fname} not found at {fpath}"


class TestForbiddenZones:
    """Verify forbidden zones are properly marked."""

    @pytest.fixture
    def audit_content(self):
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        return audit_path.read_text()

    def test_autonomous_orchestrator_forbidden(self, audit_content):
        """autonomous_orchestrator.py must be listed as forbidden."""
        assert "autonomous_orchestrator" in audit_content

    def test_duckdb_store_forbidden(self, audit_content):
        """duckdb_store.py must be listed as forbidden."""
        assert "duckdb" in audit_content.lower() or "DuckDB" in audit_content


class TestPlannerInventory:
    """Verify ground-truth planner inventory."""

    @pytest.fixture
    def audit_content(self):
        audit_path = UNIVERSAL_ROOT / "PLANNER_AUDIT_8E.md"
        return audit_path.read_text()

    def test_planner_files_listed(self, audit_content):
        """Planner files should be listed in inventory."""
        assert "planning/" in audit_content
        assert ".py" in audit_content

    def test_cost_model_mentioned(self, audit_content):
        """cost_model.py should be mentioned."""
        assert "cost_model" in audit_content

    def test_htn_planner_mentioned(self, audit_content):
        """htn_planner.py should be mentioned."""
        assert "htn_planner" in audit_content

    def test_search_mentioned(self, audit_content):
        """search.py should be mentioned."""
        assert "search.py" in audit_content or "search" in audit_content

    def test_slm_decomposer_mentioned(self, audit_content):
        """slm_decomposer.py should be mentioned."""
        assert "slm_decomposer" in audit_content

    def test_task_cache_mentioned(self, audit_content):
        """task_cache.py should be mentioned."""
        assert "task_cache" in audit_content
