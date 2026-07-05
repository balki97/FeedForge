from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .psarc_format.psarc import PSARC
from .psarc_format.sng import Song

FEEDPAK_VERSION = "1.14.0"
UINT32_NONE = 0xFFFFFFFF
NOTE_MASK_FRETHANDMUTE = 0x08
NOTE_MASK_TREMOLO = 0x10
NOTE_MASK_HARMONIC = 0x20
NOTE_MASK_PALMMUTE = 0x40
NOTE_MASK_SLAP = 0x80
NOTE_MASK_PLUCK = 0x0100
NOTE_MASK_HAMMERON = 0x0200
NOTE_MASK_PULLOFF = 0x0400
NOTE_MASK_TAP = 0x4000
NOTE_MASK_PINCHHARMONIC = 0x8000
NOTE_MASK_VIBRATO = 0x010000
NOTE_MASK_MUTE = 0x020000
NOTE_MASK_IGNORE = 0x040000
NOTE_MASK_ACCENT = 0x04000000
NOTE_MASK_PARENT = 0x08000000


@dataclass
class ConversionWarning:
    message: str


@dataclass
class ConversionResult:
    output_path: Path
    package_dir: Path
    manifest: dict[str, Any]
    warnings: list[ConversionWarning] = field(default_factory=list)


def convert_psarc(
    input_psarc: Path,
    output: Path | None = None,
    *,
    archive: bool | None = None,
    overwrite: bool = False,
    keep_workdir: bool = False,
) -> ConversionResult:
    input_psarc = Path(input_psarc)
    if not input_psarc.is_file():
        raise FileNotFoundError(f"PSARC file not found: {input_psarc}")

    if output is None:
        output = input_psarc.with_suffix(".feedpak")
    output = Path(output)
    if archive is None:
        archive = output.suffix.lower() == ".feedpak"

    package_dir = output if not archive else output.with_suffix(output.suffix + ".work")
    if package_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {package_dir}")
        if package_dir.is_dir():
            shutil.rmtree(package_dir)
        else:
            package_dir.unlink()
    if archive and output.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {output}")
        output.unlink()

    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "arrangements").mkdir()
    (package_dir / "stems").mkdir()

    warnings: list[ConversionWarning] = []
    with input_psarc.open("rb") as fh:
        content = PSARC(crypto=True).parse_stream(fh)

    metadata = _extract_metadata(content)
    sng_items = _find_sng_entries(content)
    if not sng_items:
        raise ValueError("No decrypted SNG arrangements found in PSARC.")

    arrangements: list[dict[str, Any]] = []
    rig_entries: dict[str, dict[str, Any]] = {}
    first_song: Any | None = None
    lyric_song: Any | None = None
    used_ids: set[str] = set()
    for path, data in sng_items:
        try:
            song = Song.parse(data)
        except Exception as exc:  # noqa: BLE001
            warnings.append(ConversionWarning(f"Skipped unreadable SNG {path}: {exc}"))
            continue

        if getattr(song, "vocals", None):
            if len(song.vocals) > 0:
                lyric_song = song

        if not getattr(song, "levels", None) or len(song.levels) == 0:
            warnings.append(
                ConversionWarning(f"Skipped non-playable SNG with no difficulty levels: {path}")
            )
            continue

        if first_song is None:
            first_song = song

        arr_id = _unique_id(_arrangement_id(path, metadata), used_ids)
        try:
            arrangement = _song_to_arrangement(song, path, metadata)
        except ValueError as exc:
            warnings.append(ConversionWarning(f"Skipped SNG {path}: {exc}"))
            continue
        for rig in arrangement.pop("_rigs", []):
            rig_entries.setdefault(str(rig["id"]), rig)
        arr_file = f"arrangements/{arr_id}.json"
        _write_json(package_dir / arr_file, arrangement)
        arrangements.append(
            {
                "id": arr_id,
                "name": _display_name(arr_id),
                "file": arr_file,
                "tuning": arrangement["tuning"],
                "capo": max(0, int(arrangement.get("capo", 0))),
                "type": _arrangement_type(arr_id),
            }
        )

    if not arrangements:
        raise ValueError("No SNG arrangements could be converted.")

    timeline_path = None
    if first_song is not None:
        timeline = _song_to_timeline(first_song)
        if timeline["beats"] or timeline["sections"]:
            timeline_path = "song_timeline.json"
            _write_json(package_dir / timeline_path, timeline)

        lyrics = _song_to_lyrics(lyric_song or first_song)
        lyrics_path = None
        if lyrics:
            lyrics_path = "lyrics.json"
            _write_json(package_dir / lyrics_path, lyrics)
        else:
            lyrics_path = None
    else:
        lyrics_path = None

    stem_entry = _copy_audio(content, package_dir, warnings)
    cover_path = _copy_cover(content, package_dir)

    title = metadata.get("title") or input_psarc.stem
    artist = metadata.get("artist") or "Unknown Artist"
    duration = float(metadata.get("duration") or _duration_from_song(first_song) or 0.0)

    manifest: dict[str, Any] = {
        "feedpak_version": FEEDPAK_VERSION,
        "title": str(title),
        "artist": str(artist),
        "duration": round(duration, 6),
        "arrangements": arrangements,
        "stems": [stem_entry],
    }
    if metadata.get("album"):
        manifest["album"] = str(metadata["album"])
    if metadata.get("year"):
        try:
            manifest["year"] = int(metadata["year"])
        except (TypeError, ValueError):
            warnings.append(ConversionWarning(f"Ignored non-integer year: {metadata['year']!r}"))
    if lyrics_path:
        manifest["lyrics"] = lyrics_path
    if timeline_path:
        manifest["song_timeline"] = timeline_path
    if cover_path:
        manifest["cover"] = cover_path
    if rig_entries:
        rigs_path = "rigs.json"
        manifest["rigs"] = rigs_path
        _write_json(
            package_dir / rigs_path,
            {"version": 1, "rigs": sorted(rig_entries.values(), key=lambda item: item["id"])},
        )

    _write_manifest(package_dir / "manifest.yaml", manifest)

    final_output = package_dir
    if archive:
        _zip_dir(package_dir, output)
        final_output = output
        if not keep_workdir:
            shutil.rmtree(package_dir)

    return ConversionResult(final_output, package_dir, manifest, warnings)


def _find_sng_entries(content: dict[str, bytes]) -> list[tuple[str, bytes]]:
    entries = [
        (path, data)
        for path, data in content.items()
        if path.lower().endswith(".sng") and "/bin/" in path.replace("\\", "/").lower()
    ]
    return sorted(entries, key=lambda item: item[0].lower())


def _extract_metadata(content: dict[str, bytes]) -> dict[str, Any]:
    objects: list[Any] = []
    for path, data in content.items():
        low = path.lower()
        if not (low.endswith(".json") or low.endswith(".hsan")):
            continue
        try:
            text = data.decode("utf-8-sig")
            objects.append(json.loads(text))
        except Exception:  # noqa: BLE001
            continue

    flat = list(_walk_dicts(objects))
    return {
        "title": _first_key(flat, "SongName", "Title", "Name", "SongTitle"),
        "artist": _first_key(flat, "ArtistName", "Artist", "SongArtist"),
        "album": _first_key(flat, "AlbumName", "Album"),
        "year": _first_key(flat, "SongYear", "Year"),
        "duration": _first_key(flat, "SongLength", "Duration", "SongLengthSeconds"),
        "arrangement_names": _arrangement_names(flat),
        "arrangement_tones": _arrangement_tones(flat),
    }


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_walk_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_dicts(child))
    return found


def _first_key(dicts: list[dict[str, Any]], *keys: str) -> Any | None:
    for key in keys:
        for item in dicts:
            value = item.get(key)
            if value not in (None, ""):
                return value
    return None


def _arrangement_names(dicts: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for item in dicts:
        path = item.get("SongXml") or item.get("PersistentID") or item.get("MasterID_RDV")
        name = item.get("ArrangementName") or item.get("ArrangementType")
        if path and name:
            names[str(path).lower()] = str(name)
    return names


def _arrangement_tones(dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arrangement_tones: list[dict[str, Any]] = []
    for item in dicts:
        tones = item.get("Tones")
        slot_names = {
            0: item.get("Tone_A"),
            1: item.get("Tone_B"),
            2: item.get("Tone_C"),
            3: item.get("Tone_D"),
        }
        has_slots = any(isinstance(value, str) and value for value in slot_names.values())
        if not has_slots and not isinstance(tones, list):
            continue

        raw_match_keys = [
            item.get("SongXml"),
            item.get("PersistentID"),
            item.get("MasterID_RDV"),
            item.get("ArrangementName"),
            item.get("ArrangementType"),
        ]
        match_keys = []
        for key in raw_match_keys:
            if key in (None, ""):
                continue
            key_text = str(key).lower()
            match_keys.append(key_text)
            stem = Path(key_text.replace("\\", "/")).stem
            if stem:
                match_keys.append(stem)
        if not match_keys:
            continue

        definitions = (
            [_normalize_tone_definition(tone) for tone in tones if isinstance(tone, dict)]
            if isinstance(tones, list)
            else []
        )
        arrangement_tones.append(
            {
                "match_keys": match_keys,
                "base": item.get("Tone_Base") or item.get("Tone_A"),
                "slots": {slot: value for slot, value in slot_names.items() if isinstance(value, str) and value},
                "definitions": definitions,
            }
        )
    return arrangement_tones


def _song_to_arrangement(song: Any, source_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
    tuning = [int(x) for x in list(song.metadata.tuning or [])]
    templates = [_template_to_feedpak(t) for t in song.chordTemplates]
    chart = _song_chart_data(song, templates)
    arrangement = {
        "name": _display_name(_arrangement_id(source_path, metadata)),
        "tuning": tuning,
        "capo": max(0, int(song.metadata.capo or 0)),
        "notes": chart["notes"],
        "chords": chart["chords"],
        "anchors": chart["anchors"],
        "handshapes": chart["handshapes"],
        "templates": templates,
        **({"phrases": chart["phrases"]} if chart["phrases"] else {}),
        "beats": [_beat_to_feedpak(b) for b in song.beats],
        "sections": [_section_to_feedpak(s) for s in song.sections],
    }
    tones = _song_tones_to_feedpak(song, source_path, metadata)
    if tones:
        arrangement["tones"] = tones["tones"]
        arrangement["_rigs"] = tones["rigs"]
    return arrangement


def _highest_level(song: Any) -> Any:
    levels = list(song.levels)
    if not levels:
        raise ValueError("SNG has no difficulty levels")
    return max(levels, key=lambda level: int(level.difficulty))


def _song_chart_data(song: Any, templates: list[dict[str, Any]]) -> dict[str, Any]:
    level_payloads: dict[int, dict[str, Any]] = {}
    for level in sorted(song.levels, key=lambda item: int(item.difficulty)):
        notes, chords = _notes_and_chords(song, level, templates)
        level_payloads[int(level.difficulty)] = {
            "difficulty": int(level.difficulty),
            "notes": notes,
            "chords": chords,
            "anchors": [_anchor_to_feedpak(a) for a in level.anchors],
            "handshapes": _handshapes_to_feedpak(level),
        }

    highest = level_payloads[int(_highest_level(song).difficulty)]
    phrases = _phrase_ladder_to_feedpak(song, level_payloads)
    return {
        "notes": highest["notes"],
        "chords": highest["chords"],
        "anchors": highest["anchors"],
        "handshapes": highest["handshapes"],
        "phrases": phrases,
    }


def _song_tones_to_feedpak(song: Any, source_path: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    tone_events = sorted(
        [tone for tone in getattr(song, "tones", []) if _finite_number(getattr(tone, "time", None))],
        key=lambda tone: float(tone.time),
    )
    tone_info = _tone_info_for_arrangement(source_path, metadata)
    definitions = list(tone_info.get("definitions") or []) if tone_info else []
    slot_names = dict(tone_info.get("slots") or {}) if tone_info else {}
    if not tone_events and not definitions and not slot_names:
        return None

    def tone_name(tone_id: int) -> str:
        slot_name = slot_names.get(tone_id)
        if slot_name:
            return str(slot_name)
        for definition in definitions:
            key = str(definition.get("Key") or definition.get("ToneKey") or "")
            name = _tone_definition_name(definition)
            if key.lower() in {f"tone_{tone_id}".lower(), f"tone{tone_id}".lower()} and name:
                return name
        if 0 <= tone_id < len(definitions):
            name = _tone_definition_name(definitions[tone_id])
            if name:
                return name
        return f"Tone {tone_id}"

    event_ids = [tone_id for tone_id in (_tone_id(tone) for tone in tone_events) if tone_id is not None]
    known_ids = sorted(set(event_ids) | set(slot_names))
    if not known_ids and definitions:
        known_ids = list(range(len(definitions)))
    if not known_ids:
        return None

    base_name = str(tone_info.get("base") or "").strip() if tone_info else ""
    base_id = _tone_id_for_name(base_name, slot_names, definitions)
    if base_id is None:
        base_id = 0 if 0 in known_ids else known_ids[0]
    if not base_name:
        base_name = tone_name(base_id)

    changes = []
    for tone in tone_events:
        tone_id = _tone_id(tone)
        if tone_id is None:
            continue
        name = tone_name(tone_id)
        changes.append({"t": _num(tone.time), "name": name, "rig": _rig_id(name, tone_id)})

    tones: dict[str, Any] = {"base": base_name, "base_rig": _rig_id(base_name, base_id)}
    if changes:
        tones["changes"] = changes
    if definitions:
        tones["definitions"] = definitions

    rig_ids = sorted(set(event_ids) | set(slot_names) | {base_id})
    instrument = "bass" if "bass" in source_path.lower() else "guitar"
    rigs = [
        _tone_rig(
            tone_name(tone_id),
            tone_id,
            _definition_for_tone(tone_id, tone_name(tone_id), definitions),
            instrument,
        )
        for tone_id in rig_ids
    ]
    return {"tones": tones, "rigs": rigs}


def _tone_info_for_arrangement(source_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
    source = source_path.lower()
    arrangement_id = _arrangement_id(source_path, metadata)
    for entry in metadata.get("arrangement_tones", []):
        keys = entry.get("match_keys") or []
        if any(key and key in source for key in keys):
            return entry
    for entry in metadata.get("arrangement_tones", []):
        keys = entry.get("match_keys") or []
        if arrangement_id and any(_slug(key) == arrangement_id for key in keys):
            return entry
    arrangement_tones = metadata.get("arrangement_tones", [])
    return arrangement_tones[0] if len(arrangement_tones) == 1 else {}


def _tone_definition_name(definition: dict[str, Any]) -> str:
    value = definition.get("Name") or definition.get("ToneName") or definition.get("name")
    return str(value).strip() if value not in (None, "") else ""


def _normalize_tone_definition(definition: dict[str, Any]) -> dict[str, Any]:
    tone = _json_safe(definition)
    if not isinstance(tone, dict):
        return {}

    name = tone.get("Name") or tone.get("ToneName") or tone.get("name")
    if name not in (None, "") and not isinstance(tone.get("Name"), str):
        tone["Name"] = str(name)

    key = tone.get("Key") or tone.get("ToneKey") or tone.get("key")
    if key in (None, "") and tone.get("Name") not in (None, ""):
        key = tone["Name"]
    if key not in (None, ""):
        tone["Key"] = str(key)

    gear_list = tone.get("GearList")
    if not isinstance(gear_list, dict):
        return tone

    normalized_gear: dict[str, Any] = {}
    for slot, gear in gear_list.items():
        if not isinstance(gear, dict):
            normalized_gear[str(slot)] = gear
            continue
        normalized_gear[str(slot)] = _normalize_tone_gear(gear)
    tone["GearList"] = normalized_gear
    return tone


def _normalize_tone_gear(gear: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(gear)
    key = (
        normalized.get("Key")
        or normalized.get("PedalKey")
        or normalized.get("GearKey")
        or normalized.get("EffectKey")
        or normalized.get("Type")
    )
    if key not in (None, ""):
        key_text = str(key)
        normalized["Key"] = key_text
        normalized.setdefault("PedalKey", key_text)

    gear_type = normalized.get("Type")
    if gear_type in (None, "") and key not in (None, ""):
        normalized["Type"] = str(key)

    knobs = normalized.get("KnobValues")
    if not isinstance(knobs, dict):
        normalized["KnobValues"] = {}

    return normalized


def _tone_id_for_name(
    name: str, slot_names: dict[int, str], definitions: list[dict[str, Any]]
) -> int | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    for tone_id, slot_name in slot_names.items():
        if str(slot_name).strip().lower() == normalized:
            return int(tone_id)
    for index, definition in enumerate(definitions):
        if _tone_definition_name(definition).lower() == normalized:
            return index
    return None


def _definition_for_tone(
    tone_id: int, name: str, definitions: list[dict[str, Any]]
) -> dict[str, Any] | None:
    normalized = name.strip().lower()
    for definition in definitions:
        if _tone_definition_name(definition).lower() == normalized:
            return definition
    if 0 <= tone_id < len(definitions):
        return definitions[tone_id]
    return None


def _tone_rig(
    name: str,
    tone_id: int,
    definition: dict[str, Any] | None = None,
    instrument: str = "guitar",
) -> dict[str, Any]:
    blocks = _tone_blocks_from_definition(definition)
    if not blocks:
        blocks = [
            {
                "id": "source-tone",
                "role": "amp",
                "name": name,
                "intent": {
                    "kind": "source-tone",
                    "family": "imported",
                    "tags": ["psarc", "tone"],
                },
                "params": {"sourceToneId": tone_id},
            }
        ]

    rig: dict[str, Any] = {
        "id": _rig_id(name, tone_id),
        "name": name,
        "instrument": instrument,
        "channels": 1,
        "blocks": blocks,
        "ext": {
            "source": {
                "format": "psarc-tone2014",
                "tone_id": tone_id,
                **({"definition": definition} if definition else {}),
            },
        },
    }
    node_ids = [block.get("id") for block in blocks if isinstance(block.get("id"), str)]
    if node_ids:
        rig["graph"] = {
            "nodes": ["input", *node_ids, "output"],
            "edges": _serial_edges(node_ids),
        }
    return rig


def _tone_blocks_from_definition(definition: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(definition, dict):
        return []
    gear = definition.get("GearList")
    if not isinstance(gear, dict):
        return []
    blocks: list[dict[str, Any]] = []
    for slot in (
        "PrePedal1",
        "PrePedal2",
        "PrePedal3",
        "PrePedal4",
        "Amp",
        "Cabinet",
        "PostPedal1",
        "PostPedal2",
        "PostPedal3",
        "PostPedal4",
        "Rack1",
        "Rack2",
        "Rack3",
        "Rack4",
    ):
        pedal = gear.get(slot)
        if not isinstance(pedal, dict):
            continue
        block = _pedal_to_rig_block(slot, pedal)
        if block:
            blocks.append(block)
    return blocks


def _pedal_to_rig_block(slot: str, pedal: dict[str, Any]) -> dict[str, Any] | None:
    pedal_type = pedal.get("Type") or pedal.get("PedalKey") or pedal.get("Key") or pedal.get("Category")
    knobs = pedal.get("KnobValues")
    if pedal_type in (None, "") and not isinstance(knobs, dict):
        return None
    role = _gear_slot_role(slot, pedal)
    name = str(pedal_type or role).strip()
    return {
        "id": _slug(slot) or "effect",
        "role": role,
        "name": name,
        "intent": {
            "kind": role,
            "family": _slug(str(pedal_type or role)),
            "tags": ["psarc", _slug(slot)],
        },
        "params": _rig_params(knobs if isinstance(knobs, dict) else {}),
        "ext": {"source": {"slot": slot, "pedal": _json_safe(pedal)}},
    }


def _gear_slot_role(slot: str, pedal: dict[str, Any]) -> str:
    if slot == "Amp":
        return "amp"
    if slot == "Cabinet":
        return "cab"
    category = str(pedal.get("Category") or "").lower()
    pedal_type = str(pedal.get("Type") or pedal.get("PedalKey") or pedal.get("Key") or "").lower()
    text = f"{category} {pedal_type}"
    if "delay" in text or "echo" in text:
        return "delay"
    if "reverb" in text:
        return "reverb"
    if any(token in text for token in ("chorus", "flanger", "phaser", "rotary", "vibrato")):
        return "modulation"
    if any(token in text for token in ("dist", "drive", "fuzz", "overdrive")):
        return "drive"
    if any(token in text for token in ("compress", "gate", "limiter")):
        return "dynamics"
    if any(token in text for token in ("eq", "filter", "wah")):
        return "filter"
    if "pitch" in text or "octave" in text:
        return "pitch"
    if slot.startswith("Rack"):
        return "utility"
    return "effect"


def _rig_params(values: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, (int, float)) and _finite_number(value):
            params[str(key)] = float(value)
        elif isinstance(value, (str, bool)):
            params[str(key)] = value
    return params


def _serial_edges(node_ids: list[str]) -> list[list[str]]:
    nodes = ["input", *node_ids, "output"]
    return [[nodes[index], nodes[index + 1]] for index in range(len(nodes) - 1)]


def _tone_id(tone: Any) -> int | None:
    try:
        tone_id = int(getattr(tone, "id"))
    except (TypeError, ValueError):
        return None
    return tone_id if tone_id >= 0 else None


def _rig_id(name: str, tone_id: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"tone-{tone_id}-{slug or 'imported'}"


def _phrase_ladder_to_feedpak(
    song: Any, level_payloads: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    phrases: list[dict[str, Any]] = []
    if not level_payloads:
        return phrases

    for iteration in song.phraseIterations:
        phrase_id = int(iteration.phraseId)
        if phrase_id < 0 or phrase_id >= len(song.phrases):
            continue
        phrase = song.phrases[phrase_id]
        start = _num(iteration.time)
        end = _num(iteration.endTime)
        if end <= start:
            end = start + 0.001
        max_difficulty = int(phrase.maxDifficulty)
        authored_diffs = [d for d in sorted(level_payloads) if d <= max_difficulty]
        if not authored_diffs:
            authored_diffs = sorted(level_payloads)

        levels = []
        for diff in authored_diffs:
            payload = level_payloads[diff]
            levels.append(
                {
                    "difficulty": diff,
                    "notes": _slice_by_time(payload["notes"], "t", start, end),
                    "chords": _slice_by_time(payload["chords"], "t", start, end),
                    "anchors": _slice_by_time(payload["anchors"], "time", start, end),
                    "handshapes": _slice_by_time(
                        payload["handshapes"], "start_time", start, end
                    ),
                }
            )

        if levels:
            phrases.append(
                {
                    "start_time": start,
                    "end_time": end,
                    "max_difficulty": max_difficulty,
                    "levels": levels,
                }
            )

    return phrases


def _slice_by_time(
    items: list[dict[str, Any]], key: str, start: float, end: float
) -> list[dict[str, Any]]:
    return [item for item in items if start <= float(item.get(key, 0.0)) < end]


def _notes_and_chords(
    song: Any, level: Any, templates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    notes: list[dict[str, Any]] = []
    chords: list[dict[str, Any]] = []
    seen_chords: set[tuple[float, int]] = set()
    for note in sorted(level.notes, key=lambda n: float(n.time)):
        chord_id = int(note.chordId)
        if 0 <= chord_id < len(templates) and chord_id != UINT32_NONE:
            key = (round(float(note.time), 5), chord_id)
            if key in seen_chords:
                continue
            seen_chords.add(key)
            chord = {"t": _num(note.time), "id": chord_id}
            chord_notes = _chord_notes(song, note, chord_id)
            if chord_notes:
                chord["notes"] = chord_notes
            chords.append(chord)
        else:
            notes.append(_note_to_feedpak(note))
    return notes, chords


def _note_to_feedpak(note: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"t": _num(note.time), "s": int(note.string), "f": int(note.fret)}
    sustain = float(note.sustain or 0.0)
    if sustain > 0:
        out["sus"] = _num(sustain)
    if int(note.slideTo) >= 0:
        out["sl"] = int(note.slideTo)
    if int(note.slideUnpitchTo) >= 0:
        out["slu"] = int(note.slideUnpitchTo)
    bend = _bend_value(note)
    if bend:
        out["bn"] = bend
    if int(note.leftHand) >= 0:
        out["fg"] = int(note.leftHand)
    _apply_note_mask(out, int(note.mask))
    return out


def _chord_notes(song: Any, note: Any, chord_id: int) -> list[dict[str, Any]]:
    if 0 <= int(note.chordNoteId) < len(song.chordNotes):
        chord_note = song.chordNotes[int(note.chordNoteId)]
        notes = []
        for string, fret in enumerate(song.chordTemplates[chord_id].frets):
            if int(fret) < 0:
                continue
            entry: dict[str, Any] = {"s": string, "f": int(fret)}
            sustain = float(note.sustain or 0.0)
            if sustain > 0:
                entry["sus"] = _num(sustain)
            if int(chord_note.slideTo[string]) >= 0:
                entry["sl"] = int(chord_note.slideTo[string])
            if int(chord_note.slideUnpitchTo[string]) >= 0:
                entry["slu"] = int(chord_note.slideUnpitchTo[string])
            _apply_note_mask(entry, int(chord_note.mask[string]) | int(note.mask))
            notes.append(entry)
        return notes

    template = song.chordTemplates[chord_id]
    notes = []
    for string, fret in enumerate(template.frets):
        if int(fret) < 0:
            continue
        entry: dict[str, Any] = {"s": string, "f": int(fret)}
        _apply_note_mask(entry, int(note.mask), include_note_only=False)
        notes.append(entry)
    return notes


def _apply_note_mask(
    out: dict[str, Any], mask: int, *, include_note_only: bool = True
) -> None:
    technique_fields = {
        "pm": NOTE_MASK_PALMMUTE,
        "mt": NOTE_MASK_MUTE,
        "fhm": NOTE_MASK_FRETHANDMUTE,
        "hm": NOTE_MASK_HARMONIC,
        "hp": NOTE_MASK_PINCHHARMONIC,
        "ac": NOTE_MASK_ACCENT,
        "vb": NOTE_MASK_VIBRATO,
        "tr": NOTE_MASK_TREMOLO,
        "tp": NOTE_MASK_TAP,
        "plk": NOTE_MASK_PLUCK,
        "slp": NOTE_MASK_SLAP,
        "ln": NOTE_MASK_PARENT,
        "ig": NOTE_MASK_IGNORE,
    }
    if include_note_only:
        technique_fields.update({
            "ho": NOTE_MASK_HAMMERON,
            "po": NOTE_MASK_PULLOFF,
        })
    for field, bit in technique_fields.items():
        if mask & bit:
            out[field] = True


def _bend_value(note: Any) -> float | None:
    values = [float(b.step) for b in note.bends if float(b.step) != 0.0]
    if values:
        return _num(max(values, key=abs))
    if float(note.bend_time or 0.0) > 0:
        return _num(note.bend_time)
    return None


def _template_to_feedpak(template: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": template.name or "",
        "frets": [int(x) for x in template.frets],
        "fingers": [int(x) for x in template.fingers],
    }
    return out


def _anchor_to_feedpak(anchor: Any) -> dict[str, Any]:
    out = {"time": _num(anchor.time), "fret": int(anchor.fret)}
    if int(anchor.width) > 0:
        out["width"] = int(anchor.width)
    return out


def _handshapes_to_feedpak(level: Any) -> list[dict[str, Any]]:
    shapes: list[dict[str, Any]] = []
    for group in level.fingerprints:
        for fp in group:
            if int(fp.chordId) == UINT32_NONE:
                continue
            shapes.append(
                {
                    "chord_id": int(fp.chordId),
                    "start_time": _num(fp.startTime),
                    "end_time": _num(fp.endTime),
                }
            )
    return shapes


def _song_to_timeline(song: Any) -> dict[str, Any]:
    return {
        "version": 1,
        "beats": [_beat_to_feedpak(b) for b in song.beats],
        "sections": [_section_to_feedpak(s) for s in song.sections],
    }


def _beat_to_feedpak(beat: Any) -> dict[str, Any]:
    measure = int(beat.measure)
    return {"time": _num(beat.time), "measure": measure if measure > 0 else -1}


def _section_to_feedpak(section: Any) -> dict[str, Any]:
    out = {"name": section.name or "section", "time": _num(section.startTime)}
    if int(section.number) > 0:
        out["number"] = int(section.number)
    return out


def _song_to_lyrics(song: Any) -> list[dict[str, Any]]:
    lyrics = []
    for vocal in song.vocals:
        text = (vocal.lyrics or "").strip()
        if not text:
            continue
        lyrics.append({"t": _num(vocal.time), "d": _num(vocal.length), "w": text})
    return lyrics


def _duration_from_song(song: Any | None) -> float | None:
    if song is None:
        return None
    try:
        return float(song.metadata.songLength)
    except Exception:  # noqa: BLE001
        return None


def _copy_audio(
    content: dict[str, bytes], package_dir: Path, warnings: list[ConversionWarning]
) -> dict[str, Any]:
    audio = [
        (path, data)
        for path, data in content.items()
        if path.lower().endswith((".wem", ".ogg", ".wav", ".mp3", ".flac", ".opus"))
    ]
    if not audio:
        warnings.append(ConversionWarning("No audio file found; wrote empty placeholder stem."))
        target = package_dir / "stems" / "full.wav"
        target.write_bytes(b"")
        return {"id": "full", "file": "stems/full.wav", "codec": "wav", "default": True}

    path, data = max(audio, key=lambda item: len(item[1]))
    ext = Path(path).suffix.lower() or ".bin"
    if ext == ".wem":
        converted = _convert_wem_bytes_to_ogg(data, package_dir / "stems" / "full.ogg")
        if converted:
            return {
                "id": "full",
                "file": "stems/full.ogg",
                "codec": "vorbis",
                "default": True,
            }
        warnings.append(
            ConversionWarning(
                "Could not convert WEM audio to OGG; preserved WEM, which FeedBack may not play."
            )
        )

    target_name = f"full{ext}"
    (package_dir / "stems" / target_name).write_bytes(data)
    codec = {
        ".ogg": "vorbis",
        ".wav": "wav",
        ".wem": "wem",
        ".mp3": "mp3",
        ".flac": "flac",
        ".opus": "opus",
    }.get(ext, ext.lstrip("."))
    return {"id": "full", "file": f"stems/{target_name}", "codec": codec, "default": True}


def _convert_wem_bytes_to_ogg(data: bytes, output_path: Path) -> bool:
    tools_dir = _tools_dir()
    if _convert_wem_with_vgmstream(data, output_path, tools_dir):
        return True

    ww2ogg = (tools_dir / "ww2ogg.exe").resolve()
    if not ww2ogg.is_file():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = output_path.resolve()
    temp_wem = output_path.with_name(output_path.stem + ".convert.wem").resolve()
    temp_ogg = output_path.with_name(output_path.stem + ".convert.ogg").resolve()
    temp_wem.write_bytes(data)
    try:
        for codebook in (
            (tools_dir / "packed_codebooks.bin").resolve(),
            (tools_dir / "packed_codebooks_aoTuV_603.bin").resolve(),
        ):
            if not codebook.is_file():
                continue
            temp_ogg.unlink(missing_ok=True)
            proc = subprocess.run(
                [
                    str(ww2ogg),
                    str(temp_wem),
                    "-o",
                    str(temp_ogg),
                    "--pcb",
                    str(codebook),
                ],
                cwd=str(tools_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if proc.returncode == 0 and temp_ogg.is_file() and temp_ogg.stat().st_size > 1024:
                if output_path.exists():
                    output_path.unlink()
                temp_ogg.replace(output_path)
                if output_path.read_bytes().startswith(b"OggS"):
                    return True
                output_path.unlink(missing_ok=True)
        return False
    finally:
        temp_wem.unlink(missing_ok=True)
        temp_ogg.unlink(missing_ok=True)


def _convert_wem_with_vgmstream(data: bytes, output_path: Path, tools_dir: Path) -> bool:
    vgmstream = (tools_dir / "vgmstream-cli.exe").resolve()
    oggenc = (tools_dir / "oggenc.exe").resolve()
    if not vgmstream.is_file() or not oggenc.is_file():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = output_path.resolve()
    temp_wem = output_path.with_name(output_path.stem + ".vgm.wem").resolve()
    temp_wav = output_path.with_name(output_path.stem + ".vgm.wav").resolve()
    temp_ogg = output_path.with_name(output_path.stem + ".vgm.ogg").resolve()
    temp_wem.write_bytes(data)
    try:
        decode = subprocess.run(
            [str(vgmstream), "-o", str(temp_wav), str(temp_wem)],
            cwd=str(tools_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if decode.returncode != 0 or not temp_wav.is_file() or temp_wav.stat().st_size < 1024:
            return False

        temp_ogg.unlink(missing_ok=True)
        encode = subprocess.run(
            [str(oggenc), "-Q", "-q", "5", str(temp_wav), "-o", str(temp_ogg)],
            cwd=str(tools_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if encode.returncode != 0 or not temp_ogg.is_file() or temp_ogg.stat().st_size < 1024:
            return False

        if output_path.exists():
            output_path.unlink()
        temp_ogg.replace(output_path)
        if output_path.read_bytes().startswith(b"OggS"):
            return True
        output_path.unlink(missing_ok=True)
        return False
    finally:
        temp_wem.unlink(missing_ok=True)
        temp_wav.unlink(missing_ok=True)
        temp_ogg.unlink(missing_ok=True)


def _tools_dir() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled = Path(bundle_root) / "feedback_converter" / "tools"
        if bundled.exists():
            return bundled
        return Path(bundle_root) / "tools"
    return Path(__file__).resolve().parent / "tools"


def _copy_cover(content: dict[str, bytes], package_dir: Path) -> str | None:
    images = [
        (path, data)
        for path, data in content.items()
        if path.lower().endswith((".png", ".jpg", ".jpeg", ".dds"))
    ]
    if not images:
        return None
    path, data = max(images, key=lambda item: len(item[1]))
    ext = Path(path).suffix.lower()
    if ext == ".dds":
        if _convert_dds_bytes_to_png(data, package_dir / "cover.png"):
            return "cover.png"
        return None
    if ext not in {".png", ".jpg", ".jpeg"}:
        return None
    target = f"cover{ext}"
    (package_dir / target).write_bytes(data)
    return target


def _convert_dds_bytes_to_png(data: bytes, output_path: Path) -> bool:
    tools_dir = _tools_dir()
    topng = (tools_dir / "topng.exe").resolve()
    if not topng.is_file():
        return False

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dds = output_path.with_name(output_path.stem + ".convert.dds").resolve()
    temp_dds.write_bytes(data)
    try:
        output_path.unlink(missing_ok=True)
        proc = subprocess.run(
            [
                str(topng),
                "-quiet",
                "-overwrite",
                "-out",
                "png",
                "-o",
                str(output_path),
                str(temp_dds),
            ],
            cwd=str(tools_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        return (
            proc.returncode == 0
            and output_path.is_file()
            and output_path.stat().st_size > 8
            and output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        )
    finally:
        temp_dds.unlink(missing_ok=True)


def _arrangement_id(source_path: str, metadata: dict[str, Any]) -> str:
    low_path = source_path.lower()
    for key, name in metadata.get("arrangement_names", {}).items():
        if key and key in low_path:
            return _slug(name)
    stem = Path(source_path.replace("\\", "/")).stem
    for token in ("lead", "rhythm", "bass", "vocals"):
        if token in stem.lower() or token in low_path:
            return token
    return _slug(stem)


def _arrangement_type(arr_id: str) -> str:
    return "bass" if "bass" in arr_id else "guitar"


def _unique_id(value: str, used: set[str]) -> str:
    base = _slug(value) or "arrangement"
    candidate = base
    i = 2
    while candidate in used:
        candidate = f"{base}-{i}"
        i += 1
    used.add(candidate)
    return candidate


def _display_name(value: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", value) if part) or value


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value).strip().lower())
    value = re.sub(r"-+", "-", value).strip("-_")
    return value


def _num(value: Any) -> float:
    return round(float(value), 6)


def _finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in (float("inf"), float("-inf"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if _finite_number(value) else None
    return str(value)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _zip_dir(source: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(source.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(source).as_posix())
