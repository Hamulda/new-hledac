"""
Sprint 8UA: Repo Hygiene Tests
B.1: .gitignore + .bak deletion
B.2-B.3: Forward wrappers
"""

import glob
import ast
from pathlib import Path

# /hledac/universal/tests/probe_8ua/test_xxx.py
# .parent = probe_8ua/, .parent.parent = tests/, .parent.parent.parent = universal/
# universal/ is where model_lifecycle.py lives
UNIVERSAL = Path(__file__).parent.parent.parent


class TestBakFilesRemoved:
    """test_gitignore_has_bak_rule + test_bak_files_not_present"""

    def test_bak_files_not_present(self):
        """glob.glob('**/*.bak_*', recursive=True) → []"""
        bak_files = glob.glob("**/*.bak_*", recursive=True)
        assert bak_files == [], f"Found .bak files: {bak_files}"

    def test_gitignore_has_bak_rule(self):
        """.gitignore obsahuje *.bak* pravidlo"""
        # .gitignore is in project root (parent of universal/)
        gitignore = UNIVERSAL.parent.parent / ".gitignore"
        assert gitignore.exists(), f".gitignore not found at {gitignore}"
        content = gitignore.read_text()
        has_bak = any(p in content for p in ["*.bak", "*.bak_"])
        assert has_bak, f".gitignore missing *.bak* rule"


class TestForwardWrappers:
    """B.2-B.3: model_lifecycle + decision_engine forward wrappers"""

    def test_model_lifecycle_forward(self):
        """root model_lifecycle.py → forward na brain.model_lifecycle"""
        ml_path = UNIVERSAL / "model_lifecycle.py"
        assert ml_path.exists(), f"model_lifecycle.py not found at {ml_path}"
        content = ml_path.read_text()
        assert "DEPRECATED" in content, "Missing DEPRECATED marker"
        assert "brain.model_lifecycle" in content, "Missing brain.model_lifecycle forward"

    def test_decision_engine_forward(self):
        """root intelligence/decision_engine.py → forward na brain.decision_engine"""
        de_path = UNIVERSAL / "intelligence" / "decision_engine.py"
        assert de_path.exists(), f"intelligence/decision_engine.py not found at {de_path}"
        content = de_path.read_text()
        assert "DEPRECATED" in content, "Missing DEPRECATED marker"
        assert "brain.decision_engine" in content, "Missing brain.decision_engine forward"

    def test_import_model_lifecycle_no_crash(self):
        """model_lifecycle.py parses without error"""
        ml_path = UNIVERSAL / "model_lifecycle.py"
        with open(ml_path) as f:
            ast.parse(f.read())


class TestOrphanAudit:
    """B.7: Orphan audit file exists"""

    def test_orphan_audit_file_created(self):
        """~/.hledac/orphan_audit.json existuje a je valid JSON"""
        audit_path = Path.home() / ".hledac" / "orphan_audit.json"
        assert audit_path.exists(), f"Orphan audit not found at {audit_path}"
        import json
        with open(audit_path) as f:
            data = json.load(f)
        assert isinstance(data, dict), "Orphan audit must be a dict"
        assert "dht" in data, "Missing 'dht' key"
        assert "verdict" in data["dht"], "Missing 'verdict' in dht entry"
