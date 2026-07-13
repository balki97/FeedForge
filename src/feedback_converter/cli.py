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
from feedback_converter.inspector import inspect_psarc


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
        "--inspect-json",
        action="store_true",
        help="Inspect one PSARC and write metadata JSON to stdout.",
    )
    parser.add_argument(
        "--inspect-cover-dir",
        help="Folder for cover art written during --inspect-json.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.inspect_json:
        if len(args.input) != 1:
            parser.error("--inspect-json requires exactly one input")
        try:
            cover_dir = Path(args.inspect_cover_dir) if args.inspect_cover_dir else None
            preview = inspect_psarc(Path(args.input[0]), cover_dir=cover_dir)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
            return 1
        print(json.dumps({"ok": True, "preview": _jsonable(preview)}, ensure_ascii=False), file=sys.stdout)
        return 0

    if not args.input:
        parser.error("at least one input is required")

    input_paths = [Path(item) for item in args.input]
    output_arg = Path(args.output) if args.output else None
    if len(input_paths) > 1 and output_arg is not None and output_arg.suffix:
        parser.error("--output must be a folder when converting multiple inputs")

    if len(input_paths) == 1:
        output_path = _single_output_path(input_paths[0], output_arg, args.name_template)
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
            )
        except Exception as exc:  # noqa: BLE001
            _cleanup_failed_workdir(input_paths[0], output_path, archive=not args.directory)
            print(f"error: {exc}", file=sys.stderr)
            return 1

        for result in results:
            print(f"wrote {result.output_path}")
            for warning in result.warnings:
                print(f"warning: {warning.message}", file=sys.stderr)
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
            print(f"wrote {item.result.output_path}")
            for warning in item.result.warnings:
                print(f"warning: {warning.message}", file=sys.stderr)
        else:
            print(f"error converting {item.input_path}: {item.error}", file=sys.stderr)
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


if __name__ == "__main__":
    raise SystemExit(main())
