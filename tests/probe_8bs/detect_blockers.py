#!/usr/bin/env python3
"""
SPRINT 8BS PROBE: Detekce sync I/O a CPU blockerů v async kontextech.
READ-ONLY — negeneruje žádné změny v produkčním kódu.
"""
import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path("/Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal")
IGNORE_DIRS = {".venv", "venv", ".phase", "tests/probe", "__pycache__", ".eggs", "build", "dist", ".pyenv", ".git"}


def should_ignore(path: Path) -> bool:
    """Kontrola, zda ignorovat adresář."""
    parts = path.parts
    for idir in IGNORE_DIRS:
        if idir in parts:
            return True
    return False


def get_line_for_node(node, source_lines):
    """Bezpečná extrakce řádku z AST uzlu."""
    if hasattr(node, 'lineno') and 1 <= node.lineno <= len(source_lines):
        return source_lines[node.lineno - 1]
    return ""


def find_async_functions_with_sync_calls(file_path: Path) -> Dict[str, List[Dict]]:
    """
    Najde async funkce obsahující synchronní operace.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        source_lines = source.splitlines()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return {}

    results = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue

        func_name = node.name
        async_func_key = f"{file_path.name}:{func_name}"

        func_body_lines = set()
        for child in ast.walk(node):
            if hasattr(child, 'lineno'):
                func_body_lines.add(child.lineno)

        sync_issues = []
        seen_codes = set()

        for lineno in func_body_lines:
            if lineno < 1 or lineno > len(source_lines):
                continue
            line = source_lines[lineno - 1]
            stripped = line.strip()

            if not stripped or stripped.startswith('#'):
                continue

            issue = detect_sync_issue(line, lineno)
            if issue and issue['code'] not in seen_codes:
                seen_codes.add(issue['code'])
                sync_issues.append(issue)

        if sync_issues:
            results[async_func_key] = sync_issues

    return results


def detect_sync_issue(line: str, lineno: int) -> Dict:
    """Detekce synchronních operací na úrovni řádku."""
    patterns = [
        ("requests.get", "SYNC_HTTP_GET"),
        ("requests.post", "SYNC_HTTP_POST"),
        ("requests.head", "SYNC_HTTP_HEAD"),
        ("requests.put", "SYNC_HTTP_PUT"),
        ("requests.delete", "SYNC_HTTP_DELETE"),
        ("requests.request", "SYNC_HTTP_REQUEST"),
        ("requests.Session", "SYNC_HTTP_SESSION"),
        ("urllib.request", "SYNC_URLLIB"),
        ("urllib.urlopen", "SYNC_URLLIB_OPEN"),
        (".open(", "SYNC_FILE_OPEN"),
        ("open(", "SYNC_FILE_OPEN"),
        (".read_text(", "SYNC_READ_TEXT"),
        (".read_bytes(", "SYNC_READ_BYTES"),
        (".write_text(", "SYNC_WRITE_TEXT"),
        (".write_bytes(", "SYNC_WRITE_BYTES"),
        ("json.loads(", "HEAVY_JSON_PARSE"),
        ("json.load(", "HEAVY_JSON_LOAD"),
    ]

    for pattern, issue_type in patterns:
        if pattern in line:
            return {
                'type': issue_type,
                'line': lineno,
                'code': line.strip()[:100]
            }
    return None


def main():
    print("=" * 70)
    print("SPRINT 8BS PROBE: Detekce sync I/O & CPU blockerů v async")
    print("=" * 70)

    py_files = list(REPO_ROOT.rglob("*.py"))
    py_files = [f for f in py_files if not should_ignore(f)]

    print(f"\nSkenuji {len(py_files)} Python souborů...")

    all_issues = {}
    total_http = 0
    total_file = 0
    total_json = 0

    for i, py_file in enumerate(py_files):
        if i % 500 == 0:
            print(f"  Progress: {i}/{len(py_files)}")
        issues = find_async_functions_with_sync_calls(py_file)
        if issues:
            all_issues[str(py_file.relative_to(REPO_ROOT))] = issues

    print("\n" + "=" * 70)
    print("VÝSLEDKY ANALÝZY")
    print("=" * 70)

    risk_colors = {
        "SYNC_HTTP": "🔴",
        "SYNC_URLLIB": "🔴",
        "SYNC_FILE": "🟡",
        "SYNC_READ": "🟡",
        "SYNC_WRITE": "🟡",
        "HEAVY_JSON": "🟢",
    }

    for file_rel, funcs in sorted(all_issues.items()):
        print(f"\n📁 {file_rel}")
        for func_name, issues in funcs.items():
            if not issues:
                continue
            print(f"  └─ async def {func_name}")
            for issue in issues:
                color = risk_colors.get(issue['type'], "⚪")
                print(f"      {color} L{issue['line']}: {issue['code']}")

    print("\n" + "=" * 70)
    print("SOUHRN RIZIK")
    print("=" * 70)

    all_blocks = []
    for file_rel, funcs in all_issues.items():
        for func_name, issues in funcs.items():
            all_blocks.extend(issues)

    http_blocks = [b for b in all_blocks if 'HTTP' in b['type'] or 'URLLIB' in b['type']]
    file_blocks = [b for b in all_blocks if 'FILE' in b['type'] or 'READ' in b['type'] or 'WRITE' in b['type']]
    json_blocks = [b for b in all_blocks if 'JSON' in b['type']]

    print(f"\n🔴 SYNC HTTP calls: {len(http_blocks)} blockerů")
    print(f"🟡 SYNC FILE I/O:   {len(file_blocks)} blockerů")
    print(f"🟢 HEAVY JSON:      {len(json_blocks)} blockerů")

    # Export pro JSON
    import json
    output = {
        "total_files": len(all_issues),
        "http_blockers": http_blocks,
        "file_blockers": file_blocks,
        "json_blockers": json_blocks,
        "all_issues": all_issues
    }

    with open(REPO_ROOT / "tests/probe_8bs/blockers_raw.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n✅ Detailní data uložena: tests/probe_8bs/blockers_raw.json")
    return all_issues


if __name__ == "__main__":
    main()
