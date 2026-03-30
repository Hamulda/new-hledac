"""
Sprint 8UA: Import Smoke Test
test_smoke_run_imports_clean
"""

import subprocess


class TestImportClean:
    """test_smoke_run_imports_clean"""

    def test_import_main_no_import_error(self):
        """python3 -c 'import __main__' → no ImportError, no circular import"""
        result = subprocess.run(
            ["python3", "-c", "import sys; sys.path.insert(0, '.'); import hledac.universal.__main__"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd="/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"
        )
        # Check for import errors in stderr
        has_import_error = (
            "ImportError" in result.stderr or
            "ModuleNotFoundError" in result.stderr or
            "circular import" in result.stderr
        )
        assert not has_import_error, f"Import failed: {result.stderr[:500]}"
