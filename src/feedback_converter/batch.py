from __future__ import annotations

import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .converter import ConversionResult, convert_psarc
from .inspector import inspect_psarc


@dataclass(frozen=True)
class BatchItem:
    input_path: Path
    result: ConversionResult | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.result is not None and self.error is None


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
    keep_full_stem: bool = True,
) -> BatchResult:
    """Convert multiple PSARC files, returning per-file success/error state."""
    items: list[BatchItem] = []
    normalized_inputs = [Path(path) for path in input_paths]
    resolved_source_root = Path(source_root) if source_root is not None else _common_parent(normalized_inputs)
    for input_path in normalized_inputs:
        output = _batch_output_path(
            input_path,
            Path(output_dir) if output_dir is not None else None,
            output_layout,
            resolved_source_root,
            name_template,
        )
        try:
            result = convert_psarc(
                input_path,
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
                keep_full_stem=keep_full_stem,
            )
        except Exception as exc:  # noqa: BLE001
            _cleanup_failed_workdir(input_path, output, archive=archive, keep_workdir=keep_workdir)
            items.append(BatchItem(input_path=input_path, error=str(exc)))
        else:
            items.append(BatchItem(input_path=input_path, result=result))
    return BatchResult(items=items)


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
    return metadata


def _render_name_template(template: str, metadata: dict[str, str]) -> str:
    allowed = {"artist", "title", "album", "year", "source"}

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return metadata.get(key, "") if key in allowed else match.group(0)

    return re.sub(r"\{(artist|title|album|year|source)\}", replace, str(template or "{source}"), flags=re.IGNORECASE)


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
