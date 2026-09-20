"""Common FeedPak manifest and atomic archive output for every source."""
from pathlib import Path
import os
import tempfile
import zipfile

import yaml


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_archive(source: Path, target: Path) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(source.rglob("*")):
                if file.is_file():
                    if file.is_symlink() or not file.resolve().is_relative_to(source.resolve()):
                        raise ValueError("Package contains a file outside its staging directory")
                    archive.write(file, file.relative_to(source).as_posix())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
