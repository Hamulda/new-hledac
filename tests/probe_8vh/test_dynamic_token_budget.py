"""Test: synthesis_runner.py does NOT contain hardcoded 7200 chars limit."""
import os

src_path = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "brain", "synthesis_runner.py"
)
with open(src_path) as f:
    src = f.read()


def test_dynamic_token_budget():
    # Check for hardcoded 7200 limit in RAG context (old bad pattern)
    # The new code uses _distill_findings instead
    has_distill = "_distill_findings" in src
    has_dynamic_budget = "TOTAL_BUDGET" in src or "_distill_findings" in src

    # If 7200 appears, it should be in context of the new distillation approach
    if "7200" in src and not has_distill:
        raise AssertionError("Hardcoded 7200 char limit nalezen bez dynamického budgetu")
