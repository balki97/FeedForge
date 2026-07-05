from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .converter import ConversionResult, convert_psarc


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
    archive: bool = True,
    overwrite: bool = False,
    keep_workdir: bool = False,
    include_tones: bool = True,
    b_standard_to_7_string: bool = False,
) -> BatchResult:
    """Convert multiple PSARC files, returning per-file success/error state."""
    items: list[BatchItem] = []
    for input_path in [Path(path) for path in input_paths]:
        output = None
        if output_dir is not None:
            output = Path(output_dir) / input_path.with_suffix(".feedpak").name
        try:
            result = convert_psarc(
                input_path,
                output,
                archive=archive,
                overwrite=overwrite,
                keep_workdir=keep_workdir,
                include_tones=include_tones,
                b_standard_to_7_string=b_standard_to_7_string,
            )
        except Exception as exc:  # noqa: BLE001
            _cleanup_failed_workdir(input_path, output, archive=archive, keep_workdir=keep_workdir)
            items.append(BatchItem(input_path=input_path, error=str(exc)))
        else:
            items.append(BatchItem(input_path=input_path, result=result))
    return BatchResult(items=items)


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
