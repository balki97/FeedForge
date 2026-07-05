from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .converter import (
    _arrangement_id,
    _convert_dds_bytes_to_png,
    _display_name,
    _duration_from_song,
    _extract_metadata,
    _find_sng_entries,
    _highest_level,
)
from .psarc_format.psarc import PSARC
from .psarc_format.sng import Song


@dataclass(frozen=True)
class ArrangementPreview:
    id: str
    name: str
    type: str
    tuning: list[int]
    capo: int
    difficulties: int
    notes: int
    chords: int


@dataclass(frozen=True)
class ChartPoint:
    time: float
    string: int
    fret: int


@dataclass(frozen=True)
class PsarcPreview:
    input_path: Path
    title: str
    artist: str
    album: str = ""
    year: int | None = None
    duration: float | None = None
    cover_path: Path | None = None
    arrangements: list[ArrangementPreview] = field(default_factory=list)
    chart_points: list[ChartPoint] = field(default_factory=list)
    lyrics: int = 0
    warnings: list[str] = field(default_factory=list)


def inspect_psarc(input_psarc: Path, *, cover_dir: Path | None = None) -> PsarcPreview:
    """Read lightweight song metadata and preview data from a PSARC package."""
    input_psarc = Path(input_psarc)
    warnings: list[str] = []
    if not input_psarc.is_file():
        raise FileNotFoundError(f"PSARC file not found: {input_psarc}")

    with input_psarc.open("rb") as fh:
        content = PSARC(crypto=True).parse_stream(fh)

    metadata = _extract_metadata(content)
    arrangements: list[ArrangementPreview] = []
    chart_points: list[ChartPoint] = []
    lyric_count = 0
    first_song: Any | None = None
    used_ids: set[str] = set()

    for source_path, data in _find_sng_entries(content):
        try:
            song = Song.parse(data)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Skipped unreadable SNG {source_path}: {exc}")
            continue

        if getattr(song, "vocals", None):
            lyric_count = max(lyric_count, len(song.vocals))

        if not getattr(song, "levels", None):
            continue

        if first_song is None:
            first_song = song
            chart_points = _chart_points(song)

        arr_id = _unique_preview_id(_arrangement_id(source_path, metadata), used_ids)
        highest = _highest_level(song)
        note_count = 0
        chord_count = 0
        for note in highest.notes:
            if int(note.chordId) == 0xFFFFFFFF:
                note_count += 1
            else:
                chord_count += 1
        arrangements.append(
            ArrangementPreview(
                id=arr_id,
                name=_display_name(arr_id),
                type="bass" if "bass" in arr_id else "guitar",
                tuning=[int(x) for x in list(song.metadata.tuning or [])],
                capo=max(0, int(song.metadata.capo or 0)),
                difficulties=len(song.levels),
                notes=note_count,
                chords=chord_count,
            )
        )

    cover_path = _extract_cover(content, cover_dir)
    duration = metadata.get("duration") or _duration_from_song(first_song)
    year = None
    if metadata.get("year"):
        try:
            year = int(metadata["year"])
        except (TypeError, ValueError):
            warnings.append(f"Ignored non-integer year: {metadata['year']!r}")

    return PsarcPreview(
        input_path=input_psarc,
        title=str(metadata.get("title") or input_psarc.stem),
        artist=str(metadata.get("artist") or "Unknown Artist"),
        album=str(metadata.get("album") or ""),
        year=year,
        duration=float(duration) if duration else None,
        cover_path=cover_path,
        arrangements=arrangements,
        chart_points=chart_points,
        lyrics=lyric_count,
        warnings=warnings,
    )


def _chart_points(song: Any) -> list[ChartPoint]:
    points: list[ChartPoint] = []
    try:
        highest = _highest_level(song)
    except ValueError:
        return points
    for note in sorted(highest.notes, key=lambda item: float(item.time))[:700]:
        if int(note.chordId) != 0xFFFFFFFF:
            continue
        points.append(ChartPoint(float(note.time), int(note.string), int(note.fret)))
    return points


def _extract_cover(content: dict[str, bytes], cover_dir: Path | None) -> Path | None:
    if cover_dir is None:
        return None

    images = [
        (path, data)
        for path, data in content.items()
        if path.lower().endswith((".png", ".jpg", ".jpeg", ".dds"))
    ]
    if not images:
        return None

    source_path, data = max(images, key=lambda item: len(item[1]))
    ext = Path(source_path).suffix.lower()
    cover_dir.mkdir(parents=True, exist_ok=True)

    if ext == ".dds":
        target = cover_dir / "cover.png"
        return target if _convert_dds_bytes_to_png(data, target) else None

    target = cover_dir / f"cover{ext}"
    target.write_bytes(data)
    return target


def _unique_preview_id(value: str, used: set[str]) -> str:
    base = value or "arrangement"
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate
