"""PSARC CDLC to FeedPak converter."""

__version__ = "0.1.13"

from .batch import BatchItem, BatchResult, convert_many
from .converter import ConversionResult, ConversionWarning, convert_psarc, convert_psarc_songs
from .feedpak import FeedpakEditResult, inspect_feedpak, update_feedpak
from .inspector import ArrangementPreview, PsarcPreview, inspect_psarc

__all__ = [
    "ArrangementPreview",
    "BatchItem",
    "BatchResult",
    "ConversionResult",
    "ConversionWarning",
    "FeedpakEditResult",
    "PsarcPreview",
    "convert_many",
    "convert_psarc",
    "convert_psarc_songs",
    "inspect_feedpak",
    "inspect_psarc",
    "update_feedpak",
]
