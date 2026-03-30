"""
Sprint 6B: Torch Eviction Tests
================================

Tests that verify:
- No eager/module-level torch imports in patched files
- torch is lazy-loaded where it remains as fallback
"""

import ast
import os
import unittest


def _has_module_level_torch_import(file_path):
    """Check if file has module-level torch import (not inside function/class)."""
    with open(file_path, "r") as f:
        content = f.read()

    tree = ast.parse(content)

    # Get top-level nodes
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "torch" or alias.name.startswith("torch."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "torch" or node.module.startswith("torch.")):
                return True
        # Skip function/def/class definitions - their body is not top-level
    return False


class TestTorchEviction(unittest.TestCase):
    """Tests for torch eviction from patched modules."""

    def test_stealth_layer_no_eager_torch(self):
        """Test stealth_layer.py has no eager torch import."""
        base = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"
        file_path = os.path.join(base, "layers/stealth_layer.py")
        if not os.path.exists(file_path):
            self.skipTest("stealth_layer.py not found")

        has_eager = _has_module_level_torch_import(file_path)
        self.assertFalse(has_eager, "stealth_layer.py has module-level torch import")

    def test_ner_engine_no_eager_torch(self):
        """Test ner_engine.py has no eager torch import."""
        base = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"
        file_path = os.path.join(base, "brain/ner_engine.py")
        if not os.path.exists(file_path):
            self.skipTest("ner_engine.py not found")

        has_eager = _has_module_level_torch_import(file_path)
        self.assertFalse(has_eager, "ner_engine.py has module-level torch import")

    def test_stego_detector_no_eager_torch(self):
        """Test stego_detector.py has no eager torch import."""
        base = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"
        file_path = os.path.join(base, "security/stego_detector.py")
        if not os.path.exists(file_path):
            self.skipTest("stego_detector.py not found")

        has_eager = _has_module_level_torch_import(file_path)
        self.assertFalse(has_eager, "stego_detector.py has module-level torch import")

    def test_document_intelligence_no_eager_torch(self):
        """Test document_intelligence.py has no eager torch import."""
        base = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"
        file_path = os.path.join(base, "intelligence/document_intelligence.py")
        if not os.path.exists(file_path):
            self.skipTest("document_intelligence.py not found")

        has_eager = _has_module_level_torch_import(file_path)
        self.assertFalse(has_eager, "document_intelligence.py has module-level torch import")


class TestTorchLazyFallback(unittest.TestCase):
    """Tests for lazy torch fallback patterns."""

    def test_ner_engine_has_lazy_torch(self):
        """Test ner_engine.py uses _get_torch() pattern."""
        base = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"
        file_path = os.path.join(base, "brain/ner_engine.py")
        if not os.path.exists(file_path):
            self.skipTest("ner_engine.py not found")

        with open(file_path, "r") as f:
            content = f.read()

        # Should have _get_torch function
        self.assertIn("def _get_torch(", content)
        # Should have _TORCH_AVAILABLE sentinel
        self.assertIn("_TORCH_AVAILABLE", content)

    def test_stego_detector_has_lazy_mps_check(self):
        """Test stego_detector.py uses _check_mps_available() pattern."""
        base = "/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal"
        file_path = os.path.join(base, "security/stego_detector.py")
        if not os.path.exists(file_path):
            self.skipTest("stego_detector.py not found")

        with open(file_path, "r") as f:
            content = f.read()

        # Should have _check_mps_available function
        self.assertIn("def _check_mps_available(", content)


if __name__ == "__main__":
    unittest.main()
