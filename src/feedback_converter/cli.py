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
from feedback_converter.batch import convert_many
from feedback_converter.converter import convert_psarc
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
        "--keep-workdir",
        action="store_true",
        help="Keep the intermediate .feedpak.work directory when writing a zip archive.",
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
        try:
            result = convert_psarc(
                input_paths[0],
                output_arg,
                archive=not args.directory,
                overwrite=args.overwrite,
                keep_workdir=args.keep_workdir,
            )
        except Exception as exc:  # noqa: BLE001
            _cleanup_failed_workdir(input_paths[0], output_arg, archive=not args.directory)
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(f"wrote {result.output_path}")
        for warning in result.warnings:
            print(f"warning: {warning.message}", file=sys.stderr)
        return 0

    batch = convert_many(
        input_paths,
        output_arg,
        archive=not args.directory,
        overwrite=args.overwrite,
        keep_workdir=args.keep_workdir,
    )
    for item in batch.items:
        if item.succeeded and item.result is not None:
            print(f"wrote {item.result.output_path}")
            for warning in item.result.warnings:
                print(f"warning: {warning.message}", file=sys.stderr)
        else:
            print(f"error converting {item.input_path}: {item.error}", file=sys.stderr)
    return 0 if batch.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
