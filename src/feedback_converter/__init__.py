"""PSARC CDLC to FeedPak converter."""

__version__ = "0.1.16"

from .batch import BatchItem, BatchResult, convert_many
from .converter import ConversionResult, ConversionWarning, convert_psarc, convert_psarc_songs
from .feedpak import FeedpakEditResult, inspect_feedpak, update_feedpak
from .feedpak_validator import FeedpakValidationError, FeedpakValidationResult, require_valid_feedpak, validate_feedpak
from .inspector import ArrangementPreview, PsarcPreview, inspect_psarc

__all__ = [
    "ArrangementPreview",
    "BatchItem",
    "BatchResult",
    "ConversionResult",
    "ConversionWarning",
    "FeedpakEditResult",
    "FeedpakValidationResult",
    "FeedpakValidationError",
    "PsarcPreview",
    "convert_many",
    "convert_psarc",
    "convert_psarc_songs",
    "inspect_feedpak",
    "inspect_psarc",
    "update_feedpak",
    "require_valid_feedpak",
    "validate_feedpak",
]
