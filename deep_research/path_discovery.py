"""
Path Discovery - Shadow Walker Algorithm
Integrated from hledac/scanners/deep_probe.py
"""

from __future__ import annotations
import logging
import re
from typing import List, Tuple, Optional
from urllib.parse import urljoin
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PathPattern(ABC):
    """Abstract base class for path patterns."""
    
    @abstractmethod
    def generate_predictions(self) -> List[Tuple[str, float]]:
        pass
    
    @abstractmethod
    def get_pattern_type(self) -> str:
        pass


class DatePathPattern(PathPattern):
    """Pattern for date-based paths."""
    
    def __init__(self, years: List[int]):
        self.years = sorted(set(years))
    
    def generate_predictions(self) -> List[Tuple[str, float]]:
        predictions = []
        if not self.years:
            return predictions
        next_year = max(self.years) + 1
        if next_year <= 2030:
            predictions.append((f"/{next_year}/", 0.8))
        prev_year = min(self.years) - 1
        if prev_year >= 1990:
            predictions.append((f"/{prev_year}/", 0.6))
        return predictions
    
    def get_pattern_type(self) -> str:
        return "date"


class SequentialPathPattern(PathPattern):
    """Pattern for sequential number paths."""
    
    def __init__(self, numbers: List[int]):
        self.numbers = sorted(set(numbers))
    
    def generate_predictions(self) -> List[Tuple[str, float]]:
        predictions = []
        if len(self.numbers) < 2:
            return predictions
        diffs = [self.numbers[i+1] - self.numbers[i] for i in range(len(self.numbers)-1)]
        if not diffs:
            return predictions
        most_common_step = max(set(diffs), key=diffs.count)
        next_num = int(self.numbers[-1] + most_common_step)
        if next_num <= 10000:
            predictions.append((f"/{next_num}/", 0.7))
        return predictions
    
    def get_pattern_type(self) -> str:
        return "sequential"


class FilePathPattern(PathPattern):
    """Pattern for file type paths."""
    
    def __init__(self, extensions: List[str]):
        self.extensions = list(set(ext.lower() for ext in extensions))
    
    def generate_predictions(self) -> List[Tuple[str, float]]:
        predictions = []
        common_dirs = ['data', 'files', 'documents', 'reports', 'research']
        for ext in self.extensions:
            for dir_name in common_dirs:
                predictions.append((f"/{dir_name}/file.{ext}", 0.5))
        return predictions
    
    def get_pattern_type(self) -> str:
        return "file"


class PathPatternAnalyzer:
    """Analyzes path patterns to predict new paths."""
    
    def __init__(self):
        self.patterns: List[PathPattern] = []
    
    def analyze_patterns(self, paths: List[str]) -> List[PathPattern]:
        patterns = []
        date_pattern = self._extract_date_pattern(paths)
        if date_pattern:
            patterns.append(date_pattern)
        sequential_pattern = self._extract_sequential_pattern(paths)
        if sequential_pattern:
            patterns.append(sequential_pattern)
        file_pattern = self._extract_file_pattern(paths)
        if file_pattern:
            patterns.append(file_pattern)
        self.patterns = patterns
        return patterns
    
    def _extract_date_pattern(self, paths: List[str]) -> Optional[DatePathPattern]:
        year_pattern = re.compile(r'/(\d{4})/')
        years = []
        for path in paths:
            matches = year_pattern.findall(path)
            years.extend([int(year) for year in matches])
        if len(set(years)) >= 2:
            return DatePathPattern(sorted(set(years)))
        return None
    
    def _extract_sequential_pattern(self, paths: List[str]) -> Optional[SequentialPathPattern]:
        number_pattern = re.compile(r'/(\d+)/')
        sequences = []
        for path in paths:
            matches = number_pattern.findall(path)
            sequences.extend([int(num) for num in matches])
        if len(set(sequences)) >= 3:
            return SequentialPathPattern(sorted(set(sequences)))
        return None
    
    def _extract_file_pattern(self, paths: List[str]) -> Optional[FilePathPattern]:
        extensions = []
        for path in paths:
            if '.' in path:
                ext = path.split('.')[-1].lower()
                if ext in ['pdf', 'doc', 'docx', 'txt', 'csv', 'xml', 'json']:
                    extensions.append(ext)
        if extensions:
            return FilePathPattern(list(set(extensions)))
        return None


class ShadowWalkerAlgorithm:
    """Shadow Walker algorithm for intelligent path prediction."""
    
    def __init__(self):
        self.pattern_analyzer = PathPatternAnalyzer()
    
    def predict_next_paths(
        self, 
        base_url: str, 
        known_paths: List[str],
        max_predictions: int = 20
    ) -> List[Tuple[str, float]]:
        if not known_paths:
            return []
        predictions = []
        patterns = self.pattern_analyzer.analyze_patterns(known_paths)
        for pattern in patterns:
            predicted_paths = pattern.generate_predictions()
            for path, confidence in predicted_paths:
                full_url = urljoin(base_url, path)
                predictions.append((full_url, confidence))
        predictions.sort(key=lambda x: x[1], reverse=True)
        seen_urls = set()
        unique_predictions = []
        for url, confidence in predictions:
            if url not in seen_urls:
                unique_predictions.append((url, confidence))
                seen_urls.add(url)
        return unique_predictions[:max_predictions]


def predict_hidden_paths(
    base_url: str,
    known_paths: List[str],
    max_predictions: int = 20
) -> List[Tuple[str, float]]:
    algorithm = ShadowWalkerAlgorithm()
    return algorithm.predict_next_paths(base_url, known_paths, max_predictions)


__all__ = [
    'PathPattern',
    'DatePathPattern',
    'SequentialPathPattern',
    'FilePathPattern',
    'PathPatternAnalyzer',
    'ShadowWalkerAlgorithm',
    'predict_hidden_paths',
]
