"""D.10 — Outlines is importable with structured generation APIs."""
import sys

sys.path.insert(0, ".")


def test_outlines_importable():
    """Outlines package is importable."""
    import outlines

    assert outlines is not None


def test_outlines_generator_json():
    """outlines.generator.JsonSchema exists for structured synthesis."""
    import outlines.generator

    assert hasattr(outlines.generator, "JsonSchema"), (
        "outlines.generator.JsonSchema not found — required for 8QC structured synthesis"
    )


def test_outlines_models_mlxlm():
    """outlines.models.mlxlm exists for MLX-native generation."""
    import outlines.models

    assert hasattr(outlines.models, "mlxlm"), (
        "outlines.models.mlxlm not found — required for 8QC MLX integration"
    )
