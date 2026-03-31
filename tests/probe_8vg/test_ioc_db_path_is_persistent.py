from paths import get_ioc_db_path

def test_ioc_db_path_is_persistent():
    p = get_ioc_db_path()
    assert p.suffix == ".duckdb"
    assert "memory" not in str(p)
    assert "hledac" in str(p).lower() or str(p).startswith("/")
