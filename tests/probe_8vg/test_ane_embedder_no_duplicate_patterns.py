import pathlib

def test_ane_embedder_no_duplicate_patterns():
    def _count_pattern_defs(filepath: str) -> int:
        src = pathlib.Path(filepath).read_text(errors="ignore")
        return src.count("_IOC_PATTERNS")
    ner   = _count_pattern_defs("brain/ner_engine.py")
    embed = _count_pattern_defs("brain/ane_embedder.py")
    assert ner >= 1,  "ner_engine.py musi definovat _IOC_PATTERNS"
    assert embed <= 1, \
        "ane_embedder.py nesmi DEFINOVAT _IOC_PATTERNS — pouze re-exportovat"
