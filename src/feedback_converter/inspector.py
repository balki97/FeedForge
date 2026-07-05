from __future__ import annotations

import os
import json
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
    knob_values: dict[str, Any] = field(default_factory=dict)
    recommendation_kind: str = ""
    recommendation: str = ""
    recommendation_detail: str = ""


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
    state_applied: bool = False


@dataclass(frozen=True)
class RigBuilderMappingPreview:
    tone_key: str
    preset: str
    status: str
    stages: list[RigBuilderStagePreview] = field(default_factory=list)


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
    recommendation = _gear_recommendation(gear)
    return ToneGearPreview(
        slot=str(slot),
        key=str(gear.get("Key") or gear.get("PedalKey") or gear.get("Type") or ""),
        type=str(gear.get("Type") or ""),
        category=str(gear.get("Category") or ""),
        knobs=len(knobs),
        knob_values={str(key): value for key, value in knobs.items()},
        recommendation_kind=recommendation["kind"],
        recommendation=recommendation["name"],
        recommendation_detail=recommendation["detail"],
    )


def _gear_recommendation(gear: dict[str, Any]) -> dict[str, str]:
    key = str(gear.get("Key") or gear.get("PedalKey") or gear.get("Type") or "")
    data_dir = _rig_builder_data_dir()
    if not key or data_dir is None:
        return {"kind": "", "name": "", "detail": ""}

    cab = _cab_recommendation(data_dir, key)
    if cab["name"]:
        return cab

    vst_map = _load_json_file(data_dir / "rs_gear_to_vst.json")
    vst_candidates = vst_map.get(key) if isinstance(vst_map, dict) else None
    if isinstance(vst_candidates, list) and vst_candidates:
        primary = next((item for item in vst_candidates if isinstance(item, dict) and item.get("bundled")), None)
        if primary is None:
            primary = next((item for item in vst_candidates if isinstance(item, dict)), None)
        if primary:
            name = primary.get("name") or Path(str(primary.get("bundled") or "")).stem
            asset = Path(str(primary.get("bundled") or "")).name
            detail = asset or str(primary.get("notes") or "")
            return {"kind": "VST", "name": str(name or ""), "detail": detail}

    default_captures = _load_json_file(data_dir / "default_captures.json")
    capture = default_captures.get(key) if isinstance(default_captures, dict) else None
    if isinstance(capture, dict) and capture.get("tone3000_id"):
        return {
            "kind": str(capture.get("kind") or "NAM").upper(),
            "name": f"tone3000 #{capture['tone3000_id']}",
            "detail": f"model {capture.get('model_id')}" if capture.get("model_id") else "",
        }

    rs_map = _load_json_file(data_dir / "rs_to_real.json")
    real = rs_map.get(key) if isinstance(rs_map, dict) else None
    if isinstance(real, dict):
        variant = _amp_variant(real, gear)
        if variant:
            return variant
        name = " ".join(str(real.get(part) or "").strip() for part in ("make", "model")).strip()
        return {
            "kind": str(real.get("category") or "mapped").upper(),
            "name": name or str(real.get("name") or key),
            "detail": str(real.get("tone3000_query") or ""),
        }

    return {"kind": "", "name": "", "detail": ""}


def _cab_recommendation(data_dir: Path, key: str) -> dict[str, str]:
    mic_map = _load_json_file(data_dir / "rs_cab_mic_map.json")
    if not isinstance(mic_map, dict):
        return {"kind": "", "name": "", "detail": ""}
    for base, variants in mic_map.items():
        if not isinstance(variants, dict):
            continue
        for spec in variants.values():
            if isinstance(spec, dict) and str(spec.get("effect_name") or "").lower() == key.lower():
                return {
                    "kind": "IR",
                    "name": str(spec.get("ir_file") or ""),
                    "detail": f"{base} · {spec.get('label') or spec.get('position') or ''}",
                }
    return {"kind": "", "name": "", "detail": ""}


def _amp_variant(real: dict[str, Any], gear: dict[str, Any]) -> dict[str, str] | None:
    variants = real.get("gain_variants")
    knobs = gear.get("KnobValues") if isinstance(gear.get("KnobValues"), dict) else {}
    gain = knobs.get("Gain")
    if not isinstance(variants, dict) or gain is None:
        return None
    try:
        gain_value = float(gain)
    except (TypeError, ValueError):
        return None
    for level, spec in variants.items():
        if not isinstance(spec, dict):
            continue
        lo_hi = spec.get("rs_gain_range") or []
        if len(lo_hi) != 2:
            continue
        try:
            lo, hi = float(lo_hi[0]), float(lo_hi[1])
        except (TypeError, ValueError):
            continue
        if lo <= gain_value <= hi:
            return {
                "kind": "NAM",
                "name": str(spec.get("notes") or f"tone3000 #{spec.get('tone3000_id')}"),
                "detail": f"{level} · Gain {gain_value:g}",
            }
    return None


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _rig_builder_data_dir() -> Path | None:
    configured = os.environ.get("FEEDFORGE_RIG_BUILDER_DATA_DIR")
    if configured:
        resolved = _resolve_rig_builder_data_dir(Path(configured))
        if resolved is not None:
            return resolved

    candidates = [
        Path(r"C:\Program Files\feedback\current\resources\slopsmith\plugins\rig_builder\data"),
    ]
    for candidate in candidates:
        resolved = _resolve_rig_builder_data_dir(candidate)
        if resolved is not None:
            return resolved
    return None


def _resolve_rig_builder_data_dir(path: Path) -> Path | None:
    possible = [
        path,
        path / "data",
        path / "rig_builder" / "data",
        path / "plugins" / "rig_builder" / "data",
        path / "slopsmith" / "plugins" / "rig_builder" / "data",
        path / "resources" / "slopsmith" / "plugins" / "rig_builder" / "data",
        path / "current" / "resources" / "slopsmith" / "plugins" / "rig_builder" / "data",
    ]
    for candidate in possible:
        if candidate.is_dir() and (candidate / "rs_gear_to_vst.json").is_file():
            return candidate
    return None


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
                "SELECT slot, rs_gear_type, kind, file, assigned_mode, bypassed, vst_path, vst_state "
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
    vst_state = str(row["vst_state"] or "")
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
        state_applied=bool(vst_state and kind == "vst"),
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
