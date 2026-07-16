from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .converter import (
    ConversionWarning,
    _codec_for_audio_path,
    _maybe_separate_stems,
    _write_manifest,
    _zip_dir,
)


@dataclass
class FeedpakEditResult:
    output_path: Path
    warnings: list[ConversionWarning] = field(default_factory=list)


METADATA_FIELDS = ("title", "artist", "album", "year", "duration", "language")
AUTHOR_ROLES = {"charter", "creator", "arranger", "author", "contributor"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def inspect_feedpak(input_path: Path, *, cover_dir: Path | None = None) -> dict[str, Any]:
    """Read FeedPak metadata without changing the package."""
    input_path = Path(input_path)
    if input_path.is_file():
        return _inspect_feedpak_zip(input_path, cover_dir=cover_dir)
    with _open_feedpak(input_path) as package_dir:
        manifest = _read_manifest(package_dir)
        cover_path = _extract_cover(package_dir, manifest, cover_dir)
        rigs = _read_json(package_dir / str(manifest.get("rigs") or "rigs.json"))
        arrangement_payloads = _arrangement_payloads(package_dir, manifest)
        arrangements = _arrangement_previews(arrangement_payloads)
        tones = _arrangement_tone_previews(arrangement_payloads)
        if not tones:
            tones = _rig_previews(rigs)
        return {
            "source_type": "feedpak",
            "title": str(manifest.get("title") or input_path.stem),
            "artist": str(manifest.get("artist") or "Unknown Artist"),
            "album": str(manifest.get("album") or ""),
            "year": manifest.get("year"),
            "duration": manifest.get("duration"),
            "language": str(manifest.get("language") or ""),
            "authors": _normalize_authors(manifest.get("authors")),
            "cover_path": cover_path,
            "cover": manifest.get("cover"),
            "arrangements": arrangements,
            "stems": _stem_previews(package_dir, manifest),
            "tones": tones,
            "rigs": manifest.get("rigs"),
            "lyrics": _lyrics_count(package_dir, manifest),
            "warnings": [],
        }


def _inspect_feedpak_zip(input_path: Path, *, cover_dir: Path | None) -> dict[str, Any]:
    with zipfile.ZipFile(input_path) as zf:
        manifest = _read_manifest_from_zip(zf)
        cover_path = _extract_cover_from_zip(zf, manifest, cover_dir)
        rigs = _read_json_from_zip(zf, str(manifest.get("rigs") or "rigs.json"))
        arrangement_payloads = _arrangement_payloads_from_zip(zf, manifest)
        arrangements = _arrangement_previews(arrangement_payloads)
        tones = _arrangement_tone_previews(arrangement_payloads)
        if not tones:
            tones = _rig_previews(rigs)
        return {
            "source_type": "feedpak",
            "title": str(manifest.get("title") or input_path.stem),
            "artist": str(manifest.get("artist") or "Unknown Artist"),
            "album": str(manifest.get("album") or ""),
            "year": manifest.get("year"),
            "duration": manifest.get("duration"),
            "language": str(manifest.get("language") or ""),
            "authors": _normalize_authors(manifest.get("authors")),
            "cover_path": cover_path,
            "cover": manifest.get("cover"),
            "arrangements": arrangements,
            "stems": _stem_previews_from_zip(zf, manifest),
            "tones": tones,
            "rigs": manifest.get("rigs"),
            "lyrics": _lyrics_count_from_zip(zf, manifest),
            "warnings": [],
        }


def update_feedpak(
    input_path: Path,
    output_path: Path | None = None,
    *,
    metadata: dict[str, Any] | None = None,
    authors: list[dict[str, str]] | None = None,
    cover_path: Path | None = None,
    remove_cover: bool = False,
    separate_stems: bool = False,
    demucs_url: str | None = None,
    demucs_api_key: str | None = None,
    demucs_model: str | None = None,
    demucs_stems: list[str] | None = None,
    overwrite: bool = False,
) -> FeedpakEditResult:
    """Edit an existing FeedPak and write a new package or overwrite it."""
    input_path = Path(input_path)
    target = Path(output_path) if output_path else input_path
    if target.exists() and target.resolve() != input_path.resolve() and not overwrite:
        raise FileExistsError(f"Output already exists: {target}")

    warnings: list[ConversionWarning] = []
    with tempfile.TemporaryDirectory(prefix="feedforge-feedpak-") as temp:
        package_dir = Path(temp) / "package.feedpak"
        _extract_or_copy(input_path, package_dir)
        manifest = _read_manifest(package_dir)

        _apply_metadata(manifest, metadata or {})
        if authors is not None:
            manifest["authors"] = _normalize_authors(authors)
        _apply_cover(package_dir, manifest, cover_path=cover_path, remove_cover=remove_cover)

        if separate_stems:
            full_entry = _full_stem_entry(manifest)
            stem_entries, separation = _maybe_separate_stems(
                package_dir,
                full_entry,
                warnings,
                separate_stems=True,
                demucs_url=demucs_url,
                demucs_api_key=demucs_api_key,
                demucs_model=demucs_model,
                demucs_stems=demucs_stems,
            )
            manifest["stems"] = stem_entries
            if separation:
                manifest["stem_separation"] = separation

        _write_manifest(package_dir / "manifest.yaml", manifest)
        _write_package(package_dir, target, overwrite=overwrite or target.resolve() == input_path.resolve())

    return FeedpakEditResult(output_path=target, warnings=warnings)


class _FeedpakContext:
    def __init__(self, input_path: Path) -> None:
        self.input_path = Path(input_path)
        self.temp: tempfile.TemporaryDirectory[str] | None = None
        self.package_dir: Path | None = None

    def __enter__(self) -> Path:
        if self.input_path.is_dir():
            self.package_dir = self.input_path
            return self.input_path
        self.temp = tempfile.TemporaryDirectory(prefix="feedforge-inspect-feedpak-")
        self.package_dir = Path(self.temp.name) / "package.feedpak"
        _extract_zip(self.input_path, self.package_dir)
        return self.package_dir

    def __exit__(self, *_exc: object) -> None:
        if self.temp is not None:
            self.temp.cleanup()


def _open_feedpak(input_path: Path) -> _FeedpakContext:
    return _FeedpakContext(input_path)


def _extract_or_copy(input_path: Path, package_dir: Path) -> None:
    if input_path.is_dir():
        shutil.copytree(input_path, package_dir)
        return
    _extract_zip(input_path, package_dir)


def _extract_zip(input_path: Path, package_dir: Path) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_path) as zf:
        for member in zf.infolist():
            target = (package_dir / member.filename).resolve()
            if package_dir.resolve() not in target.parents and target != package_dir.resolve():
                raise ValueError(f"Unsafe path in FeedPak archive: {member.filename}")
            zf.extract(member, package_dir)


def _write_package(package_dir: Path, target: Path, *, overwrite: bool) -> None:
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {target}")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".feedpak":
        _zip_dir(package_dir, target)
    else:
        shutil.copytree(package_dir, target)


def _read_manifest(package_dir: Path) -> dict[str, Any]:
    path = package_dir / "manifest.yaml"
    if not path.is_file():
        raise FileNotFoundError("FeedPak is missing manifest.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest.yaml is not a mapping")
    return data


def _read_manifest_from_zip(zf: zipfile.ZipFile) -> dict[str, Any]:
    data = yaml.safe_load(zf.read("manifest.yaml").decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest.yaml is not a mapping")
    return data


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_from_zip(zf: zipfile.ZipFile, name: str) -> Any:
    safe_name = _safe_archive_name(name)
    if not safe_name or safe_name not in zf.namelist():
        return None
    return json.loads(zf.read(safe_name).decode("utf-8"))


def _extract_cover(package_dir: Path, manifest: dict[str, Any], cover_dir: Path | None) -> str | None:
    cover = manifest.get("cover")
    if not cover or cover_dir is None:
        return None
    source = package_dir / str(cover)
    if not source.is_file():
        return None
    cover_dir.mkdir(parents=True, exist_ok=True)
    target = cover_dir / f"cover{source.suffix.lower() or '.png'}"
    shutil.copy2(source, target)
    return str(target)


def _extract_cover_from_zip(zf: zipfile.ZipFile, manifest: dict[str, Any], cover_dir: Path | None) -> str | None:
    cover = _safe_archive_name(str(manifest.get("cover") or ""))
    if not cover or cover_dir is None or cover not in zf.namelist():
        return None
    cover_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(cover).suffix.lower() or ".png"
    target = cover_dir / f"cover{suffix}"
    target.write_bytes(zf.read(cover))
    return str(target)


def _arrangement_payloads(package_dir: Path, manifest: dict[str, Any]) -> list[tuple[dict[str, Any], Any]]:
    rows = []
    for entry in manifest.get("arrangements") or []:
        if isinstance(entry, dict):
            rows.append((entry, _read_json(package_dir / str(entry.get("file") or ""))))
    return rows


def _arrangement_payloads_from_zip(zf: zipfile.ZipFile, manifest: dict[str, Any]) -> list[tuple[dict[str, Any], Any]]:
    rows = []
    for entry in manifest.get("arrangements") or []:
        if isinstance(entry, dict):
            rows.append((entry, _read_json_from_zip(zf, str(entry.get("file") or ""))))
    return rows


def _arrangement_previews(payloads: list[tuple[dict[str, Any], Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry, data in payloads:
        rows.append(
            {
                "id": entry.get("id") or entry.get("name") or "",
                "name": entry.get("name") or entry.get("id") or "Arrangement",
                "type": entry.get("type") or "guitar",
                "tuning": entry.get("tuning") or [],
                "capo": entry.get("capo") or 0,
                "difficulties": _difficulty_count(data),
                "notes": _event_count(data),
                "chords": 0,
                "note_count": entry.get("note_count") or _event_count(data),
                "event_count": entry.get("event_count") or _event_count(data),
                "file": entry.get("file") or "",
            }
        )
    return rows


def _arrangement_tone_previews(payloads: list[tuple[dict[str, Any], Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry, data in payloads:
        if not isinstance(data, dict) or not isinstance(data.get("tones"), dict):
            continue
        tones = data["tones"]
        arr_id = str(entry.get("id") or entry.get("name") or "")
        rows.append(
            {
                "arrangement_id": arr_id,
                "arrangement_name": str(entry.get("name") or arr_id or "Arrangement"),
                "base": str(tones.get("base") or ""),
                "base_rig": str(tones.get("base_rig") or ""),
                "definitions": [_tone_definition_preview(definition) for definition in tones.get("definitions") or []],
                "changes": [_tone_change_preview(change) for change in tones.get("changes") or []],
            }
        )
    return rows


def _tone_definition_preview(definition: Any) -> dict[str, Any]:
    if not isinstance(definition, dict):
        return {"key": "", "name": "Tone", "gear": []}
    gear_list = definition.get("GearList") or definition.get("gear") or {}
    gear = []
    if isinstance(gear_list, dict):
        for slot, item in gear_list.items():
            if isinstance(item, dict):
                gear.append(_source_gear_to_preview(str(slot), item))
    return {
        "key": str(definition.get("Key") or definition.get("ToneKey") or definition.get("key") or ""),
        "name": str(definition.get("Name") or definition.get("ToneName") or definition.get("name") or "Tone"),
        "gear": gear,
    }


def _tone_change_preview(change: Any) -> dict[str, Any]:
    if not isinstance(change, dict):
        return {"time": 0.0, "name": "", "rig": ""}
    return {
        "time": float(change.get("t") or change.get("time") or 0.0),
        "name": str(change.get("name") or change.get("tone") or ""),
        "rig": str(change.get("rig") or change.get("base_rig") or ""),
    }


def _source_gear_to_preview(slot: str, item: dict[str, Any]) -> dict[str, Any]:
    key = str(item.get("Key") or item.get("PedalKey") or item.get("name") or "")
    return {
        "slot": slot,
        "key": key,
        "type": str(item.get("Type") or item.get("type") or ""),
        "category": str(item.get("Type") or item.get("type") or ""),
        "knobs": len(item.get("KnobValues") or item.get("params") or {}),
        "knob_values": item.get("KnobValues") or item.get("params") or {},
        "route": str(item.get("route") or item.get("feedbackRoute") or ""),
    }


def _stem_previews(package_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for stem in manifest.get("stems") or []:
        if not isinstance(stem, dict):
            continue
        file_name = str(stem.get("file") or "")
        path = package_dir / file_name
        rows.append(
            {
                "id": stem.get("id") or Path(file_name).stem,
                "file": file_name,
                "codec": stem.get("codec") or _codec_for_audio_path(file_name),
                "default": bool(stem.get("default")),
                "size": path.stat().st_size if path.is_file() else None,
            }
        )
    return rows


def _stem_previews_from_zip(zf: zipfile.ZipFile, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    sizes = {item.filename: item.file_size for item in zf.infolist() if not item.is_dir()}
    for stem in manifest.get("stems") or []:
        if not isinstance(stem, dict):
            continue
        file_name = _safe_archive_name(str(stem.get("file") or ""))
        rows.append(
            {
                "id": stem.get("id") or Path(file_name).stem,
                "file": file_name,
                "codec": stem.get("codec") or _codec_for_audio_path(file_name),
                "default": bool(stem.get("default")),
                "size": sizes.get(file_name),
            }
        )
    return rows


def _rig_previews(rigs: Any) -> list[dict[str, Any]]:
    if not isinstance(rigs, dict):
        return []
    rows = []
    for rig in rigs.get("rigs") or []:
        if not isinstance(rig, dict):
            continue
        blocks = []
        for block in rig.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            blocks.append(
                {
                    "id": block.get("id") or "",
                    "role": block.get("role") or "",
                    "name": block.get("name") or "",
                    "route": block.get("route") or block.get("vst") or "",
                    "params": block.get("params") or {},
                    "source": (block.get("ext") or {}).get("source") or {},
                }
            )
        rows.append(
            {
                "arrangement_id": rig.get("arrangement_id") or rig.get("arrangement") or "",
                "arrangement_name": rig.get("arrangement_name") or rig.get("instrument") or "Rig",
                "base": rig.get("name") or "",
                "base_rig": rig.get("id") or "",
                "definitions": [
                    {
                        "key": rig.get("id") or "",
                        "name": rig.get("name") or "Rig",
                        "gear": [_block_to_gear(block) for block in blocks],
                    }
                ],
                "changes": [],
                "blocks": blocks,
            }
        )
    return rows


def _block_to_gear(block: dict[str, Any]) -> dict[str, Any]:
    source = block.get("source") or {}
    source_item = next((value for value in source.values() if isinstance(value, dict)), {})
    key = str(source_item.get("Key") or source_item.get("PedalKey") or block.get("name") or "")
    return {
        "slot": block.get("id") or source.get("slot") or block.get("role") or "",
        "key": key,
        "type": block.get("role") or "",
        "category": block.get("role") or "",
        "knobs": len(block.get("params") or {}),
        "knob_values": block.get("params") or {},
        "route": block.get("route") or "",
    }


def _difficulty_count(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    if isinstance(data.get("levels"), list):
        return len(data["levels"])
    if isinstance(data.get("notes"), list):
        return 1
    return 0


def _event_count(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    if isinstance(data.get("notes"), list):
        return len(data["notes"])
    if isinstance(data.get("events"), list):
        return len(data["events"])
    if isinstance(data.get("levels"), list):
        return sum(_event_count(level) for level in data["levels"] if isinstance(level, dict))
    return 0


def _lyrics_count(package_dir: Path, manifest: dict[str, Any]) -> int:
    lyrics = manifest.get("lyrics")
    if not lyrics:
        return 0
    data = _read_json(package_dir / str(lyrics))
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("lyrics", "phrases", "notes", "events"):
            if isinstance(data.get(key), list):
                return len(data[key])
    return 0


def _lyrics_count_from_zip(zf: zipfile.ZipFile, manifest: dict[str, Any]) -> int:
    lyrics = manifest.get("lyrics")
    if not lyrics:
        return 0
    data = _read_json_from_zip(zf, str(lyrics))
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("lyrics", "phrases", "notes", "events"):
            if isinstance(data.get(key), list):
                return len(data[key])
    return 0


def _safe_archive_name(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def _normalize_authors(value: Any) -> list[dict[str, str]]:
    rows = []
    for item in value or []:
        if isinstance(item, str):
            name = item.strip()
            role = "charter"
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            role = str(item.get("role") or "charter").strip().lower()
        else:
            continue
        if not name:
            continue
        if role not in AUTHOR_ROLES:
            role = "contributor"
        rows.append({"name": name, "role": role})
    return rows


def _apply_metadata(manifest: dict[str, Any], metadata: dict[str, Any]) -> None:
    for key in METADATA_FIELDS:
        if key not in metadata:
            continue
        value = metadata[key]
        if value in (None, ""):
            manifest.pop(key, None)
            continue
        if key == "year":
            try:
                manifest[key] = int(value)
            except (TypeError, ValueError):
                manifest[key] = str(value)
        elif key == "duration":
            manifest[key] = float(value)
        else:
            manifest[key] = str(value)


def _apply_cover(
    package_dir: Path,
    manifest: dict[str, Any],
    *,
    cover_path: Path | None,
    remove_cover: bool,
) -> None:
    current = manifest.get("cover")
    if remove_cover:
        if current:
            (package_dir / str(current)).unlink(missing_ok=True)
        manifest.pop("cover", None)
        return
    if cover_path is None:
        return
    source = Path(cover_path)
    if not source.is_file():
        raise FileNotFoundError(f"Cover image was not found: {source}")
    suffix = source.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise ValueError("Cover image must be PNG, JPG, JPEG, or WEBP.")
    if current:
        (package_dir / str(current)).unlink(missing_ok=True)
    target = f"cover{suffix}"
    shutil.copy2(source, package_dir / target)
    manifest["cover"] = target


def _full_stem_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    for stem in manifest.get("stems") or []:
        if isinstance(stem, dict) and str(stem.get("id") or "").lower() == "full":
            return dict(stem)
    for stem in manifest.get("stems") or []:
        if isinstance(stem, dict) and stem.get("file"):
            full = dict(stem)
            full["id"] = "full"
            return full
    raise ValueError("FeedPak has no full mix stem to separate.")
