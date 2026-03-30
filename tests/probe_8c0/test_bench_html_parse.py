"""
Sprint 8C0 Benchmark 2: HTML Parse Throughput

Measures:
- pages_per_second (parse throughput)
- p50 / p95 parse latency (ms)

Fixtures: real HTML files from fixture_manifest.json (within repo).

Compares parser paths if multiple exist:
- selectolax (fast, CSS selector)
- lxml (fallback, XPath)
- built-in html.parser (stdlib, always available)

If selectolax not installed → report MISSING_DEP honestly.
"""

import sys
import time
import unittest
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.bench_8c0.common_stats import (
    build_result,
    check_selectolax,
    load_html_fixtures,
    write_results,
    compute_percentile,
)


# ---------------------------------------------------------------------------
# Parser implementations
# ---------------------------------------------------------------------------

def parse_with_selectolax(html: str) -> List[str]:
    """Parse HTML with selectolax, extract all text content."""
    from selectolax.parser import HTMLParser
    parser = HTMLParser(html)
    return [node.text() for node in parser.css("body")] if parser.css("body") else []


def parse_with_lxml(html: str) -> List[str]:
    """Parse HTML with lxml, extract text content."""
    try:
        from lxml import html as lxml_html
        tree = lxml_html.fromstring(html)
        return tree.xpath("//body//text()")
    except Exception:
        return []


def parse_with_stdlib(html_content: str) -> List[str]:
    """Parse HTML with stdlib html.parser, extract text."""
    import html.parser as _html_parser
    class TextExtractor(_html_parser.HTMLParser):
        def __init__(self):
            super().__init__()
            self.texts: List[str] = []
            self._in_body = False

        def handle_starttag(self, tag, _attrs):
            if tag == "body":
                self._in_body = True

        def handle_endtag(self, tag):
            if tag == "body":
                self._in_body = False

        def handle_data(self, data):
            if self._in_body:
                self.texts.append(data)

    parser = TextExtractor()
    try:
        parser.feed(html_content)
        return parser.texts
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------

class TestHTMLParseBenchmark(unittest.TestCase):
    """
    HTML parse throughput benchmark.
    """

    @classmethod
    def setUpClass(cls):
        cls.fixtures = load_html_fixtures(limit=50)
        cls.selectolax_available = check_selectolax()

    def test_fixtures_loaded(self):
        """Verify we have real HTML fixtures to parse."""
        self.assertGreater(
            len(self.fixtures), 0,
            "No HTML fixtures found — benchmark cannot run"
        )

    def test_selectolax_throughput(self):
        """
        Measure selectolax parse throughput (pages/s, p50/p95 latency ms).
        Report MISSING_DEP if not installed.
        """
        fixtures = self.fixtures
        if not fixtures:
            self.skipTest("No HTML fixtures")

        if not self.selectolax_available:
            result = build_result(
                benchmark="html_parse_selectolax",
                durations_ms=[],
                warmup=0,
                unit="pages/s",
                fixtures=[],
                status="MISSING_DEP",
                reason="selectolax not installed",
            )
            output_path = PROJECT_ROOT / "tests" / "probe_8c0" / "results" / "html_parse_selectolax.jsonl"
            write_results([result], output_path)
            self.skipTest("selectolax not installed — reported as MISSING_DEP")

        # Warmup
        for _, html in fixtures[:3]:
            parse_with_selectolax(html)

        # Measure
        n_runs = 10
        durations: List[float] = []

        for _ in range(n_runs):
            start = time.perf_counter_ns()
            for _, html in fixtures:
                parse_with_selectolax(html)
            elapsed_ns = time.perf_counter_ns() - start
            durations.append(elapsed_ns / 1_000_000)  # ms total for all pages

        pages_per_run = len(fixtures)
        total_ms = sum(durations)
        total_s = total_ms / 1000
        pages_per_second = pages_per_run / total_s * n_runs if total_s > 0 else 0.0  # approximate

        # Per-page latency in ms
        per_page_ms = [d / pages_per_run for d in durations]

        result = build_result(
            benchmark="html_parse_selectolax",
            durations_ms=per_page_ms,
            warmup=2,
            unit="ms/page",
            fixtures=[fp for fp, _ in fixtures],
            status="PASS",
            extra={
                "pages_per_second": round(pages_per_second, 2),
                "p50_latency_ms": round(compute_percentile(per_page_ms, 0.50), 3),
                "p95_latency_ms": round(compute_percentile(per_page_ms, 0.95), 3),
                "total_pages_parsed": pages_per_run * n_runs,
            },
        )

        output_path = PROJECT_ROOT / "tests" / "probe_8c0" / "results" / "html_parse_selectolax.jsonl"
        write_results([result], output_path)

        self.assertGreater(result["median"], 0)

    def test_lxml_throughput(self):
        """
        Measure lxml parse throughput as fallback parser path.
        """
        fixtures = self.fixtures
        if not fixtures:
            self.skipTest("No HTML fixtures")

        lxml_available = True
        try:
            from lxml import html  # noqa: F401
        except ImportError:
            lxml_available = False

        if not lxml_available:
            result = build_result(
                benchmark="html_parse_lxml",
                durations_ms=[],
                warmup=0,
                unit="pages/s",
                fixtures=[],
                status="MISSING_DEP",
                reason="lxml not installed",
            )
            output_path = PROJECT_ROOT / "tests" / "probe_8c0" / "results" / "html_parse_lxml.jsonl"
            write_results([result], output_path)
            self.skipTest("lxml not installed — reported as MISSING_DEP")

        # Warmup
        for _, html_content in fixtures[:3]:
            parse_with_lxml(html_content)

        # Measure
        n_runs = 10
        durations: List[float] = []

        for _ in range(n_runs):
            start = time.perf_counter_ns()
            for _, html_content in fixtures:
                parse_with_lxml(html_content)
            elapsed_ns = time.perf_counter_ns() - start
            durations.append(elapsed_ns / 1_000_000)

        pages_per_run = len(fixtures)
        per_page_ms = [d / pages_per_run for d in durations]
        total_s = sum(durations) / 1000
        pages_per_second = pages_per_run / total_s * n_runs if total_s > 0 else 0

        result = build_result(
            benchmark="html_parse_lxml",
            durations_ms=per_page_ms,
            warmup=2,
            unit="ms/page",
            fixtures=[fp for fp, _ in fixtures],
            status="PASS",
            extra={
                "pages_per_second": round(pages_per_second, 2),
                "p50_latency_ms": round(compute_percentile(per_page_ms, 0.50), 3),
                "p95_latency_ms": round(compute_percentile(per_page_ms, 0.95), 3),
                "total_pages_parsed": pages_per_run * n_runs,
            },
        )

        output_path = PROJECT_ROOT / "tests" / "probe_8c0" / "results" / "html_parse_lxml.jsonl"
        write_results([result], output_path)

        self.assertGreater(result["median"], 0)

    def test_stdlib_throughput(self):
        """
        Measure stdlib html.parser throughput as baseline.
        Always available — serves as guaranteed baseline.
        """
        fixtures = self.fixtures
        if not fixtures:
            self.skipTest("No HTML fixtures")

        # Warmup
        for _, html_content in fixtures[:3]:
            parse_with_stdlib(html_content)

        # Measure
        n_runs = 10
        durations: List[float] = []

        for _ in range(n_runs):
            start = time.perf_counter_ns()
            for _, html_content in fixtures:
                parse_with_stdlib(html_content)
            elapsed_ns = time.perf_counter_ns() - start
            durations.append(elapsed_ns / 1_000_000)

        pages_per_run = len(fixtures)
        per_page_ms = [d / pages_per_run for d in durations]
        total_s = sum(durations) / 1000
        pages_per_second = pages_per_run / total_s * n_runs if total_s > 0 else 0

        result = build_result(
            benchmark="html_parse_stdlib",
            durations_ms=per_page_ms,
            warmup=2,
            unit="ms/page",
            fixtures=[fp for fp, _ in fixtures],
            status="PASS",
            extra={
                "pages_per_second": round(pages_per_second, 2),
                "p50_latency_ms": round(compute_percentile(per_page_ms, 0.50), 3),
                "p95_latency_ms": round(compute_percentile(per_page_ms, 0.95), 3),
                "total_pages_parsed": pages_per_run * n_runs,
            },
        )

        output_path = PROJECT_ROOT / "tests" / "probe_8c0" / "results" / "html_parse_stdlib.jsonl"
        write_results([result], output_path)

        self.assertGreater(result["median"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
