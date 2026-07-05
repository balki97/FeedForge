from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .converter import _extract_metadata, _find_sng_entries, _song_tones_to_feedpak
from .inspector import _load_json_file, _rig_builder_data_dir, _rig_builder_db
from .psarc_format.psarc import PSARC
from .psarc_format.sng import Song


@dataclass(frozen=True)
class SeededTone:
    tone_key: str
    status: str
    stages: int
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SeedResult:
    db_path: Path
    song_key: str
    tones: list[SeededTone]


GEAR_SLOTS = (
    ("PrePedal1", "pre_pedal"),
    ("PrePedal2", "pre_pedal"),
    ("PrePedal3", "pre_pedal"),
    ("PrePedal4", "pre_pedal"),
    ("Amp", "amp"),
    ("PostPedal1", "post_pedal"),
    ("PostPedal2", "post_pedal"),
    ("PostPedal3", "post_pedal"),
    ("PostPedal4", "post_pedal"),
    ("Rack1", "rack"),
    ("Rack2", "rack"),
    ("Rack3", "rack"),
    ("Rack4", "rack"),
    ("Cabinet", "cabinet"),
)


def seed_rig_builder_routes(input_psarc: Path, *, force: bool = True) -> SeedResult:
    input_psarc = Path(input_psarc)
    db_path = _rig_builder_db() or _default_rig_builder_db_path()
    data_dir = _rig_builder_data_dir()
    if db_path is None:
        raise FileNotFoundError("FeedBack Rig Builder database was not found.")
    if data_dir is None:
        raise FileNotFoundError("FeedBack Rig Builder data folder was not found.")

    with input_psarc.open("rb") as fh:
        content = PSARC(crypto=True).parse_stream(fh)
    metadata = _extract_metadata(content)
    song_key = input_psarc.with_suffix(".feedpak").name

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        seeded: list[SeededTone] = []
        seen_tone_keys: set[str] = set()
        for source_path, data in _find_sng_entries(content):
            try:
                song = Song.parse(data)
            except Exception:
                continue
            tone_data = _song_tones_to_feedpak(song, source_path, metadata)
            if not tone_data:
                continue
            for definition in (tone_data.get("tones") or {}).get("definitions") or []:
                if not isinstance(definition, dict):
                    continue
                tone_key = str(definition.get("Key") or definition.get("Name") or "").strip()
                if not tone_key:
                    continue
                if tone_key in seen_tone_keys:
                    continue
                seen_tone_keys.add(tone_key)
                if not force and _has_mapping(conn, song_key, tone_key):
                    continue
                seeded.append(_seed_definition(conn, data_dir, song_key, tone_key, definition))
        conn.commit()
        return SeedResult(db_path=db_path, song_key=song_key, tones=seeded)
    finally:
        conn.close()


def _seed_definition(
    conn: sqlite3.Connection,
    data_dir: Path,
    song_key: str,
    tone_key: str,
    definition: dict[str, Any],
) -> SeededTone:
    _delete_mapping(conn, song_key, tone_key)
    preset_name = f"{song_key}::{tone_key}"
    conn.execute(
        "INSERT INTO presets (name, model_file, ir_file, input_gain, output_gain, gate_threshold, settings_json) "
        "VALUES (?, '', '', 1.0, 1.0, -60.0, '{}')",
        (preset_name,),
    )
    preset_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    missing: list[str] = []
    model_file = ""
    ir_file = ""
    stage_count = 0
    for slot_order, stage in enumerate(_stages_from_definition(data_dir, definition, missing)):
        conn.execute(
            "INSERT INTO preset_pieces "
            "(preset_id, slot_order, slot, rs_gear_type, kind, file, params_json, tone3000_id, "
            "assigned_mode, bypassed, vst_path, vst_format, vst_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'feedforge', 0, ?, ?, ?)",
            (
                preset_id,
                slot_order,
                stage["slot"],
                stage["gear"],
                stage["kind"],
                stage.get("file"),
                json.dumps(stage.get("params") or {}, ensure_ascii=False),
                stage.get("tone3000_id"),
                stage.get("vst_path"),
                stage.get("vst_format"),
                json.dumps(stage.get("vst_state"), ensure_ascii=False) if stage.get("vst_state") else None,
            ),
        )
        stage_count += 1
        if not model_file and stage["kind"] == "nam" and stage.get("file"):
            model_file = stage["file"]
        if not ir_file and stage["kind"] in {"ir", "rs_ir"} and stage.get("file"):
            ir_file = stage["file"]

    conn.execute(
        "UPDATE presets SET model_file = ?, ir_file = ? WHERE id = ?",
        (model_file, ir_file, preset_id),
    )
    conn.execute(
        "INSERT INTO tone_mappings (filename, tone_key, preset_id) VALUES (?, ?, ?)",
        (song_key, tone_key, preset_id),
    )
    return SeededTone(
        tone_key=tone_key,
        status="ready" if not missing and stage_count else "partial",
        stages=stage_count,
        missing=missing,
    )


def _stages_from_definition(
    data_dir: Path,
    definition: dict[str, Any],
    missing: list[str],
) -> list[dict[str, Any]]:
    gear_list = definition.get("GearList") if isinstance(definition.get("GearList"), dict) else {}
    stages: list[dict[str, Any]] = []
    for gear_slot, slot_type in GEAR_SLOTS:
        gear = gear_list.get(gear_slot)
        if not isinstance(gear, dict):
            continue
        key = str(gear.get("Key") or gear.get("PedalKey") or gear.get("Type") or "").strip()
        if not key:
            continue
        params = gear.get("KnobValues") if isinstance(gear.get("KnobValues"), dict) else {}
        stage = _resolve_stage(data_dir, slot_type, key, params)
        if stage is None:
            missing.append(key)
            continue
        stages.append(stage)
    return stages


def _resolve_stage(data_dir: Path, slot: str, gear_key: str, params: dict[str, Any]) -> dict[str, Any] | None:
    vst = _resolve_vst(data_dir, gear_key)
    if vst:
        return {
            "slot": slot,
            "gear": gear_key,
            "kind": "vst",
            "file": None,
            "params": params,
            "vst_path": str(vst),
            "vst_format": "VST3",
            "vst_state": {"params": {}},
        }
    if slot == "cabinet":
        cab = _resolve_cab_ir(data_dir, gear_key)
        if cab:
            return {
                "slot": slot,
                "gear": cab["gear"],
                "kind": cab["kind"],
                "file": cab["file"],
                "params": params,
                "vst_path": None,
                "vst_format": None,
                "vst_state": None,
            }
    return None


def _resolve_vst(data_dir: Path, gear_key: str) -> Path | None:
    vst_map = _load_json_file(data_dir / "rs_gear_to_vst.json")
    candidates = vst_map.get(gear_key) if isinstance(vst_map, dict) else None
    if not isinstance(candidates, list):
        return None
    plugin_root = data_dir.parent
    for item in candidates:
        if not isinstance(item, dict) or not item.get("bundled"):
            continue
        candidate = plugin_root / str(item["bundled"])
        if candidate.exists():
            return candidate
    return None


def _resolve_cab_ir(data_dir: Path, gear_key: str) -> dict[str, str] | None:
    config_dir = _rig_builder_config_dir()
    if config_dir is None:
        return None
    ir_root = config_dir / "nam_irs"
    mic_map = _load_json_file(data_dir / "rs_cab_mic_map.json")
    if isinstance(mic_map, dict):
        for base, variants in mic_map.items():
            if not isinstance(variants, dict):
                continue
            for spec in variants.values():
                if isinstance(spec, dict) and str(spec.get("effect_name") or "").lower() == gear_key.lower():
                    file_name = str(spec.get("ir_file") or "")
                    if file_name and (ir_root / file_name).exists():
                        return {"gear": str(base), "kind": "rs_ir", "file": file_name}
                    fallback = _fallback_ir(ir_root, str(base))
                    if fallback:
                        return {"gear": str(base), "kind": "ir", "file": fallback}
    fallback = _fallback_ir(ir_root, gear_key)
    if fallback:
        return {"gear": gear_key, "kind": "ir", "file": fallback}
    return None


def _fallback_ir(ir_root: Path, gear_key: str) -> str | None:
    preferred = (
        "other/Bass Cab Sim 2.wav"
        if gear_key.lower().startswith("bass_")
        else "other/greenback 212 1 mono.wav"
    )
    if (ir_root / preferred).exists():
        return preferred
    for item in sorted(ir_root.rglob("*.wav")):
        try:
            return item.relative_to(ir_root).as_posix()
        except ValueError:
            return item.name
    return None


def _delete_mapping(conn: sqlite3.Connection, song_key: str, tone_key: str) -> None:
    rows = conn.execute(
        "SELECT preset_id FROM tone_mappings WHERE filename = ? AND tone_key = ?",
        (song_key, tone_key),
    ).fetchall()
    for (preset_id,) in rows:
        conn.execute("DELETE FROM preset_pieces WHERE preset_id = ?", (preset_id,))
        conn.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
    conn.execute("DELETE FROM tone_mappings WHERE filename = ? AND tone_key = ?", (song_key, tone_key))


def _has_mapping(conn: sqlite3.Connection, song_key: str, tone_key: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM tone_mappings WHERE filename = ? AND tone_key = ? LIMIT 1",
        (song_key, tone_key),
    ).fetchone())


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS presets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE,
          model_file TEXT,
          ir_file TEXT,
          input_gain REAL DEFAULT 1.0,
          output_gain REAL DEFAULT 1.0,
          gate_threshold REAL DEFAULT -60.0,
          settings_json TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS tone_mappings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          filename TEXT,
          tone_key TEXT,
          preset_id INTEGER,
          UNIQUE(filename, tone_key)
        );
        CREATE TABLE IF NOT EXISTS preset_pieces (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          preset_id INTEGER,
          slot_order INTEGER,
          slot TEXT,
          rs_gear_type TEXT,
          kind TEXT,
          file TEXT,
          params_json TEXT,
          tone3000_id INTEGER,
          assigned_mode TEXT DEFAULT 'feedforge',
          bypassed INTEGER DEFAULT 0,
          vst_path TEXT,
          vst_format TEXT,
          vst_state TEXT
        );
        """
    )


def _rig_builder_config_dir() -> Path | None:
    db = _rig_builder_db()
    if db:
        return db.parent
    candidate = _default_rig_builder_db_path()
    return candidate.parent if candidate else None


def _default_rig_builder_db_path() -> Path | None:
    import os

    root = os.environ.get("APPDATA")
    if not root:
        return None
    config = Path(root) / "feedback-desktop" / "slopsmith-config"
    return config / "nam_tone.db" if config.is_dir() else None
