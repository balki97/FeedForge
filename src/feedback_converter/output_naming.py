from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any


SUPPORTED_TEMPLATE_FIELDS = frozenset({"artist", "title", "album", "year", "source", "parts"})
SUPPORTED_OUTPUT_LAYOUTS = frozenset({"flat", "preserve", "artist"})
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}
)
_TEMPLATE_FIELD_RE = re.compile(r"\{([^{}]+)\}")


def validate_name_template(template: str | None) -> str:
    effective = str(template or "{source}")
    unknown = sorted(
        {
            match.group(1)
            for match in _TEMPLATE_FIELD_RE.finditer(effective)
            if match.group(1).lower() not in SUPPORTED_TEMPLATE_FIELDS
        },
        key=str.casefold,
    )
    if unknown:
        fields = ", ".join(f"{{{field}}}" for field in unknown)
        allowed = ", ".join(f"{{{field}}}" for field in sorted(SUPPORTED_TEMPLATE_FIELDS))
        raise ValueError(f"Unknown output naming field(s): {fields}. Available fields: {allowed}.")
    return effective


def validate_template_metadata(template: str | None, metadata: dict[str, Any]) -> None:
    effective = validate_name_template(template)
    requested = {match.group(1).lower() for match in _TEMPLATE_FIELD_RE.finditer(effective)}
    available = {
        "artist": str(metadata.get("artist") or "").strip(),
        "title": str(metadata.get("title") or "").strip(),
        "album": str(metadata.get("album") or "").strip(),
        "year": str(metadata.get("year") or "").strip(),
        "parts": arrangement_parts_code(metadata),
        # The source filename is always available and needs no metadata entry.
        "source": "available",
    }
    missing = sorted(field for field in requested if not available.get(field))
    if missing:
        fields = ", ".join(f"{{{field}}}" for field in missing)
        raise ValueError(
            f"Cannot apply the selected output naming convention because source metadata is missing: {fields}. "
            "Choose Source filename or fix the source metadata."
        )


def normalize_output_layout(layout: str | None) -> str:
    normalized = str(layout or "flat").strip().lower()
    if normalized not in SUPPORTED_OUTPUT_LAYOUTS:
        allowed = ", ".join(sorted(SUPPORTED_OUTPUT_LAYOUTS))
        raise ValueError(f"Unsupported output layout {layout!r}. Expected one of: {allowed}.")
    return normalized


def safe_path_segment(value: str, fallback: str = "converted", *, max_length: int = 120) -> str:
    def clean(candidate: str) -> str:
        normalized = unicodedata.normalize("NFC", candidate)
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", normalized)
        sanitized = re.sub(r"\s+", " ", sanitized).strip().rstrip(". ")
        return sanitized[:max_length].rstrip(". ")

    cleaned = clean(str(value or "")) or clean(str(fallback or "")) or "converted"
    if cleaned.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def output_name_values(input_psarc: Path, metadata: dict[str, Any], *, fallback_title: str = "") -> dict[str, str]:
    source = Path(input_psarc).stem
    return {
        "artist": str(metadata.get("artist") or "Unknown Artist").strip(),
        "title": str(metadata.get("title") or fallback_title or source).strip(),
        "album": str(metadata.get("album") or "").strip(),
        "year": str(metadata.get("year") or "").strip(),
        "source": source,
        "parts": arrangement_parts_code(metadata),
    }


def render_output_template(
    template: str | None,
    metadata: dict[str, Any],
    *,
    input_psarc: Path,
    fallback_title: str = "",
) -> str:
    effective = validate_name_template(template)
    values = output_name_values(input_psarc, metadata, fallback_title=fallback_title)
    rendered = re.sub(
        r"\{(artist|title|album|year|source|parts)\}",
        lambda match: values[match.group(1).lower()],
        effective,
        flags=re.IGNORECASE,
    )
    # Predefined templates use " - " separators. Collapse separators left behind by
    # optional metadata such as album/year while preserving literal custom text.
    rendered = re.sub(r"(?:\s+-\s*){2,}", " - ", rendered).strip(" -_.")
    if not rendered:
        rendered = values["title"] or values["source"]
    return safe_path_segment(rendered, values["source"])


def arrangement_parts_code(metadata: dict[str, Any]) -> str:
    names = metadata.get("arrangement_names")
    if not isinstance(names, dict):
        return ""
    labels = [f"{key} {value}".lower() for key, value in names.items()]
    return "".join(
        code
        for needle, code in (("bass", "B"), ("lead", "L"), ("rhythm", "R"), ("vocal", "V"), ("combo", "C"))
        if any(needle in label for label in labels)
    )


def output_folder(
    base_dir: Path,
    input_path: Path,
    metadata: dict[str, Any],
    *,
    output_layout: str,
    source_root: Path | None,
) -> Path:
    layout = normalize_output_layout(output_layout)
    folder = Path(base_dir)
    if layout == "artist":
        folder = folder / safe_path_segment(str(metadata.get("artist") or "Unknown Artist"), "Unknown Artist")
    elif layout == "preserve" and source_root:
        try:
            relative_dir = Path(input_path).parent.resolve().relative_to(Path(source_root).resolve())
        except ValueError:
            relative_dir = Path()
        if relative_dir.parts:
            folder = folder / relative_dir
    return folder


def output_path(
    input_path: Path,
    base_dir: Path,
    metadata: dict[str, Any],
    *,
    output_layout: str,
    source_root: Path | None,
    name_template: str,
    fallback_title: str,
    suffix: str,
) -> Path:
    folder = output_folder(
        base_dir,
        input_path,
        metadata,
        output_layout=output_layout,
        source_root=source_root,
    )
    name = render_output_template(
        name_template,
        metadata,
        input_psarc=input_path,
        fallback_title=fallback_title,
    )
    return folder / f"{name}{suffix}"


def unique_output_path(path: Path, reserved: set[Path], *, overwrite: bool) -> Path:
    """Reserve a collision-safe path without modifying the filesystem."""
    path = Path(path)
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
