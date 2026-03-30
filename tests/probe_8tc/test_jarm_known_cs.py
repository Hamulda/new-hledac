"""Sprint 8TC B.2: JARM known C2 detection"""
import pytest
from hledac.universal.transport.tor_transport import check_jarm_malicious


def test_jarm_known_cs():
    """check_jarm_malicious('2ad2ad0002ad2ad00042d42d000000ad') == 'Cobalt Strike 4.x'"""
    fp = "2ad2ad0002ad2ad00042d42d000000ad"
    result = check_jarm_malicious(fp)
    assert result == "Cobalt Strike 4.x"


def test_jarm_known_metasploit():
    """Known Metasploit JARM fingerprint"""
    fp = "07d14d16d21d21d07c42d41d00041d24"
    result = check_jarm_malicious(fp)
    assert result == "Metasploit Framework"


def test_jarm_unknown_returns_none():
    """check_jarm_malicious('0' * 32) → None"""
    fp = "0" * 32
    result = check_jarm_malicious(fp)
    assert result is None
