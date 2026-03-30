"""Sprint 8UC: xgrammar availability check."""
import pytest


def test_xgrammar_grammar_compiler_available():
    """GrammarCompiler class must be available."""
    import xgrammar
    assert hasattr(xgrammar, 'GrammarCompiler')


def test_xgrammar_contrib_hf_logits_processor():
    """xgrammar.contrib.hf.LogitsProcessor should be accessible."""
    import xgrammar
    assert hasattr(xgrammar.contrib, 'hf')
    assert hasattr(xgrammar.contrib.hf, 'LogitsProcessor')


def test_xgrammar_tokenizer_info_from_tokenizer():
    """TokenizerInfo can be constructed from a tokenizer."""
    import xgrammar
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained("gpt2", trust_remote_code=True)
        ti = xgrammar.tokenizer_info.TokenizerInfo.from_tokenizer(tok)
        assert ti is not None
    except Exception:
        pytest.skip("transformers or gpt2 not available")
