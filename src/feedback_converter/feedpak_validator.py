from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


SCHEMA_DIR = Path(__file__).resolve().parent / "data" / "feedpak_schemas"
SUPPORTED_MAJOR = 1
SIDE_FILE_SCHEMAS = {
    "lyrics": "lyrics.schema.json",
    "vocal_pitch": "vocal-pitch.schema.json",
    "song_timeline": "song-timeline.schema.json",
    "drum_tab": "drum-tab.schema.json",
    "vocal_pitch_contour": "vocal-pitch-contour.schema.json",
    "keys": "keys.schema.json",
    "harmony": "harmony.schema.json",
    "rigs": "rigs.schema.json",
}
NON_JSON_POINTERS = ("cover", "preview")
JSONC_STRIP_RE = re.compile(
    r'"(?:[^"\\]|\\.)*"|'
    r"//.*|"
    r"/\*[\s\S]*?\*/",
)


@dataclass(frozen=True)
class FeedpakValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


class FeedpakValidationError(ValueError):
    def __init__(self, result: FeedpakValidationResult) -> None:
        self.result = result
        details = "; ".join(result.errors[:4])
        if len(result.errors) > 4:
            details += f" (+{len(result.errors) - 4} more)"
        super().__init__(f"FeedPak spec validation failed: {details}")


class _Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def err(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def validate_feedpak(package: Path) -> FeedpakValidationResult:
    """Validate a FeedPak directory or zip against the official FeedPak schemas."""
    package = Path(package)
    report = _Report()
    try:
        if package.is_dir():
            _validate_dir(package, report)
        elif package.is_file() and zipfile.is_zipfile(package):
            with tempfile.TemporaryDirectory(prefix="feedforge-validate-feedpak-") as temp:
                root = Path(temp) / "package.feedpak"
                with zipfile.ZipFile(package) as zf:
                    for name in zf.namelist():
                        if name.startswith("/") or ".." in Path(name).parts or "\\" in name or ":" in name:
                            report.err(f"unsafe path inside archive: {name}")
                    if report.ok:
                        zf.extractall(root)
                        _validate_dir(root, report)
        else:
            report.err("not a FeedPak directory or zip archive")
    except Exception as exc:  # noqa: BLE001
        report.err(f"validation failed: {exc}")
    return FeedpakValidationResult(ok=report.ok, errors=report.errors, warnings=report.warnings)


def require_valid_feedpak(package: Path) -> FeedpakValidationResult:
    """Return the validation report or raise with concise, user-facing details."""
    result = validate_feedpak(package)
    if not result.ok:
        raise FeedpakValidationError(result)
    return result


def _schema_validator(name: str) -> Draft202012Validator:
    with (SCHEMA_DIR / name).open(encoding="utf-8") as fh:
        return Draft202012Validator(json.load(fh))


def _semver_pattern() -> re.Pattern[str]:
    with (SCHEMA_DIR / "manifest.schema.json").open(encoding="utf-8") as fh:
        pattern = json.load(fh)["$defs"]["semver"]["pattern"]
    return re.compile(pattern)


SEMVER_RE = _semver_pattern()


def _validate_dir(root: Path, report: _Report) -> None:
    manifest_path = root / "manifest.yaml"
    if not _within_root(root, manifest_path):
        report.err("manifest.yaml escapes the package root")
        return
    if not manifest_path.is_file():
        report.err("no manifest.yaml at package root")
        return
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        report.err(f"manifest.yaml: not valid YAML ({exc})")
        return
    if not isinstance(manifest, dict):
        report.err("manifest.yaml: top level must be a mapping")
        return

    _validate_object(manifest, _schema_validator("manifest.schema.json"), "manifest.yaml", report)
    feedpak_version = manifest.get("feedpak_version", "1.0.0")
    if not isinstance(feedpak_version, str) or not SEMVER_RE.match(feedpak_version):
        report.err(f"feedpak_version is not a valid semver string: {feedpak_version!r}")
    else:
        major = int(feedpak_version.split(".")[0])
        if major > SUPPORTED_MAJOR:
            report.warn(
                f"feedpak_version {feedpak_version} has major {major} > supported {SUPPORTED_MAJOR}; "
                "this validator may not understand it"
            )

    arrangement_validator = _schema_validator("arrangement.schema.json")
    notation_validator = _schema_validator("notation.schema.json")
    for index, arrangement in enumerate(manifest.get("arrangements", []) or []):
        if not isinstance(arrangement, dict):
            continue
        file_name = arrangement.get("file")
        if file_name is not None and _check_pointer(root, file_name, f"arrangements[{index}].file", report):
            _validate_json_file(root, file_name, arrangement_validator, report)
        notation = arrangement.get("notation")
        if notation is not None and _check_pointer(root, notation, f"arrangements[{index}].notation", report):
            _validate_json_file(root, notation, notation_validator, report)

    for index, stem in enumerate(manifest.get("stems", []) or []):
        if isinstance(stem, dict) and "file" in stem:
            _check_pointer(root, stem["file"], f"stems[{index}].file", report)

    for key, schema_name in SIDE_FILE_SCHEMAS.items():
        relpath = manifest.get(key)
        if relpath is not None and _check_pointer(root, relpath, key, report):
            _validate_json_file(root, relpath, _schema_validator(schema_name), report)

    for key in NON_JSON_POINTERS:
        relpath = manifest.get(key)
        if relpath is not None:
            _check_pointer(root, relpath, key, report)


def _validate_object(data: Any, validator: Draft202012Validator, label: str, report: _Report) -> None:
    for error in sorted(validator.iter_errors(data), key=lambda err: list(err.path)):
        location = "/".join(str(item) for item in error.path) or "<root>"
        report.err(f"{label}: {location}: {error.message}")


def _validate_json_file(root: Path, relpath: str, validator: Draft202012Validator, report: _Report) -> None:
    target = root / relpath
    if not target.is_file():
        report.err(f"missing file referenced by manifest: {relpath}")
        return
    try:
        raw = target.read_text(encoding="utf-8")
        data = _parse_jsonc(raw) if relpath.endswith(".jsonc") else json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        kind = "not valid JSON after JSONC comment-stripping" if relpath.endswith(".jsonc") else "not valid JSON"
        report.err(f"{relpath}: {kind} ({exc})")
        return
    _validate_object(data, validator, relpath, report)


def _parse_jsonc(text: str) -> object:
    def strip(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.startswith('"'):
            return value
        if value.startswith("/*"):
            return "\n" * value.count("\n") if "\n" in value else " "
        return ""

    return json.loads(JSONC_STRIP_RE.sub(strip, text))


def _check_pointer(root: Path, relpath: str, key: str, report: _Report) -> bool:
    if not _safe_relpath(relpath):
        report.err(f"manifest '{key}' is not a safe relative path: {relpath!r}")
        return False
    target = root / relpath
    if not _within_root(root, target):
        report.err(f"manifest '{key}' escapes the package root: {relpath}")
        return False
    if not target.resolve().is_file():
        report.err(f"missing file referenced by manifest '{key}': {relpath}")
        return False
    return True


def _safe_relpath(path: str) -> bool:
    if not isinstance(path, str) or not path:
        return False
    if path.startswith("/") or "\\" in path or ":" in path:
        return False
    parts = path.split("/")
    return ".." not in parts and "" not in parts[:-1]


def _within_root(root: Path, target: Path) -> bool:
    root_real = root.resolve()
    target_real = target.resolve()
    return root_real == target_real or root_real in target_real.parents
