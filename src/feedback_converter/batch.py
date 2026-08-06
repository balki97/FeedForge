from __future__ import annotations

import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .converter import ConversionResult, convert_psarc_songs, plan_psarc_songs
from .inspector import inspect_psarc
from .output_naming import validate_name_template


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


def plan_conversion_request(request: dict[str, object]) -> dict[str, object]:
    """Build one collision-safe output plan for a desktop conversion queue."""
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
    reserved_outputs: set[Path] = set()
    results: list[dict[str, object]] = []

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            results.append({"ok": False, "inputPath": "", "error": "Invalid conversion planning item."})
            continue
        input_value = str(raw_item.get("inputPath") or "").strip()
        source_root_value = str(raw_item.get("sourceRoot") or "").strip()
        input_path = Path(input_value)
        try:
            plan = plan_psarc_songs(
                input_path,
                output_dir,
                output_layout=output_layout,
                source_root=Path(source_root_value) if source_root_value else None,
                name_template=name_template,
                overwrite=overwrite,
                reserved_outputs=reserved_outputs,
                rs1_songs_psarc=rs1_songs_psarc if _is_rs1_compatibility_archive(input_path) else None,
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"ok": False, "inputPath": input_value, "error": str(exc)})
        else:
            results.append({"ok": True, **plan.to_dict()})

    failed = sum(1 for item in results if not item.get("ok"))
    return {
        "ok": True,
        "total": len(results),
        "planned": len(results) - failed,
        "failed": failed,
        "items": results,
    }


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
    lowered_template = str(name_template or "").lower()
    needs_metadata = (
        "{artist}" in lowered_template
        or "{title}" in lowered_template
        or "{album}" in lowered_template
        or "{year}" in lowered_template
        or "{parts}" in lowered_template
        or str(output_layout or "").strip().lower() == "artist"
    )
    metadata = _output_name_metadata(input_path, needs_metadata=needs_metadata)
    file_name = f"{_safe_path_segment(_render_name_template(name_template, metadata), metadata['source'])}.feedpak"
    layout = str(output_layout or "flat").strip().lower()
    if layout == "preserve":
        try:
            relative_parent = input_path.parent.resolve().relative_to(Path(source_root).resolve()) if source_root else Path()
        except ValueError:
            relative_parent = Path()
        return output_dir / relative_parent / file_name
    if layout == "artist":
        return output_dir / _safe_path_segment(metadata["artist"]) / file_name
    return output_dir / file_name


def _common_parent(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    try:
        return Path(os.path.commonpath([str(path.parent.resolve()) for path in paths]))
    except Exception:  # noqa: BLE001
        return None


def _output_name_metadata(input_path: Path, *, needs_metadata: bool) -> dict[str, str]:
    source = input_path.stem
    metadata = {
        "source": source,
        "artist": "Unknown Artist",
        "title": source,
        "album": "",
        "year": "",
        "parts": "",
    }
    if not needs_metadata:
        return metadata
    try:
        preview = inspect_psarc(input_path)
    except Exception:  # noqa: BLE001
        return metadata
    metadata["artist"] = str(getattr(preview, "artist", None) or metadata["artist"])
    metadata["title"] = str(getattr(preview, "title", None) or metadata["title"])
    metadata["album"] = str(getattr(preview, "album", None) or "")
    metadata["year"] = str(getattr(preview, "year", None) or "")
    metadata["parts"] = _arrangement_parts_code(getattr(preview, "arrangements", None))
    return metadata


def _render_name_template(template: str, metadata: dict[str, str]) -> str:
    allowed = {"artist", "title", "album", "year", "source", "parts"}

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return metadata.get(key, "") if key in allowed else match.group(0)

    return re.sub(r"\{(artist|title|album|year|source|parts)\}", replace, str(template or "{source}"), flags=re.IGNORECASE)


def _arrangement_parts_code(arrangements: object) -> str:
    labels: list[str] = []
    for arrangement in arrangements or []:
        if isinstance(arrangement, dict):
            labels.append(f"{arrangement.get('type', '')} {arrangement.get('id', '')} {arrangement.get('name', '')}".lower())
        else:
            labels.append(
                f"{getattr(arrangement, 'type', '')} {getattr(arrangement, 'id', '')} {getattr(arrangement, 'name', '')}".lower()
            )
    return "".join(
        code
        for needle, code in (("bass", "B"), ("lead", "L"), ("rhythm", "R"), ("vocal", "V"), ("combo", "C"))
        if any(needle in label for label in labels)
    )


def _safe_path_segment(value: str, fallback: str = "Unknown Artist") -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", ascii_value or str(value or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(". ")
    return cleaned or fallback


def _cleanup_failed_workdir(
    input_path: Path,
    output: Path | None,
    *,
    archive: bool,
    keep_workdir: bool,
) -> None:
    if not archive or keep_workdir:
        return
    target = output or input_path.with_suffix(".feedpak")
    workdir = target.with_suffix(target.suffix + ".work")
    if workdir.is_dir():
        shutil.rmtree(workdir, ignore_errors=True)
