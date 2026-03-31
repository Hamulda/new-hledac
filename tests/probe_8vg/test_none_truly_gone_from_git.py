import subprocess

def test_none_truly_gone_from_git():
    result = subprocess.run(
        ["git", "ls-files", "None"],
        capture_output=True, text=True
    )
    assert result.stdout.strip() == "", \
        f"Soubor 'None' stale v git indexu: {result.stdout}"
