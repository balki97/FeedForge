from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .converter import (
    _arrangement_id,
    _convert_dds_bytes_to_png,
    _display_name,
    _duration_from_song,
    _authors_from_metadata,
    _extract_metadata,
    _find_sng_entries,
    _arrangement_event_count,
    _arrangement_note_count,
    _song_chart_data,
    _song_tones_to_feedpak,
    _template_to_feedpak,
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
    event_count: int
    note_count: int


@dataclass(frozen=True)
class ToneGearPreview:
    slot: str
    key: str
    type: str
    category: str
    knobs: int
    knob_values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToneDefinitionPreview:
    name: str
    key: str
    gear: list[ToneGearPreview] = field(default_factory=list)


@dataclass(frozen=True)
class ToneChangePreview:
    time: float
    name: str
    rig: str


@dataclass(frozen=True)
class ArrangementTonePreview:
    arrangement_id: str
    arrangement_name: str
    base: str
    base_rig: str
    definitions: list[ToneDefinitionPreview] = field(default_factory=list)
    changes: list[ToneChangePreview] = field(default_factory=list)


@dataclass(frozen=True)
class PsarcPreview:
    input_path: Path
    title: str
    artist: str
    album: str = ""
    year: int | None = None
    duration: float | None = None
    authors: list[dict[str, str]] = field(default_factory=list)
    cover_path: Path | None = None
    arrangements: list[ArrangementPreview] = field(default_factory=list)
    tones: list[ArrangementTonePreview] = field(default_factory=list)
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
    tones: list[ArrangementTonePreview] = []
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

        arr_id = _unique_preview_id(_arrangement_id(source_path, metadata), used_ids)
        templates = [_template_to_feedpak(template) for template in song.chordTemplates]
        chart = _song_chart_data(song, templates)
        note_count = len(chart["notes"])
        chord_count = len(chart["chords"])
        chart_counts = {"notes": chart["notes"], "chords": chart["chords"]}
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
                event_count=_arrangement_event_count(chart_counts),
                note_count=_arrangement_note_count(chart_counts),
            )
        )
        tone_preview = _tone_preview(song, source_path, arr_id, _display_name(arr_id), metadata)
        if tone_preview is not None:
            tones.append(tone_preview)

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
        authors=_authors_from_metadata(metadata),
        cover_path=cover_path,
        arrangements=arrangements,
        tones=tones,
        lyrics=lyric_count,
        warnings=warnings,
    )


def _preview_chord_note_count(song: Any, chord_id: int) -> int:
    try:
        template = song.chordTemplates[chord_id]
    except Exception:  # noqa: BLE001
        return 1
    count = 0
    for fret in getattr(template, "frets", []) or []:
        try:
            if int(fret) >= 0:
                count += 1
        except Exception:  # noqa: BLE001
            continue
    return max(1, count)


def _tone_preview(
    song: Any,
    source_path: str,
    arrangement_id: str,
    arrangement_name: str,
    metadata: dict[str, Any],
) -> ArrangementTonePreview | None:
    converted = _song_tones_to_feedpak(song, source_path, metadata)
    if not converted:
        return None

    tone_data = converted.get("tones") or {}
    definitions = [
        _tone_definition_preview(definition)
        for definition in tone_data.get("definitions") or []
        if isinstance(definition, dict)
    ]
    changes = [
        ToneChangePreview(
            time=float(change.get("t") or 0.0),
            name=str(change.get("name") or ""),
            rig=str(change.get("rig") or ""),
        )
        for change in tone_data.get("changes") or []
        if isinstance(change, dict)
    ]
    return ArrangementTonePreview(
        arrangement_id=arrangement_id,
        arrangement_name=arrangement_name,
        base=str(tone_data.get("base") or ""),
        base_rig=str(tone_data.get("base_rig") or ""),
        definitions=definitions,
        changes=changes,
    )


def _tone_definition_preview(definition: dict[str, Any]) -> ToneDefinitionPreview:
    gear_list = definition.get("GearList") if isinstance(definition.get("GearList"), dict) else {}
    gear = [
        _tone_gear_preview(slot, item)
        for slot, item in gear_list.items()
        if isinstance(item, dict)
    ]
    return ToneDefinitionPreview(
        name=str(definition.get("Name") or definition.get("ToneName") or definition.get("name") or ""),
        key=str(definition.get("Key") or definition.get("ToneKey") or definition.get("key") or ""),
        gear=gear,
    )


def _tone_gear_preview(slot: str, gear: dict[str, Any]) -> ToneGearPreview:
    knobs = gear.get("KnobValues") if isinstance(gear.get("KnobValues"), dict) else {}
    return ToneGearPreview(
        slot=str(slot),
        key=str(gear.get("Key") or gear.get("PedalKey") or gear.get("Type") or ""),
        type=str(gear.get("Type") or ""),
        category=str(gear.get("Category") or ""),
        knobs=len(knobs),
        knob_values={str(key): value for key, value in knobs.items()},
    )


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

