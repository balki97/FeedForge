from __future__ import annotations

import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .converter import (
    ConversionResult,
    PsarcPlanningData,
    convert_psarc_songs,
    load_psarc_planning_data,
    plan_loaded_psarc_songs,
    plan_psarc_songs,
    psarc_planning_data_from_cache,
)
from .inspector import inspect_psarc
from .output_naming import (
    output_path as build_output_path,
    validate_name_template,
    validate_template_metadata,
)


@dataclass(frozen=True)
class BatchItem:
    input_path: Path
    result: ConversionResult | None = None
    results: list[ConversionResult] = field(default_factory=list)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return (self.result is not None or bool(self.results)) and self.error is None


@dataclass(frozen=True)
class BatchResult:
    items: list[BatchItem] = field(default_factory=list)

    @property
    def succeeded(self) -> list[BatchItem]:
        return [item for item in self.items if item.succeeded]

    @property
    def failed(self) -> list[BatchItem]:
        return [item for item in self.items if not item.succeeded]

    @property
    def ok(self) -> bool:
        return not self.failed


def convert_many(
    input_paths: list[Path],
    output_dir: Path | None = None,
    *,
    output_layout: str = "flat",
    name_template: str = "{source}",
    source_root: Path | None = None,
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
) -> BatchResult:
    """Convert multiple PSARC files, returning per-file success/error state."""
    items: list[BatchItem] = []
    normalized_inputs = [Path(path) for path in input_paths]
    support_songs_psarc = Path(rs1_songs_psarc) if rs1_songs_psarc is not None else _selected_rs1_songs_psarc(normalized_inputs)
    resolved_source_root = Path(source_root) if source_root is not None else _common_parent(normalized_inputs)
    reserved_outputs: set[Path] = set()
    for input_path in normalized_inputs:
        try:
            plan = plan_psarc_songs(
                input_path,
                Path(output_dir) if output_dir is not None else None,
                output_layout=output_layout,
                source_root=resolved_source_root,
                name_template=name_template,
                overwrite=overwrite,
                reserved_outputs=reserved_outputs,
                rs1_songs_psarc=support_songs_psarc if _is_rs1_compatibility_archive(input_path) else None,
            )
            results = convert_psarc_songs(
                input_path,
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
                rs1_songs_psarc=support_songs_psarc if _is_rs1_compatibility_archive(input_path) else None,
                output_layout=output_layout,
                source_root=resolved_source_root,
                name_template=name_template,
                output_plan=plan.to_dict(),
            )
        except Exception as exc:  # noqa: BLE001
            items.append(BatchItem(input_path=input_path, error=str(exc)))
        else:
            items.append(BatchItem(input_path=input_path, result=results[0] if results else None, results=results))
    return BatchResult(items=items)


def plan_conversion_request(
    request: dict[str, object],
    *,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Build one fast, deterministic, collision-safe desktop conversion plan."""
    if not isinstance(request, dict):
        raise ValueError("Conversion planning request must be a JSON object.")
    raw_items = request.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Conversion planning request does not contain any PSARC files.")

    output_dir_value = str(request.get("outputDir") or "").strip()
    output_dir = Path(output_dir_value) if output_dir_value else None
    output_layout = str(request.get("outputLayout") or "flat")
    name_template = validate_name_template(str(request.get("nameTemplate") or "{source}"))
    overwrite = request.get("overwrite") is True
    rs1_value = str(request.get("rs1SongsPsarc") or "").strip()
    rs1_songs_psarc = Path(rs1_value) if rs1_value else None
    worker_count = _planning_worker_count(request.get("workers"), len(raw_items))
    cache_value = str(request.get("cachePath") or "").strip()
    cache = _PlanningMetadataCache(Path(cache_value) if cache_value else None)
    reserved_outputs: set[Path] = set()
    total = len(raw_items)
    loaded: list[PsarcPlanningData | None] = [None] * total
    errors: list[str | None] = [None] * total
    input_values = [""] * total
    source_roots: list[Path | None] = [None] * total
    cache_hits = 0
    completed = 0
    last_report_at = 0.0
    last_reported_completed = -1
    started_at = time.perf_counter()

    def report(*, stage: str, input_path: str = "", force: bool = False) -> None:
        nonlocal last_report_at, last_reported_completed
        if progress_callback is None:
            return
        now = time.monotonic()
        if not force and completed < total and completed == last_reported_completed:
            return
        if not force and completed < total and now - last_report_at < 0.1 and completed - last_reported_completed < 20:
            return
        payload: dict[str, object] = {
            "stage": stage,
            "completed": completed,
            "total": total,
            "cached": cache_hits,
            "workers": worker_count,
        }
        if input_path:
            payload["inputPath"] = input_path
        try:
            progress_callback(payload)
        except Exception:  # noqa: BLE001
            pass
        last_report_at = now
        last_reported_completed = completed

    report(stage="metadata", force=True)
    futures: dict[object, tuple[int, Path]] = {}
    try:
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="feedforge-plan") as executor:
            for index, raw_item in enumerate(raw_items):
                if not isinstance(raw_item, dict):
                    errors[index] = "Invalid conversion planning item."
                    completed += 1
                    report(stage="metadata")
                    continue
                input_value = str(raw_item.get("inputPath") or "").strip()
                source_root_value = str(raw_item.get("sourceRoot") or "").strip()
                input_values[index] = input_value
                source_roots[index] = Path(source_root_value) if source_root_value else None
                input_path = Path(input_value)
                try:
                    stat = input_path.stat()
                    if not input_path.is_file():
                        raise FileNotFoundError(f"PSARC file not found: {input_path}")
                except Exception as exc:  # noqa: BLE001
                    errors[index] = str(exc)
                    completed += 1
                    report(stage="metadata", input_path=input_value)
                    continue

                cached = cache.get(input_path, stat.st_size, stat.st_mtime_ns)
                if cached is not None:
                    loaded[index] = cached
                    cache_hits += 1
                    completed += 1
                    report(stage="metadata", input_path=input_value)
                    continue

                future = executor.submit(
                    load_psarc_planning_data,
                    input_path,
                    rs1_songs_psarc=rs1_songs_psarc if _is_rs1_compatibility_archive(input_path) else None,
                )
                futures[future] = (index, input_path)

            for future in as_completed(futures):
                index, input_path = futures[future]
                try:
                    planning_data = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors[index] = str(exc)
                else:
                    loaded[index] = planning_data
                    cache.put(planning_data)
                completed += 1
                report(stage="metadata", input_path=str(input_path))
        cache.commit()
    finally:
        cache.close()

    report(stage="reserving", force=True)
    results: list[dict[str, object]] = []
    for index in range(total):
        input_value = input_values[index]
        planning_data = loaded[index]
        if planning_data is None:
            results.append({"ok": False, "inputPath": input_value, "error": errors[index] or "Output metadata could not be read."})
            continue
        try:
            plan = plan_loaded_psarc_songs(
                planning_data,
                output_dir,
                output_layout=output_layout,
                source_root=source_roots[index],
                name_template=name_template,
                overwrite=overwrite,
                reserved_outputs=reserved_outputs,
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"ok": False, "inputPath": input_value, "error": str(exc)})
        else:
            results.append({"ok": True, **plan.to_dict()})

    failed = sum(1 for item in results if not item.get("ok"))
    report(stage="complete", force=True)
    return {
        "ok": True,
        "total": len(results),
        "planned": len(results) - failed,
        "failed": failed,
        "cached": cache_hits,
        "workers": worker_count,
        "durationMs": round((time.perf_counter() - started_at) * 1000),
        "items": results,
    }


def _planning_worker_count(value: object, total: int) -> int:
    try:
        requested = int(value or 4)
    except (TypeError, ValueError):
        requested = 4
    return min(max(1, requested), 8, max(1, total))


class _PlanningMetadataCache:
    """Small persistent metadata cache keyed by canonical path and source fingerprint."""

    def __init__(self, path: Path | None) -> None:
        self.connection: sqlite3.Connection | None = None
        self.pending = 0
        if path is None:
            return
        connection: sqlite3.Connection | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=10)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS psarc_metadata_v1 (
                    path TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    mtime_ns TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    last_used INTEGER NOT NULL
                )
                """
            )
            cutoff = int(time.time()) - 180 * 24 * 60 * 60
            connection.execute("DELETE FROM psarc_metadata_v1 WHERE last_used < ?", (cutoff,))
            connection.commit()
            self.connection = connection
        except (OSError, sqlite3.Error):
            try:
                if connection is not None:
                    connection.close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(path))

    def get(self, path: Path, size: int, mtime_ns: int) -> PsarcPlanningData | None:
        if self.connection is None:
            return None
        key = self._key(path)
        try:
            row = self.connection.execute(
                "SELECT payload FROM psarc_metadata_v1 WHERE path = ? AND size = ? AND mtime_ns = ?",
                (key, int(size), str(mtime_ns)),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row[0])
            planning_data = psarc_planning_data_from_cache(path, size, mtime_ns, payload)
            self.connection.execute(
                "UPDATE psarc_metadata_v1 SET last_used = ? WHERE path = ?",
                (int(time.time()), key),
            )
            self.pending += 1
            return planning_data
        except (ValueError, TypeError, json.JSONDecodeError, sqlite3.Error):
            try:
                self.connection.execute("DELETE FROM psarc_metadata_v1 WHERE path = ?", (key,))
            except sqlite3.Error:
                pass
            return None

    def put(self, planning_data: PsarcPlanningData) -> None:
        if self.connection is None:
            return
        try:
            self.connection.execute(
                """
                INSERT INTO psarc_metadata_v1(path, size, mtime_ns, payload, last_used)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    payload = excluded.payload,
                    last_used = excluded.last_used
                """,
                (
                    self._key(planning_data.input_path),
                    planning_data.source_size,
                    str(planning_data.source_mtime_ns),
                    json.dumps(planning_data.to_cache_payload(), ensure_ascii=False, separators=(",", ":")),
                    int(time.time()),
                ),
            )
            self.pending += 1
            if self.pending >= 100:
                self.commit()
        except (TypeError, ValueError, sqlite3.Error):
            pass

    def commit(self) -> None:
        if self.connection is None or not self.pending:
            return
        try:
            self.connection.commit()
            self.pending = 0
        except sqlite3.Error:
            pass

    def close(self) -> None:
        if self.connection is None:
            return
        self.commit()
        try:
            self.connection.close()
        except sqlite3.Error:
            pass
        self.connection = None


def _is_rs1_compatibility_archive(path: Path) -> bool:
    return "rs1compatibility" in path.name.lower() and path.suffix.lower() == ".psarc"


def _is_rs1_songs_archive(path: Path) -> bool:
    return path.name.lower() == "songs.psarc"


def _selected_rs1_songs_psarc(paths: list[Path]) -> Path | None:
    for path in paths:
        if _is_rs1_songs_archive(path):
            return path
    return None


def _batch_output_path(
    input_path: Path,
    output_dir: Path | None,
    output_layout: str,
    source_root: Path | None,
    name_template: str = "{source}",
) -> Path | None:
    if output_dir is None:
        return None
    template = validate_name_template(name_template)
    layout = str(output_layout or "flat").strip().lower()
    lowered_template = str(name_template or "").lower()
    needs_metadata = (
        "{artist}" in lowered_template
        or "{title}" in lowered_template
        or "{album}" in lowered_template
        or "{year}" in lowered_template
        or "{parts}" in lowered_template
        or layout == "artist"
    )
    metadata = _output_name_metadata(input_path, needs_metadata=needs_metadata)
    validate_template_metadata(template, metadata)
    if layout == "artist" and not str(metadata.get("artist") or "").strip():
        raise ValueError("Cannot use Artist folders because the package metadata does not contain an artist.")
    return build_output_path(
        input_path,
        output_dir,
        metadata,
        output_layout=layout,
        source_root=source_root,
        name_template=template,
        fallback_title=input_path.stem,
        suffix=".feedpak",
    )


def _common_parent(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    try:
        return Path(os.path.commonpath([str(path.parent.resolve()) for path in paths]))
    except Exception:  # noqa: BLE001
        return None


def _output_name_metadata(input_path: Path, *, needs_metadata: bool) -> dict[str, object]:
    metadata: dict[str, object] = {
        "artist": "",
        "title": "",
        "album": "",
        "year": "",
        "arrangement_names": {},
    }
    if not needs_metadata:
        return metadata
    if input_path.suffix.lower() == ".feedpak" or input_path.is_dir():
        # Imported lazily to avoid a batch -> feedpak -> converter import cycle.
        from .feedpak import inspect_feedpak

        preview = inspect_feedpak(input_path)
        artist = preview.get("artist")
        title = preview.get("title")
        album = preview.get("album")
        year = preview.get("year")
        arrangements = preview.get("arrangements") or []
    else:
        preview = inspect_psarc(input_path)
        artist = getattr(preview, "artist", None)
        title = getattr(preview, "title", None)
        album = getattr(preview, "album", None)
        year = getattr(preview, "year", None)
        arrangements = getattr(preview, "arrangements", None) or []
    metadata["artist"] = str(artist or "")
    metadata["title"] = str(title or "")
    metadata["album"] = str(album or "")
    metadata["year"] = str(year or "")
    metadata["arrangement_names"] = {
        str(arrangement.get("id") or index) if isinstance(arrangement, dict) else str(getattr(arrangement, "id", index)): (
            str(arrangement.get("name") or arrangement.get("type") or "")
            if isinstance(arrangement, dict)
            else str(getattr(arrangement, "name", None) or getattr(arrangement, "type", None) or "")
        )
        for index, arrangement in enumerate(arrangements)
    }
    return metadata
