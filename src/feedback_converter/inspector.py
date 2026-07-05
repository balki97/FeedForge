from __future__ import annotations

import os
import sqlite3
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
    _song_tones_to_feedpak,
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
class ToneGearPreview:
    slot: str
    key: str
    type: str
    category: str
    knobs: int


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
class RigBuilderStagePreview:
    slot: str
    gear: str
    kind: str
    asset: str
    assigned_mode: str
    bypassed: bool
    status: str


@dataclass(frozen=True)
class RigBuilderMappingPreview:
    tone_key: str
    preset: str
    status: str
    stages: list[RigBuilderStagePreview] = field(default_factory=list)


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
    tones: list[ArrangementTonePreview] = field(default_factory=list)
    rig_builder: list[RigBuilderMappingPreview] = field(default_factory=list)
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
    tones: list[ArrangementTonePreview] = []
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
        cover_path=cover_path,
        arrangements=arrangements,
        tones=tones,
        rig_builder=_rig_builder_preview(input_psarc),
        chart_points=chart_points,
        lyrics=lyric_count,
        warnings=warnings,
    )


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
    )


def _rig_builder_preview(input_psarc: Path) -> list[RigBuilderMappingPreview]:
    db = _rig_builder_db()
    if db is None:
        return []

    song_key = input_psarc.with_suffix(".feedpak").name
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return []

    try:
        rows = conn.execute(
            "SELECT tm.tone_key, tm.preset_id, p.name "
            "FROM tone_mappings tm "
            "LEFT JOIN presets p ON p.id = tm.preset_id "
            "WHERE tm.filename = ? "
            "ORDER BY tm.tone_key",
            (song_key,),
        ).fetchall()
        mappings: list[RigBuilderMappingPreview] = []
        for row in rows:
            stages = [_rig_builder_stage_preview(stage) for stage in conn.execute(
                "SELECT slot, rs_gear_type, kind, file, assigned_mode, bypassed, vst_path "
                "FROM preset_pieces WHERE preset_id = ? ORDER BY slot_order",
                (row["preset_id"],),
            )]
            if not stages:
                status = "missing"
            elif any(stage.status == "missing" for stage in stages):
                status = "partial"
            else:
                status = "ready"
            mappings.append(
                RigBuilderMappingPreview(
                    tone_key=str(row["tone_key"] or ""),
                    preset=str(row["name"] or ""),
                    status=status,
                    stages=stages,
                )
            )
        return mappings
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _rig_builder_stage_preview(row: sqlite3.Row) -> RigBuilderStagePreview:
    kind = str(row["kind"] or "none")
    file_asset = str(row["file"] or "")
    vst_path = str(row["vst_path"] or "")
    asset = Path(vst_path).name if vst_path else file_asset
    status = "ready"
    if kind == "none" or not asset:
        status = "missing"
    if bool(row["bypassed"]):
        status = "bypassed"
    return RigBuilderStagePreview(
        slot=str(row["slot"] or ""),
        gear=str(row["rs_gear_type"] or ""),
        kind=kind,
        asset=asset,
        assigned_mode=str(row["assigned_mode"] or ""),
        bypassed=bool(row["bypassed"]),
        status=status,
    )


def _rig_builder_db() -> Path | None:
    candidates: list[Path] = []
    for env_name, app_name in (
        ("APPDATA", "feedback-desktop"),
        ("APPDATA", "slopsmith-desktop"),
    ):
        root = os.environ.get(env_name)
        if root:
            candidates.append(Path(root) / app_name / "slopsmith-config" / "nam_tone.db")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


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
