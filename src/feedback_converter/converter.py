from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .feedpak_validator import FeedpakValidationResult, require_valid_feedpak
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
B_STANDARD_6_TUNING = [-5, -5, -5, -5, -5, -5]
SEVEN_STRING_STANDARD_TUNING = [0, 0, 0, 0, 0, 0, 0]
STANDARD_6_PITCHES = [40, 45, 50, 55, 59, 64]
STANDARD_7_PITCHES = [35, 40, 45, 50, 55, 59, 64]
GENERIC_AUTHOR_NAMES = {
    "author",
    "cdlc author",
    "cdlc creator",
    "custom dlc author",
    "custom dlc creator",
    "custom song author",
    "custom song creator",
    "creator",
    "unknown",
    "unknown author",
    "unknown creator",
}


@dataclass
class ConversionWarning:
    message: str


@dataclass
class ConversionResult:
    output_path: Path
    package_dir: Path
    manifest: dict[str, Any]
    warnings: list[ConversionWarning] = field(default_factory=list)
    validation: FeedpakValidationResult | None = None


def convert_psarc_songs(
    input_psarc: Path,
    output: Path | None = None,
    *,
    archive: bool = True,
    overwrite: bool = False,
    keep_workdir: bool = False,
    include_tones: bool = True,
    b_standard_to_7_string: bool = False,
    separate_stems: bool = False,
    demucs_url: str | None = None,
    demucs_api_key: str | None = None,
    demucs_model: str | None = None,
    demucs_stems: list[str] | None = None,
    rs1_songs_psarc: Path | None = None,
) -> list[ConversionResult]:
    """Convert a PSARC, splitting multi-song containers into one FeedPak per song."""
    input_psarc = Path(input_psarc)
    if not input_psarc.is_file():
        raise FileNotFoundError(f"PSARC file not found: {input_psarc}")
    with input_psarc.open("rb") as fh:
        content = PSARC(crypto=True).parse_stream(fh)
    rs1_songs_content = _load_rs1_songs_content(input_psarc, content, rs1_songs_psarc)

    groups = _song_groups(content)
    playable_groups = _playable_song_groups(groups)
    if len(playable_groups) <= 1:
        merged_content = _content_with_rs1_audio(content, input_psarc.stem, rs1_songs_content)
        return [
            convert_psarc(
                input_psarc,
                output,
                archive=archive,
                overwrite=overwrite,
                keep_workdir=keep_workdir,
                include_tones=include_tones,
                b_standard_to_7_string=b_standard_to_7_string,
                separate_stems=separate_stems,
                demucs_url=demucs_url,
                demucs_api_key=demucs_api_key,
                demucs_model=demucs_model,
                demucs_stems=demucs_stems,
                _content=merged_content,
            )
        ]

    if output is None:
        base_dir = input_psarc.parent
    else:
        output = Path(output)
        base_dir = output.parent if output.suffix else output
    results: list[ConversionResult] = []
    reserved_outputs: set[Path] = set()
    for key, paths in sorted(playable_groups.items()):
        song_content = _content_for_song_group(content, key, paths, rs1_songs_content=rs1_songs_content)
        output = _unique_output_path(
            base_dir / f"{_safe_output_stem(_metadata_song_title(song_content) or key)}.feedpak",
            reserved_outputs,
            overwrite=overwrite,
        )
        try:
            result = convert_psarc(
                input_psarc,
                output,
                archive=archive,
                overwrite=overwrite,
                keep_workdir=keep_workdir,
                include_tones=include_tones,
                b_standard_to_7_string=b_standard_to_7_string,
                separate_stems=separate_stems,
                demucs_url=demucs_url,
                demucs_api_key=demucs_api_key,
                demucs_model=demucs_model,
                demucs_stems=demucs_stems,
                _content=song_content,
            )
        except Exception:
            _cleanup_output(output, archive=archive, keep_workdir=keep_workdir)
            raise
        results.append(result)
    return results


def _unique_output_path(path: Path, reserved: set[Path], *, overwrite: bool) -> Path:
    """Return a batch-unique output path without touching the filesystem."""
    resolved = path.resolve()
    if resolved not in reserved and (overwrite or not path.exists()):
        reserved.add(resolved)
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        resolved_candidate = candidate.resolve()
        if resolved_candidate not in reserved and (overwrite or not candidate.exists()):
            reserved.add(resolved_candidate)
            return candidate
        counter += 1


def _cleanup_output(output: Path, *, archive: bool, keep_workdir: bool) -> None:
    if keep_workdir:
        return
    target = output.with_suffix(output.suffix + ".work") if archive else output
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def convert_psarc(
    input_psarc: Path,
    output: Path | None = None,
    *,
    archive: bool | None = None,
    overwrite: bool = False,
    keep_workdir: bool = False,
    include_tones: bool = True,
    b_standard_to_7_string: bool = False,
    separate_stems: bool = False,
    demucs_url: str | None = None,
    demucs_api_key: str | None = None,
    demucs_model: str | None = None,
    demucs_stems: list[str] | None = None,
    _content: dict[str, bytes] | None = None,
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
    if _content is None:
        with input_psarc.open("rb") as fh:
            content = PSARC(crypto=True).parse_stream(fh)
    else:
        content = _content

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
            if not _is_vocal_sng(path, song):
                warnings.append(
                    ConversionWarning(f"Skipped non-playable SNG with no difficulty levels: {path}")
                )
            continue

        if first_song is None:
            first_song = song

        arr_id = _unique_id(_arrangement_id(path, metadata), used_ids)
        try:
            arrangement = _song_to_arrangement(song, path, metadata, include_tones=include_tones)
        except ValueError as exc:
            warnings.append(ConversionWarning(f"Skipped SNG {path}: {exc}"))
            continue
        if b_standard_to_7_string and _is_b_standard_six_string(arrangement.get("tuning")):
            arrangement = _b_standard_arrangement_to_seven_string(arrangement)
            warnings.append(
                ConversionWarning(
                    f"Converted B-standard six-string arrangement to seven-string standard: {arrangement['name']}"
                )
            )
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
                "event_count": _arrangement_event_count(arrangement),
                "note_count": _arrangement_note_count(arrangement),
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
            if not any(item["id"] == "vocals" for item in arrangements):
                vocals_id = _unique_id("vocals", used_ids)
                vocals_file = f"arrangements/{vocals_id}.json"
                _write_json(package_dir / vocals_file, _karaoke_arrangement(first_song))
                arrangements.append(
                    {
                        "id": vocals_id,
                        "name": "Vocals",
                        "file": vocals_file,
                        "tuning": [0, 0, 0, 0, 0, 0],
                        "capo": 0,
                        "type": "vocals",
                        "event_count": len(lyrics),
                        "note_count": len(lyrics),
                    }
                )
        else:
            lyrics_path = None
    else:
        lyrics_path = None

    stem_entries, stem_separation = _copy_audio(
        content,
        package_dir,
        warnings,
        separate_stems=separate_stems,
        demucs_url=demucs_url,
        demucs_api_key=demucs_api_key,
        demucs_model=demucs_model,
        demucs_stems=demucs_stems,
    )
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
        "stems": stem_entries,
    }
    authors = _authors_from_metadata(metadata)
    if authors:
        manifest["authors"] = authors
    if stem_separation:
        manifest["stem_separation"] = stem_separation
    if metadata.get("album"):
        manifest["album"] = str(metadata["album"])
    if metadata.get("year"):
        try:
            manifest["year"] = int(metadata["year"])
        except (TypeError, ValueError):
            warnings.append(ConversionWarning(f"Ignored non-integer year: {metadata['year']!r}"))
    if lyrics_path:
        manifest["lyrics"] = lyrics_path
        manifest["lyrics_source"] = "authored"
        manifest["language"] = "und"
        manifest["lyric_tracks"] = [
            {
                "id": "original",
                "file": lyrics_path,
                "language": "und",
                "kind": "original",
                "lyrics_source": "authored",
                **({"stem": "vocals"} if any(str(stem.get("id")) == "vocals" for stem in stem_entries) else {}),
                "name": "Original",
            }
        ]
        vocal_pitch = _maybe_write_vocal_pitch(
            package_dir,
            lyrics,
            stem_entries,
            demucs_url=demucs_url,
            demucs_api_key=demucs_api_key,
            warnings=warnings,
        )
        if vocal_pitch:
            manifest["vocal_pitch"] = vocal_pitch
            manifest["pitch_extraction"] = {"engine": "crepe", "model": "v1", "version": "1.0.0"}
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

    try:
        validation = require_valid_feedpak(package_dir)
    except Exception:
        if not keep_workdir:
            shutil.rmtree(package_dir, ignore_errors=True)
        raise
    for warning in validation.warnings:
        warnings.append(ConversionWarning(f"FeedPak spec validation warning: {warning}"))

    final_output = package_dir
    if archive:
        _zip_dir(package_dir, output)
        final_output = output
        if not keep_workdir:
            shutil.rmtree(package_dir)

    return ConversionResult(final_output, package_dir, manifest, warnings, validation)


def _find_sng_entries(content: dict[str, bytes]) -> list[tuple[str, bytes]]:
    entries = [
        (path, data)
        for path, data in content.items()
        if path.lower().endswith(".sng") and "/bin/" in path.replace("\\", "/").lower()
    ]
    return sorted(entries, key=lambda item: item[0].lower())


ARRANGEMENT_SUFFIX_RE = re.compile(
    r"_(?:lead|lead\d+|rhythm|rhythm\d+|combo|combo\d+|bass|bass\d+|vocals?|showlights)$",
    re.IGNORECASE,
)


def _song_groups(content: dict[str, bytes]) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for path, data in content.items():
        key = ""
        if path.lower().endswith((".json", ".hsan")):
            key = _song_key_from_manifest(data) or _song_group_key_from_path(path)
        elif path.lower().endswith(".sng"):
            key = _song_group_key_from_path(path)
        if key:
            groups.setdefault(key.lower(), set()).add(path)
    return {key: paths for key, paths in groups.items() if any(path.lower().endswith(".sng") for path in paths)}


def _playable_song_groups(groups: dict[str, set[str]]) -> dict[str, set[str]]:
    """Return groups that contain playable arrangements, not vocal-only sidecars."""
    return {
        key: paths
        for key, paths in groups.items()
        if any(_is_playable_sng_path(path) for path in paths)
    }


def _song_key_from_manifest(data: bytes) -> str:
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001
        return ""
    for item in _walk_dicts(obj):
        value = item.get("SongKey") or item.get("DLCKey")
        if value not in (None, ""):
            return _slug(str(value))
    return ""


def _song_group_key_from_path(path: str) -> str:
    stem = Path(path.replace("\\", "/")).stem
    return _slug(ARRANGEMENT_SUFFIX_RE.sub("", stem))


def _is_playable_sng_path(path: str) -> bool:
    stem = Path(path.replace("\\", "/")).stem.lower()
    return bool(re.search(r"_(?:lead\d*|rhythm\d*|combo\d*|bass\d*)$", stem))


def _content_for_song_group(
    content: dict[str, bytes],
    key: str,
    paths: set[str],
    *,
    rs1_songs_content: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    key = key.lower()
    selected = {path: content[path] for path in paths if path in content}

    for path, data in content.items():
        low = path.replace("\\", "/").lower()
        stem_key = _song_group_key_from_path(path)
        if low.endswith((".json", ".hsan", ".sng", ".xml", ".dds")) and (
            stem_key == key or _is_vocal_sidecar_for_key(stem_key, key)
        ):
            selected[path] = data
        elif f"album_{key}_" in low or f"album_{key}." in low:
            selected[path] = data

    bnk_paths = [
        path for path in content
        if path.replace("\\", "/").lower().endswith(".bnk")
        and Path(path.replace("\\", "/")).stem.lower() in {f"song_{key}", f"{key}"}
    ]
    wem_paths = _wem_paths_for_banks(content, bnk_paths)
    for path in wem_paths:
        selected[path] = content[path]
    external_wem_paths: set[str] = set()
    if rs1_songs_content:
        external_bnk_paths = _bank_paths_for_song_key(rs1_songs_content, key)
        external_wem_paths = _wem_paths_for_banks(rs1_songs_content, external_bnk_paths)
        for path in external_bnk_paths:
            selected[path] = rs1_songs_content[path]
        for path in external_wem_paths:
            selected[path] = rs1_songs_content[path]
    if (bnk_paths or rs1_songs_content) and not wem_paths and not external_wem_paths:
        # A grouped multi-song PSARC with an unresolvable bank is safer to fail
        # later with "No audio file found" than to borrow another song's WEM.
        selected = {path: data for path, data in selected.items() if not path.lower().endswith((".wem", ".ogg", ".wav", ".mp3", ".flac", ".opus"))}
    return selected


def _load_rs1_songs_content(
    input_psarc: Path,
    content: dict[str, bytes],
    rs1_songs_psarc: Path | None,
) -> dict[str, bytes] | None:
    source = Path(rs1_songs_psarc) if rs1_songs_psarc else _default_rs1_songs_psarc(input_psarc, content)
    if source is None:
        return None
    if not source.is_file():
        raise FileNotFoundError(f"RS1 songs.psarc file not found: {source}")
    with source.open("rb") as fh:
        return PSARC(crypto=True).parse_stream(fh)


def _default_rs1_songs_psarc(input_psarc: Path, content: dict[str, bytes]) -> Path | None:
    if "rs1compatibility" not in input_psarc.name.lower():
        return None
    if any(path.lower().endswith(".wem") for path in content):
        return None
    candidate = input_psarc.parent.parent / "songs.psarc"
    return candidate if candidate.is_file() else None


def _content_with_rs1_audio(
    content: dict[str, bytes],
    key: str,
    rs1_songs_content: dict[str, bytes] | None,
) -> dict[str, bytes]:
    if not rs1_songs_content:
        return content
    selected = dict(content)
    bnk_paths = _bank_paths_for_song_key(rs1_songs_content, _slug(key))
    for bnk_path in bnk_paths:
        selected[bnk_path] = rs1_songs_content[bnk_path]
    for wem_path in _wem_paths_for_banks(rs1_songs_content, bnk_paths):
        selected[wem_path] = rs1_songs_content[wem_path]
    return selected


def _bank_paths_for_song_key(content: dict[str, bytes], key: str) -> list[str]:
    wanted = {f"song_{key}", key}
    return [
        path
        for path in content
        if path.replace("\\", "/").lower().endswith(".bnk")
        and Path(path.replace("\\", "/")).stem.lower() in wanted
        and not Path(path.replace("\\", "/")).stem.lower().endswith("_preview")
    ]


def _is_vocal_sidecar_for_key(stem_key: str, key: str) -> bool:
    return stem_key in {
        f"{key}_vocals",
        f"{key}_vocal",
        f"{key}_jvocals",
        f"{key}_jvocal",
        f"{key}_lyrics",
    }


def _wem_paths_for_banks(content: dict[str, bytes], bnk_paths: list[str]) -> set[str]:
    wem_by_id = {
        int(Path(path).stem): path
        for path in content
        if path.lower().endswith(".wem") and Path(path).stem.isdigit()
    }
    found: set[str] = set()
    for bnk_path in bnk_paths:
        data = content.get(bnk_path, b"")
        for offset in range(0, max(0, len(data) - 3)):
            value = struct.unpack_from("<I", data, offset)[0]
            if value in wem_by_id:
                found.add(wem_by_id[value])
    return found


def _metadata_song_title(content: dict[str, bytes]) -> str:
    meta = _extract_metadata(content)
    artist = str(meta.get("artist") or "").strip()
    title = str(meta.get("title") or "").strip()
    return f"{artist} - {title}".strip(" -") if artist or title else ""


def _safe_output_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", normalized).strip(" ._")
    return safe[:120] or "converted"


def _is_vocal_sng(path: str, song: Any) -> bool:
    return "vocal" in path.replace("\\", "/").lower() or bool(getattr(song, "vocals", None))


def _extract_metadata(content: dict[str, bytes]) -> dict[str, Any]:
    objects: list[Any] = []
    text_entries: list[tuple[str, str]] = []
    for path, data in content.items():
        low = path.lower()
        if low.endswith((".json", ".hsan")):
            try:
                text = data.decode("utf-8-sig")
                objects.append(json.loads(text))
            except Exception:  # noqa: BLE001
                continue
        elif low.endswith((".version", ".txt", ".ini", ".xml")):
            try:
                text_entries.append((path, data.decode("utf-8-sig")))
            except Exception:  # noqa: BLE001
                continue

    flat = list(_walk_dicts(objects))
    title = _first_key(flat, "SongName", "Title", "Name", "SongTitle")
    artist = _first_key(flat, "ArtistName", "Artist", "SongArtist")
    authors = _dedupe_authors([*_metadata_authors(flat), *_metadata_text_authors(text_entries)])
    if not authors:
        authors = _metadata_key_suffix_authors(flat, title=title, artist=artist)
    return {
        "title": title,
        "artist": artist,
        "album": _first_key(flat, "AlbumName", "Album"),
        "year": _first_key(flat, "SongYear", "Year"),
        "duration": _first_key(flat, "SongLength", "Duration", "SongLengthSeconds"),
        "authors": authors,
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


def _metadata_authors(dicts: list[dict[str, Any]]) -> list[dict[str, str]]:
    authors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for item in dicts:
        for key, value in item.items():
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                continue
            role = _author_role_from_key(key)
            if role is None:
                continue
            name = _clean_author_name(str(value))
            if not name:
                continue
            identity = (name.lower(), role)
            if identity in seen:
                continue
            seen.add(identity)
            authors.append({"name": name, "role": role})

        for key in ("Authors", "Author", "Creators", "Contributors"):
            value = item.get(key)
            if isinstance(value, list):
                for entry in value:
                    author = _normalize_author_entry(entry)
                    if not author:
                        continue
                    identity = (author["name"].lower(), author.get("role", ""))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    authors.append(author)
            elif isinstance(value, dict):
                author = _normalize_author_entry(value)
                if author:
                    identity = (author["name"].lower(), author.get("role", ""))
                    if identity not in seen:
                        seen.add(identity)
                        authors.append(author)

    return authors


def _metadata_text_authors(entries: list[tuple[str, str]]) -> list[dict[str, str]]:
    authors: list[dict[str, str]] = []
    for path, text in entries:
        lower_path = path.lower()
        if lower_path.endswith("toolkit.version"):
            for raw_line in text.splitlines():
                match = re.search(
                    r"(?i)package\s+author\s*:\s*(.*?)(?=[ \t]*package\s+(?:version|comment)\s*:|[ \t]*$)",
                    raw_line,
                )
                if not match:
                    continue
                name = _clean_author_name(match.group(1))
                if name:
                    authors.append({"name": name, "role": "charter"})
            continue
        for raw_line in text.splitlines():
            line = re.sub(r"^\s*<!--\s*|\s*-->\s*$", "", raw_line).strip()
            if not line:
                continue
            match = re.match(
                r"(?i)^(?:charted|chart|authored|created|made|converted|arranged|transcribed)\s+by\s*[:\-]?\s*(.+?)\s*$",
                line,
            ) or re.match(
                r"(?i)^(?:charter|chart\s+author|author|creator|arranger|transcriber)\s*[:\-]\s*(.+?)\s*$",
                line,
            )
            if not match:
                continue
            role = "charter"
            label = line.split(":", 1)[0].split("-", 1)[0].lower()
            if "arrang" in label:
                role = "arranger"
            elif "transcrib" in label:
                role = "transcriber"
            name = _clean_author_name(match.group(1))
            if name:
                authors.append({"name": name, "role": role})
    return _dedupe_authors(authors)


def _metadata_key_suffix_authors(dicts: list[dict[str, Any]], *, title: Any, artist: Any) -> list[dict[str, str]]:
    title_part = _compact_credit_part(title)
    artist_part = _compact_credit_part(artist)
    if not title_part or not artist_part:
        return []

    candidates: list[dict[str, str]] = []
    for item in dicts:
        for key in ("DLCKey", "SongKey", "FullName"):
            value = item.get(key)
            if not isinstance(value, str):
                continue
            name = _author_from_song_key(value, artist_part=artist_part, title_part=title_part)
            if name:
                candidates.append({"name": name, "role": "charter"})
    return _dedupe_authors(candidates)


def _author_from_song_key(value: str, *, artist_part: str, title_part: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = re.sub(r"(?i)_(lead|lead\d+|rhythm|rhythm\d+|bass|bass\d+|vocals?)$", "", raw)
    compact = _compact_credit_part(raw)
    prefix = f"{artist_part}{title_part}"
    if not compact.lower().startswith(prefix.lower()):
        return None
    suffix_start = len(prefix)
    suffix = compact[suffix_start:]
    author = _clean_author_name(_prettify_compact_author(suffix))
    if not author or len(_compact_credit_part(author)) < 3:
        return None
    return author


def _compact_credit_part(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or ""))


def _prettify_compact_author(value: str) -> str:
    text = str(value or "").strip("_- ")
    if not text:
        return ""
    text = re.sub(r"(?i)(?:remastered|ddc|rs2014|v\d+|r\d+|p)$", "", text).strip("_- ")
    return text


def _clean_author_name(value: str) -> str | None:
    name = str(value or "").strip().strip("\"'")
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"(?i)\s*\((?:remastered|arrangement id|ddc)\s+by\s+[^)]*\)\s*", " ", name).strip()
    if not name:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    if not normalized:
        return None
    if normalized in GENERIC_AUTHOR_NAMES:
        return None
    return name


def _dedupe_authors(authors: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for author in authors:
        normalized = _normalize_author_entry(author)
        if not normalized:
            continue
        identity = (normalized["name"].lower(), normalized.get("role", ""))
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(normalized)
    return deduped


def _author_role_from_key(key: str) -> str | None:
    normalized = key.lower().replace("_", "").replace("-", "").replace(" ", "")
    if normalized in {
        "charter",
        "chartauthor",
        "songauthor",
        "dlcauthor",
        "author",
        "packageauthor",
        "customsongauthor",
        "customdlcauthor",
        "cdlcauthor",
        "manifestauthor",
        "arrangementauthor",
        "tabauthor",
    }:
        return "charter"
    if normalized in {
        "creator",
        "createdby",
        "packagecreator",
        "customsongcreator",
        "customdlccreator",
        "cdlccreator",
        "toolkitcreator",
    }:
        return "creator"
    if normalized in {"arranger", "transcriber", "editor", "mixer", "engineer", "proofreader"}:
        return normalized
    return None


def _normalize_author_entry(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        name = _clean_author_name(value)
        return {"name": name, "role": "charter"} if name else None
    if not isinstance(value, dict):
        return None
    name = _first_key([value], "name", "Name", "displayName", "DisplayName", "username", "Username")
    if name in (None, ""):
        return None
    role = _first_key([value], "role", "Role", "type", "Type") or "charter"
    cleaned_name = _clean_author_name(str(name))
    if not cleaned_name:
        return None
    author = {"name": cleaned_name, "role": str(role).strip() or "charter"}
    email = _first_key([value], "email", "Email")
    url = _first_key([value], "url", "Url", "URL", "website", "Website")
    if email:
        author["email"] = str(email).strip()
    if url:
        author["url"] = str(url).strip()
    return author if author["name"] else None


def _authors_from_metadata(metadata: dict[str, Any]) -> list[dict[str, str]]:
    authors = metadata.get("authors")
    if not isinstance(authors, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in authors:
        author = _normalize_author_entry(item)
        if author:
            cleaned.append(author)
    return cleaned


def _arrangement_names(dicts: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for item in dicts:
        path = item.get("SongXml") or item.get("PersistentID") or item.get("MasterID_RDV")
        name = _arrangement_label_from_manifest(item)
        if path and name:
            for key in _arrangement_match_keys(path):
                names[key] = name
    return names


def _arrangement_label_from_manifest(item: dict[str, Any]) -> str:
    props = item.get("ArrangementProperties")
    if isinstance(props, dict):
        if _truthy_manifest_flag(props.get("pathBass")):
            return "Bass"
        if _truthy_manifest_flag(props.get("pathLead")):
            return "Lead"
        if _truthy_manifest_flag(props.get("pathRhythm")):
            return "Rhythm"
    name = item.get("ArrangementName") or item.get("ArrangementType")
    return str(name) if name not in (None, "") else ""


def _truthy_manifest_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes"}


def _arrangement_match_keys(value: Any) -> set[str]:
    text = str(value).strip().lower()
    if not text:
        return set()
    normalized = text.replace("\\", "/")
    keys = {normalized}
    stem = Path(normalized).stem.lower()
    if stem:
        keys.add(stem)
    if ":" in normalized:
        tail = normalized.rsplit(":", 1)[-1].strip()
        if tail:
            keys.add(tail)
            keys.add(Path(tail.replace("\\", "/")).stem.lower())
    return {key for key in keys if key}


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


def _song_to_arrangement(
    song: Any,
    source_path: str,
    metadata: dict[str, Any],
    *,
    include_tones: bool = True,
) -> dict[str, Any]:
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
        "sections": _sections_to_feedpak(song),
    }
    arrangement["stats"] = {
        "events": _arrangement_event_count(arrangement),
        "notes": _arrangement_note_count(arrangement),
    }
    if include_tones:
        tones = _song_tones_to_feedpak(song, source_path, metadata)
        if tones:
            arrangement["tones"] = tones["tones"]
            arrangement["_rigs"] = tones["rigs"]
    return arrangement


def _arrangement_event_count(arrangement: dict[str, Any]) -> int:
    return len(arrangement.get("notes") or []) + len(arrangement.get("chords") or [])


def _arrangement_note_count(arrangement: dict[str, Any]) -> int:
    total = len(arrangement.get("notes") or [])
    for chord in arrangement.get("chords") or []:
        if isinstance(chord, dict) and isinstance(chord.get("notes"), list):
            total += len(chord["notes"])
        else:
            total += 1
    return total


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

    phrases = _phrase_ladder_to_feedpak(song, level_payloads)
    flat = _flat_chart_payload(level_payloads, phrases)
    return {
        "notes": flat["notes"],
        "chords": flat["chords"],
        "anchors": flat["anchors"],
        "handshapes": flat["handshapes"],
        "phrases": phrases,
    }


def _flat_chart_payload(
    level_payloads: dict[int, dict[str, Any]],
    phrases: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    if not level_payloads:
        return {"notes": [], "chords": [], "anchors": [], "handshapes": []}
    if len(level_payloads) == 1 or not phrases:
        return max(
            level_payloads.values(),
            key=lambda payload: len(payload["notes"]) + len(payload["chords"]),
        )

    flat = {"notes": [], "chords": [], "anchors": [], "handshapes": []}
    for phrase in phrases:
        levels = sorted(
            [level for level in phrase.get("levels", []) if isinstance(level, dict)],
            key=lambda level: int(level.get("difficulty", 0)),
        )
        if not levels:
            continue
        max_difficulty = int(phrase.get("max_difficulty", levels[-1].get("difficulty", 0)))
        eligible = [level for level in levels if int(level.get("difficulty", 0)) <= max_difficulty]
        level = eligible[-1] if eligible else levels[-1]
        flat["notes"].extend(level.get("notes") or [])
        flat["chords"].extend(level.get("chords") or [])
        flat["anchors"].extend(level.get("anchors") or [])
        flat["handshapes"].extend(level.get("handshapes") or [])

    if not flat["notes"] and not flat["chords"]:
        return max(
            level_payloads.values(),
            key=lambda payload: len(payload["notes"]) + len(payload["chords"]),
        )
    return flat


def _song_tones_to_feedpak(song: Any, source_path: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    tone_events = sorted(
        [tone for tone in getattr(song, "tones", []) if _finite_number(getattr(tone, "time", None))],
        key=lambda tone: float(tone.time),
    )
    tone_info = _tone_info_for_arrangement(source_path, metadata)
    definitions = _unique_tone_definitions(list(tone_info.get("definitions") or [])) if tone_info else []
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
    source_stem = Path(source_path.replace("\\", "/")).stem.lower()
    arrangement_id = _arrangement_id(source_path, metadata)
    for entry in metadata.get("arrangement_tones", []):
        keys = entry.get("match_keys") or []
        if any(_tone_match_key_matches_source(str(key), source, source_stem, arrangement_id) for key in keys):
            return entry
    for entry in metadata.get("arrangement_tones", []):
        keys = entry.get("match_keys") or []
        if arrangement_id and any(_tone_match_key_matches_arrangement_id(str(key), arrangement_id) for key in keys):
            return entry
    arrangement_tones = metadata.get("arrangement_tones", [])
    return arrangement_tones[0] if len(arrangement_tones) == 1 else {}


def _tone_match_key_matches_source(key: str, source: str, source_stem: str, arrangement_id: str) -> bool:
    key = (key or "").strip().lower()
    if not key:
        return False
    key_stem = key.rsplit(":", 1)[-1].replace("\\", "/").rsplit("/", 1)[-1]
    if key_stem == source_stem:
        return True
    if key_stem and source_stem.endswith(f"_{key_stem}"):
        return True
    if key_stem and source_stem.endswith(f"-{key_stem}"):
        return True
    key_slug = _slug(key_stem)
    if arrangement_id and key_slug == arrangement_id:
        tokens = set(re.split(r"[-_\\/.]+", source_stem))
        return arrangement_id in tokens
    if key.isdigit():
        return False
    return len(key) >= 4 and key in source


def _tone_match_key_matches_arrangement_id(key: str, arrangement_id: str) -> bool:
    key = (key or "").strip().lower()
    if not key or not arrangement_id:
        return False
    key_slug = _slug(key.rsplit(":", 1)[-1].replace("\\", "/").rsplit("/", 1)[-1])
    return key_slug == arrangement_id or key_slug.endswith(f"-{arrangement_id}") or key_slug.endswith(f"_{arrangement_id}")


def _tone_definition_name(definition: dict[str, Any]) -> str:
    value = definition.get("Name") or definition.get("ToneName") or definition.get("name")
    return str(value).strip() if value not in (None, "") else ""


def _unique_tone_definitions(definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, dict):
            continue
        key = str(
            definition.get("Key")
            or definition.get("ToneKey")
            or definition.get("Name")
            or definition.get("ToneName")
            or ""
        ).strip().lower()
        if not key:
            key = json.dumps(_json_safe(definition), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        unique.append(definition)
    return unique


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
    if isinstance(knobs, dict):
        normalized["KnobValues"] = {
            str(name): value
            for name, value in knobs.items()
            if str(name).strip()
        }
    else:
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
        "PostPedal1",
        "PostPedal2",
        "PostPedal3",
        "PostPedal4",
        "Rack1",
        "Rack2",
        "Rack3",
        "Rack4",
        "Cabinet",
    ):
        pedal = gear.get(slot)
        if not isinstance(pedal, dict):
            continue
        block = _pedal_to_rig_block(slot, pedal)
        if block:
            blocks.append(block)
    return blocks


def _pedal_to_rig_block(slot: str, pedal: dict[str, Any]) -> dict[str, Any] | None:
    pedal_type = (
        pedal.get("Key")
        or pedal.get("PedalKey")
        or pedal.get("GearKey")
        or pedal.get("EffectKey")
        or pedal.get("Type")
        or pedal.get("Category")
    )
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
    pedal_type = str(
        pedal.get("Key")
        or pedal.get("PedalKey")
        or pedal.get("GearKey")
        or pedal.get("EffectKey")
        or pedal.get("Type")
        or ""
    ).lower()
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
    bend_curve = _bend_curve(float(note.time), note.bends)
    if bend_curve:
        out["bnv"] = bend_curve
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
            bend_source = chord_note.bends[string]
            bend_values = list(bend_source.bendValues[: int(bend_source.count)])
            bend = _bend_value_from_points(bend_values)
            if bend:
                entry["bn"] = bend
            bend_curve = _bend_curve(float(note.time), bend_values)
            if bend_curve:
                entry["bnv"] = bend_curve
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


def _bend_value_from_points(bends: Any) -> float | None:
    values = [float(b.step) for b in bends if float(b.step) != 0.0]
    if values:
        return _num(max(values, key=abs))
    return None


def _bend_curve(note_time: float, bends: Any) -> list[dict[str, float]] | None:
    points = []
    last: tuple[float, float] | None = None
    for bend in bends:
        step = float(bend.step)
        time_value = float(bend.time)
        relative_time = time_value - note_time
        if relative_time < -0.001:
            relative_time = time_value
        relative_time = max(0.0, relative_time)
        point = (_num(relative_time), _num(step))
        if last == point:
            continue
        points.append({"t": point[0], "v": point[1]})
        last = point
    if len(points) < 2:
        return None
    if not any(abs(float(point["v"])) > 0 for point in points):
        return None
    return points


def _template_to_feedpak(template: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": template.name or "",
        "frets": [int(x) for x in template.frets],
        "fingers": [int(x) for x in template.fingers],
    }
    return out


def _is_b_standard_six_string(tuning: Any) -> bool:
    return [int(value) for value in tuning or []] == B_STANDARD_6_TUNING


def _b_standard_arrangement_to_seven_string(arrangement: dict[str, Any]) -> dict[str, Any]:
    converted = json.loads(json.dumps(arrangement))
    converted["tuning"] = list(SEVEN_STRING_STANDARD_TUNING)
    converted["name"] = f"{converted.get('name') or 'Arrangement'} 7-string"
    converted["notes"] = [_convert_note_to_seven_string(note) for note in converted.get("notes", [])]
    converted["chords"] = [_convert_chord_to_seven_string(chord) for chord in converted.get("chords", [])]
    converted["templates"] = [_convert_template_to_seven_string(template) for template in converted.get("templates", [])]
    converted["stats"] = {
        "events": _arrangement_event_count(converted),
        "notes": _arrangement_note_count(converted),
    }
    for phrase in converted.get("phrases", []):
        for level in phrase.get("levels", []):
            level["notes"] = [_convert_note_to_seven_string(note) for note in level.get("notes", [])]
            level["chords"] = [_convert_chord_to_seven_string(chord) for chord in level.get("chords", [])]
    return converted


def _convert_note_to_seven_string(note: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(note, dict) or "s" not in note or "f" not in note:
        return note
    mapped = dict(note)
    target = _map_pitch_to_seven_string(int(note["s"]), int(note["f"]))
    if target is None:
        return mapped
    new_string, new_fret = target
    mapped["s"] = new_string
    mapped["f"] = new_fret
    for key in ("sl", "slu"):
        if key in mapped:
            mapped[key] = _map_target_fret_to_string(int(note["s"]), int(mapped[key]), new_string)
    return mapped


def _convert_chord_to_seven_string(chord: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(chord, dict):
        return chord
    mapped = dict(chord)
    used: set[int] = set()
    notes = []
    for note in chord.get("notes", []):
        if not isinstance(note, dict) or "s" not in note or "f" not in note:
            notes.append(note)
            continue
        mapped_note = dict(note)
        target = _map_pitch_to_seven_string(int(note["s"]), int(note["f"]), used)
        if target is not None:
            new_string, new_fret = target
            used.add(new_string)
            mapped_note["s"] = new_string
            mapped_note["f"] = new_fret
            for key in ("sl", "slu"):
                if key in mapped_note:
                    mapped_note[key] = _map_target_fret_to_string(int(note["s"]), int(mapped_note[key]), new_string)
        notes.append(mapped_note)
    if notes:
        mapped["notes"] = sorted(notes, key=lambda item: int(item.get("s", 0)) if isinstance(item, dict) else 0)
    return mapped


def _convert_template_to_seven_string(template: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(template, dict):
        return template
    mapped = dict(template)
    old_frets = [int(value) for value in template.get("frets", [])]
    old_fingers = [int(value) for value in template.get("fingers", [])]
    new_frets = [-1] * 7
    new_fingers = [-1] * 7
    used: set[int] = set()
    for old_string, fret in enumerate(old_frets[:6]):
        if fret < 0:
            continue
        target = _map_pitch_to_seven_string(old_string, fret, used)
        if target is None:
            continue
        new_string, new_fret = target
        used.add(new_string)
        new_frets[new_string] = new_fret
        if old_string < len(old_fingers):
            new_fingers[new_string] = int(old_fingers[old_string])
    mapped["frets"] = new_frets
    mapped["fingers"] = new_fingers
    return mapped


def _map_pitch_to_seven_string(
    old_string: int,
    fret: int,
    used_strings: set[int] | None = None,
) -> tuple[int, int] | None:
    if not 0 <= old_string < 6:
        return None
    source_pitch = STANDARD_6_PITCHES[old_string] + B_STANDARD_6_TUNING[old_string] + fret
    candidates: list[tuple[int, int, int, int, int]] = []
    for new_string, base_pitch in enumerate(STANDARD_7_PITCHES):
        new_fret = source_pitch - base_pitch
        if new_fret < 0 or new_fret > 24:
            continue
        collision = 1 if used_strings and new_string in used_strings else 0
        preferred_string = _preferred_seven_string(old_string)
        candidates.append((collision, abs(new_string - preferred_string), abs(new_fret - fret), new_string, new_fret))
    if not candidates:
        return None
    if used_strings and all(candidate[0] for candidate in candidates):
        return None
    _collision, _distance, _fret_delta, new_string, new_fret = min(candidates)
    return new_string, new_fret


def _map_target_fret_to_string(old_string: int, target_fret: int, new_string: int) -> int:
    if not (0 <= old_string < 6 and 0 <= new_string < 7):
        return target_fret
    target_pitch = STANDARD_6_PITCHES[old_string] + B_STANDARD_6_TUNING[old_string] + target_fret
    mapped = target_pitch - STANDARD_7_PITCHES[new_string]
    return mapped if mapped >= 0 else target_fret


def _preferred_seven_string(old_string: int) -> int:
    return old_string if old_string <= 3 else old_string + 1


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
        "sections": _sections_to_feedpak(song),
    }


def _beat_to_feedpak(beat: Any) -> dict[str, Any]:
    measure = int(beat.measure)
    return {"time": _num(beat.time), "measure": measure if measure > 0 else -1}


def _section_to_feedpak(section: Any) -> dict[str, Any]:
    out = {"name": section.name or "section", "time": _num(section.startTime)}
    if int(section.number) > 0:
        out["number"] = int(section.number)
    return out


def _sections_to_feedpak(song: Any) -> list[dict[str, Any]]:
    sections = [_section_to_feedpak(section) for section in getattr(song, "sections", [])]
    if sections:
        return sections
    return _sections_from_phrases(song)


def _sections_from_phrases(song: Any) -> list[dict[str, Any]]:
    phrases = list(getattr(song, "phrases", []) or [])
    iterations = list(getattr(song, "phraseIterations", []) or [])
    if not phrases or not iterations:
        return []
    generated: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for iteration in iterations:
        phrase_id = int(getattr(iteration, "phraseId", -1))
        if phrase_id < 0 or phrase_id >= len(phrases):
            continue
        name = str(getattr(phrases[phrase_id], "name", "") or "").strip() or "phrase"
        counters[name] = counters.get(name, 0) + 1
        generated.append({"name": name, "time": _num(iteration.time), "number": counters[name]})
    return generated


def _song_to_lyrics(song: Any) -> list[dict[str, Any]]:
    lyrics = []
    for vocal in song.vocals:
        text = (vocal.lyrics or "").strip()
        if not text:
            continue
        lyrics.append({"t": _num(vocal.time), "d": _num(vocal.length), "w": text})
    return lyrics


def _karaoke_arrangement(song: Any) -> dict[str, Any]:
    return {
        "name": "Vocals",
        "tuning": [0, 0, 0, 0, 0, 0],
        "capo": 0,
        "notes": [],
        "chords": [],
        "anchors": [],
        "handshapes": [],
        "templates": [],
        "beats": [_beat_to_feedpak(b) for b in getattr(song, "beats", [])],
        "sections": _sections_to_feedpak(song),
    }


def _duration_from_song(song: Any | None) -> float | None:
    if song is None:
        return None
    try:
        return float(song.metadata.songLength)
    except Exception:  # noqa: BLE001
        return None


def _copy_audio(
    content: dict[str, bytes],
    package_dir: Path,
    warnings: list[ConversionWarning],
    *,
    separate_stems: bool = False,
    demucs_url: str | None = None,
    demucs_api_key: str | None = None,
    demucs_model: str | None = None,
    demucs_stems: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    audio = [
        (path, data)
        for path, data in content.items()
        if path.lower().endswith((".wem", ".ogg", ".wav", ".mp3", ".flac", ".opus"))
    ]
    if not audio:
        raise ValueError(
            "No audio file found in PSARC. This appears to be a charts-only package, such as an RS1 "
            "compatibility DLC archive. FeedForge will not write a silent placeholder FeedPak because "
            "FeedBack needs a real full mix audio stem for playback."
        )

    path, data = _select_primary_audio(audio)
    ext = Path(path).suffix.lower() or ".bin"
    if ext == ".wem":
        converted = _convert_wem_bytes_to_ogg(data, package_dir / "stems" / "full.ogg")
        if converted:
            full_entry = {
                "id": "full",
                "file": "stems/full.ogg",
                "codec": "vorbis",
                "default": True,
            }
            return _maybe_separate_stems(
                package_dir,
                full_entry,
                warnings,
                separate_stems=separate_stems,
                demucs_url=demucs_url,
                demucs_api_key=demucs_api_key,
                demucs_model=demucs_model,
                demucs_stems=demucs_stems,
            )
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
    full_entry = {"id": "full", "file": f"stems/{target_name}", "codec": codec, "default": True}
    return _maybe_separate_stems(
        package_dir,
        full_entry,
        warnings,
        separate_stems=separate_stems,
        demucs_url=demucs_url,
        demucs_api_key=demucs_api_key,
        demucs_model=demucs_model,
        demucs_stems=demucs_stems,
    )


def _maybe_separate_stems(
    package_dir: Path,
    full_entry: dict[str, Any],
    warnings: list[ConversionWarning],
    *,
    separate_stems: bool,
    demucs_url: str | None,
    demucs_api_key: str | None,
    demucs_model: str | None,
    demucs_stems: list[str] | None,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    if not separate_stems:
        return ([full_entry], None)

    source = package_dir / str(full_entry["file"])
    resolved_url = _resolve_demucs_url(demucs_url)
    if not resolved_url:
        warnings.append(
            ConversionWarning(
                "Stem separation was requested but no Demucs server URL is configured; wrote full mix only."
            )
        )
        return ([full_entry], None)
    if not source.is_file() or source.stat().st_size == 0:
        warnings.append(ConversionWarning("Stem separation skipped because the converted full mix is empty."))
        return ([full_entry], None)

    requested = _normalize_demucs_stems(demucs_stems)
    try:
        stems = _run_demucs_server(
            source,
            package_dir / "stems",
            server_url=resolved_url,
            api_key=demucs_api_key,
            model=demucs_model,
            requested_stems=requested,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(ConversionWarning(f"Stem separation failed; wrote full mix only: {exc}"))
        return ([full_entry], None)

    if not stems:
        warnings.append(ConversionWarning("Stem separation returned no usable stems; wrote full mix only."))
        return ([full_entry], None)
    missing = [stem for stem in requested if stem not in {stem_id for stem_id, _ in stems}]
    if missing:
        warnings.append(
            ConversionWarning(
                f"Stem separation did not return requested stem(s): {', '.join(missing)}. "
                "This can happen when the selected model does not support those sources."
            )
        )

    returned_ids = {stem_id for stem_id, _ in stems}
    complete_split = _has_complete_stem_mix(returned_ids)
    full_mix = dict(full_entry)
    full_mix["default"] = not complete_split
    stem_entries: list[dict[str, Any]] = [full_mix]
    for stem_id, rel_file in stems:
        stem_entries.append(
            {
                "id": stem_id,
                "file": rel_file,
                "codec": _codec_for_audio_path(rel_file),
                "default": complete_split,
            }
        )
    stem_entries.sort(key=lambda item: _stem_sort_key(str(item["id"])))
    return (
        stem_entries,
        {"engine": "demucs", "model": _normalize_demucs_model(demucs_model) or "server", "version": "1.0.0"},
    )


def _resolve_demucs_url(demucs_url: str | None) -> str:
    url = (
        demucs_url
        or os.environ.get("FEEDFORGE_DEMUCS_URL")
        or os.environ.get("DEMUCS_SERVER_URL")
        or _feedback_demucs_url()
        or ""
    ).strip()
    return url.rstrip("/")


def _feedback_demucs_url() -> str | None:
    for config_dir in _feedback_config_dirs():
        for path, key in (
            (config_dir / "studio_demucs.json", "url"),
            (config_dir / "config.json", "demucs_server_url"),
        ):
            value = _json_string_value(path, key)
            if value:
                return value
    return None


def _feedback_config_dirs() -> list[Path]:
    dirs = [Path(os.environ.get("CONFIG_DIR", str(Path.home() / ".local" / "share" / "feedback")))]
    appdata = os.environ.get("APPDATA")
    if appdata:
        root = Path(appdata)
        dirs.extend(
            [
                root / "feedback-desktop" / "slopsmith-config",
                root / "slopsmith-desktop" / "slopsmith-config",
                root / "FeedBack" / "slopsmith-config",
                root / "feedback" / "slopsmith-config",
            ]
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for path in dirs:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _json_string_value(path: Path, key: str) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    value = data.get(key) if isinstance(data, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _feedback_demucs_api_key() -> str | None:
    for config_dir in _feedback_config_dirs():
        value = _json_string_value(config_dir / "studio_demucs.json", "api_key")
        if value:
            return value
    return None


def _normalize_demucs_stems(stems: list[str] | None) -> list[str]:
    allowed = {"guitar", "bass", "drums", "vocals", "piano", "other"}
    requested = []
    for stem in stems or ["guitar", "bass", "drums", "vocals", "other"]:
        value = str(stem).strip().lower()
        if value in allowed and value not in requested:
            requested.append(value)
    return requested or ["guitar", "bass", "drums", "vocals", "other"]


def _has_complete_stem_mix(stem_ids: set[str]) -> bool:
    ids = {str(stem_id).strip().lower() for stem_id in stem_ids}
    if {"guitar", "bass", "drums", "vocals", "other"}.issubset(ids):
        return True
    return {"guitar", "bass", "drums", "vocals", "piano", "other"}.issubset(ids)


def _normalize_demucs_model(model: str | None) -> str:
    value = str(model or "").strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80]


def _run_demucs_server(
    source_audio: Path,
    stems_dir: Path,
    *,
    server_url: str,
    api_key: str | None,
    model: str | None,
    requested_stems: list[str],
) -> list[tuple[str, str]]:
    headers = {}
    api_key = api_key or _feedback_demucs_api_key()
    if api_key:
        headers["X-API-Key"] = api_key
    model_name = _normalize_demucs_model(model)
    result = _demucs_post_file(server_url, source_audio, requested_stems, headers, model=model_name)
    job_id = str(result.get("job_id") or "")
    if result.get("status") == "processing":
        result = _poll_demucs_job(server_url, job_id, headers)
        job_id = str(result.get("job_id") or job_id)
    if result.get("status") == "failed":
        _cleanup_demucs_job(server_url, job_id, headers)
        raise RuntimeError(str(result.get("error") or "server reported failure"))

    stem_urls = result.get("stems")
    if not isinstance(stem_urls, dict):
        raise RuntimeError("server response did not include a stems object")

    try:
        stems_dir.mkdir(parents=True, exist_ok=True)
        written: list[tuple[str, str]] = []
        for stem_name, stem_url in stem_urls.items():
            stem_id = str(stem_name).strip().lower()
            if stem_id not in set(requested_stems):
                continue
            if not isinstance(stem_url, str) or not stem_url:
                continue
            data = _download_demucs_file(server_url, stem_url, headers)
            ext = Path(urllib.parse.urlparse(stem_url).path).suffix.lower() or ".ogg"
            target = stems_dir / f"{_safe_stem_id(stem_id)}{ext}"
            if ext == ".wav":
                wav_target = target
                wav_target.write_bytes(data)
                ogg_target = stems_dir / f"{_safe_stem_id(stem_id)}.ogg"
                if _convert_wav_file_to_ogg(wav_target, ogg_target):
                    wav_target.unlink(missing_ok=True)
                    target = ogg_target
                else:
                    target = wav_target
            else:
                target.write_bytes(data)
            if target.stat().st_size > 0:
                written.append((stem_id, f"stems/{target.name}"))
        return written
    finally:
        _cleanup_demucs_job(server_url, job_id, headers)


def _maybe_write_vocal_pitch(
    package_dir: Path,
    lyrics: list[dict[str, Any]],
    stem_entries: list[dict[str, Any]],
    *,
    demucs_url: str | None,
    demucs_api_key: str | None,
    warnings: list[ConversionWarning],
) -> str | None:
    if not lyrics:
        return None
    vocals = next((stem for stem in stem_entries if str(stem.get("id")) == "vocals"), None)
    if not vocals:
        return None
    vocals_path = package_dir / str(vocals.get("file") or "")
    if not vocals_path.is_file() or vocals_path.stat().st_size == 0:
        return None
    resolved_url = _resolve_demucs_url(demucs_url)
    if not resolved_url:
        return None
    if not _demucs_supports_pitch(resolved_url, demucs_api_key):
        warnings.append(
            ConversionWarning(
                "Karaoke pitch generation skipped: the configured Demucs server does not expose pitch generation."
            )
        )
        return None
    try:
        notes = _run_pitch_server(
            vocals_path,
            lyrics,
            server_url=resolved_url,
            api_key=demucs_api_key,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(ConversionWarning(f"Karaoke pitch generation skipped: {exc}"))
        return None
    if not notes:
        warnings.append(ConversionWarning("Karaoke pitch generation returned no pitched syllables."))
        return None
    path = "vocal_pitch.json"
    _write_json(package_dir / path, {"version": 1, "notes": notes})
    return path


def _demucs_supports_pitch(server_url: str, api_key: str | None) -> bool:
    headers = {}
    api_key = api_key or _feedback_demucs_api_key()
    if api_key:
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{server_url}/health", headers=headers)
    try:
        response = _read_json_response(req, timeout=10)
    except Exception:  # noqa: BLE001
        return True
    capabilities = response.get("capabilities")
    if isinstance(capabilities, dict) and capabilities.get("pitch") is False:
        return False
    return True


def _run_pitch_server(
    vocals_path: Path,
    lyrics: list[dict[str, Any]],
    *,
    server_url: str,
    api_key: str | None,
) -> list[dict[str, Any]]:
    headers = {}
    api_key = api_key or _feedback_demucs_api_key()
    if api_key:
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    fields = {"lyrics": json.dumps(lyrics, ensure_ascii=False)}
    result = _post_multipart_json(
        f"{server_url}/pitch",
        file_path=vocals_path,
        file_field="file",
        fields=fields,
        headers=headers,
        timeout=300,
    )
    raw_notes = result.get("notes")
    if not isinstance(raw_notes, list):
        raise RuntimeError("pitch endpoint did not return a notes list")
    notes: list[dict[str, Any]] = []
    for note in raw_notes:
        if not isinstance(note, dict):
            continue
        try:
            t = float(note["t"])
            d = float(note["d"])
            midi = int(note["midi"])
        except (KeyError, TypeError, ValueError):
            continue
        if _finite_number(t) and _finite_number(d):
            notes.append({"t": round(t, 3), "d": round(d, 3), "midi": midi})
    return notes


def _demucs_post_file(
    server_url: str,
    source_audio: Path,
    requested_stems: list[str],
    headers: dict[str, str],
    *,
    model: str = "",
) -> dict[str, Any]:
    query = {"stems": ",".join(requested_stems)}
    if model:
        query["model"] = model
    endpoint = f"{server_url}/separate?{urllib.parse.urlencode(query)}"
    return _post_multipart_json(
        endpoint,
        file_path=source_audio,
        file_field="file",
        fields={},
        headers=headers,
        timeout=900,
    )


def _post_multipart_json(
    endpoint: str,
    *,
    file_path: Path,
    file_field: str,
    fields: dict[str, str],
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    boundary = uuid.uuid4().hex
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )
    chunks.append(
        (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"{file_field}\"; filename=\"{file_path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(
        endpoint,
        data=b"".join(chunks),
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    return _read_json_response(req, timeout=timeout)


def _poll_demucs_job(server_url: str, job_id: str, headers: dict[str, str]) -> dict[str, Any]:
    if not job_id:
        raise RuntimeError("server returned processing without a job_id")
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(5)
        req = urllib.request.Request(f"{server_url}/jobs/{urllib.parse.quote(job_id)}", headers=headers)
        result = _read_json_response(req, timeout=30)
        if result.get("status") in {"complete", "failed"}:
            return result
    raise RuntimeError("server job timed out")


def _download_demucs_file(server_url: str, stem_url: str, headers: dict[str, str]) -> bytes:
    if stem_url.startswith(("http://", "https://")):
        url = stem_url
    else:
        url = f"{server_url}{stem_url if stem_url.startswith('/') else '/' + stem_url}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"stem download failed ({exc.code}): {body[:300]}") from exc


def _cleanup_demucs_job(server_url: str, job_id: str, headers: dict[str, str]) -> None:
    if not job_id:
        return
    req = urllib.request.Request(
        f"{server_url}/jobs/{urllib.parse.quote(job_id)}",
        headers=headers,
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except Exception:  # noqa: BLE001
        return


def _read_json_response(req: urllib.request.Request, *, timeout: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"server returned {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"cannot connect to server: {exc.reason}") from exc
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError("server returned a non-object response")
    return data


def _codec_for_audio_path(rel_file: str) -> str:
    return {
        ".ogg": "vorbis",
        ".wav": "wav",
        ".mp3": "mp3",
        ".flac": "flac",
        ".opus": "opus",
    }.get(Path(rel_file).suffix.lower(), Path(rel_file).suffix.lower().lstrip("."))


def _stem_sort_key(stem_id: str) -> tuple[int, str]:
    order = {"full": 0, "guitar": 1, "bass": 2, "drums": 3, "vocals": 4, "piano": 5, "other": 6}
    return (order.get(stem_id, 99), stem_id)


def _safe_stem_id(stem_id: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", stem_id.lower()).strip("_") or "stem"


def _select_primary_audio(audio: list[tuple[str, bytes]]) -> tuple[str, bytes]:
    full_song = [
        item for item in audio
        if "preview" not in Path(item[0]).stem.lower()
    ]
    return max(full_song or audio, key=lambda item: len(item[1]))


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


def _convert_wav_file_to_ogg(input_path: Path, output_path: Path) -> bool:
    tools_dir = _tools_dir()
    oggenc = (tools_dir / "oggenc.exe").resolve()
    if not oggenc.is_file() or not input_path.is_file():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = output_path.resolve()
    temp_ogg = output_path.with_name(output_path.stem + ".encode.ogg").resolve()
    try:
        temp_ogg.unlink(missing_ok=True)
        encode = subprocess.run(
            [str(oggenc), "-Q", "-q", "5", str(input_path.resolve()), "-o", str(temp_ogg)],
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
