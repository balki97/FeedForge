"""PSARC CDLC to FeedPak converter."""

__version__ = "2.0.6"

from .batch import BatchItem, BatchResult, convert_many
from .converter import AudioExportResult, ConversionResult, ConversionWarning, convert_psarc, convert_psarc_songs, export_psarc_audio
from .feedpak import FeedpakAudioExportResult, FeedpakEditResult, export_feedpak_audio, inspect_feedpak, update_feedpak
from .feedpak_validator import FeedpakValidationError, FeedpakValidationResult, require_valid_feedpak, validate_feedpak
from .inspector import ArrangementPreview, PsarcPreview, inspect_psarc
from .gp5 import Gp5ExportResult, export_feedpak_gp5

__all__ = [
    "ArrangementPreview",
    "BatchItem",
    "BatchResult",
    "AudioExportResult",
    "ConversionResult",
    "ConversionWarning",
    "FeedpakEditResult",
    "FeedpakAudioExportResult",
    "Gp5ExportResult",
    "FeedpakValidationResult",
    "FeedpakValidationError",
    "PsarcPreview",
    "convert_many",
    "convert_psarc",
    "convert_psarc_songs",
    "export_psarc_audio",
    "export_feedpak_audio",
    "export_feedpak_gp5",
    "inspect_feedpak",
    "inspect_psarc",
    "update_feedpak",
    "require_valid_feedpak",
    "validate_feedpak",
]
