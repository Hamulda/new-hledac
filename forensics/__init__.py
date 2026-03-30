"""
Universal Forensics Module
==========================

Digital forensics and metadata extraction capabilities for OSINT analysis.

Features:
- Universal metadata extraction from images, documents, audio, video
- EXIF parsing with GPS coordinate extraction
- PDF and Office document metadata
- Archive structure analysis
- Scrubbing detection
- Timeline reconstruction
- Attribution analysis

Example:
    from hledac.universal.forensics import (
        UniversalMetadataExtractor,
        create_metadata_extractor,
        MetadataResult,
    )

    extractor = create_metadata_extractor()
    await extractor.initialize()

    result = await extractor.extract("/path/to/file.jpg")
    print(result.to_json())

    await extractor.close()
"""

from __future__ import annotations

# Availability flag
METADATA_EXTRACTOR_AVAILABLE = False

# Placeholder exports
UniversalMetadataExtractor = None
MetadataResult = None
ImageMetadata = None
PDFMetadata = None
DocxMetadata = None
AudioMetadata = None
VideoMetadata = None
ArchiveMetadata = None
GenericMetadata = None
GPSCoordinates = None
TimelineEvent = None
AttributionData = None
ScrubbingAnalysis = None
create_metadata_extractor = None


def _load_metadata_extractor():
    """Lazy load metadata extractor module."""
    global METADATA_EXTRACTOR_AVAILABLE
    global UniversalMetadataExtractor
    global MetadataResult
    global ImageMetadata
    global PDFMetadata
    global DocxMetadata
    global AudioMetadata
    global VideoMetadata
    global ArchiveMetadata
    global GenericMetadata
    global GPSCoordinates
    global TimelineEvent
    global AttributionData
    global ScrubbingAnalysis
    global create_metadata_extractor

    if METADATA_EXTRACTOR_AVAILABLE:
        return

    try:
        from .metadata_extractor import (
            ArchiveMetadata,
            AttributionData,
            AudioMetadata,
            DocxMetadata,
            GenericMetadata,
            GPSCoordinates,
            ImageMetadata,
            MetadataResult,
            PDFMetadata,
            ScrubbingAnalysis,
            TimelineEvent,
            UniversalMetadataExtractor,
            VideoMetadata,
            create_metadata_extractor,
        )
        METADATA_EXTRACTOR_AVAILABLE = True
    except ImportError:
        pass


# Auto-load on first import attempt
try:
    _load_metadata_extractor()
except Exception:
    pass


__all__ = [
    "METADATA_EXTRACTOR_AVAILABLE",
    "UniversalMetadataExtractor",
    "MetadataResult",
    "ImageMetadata",
    "PDFMetadata",
    "DocxMetadata",
    "AudioMetadata",
    "VideoMetadata",
    "ArchiveMetadata",
    "GenericMetadata",
    "GPSCoordinates",
    "TimelineEvent",
    "AttributionData",
    "ScrubbingAnalysis",
    "create_metadata_extractor",
]
