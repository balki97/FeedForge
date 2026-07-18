from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feedback_converter import __version__
from feedback_converter.batch import _batch_output_path, convert_many
from feedback_converter.converter import convert_psarc, convert_psarc_songs
from feedback_converter.feedpak import inspect_feedpak, update_feedpak
from feedback_converter.feedpak_validator import validate_feedpak
from feedback_converter.inspector import inspect_psarc


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:  # noqa: BLE001
                pass


def _safe_text(value: Any) -> str:
    text = str(value)
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8", errors="replace")


def _print(value: Any, *, stream: Any = None) -> None:
    target = stream or sys.stdout
    try:
        print(_safe_text(value), file=target)
    except UnicodeEncodeError:
        encoded = _safe_text(value).encode(getattr(target, "encoding", None) or "utf-8", errors="backslashreplace")
        target.buffer.write(encoded + b"\n")
        target.flush()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _cleanup_failed_workdir(input_path: Path, output_path: Path | None, *, archive: bool) -> None:
    if not archive:
        return

    target = output_path or input_path.with_suffix(".feedpak")
    workdir = target.with_suffix(target.suffix + ".work")
    if workdir.is_dir():
        shutil.rmtree(workdir, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="psarc2feedpak",
        description="Convert PSARC CDLC archives to FeedPak packages.",
    )
    parser.add_argument("input", nargs="*", help="Input .psarc file(s).")
    parser.add_argument(
        "-o",
        "--output",
        help=(
            "Output .feedpak file/directory for one input, or an output folder "
            "when converting multiple inputs."
        ),
    )
    parser.add_argument(
        "--directory",
        action="store_true",
        help="Write an unpacked .feedpak directory instead of a zip archive.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output path.",
    )
    parser.add_argument(
        "--output-layout",
        choices=["flat", "preserve", "artist"],
        default="flat",
        help="Batch output folder layout: flat, preserve source folders, or sort by artist metadata.",
    )
    parser.add_argument(
        "--source-root",
        help="Source folder root used with --output-layout preserve.",
    )
    parser.add_argument(
        "--name-template",
        default="{source}",
        help="Output filename template. Available fields: {artist}, {title}, {album}, {year}, {source}.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep the intermediate .feedpak.work directory when writing a zip archive.",
    )
    parser.add_argument(
        "--no-tones",
        action="store_true",
        help="Do not export tone definitions or rig metadata.",
    )
    parser.add_argument(
        "--b-standard-to-7-string",
        action="store_true",
        help="Convert six-string B-standard arrangements to seven-string standard charts.",
    )
    parser.add_argument(
        "--separate-stems",
        action="store_true",
        help="Split the converted full mix into instrument stems through a Demucs-compatible server.",
    )
    parser.add_argument(
        "--demucs-url",
        help="Demucs-compatible server URL. Defaults to FEEDFORGE_DEMUCS_URL or DEMUCS_SERVER_URL.",
    )
    parser.add_argument(
        "--demucs-api-key",
        help="Optional Demucs server API key sent as X-API-Key.",
    )
    parser.add_argument(
        "--demucs-model",
        help="Optional Demucs-compatible server model, such as htdemucs_6s or bs_roformer_sw.",
    )
    parser.add_argument(
        "--demucs-stems",
        default="guitar,bass,drums,vocals,other",
        help="Comma-separated stems to request from the Demucs server.",
    )
    parser.add_argument(
        "--rs1-songs-psarc",
        help=(
            "Optional songs.psarc path used to resolve audio for RS1 compatibility packs. "
            "By default FeedForge checks the parent of the DLC folder for songs.psarc."
        ),
    )
    parser.add_argument(
        "--inspect-json",
        action="store_true",
        help="Inspect one PSARC or FeedPak and write metadata JSON to stdout.",
    )
    parser.add_argument(
        "--inspect-cover-dir",
        help="Folder for cover art written during --inspect-json.",
    )
    parser.add_argument(
        "--validate-feedpak",
        action="store_true",
        help="Validate one or more FeedPak packages against the bundled FeedPak spec schemas.",
    )
    parser.add_argument("--feedpak-title", help="Set FeedPak title when editing an existing FeedPak.")
    parser.add_argument("--feedpak-artist", help="Set FeedPak artist when editing an existing FeedPak.")
    parser.add_argument("--feedpak-album", help="Set FeedPak album when editing an existing FeedPak.")
    parser.add_argument("--feedpak-year", help="Set FeedPak year when editing an existing FeedPak.")
    parser.add_argument("--feedpak-language", help="Set FeedPak language when editing an existing FeedPak.")
    parser.add_argument(
        "--feedpak-authors-json",
        help="JSON array of FeedPak author objects, for example [{\"name\":\"Name\",\"role\":\"charter\"}].",
    )
    parser.add_argument("--feedpak-cover", help="PNG/JPG/WEBP cover image to add or replace in an existing FeedPak.")
    parser.add_argument(
        "--feedpak-remove-cover",
        action="store_true",
        help="Remove the cover image from an existing FeedPak.",
    )
    parser.add_argument(
        "--feedpak-stem-updates-json",
        help="JSON array of stem updates, for example [{\"id\":\"guitar\",\"file\":\"C:/audio/guitar.ogg\"}].",
    )
    parser.add_argument(
        "--feedpak-remove-stems",
        help="Comma-separated non-full stem ids to remove from an existing FeedPak.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.validate_feedpak:
        if not args.input:
            parser.error("--validate-feedpak requires at least one input")
        results = []
        ok = True
        for input_item in args.input:
            input_path = Path(input_item)
            validation = validate_feedpak(input_path)
            ok = ok and validation.ok
            results.append({"input_path": str(input_path), "validation": validation.to_dict()})
        _print(json.dumps({"ok": ok, "results": _jsonable(results)}, ensure_ascii=False), stream=sys.stdout)
        return 0 if ok else 1

    if args.inspect_json:
        if len(args.input) != 1:
            parser.error("--inspect-json requires exactly one input")
        try:
            cover_dir = Path(args.inspect_cover_dir) if args.inspect_cover_dir else None
            input_path = Path(args.input[0])
            preview = (
                inspect_feedpak(input_path, cover_dir=cover_dir)
                if input_path.suffix.lower() == ".feedpak" or input_path.is_dir()
                else inspect_psarc(input_path, cover_dir=cover_dir)
            )
        except Exception as exc:  # noqa: BLE001
            _print(json.dumps({"ok": False, "error": str(exc)}), stream=sys.stdout)
            return 1
        _print(json.dumps({"ok": True, "preview": _jsonable(preview)}, ensure_ascii=False), stream=sys.stdout)
        return 0

    if not args.input:
        parser.error("at least one input is required")

    input_paths = [Path(item) for item in args.input]
    output_arg = Path(args.output) if args.output else None
    if len(input_paths) > 1 and output_arg is not None and output_arg.suffix:
        parser.error("--output must be a folder when converting multiple inputs")

    if len(input_paths) == 1:
        output_path = _single_output_path(input_paths[0], output_arg, args.name_template)
        if input_paths[0].suffix.lower() == ".feedpak" or input_paths[0].is_dir():
            try:
                result = update_feedpak(
                    input_paths[0],
                    output_path,
                    metadata=_feedpak_metadata_args(args),
                    authors=_feedpak_authors(args.feedpak_authors_json),
                    cover_path=Path(args.feedpak_cover) if args.feedpak_cover else None,
                    remove_cover=args.feedpak_remove_cover,
                    separate_stems=args.separate_stems,
                    demucs_url=args.demucs_url,
                    demucs_api_key=args.demucs_api_key,
                    demucs_model=args.demucs_model,
                    demucs_stems=_split_csv(args.demucs_stems),
                    stem_updates=_json_arg(args.feedpak_stem_updates_json, "feedpak stem updates"),
                    remove_stems=_split_csv(args.feedpak_remove_stems),
                    overwrite=args.overwrite,
                )
            except Exception as exc:  # noqa: BLE001
                _print(f"error: {exc}", stream=sys.stderr)
                return 1
            _print(f"wrote {result.output_path}")
            if result.validation and result.validation.ok:
                _print(f"validated {result.output_path}")
            for warning in result.warnings:
                _print(f"warning: {warning.message}", stream=sys.stderr)
            return 0

        try:
            results = convert_psarc_songs(
                input_paths[0],
                output_path,
                archive=not args.directory,
                overwrite=args.overwrite,
                keep_workdir=args.keep_workdir,
                include_tones=not args.no_tones,
                b_standard_to_7_string=args.b_standard_to_7_string,
                separate_stems=args.separate_stems,
                demucs_url=args.demucs_url,
                demucs_api_key=args.demucs_api_key,
                demucs_model=args.demucs_model,
                demucs_stems=_split_csv(args.demucs_stems),
                rs1_songs_psarc=Path(args.rs1_songs_psarc) if args.rs1_songs_psarc else None,
            )
        except Exception as exc:  # noqa: BLE001
            _cleanup_failed_workdir(input_paths[0], output_path, archive=not args.directory)
            _print(f"error: {exc}", stream=sys.stderr)
            return 1

        for result in results:
            _print(f"wrote {result.output_path}")
            if result.validation and result.validation.ok:
                _print(f"validated {result.output_path}")
            for warning in result.warnings:
                _print(f"warning: {warning.message}", stream=sys.stderr)
        return 0

    batch = convert_many(
        input_paths,
        output_arg,
        output_layout=args.output_layout,
        name_template=args.name_template,
        source_root=Path(args.source_root) if args.source_root else None,
        archive=not args.directory,
        overwrite=args.overwrite,
        keep_workdir=args.keep_workdir,
        include_tones=not args.no_tones,
        b_standard_to_7_string=args.b_standard_to_7_string,
        separate_stems=args.separate_stems,
        demucs_url=args.demucs_url,
        demucs_api_key=args.demucs_api_key,
        demucs_model=args.demucs_model,
        demucs_stems=_split_csv(args.demucs_stems),
    )
    for item in batch.items:
        if item.succeeded and item.result is not None:
            _print(f"wrote {item.result.output_path}")
            if item.result.validation and item.result.validation.ok:
                _print(f"validated {item.result.output_path}")
            for warning in item.result.warnings:
                _print(f"warning: {warning.message}", stream=sys.stderr)
        else:
            _print(f"error converting {item.input_path}: {item.error}", stream=sys.stderr)
    return 0 if batch.ok else 1


def _single_output_path(input_path: Path, output_arg: Path | None, name_template: str = "{source}") -> Path | None:
    if output_arg is None:
        return None
    if output_arg.exists() and output_arg.is_dir():
        return _batch_output_path(input_path, output_arg, "flat", None, name_template)
    if not output_arg.suffix:
        return _batch_output_path(input_path, output_arg, "flat", None, name_template)
    return output_arg


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _feedpak_metadata_args(args: argparse.Namespace) -> dict[str, Any]:
    mapping = {
        "title": args.feedpak_title,
        "artist": args.feedpak_artist,
        "album": args.feedpak_album,
        "year": args.feedpak_year,
        "language": args.feedpak_language,
    }
    return {key: value for key, value in mapping.items() if value is not None}


def _feedpak_authors(value: str | None) -> list[dict[str, str]] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("--feedpak-authors-json must be a JSON array")
    return parsed


def _json_arg(value: str | None, label: str) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
