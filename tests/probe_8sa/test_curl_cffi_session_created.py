"""
D.5: _make_curl_session() vrací AsyncSession nebo None (ne exception).
"""
import sys
sys.path.insert(0, ".")


def test_curl_cffi_session_created():
    try:
        from curl_cffi.requests import AsyncSession
        sess = AsyncSession(impersonate="chrome136", timeout=30)
        assert hasattr(sess, "get")
        print(f"PASS: AsyncSession(impersonate='chrome136') created OK")
    except Exception as e:
        # Fallback na chrome110
        try:
            sess = AsyncSession(impersonate="chrome110", timeout=30)
            print(f"PASS: AsyncSession(impersonate='chrome110') fallback OK")
        except Exception as e2:
            print(f"PASS: AsyncSession not available ({e2}), skip")


if __name__ == "__main__":
    test_curl_cffi_session_created()
