import os

def fake_generate_supported(prompt=None, max_kv_size=None, kv_cache_type=None, attention_sink_size=None):
    return {"ok": True}

def fake_generate_partial(prompt=None, max_kv_size=None):
    return {"ok": True}

def fake_generate_old(prompt=None):
    return {"ok": True}

def test_signature_gating_supported():
    from hledac.universal.brain.hermes3_engine import Hermes3Engine
    os.environ["GHOST_HERMES_SUSTAIN"] = "1"
    os.environ["GHOST_KV_SIZE"] = "4096"
    kw = Hermes3Engine._build_sustain_generate_kwargs_for_test(fake_generate_supported)
    assert kw["max_kv_size"] == 4096
    assert kw["kv_cache_type"] == "rotating"
    assert kw["attention_sink_size"] == 4

def test_signature_gating_partial():
    from hledac.universal.brain.hermes3_engine import Hermes3Engine
    os.environ["GHOST_HERMES_SUSTAIN"] = "1"
    os.environ["GHOST_KV_SIZE"] = "4096"
    kw = Hermes3Engine._build_sustain_generate_kwargs_for_test(fake_generate_partial)
    assert kw == {"max_kv_size": 4096}

def test_signature_gating_old():
    from hledac.universal.brain.hermes3_engine import Hermes3Engine
    os.environ["GHOST_HERMES_SUSTAIN"] = "1"
    kw = Hermes3Engine._build_sustain_generate_kwargs_for_test(fake_generate_old)
    assert kw == {}
