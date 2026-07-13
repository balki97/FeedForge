from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _convert_one(input_path: str, output_dir: str) -> dict[str, object]:
    from feedback_converter.converter import convert_psarc_songs

    source = Path(input_path)
    target = Path(output_dir) / f"{source.stem}.feedpak"
    started = time.time()
    results = convert_psarc_songs(
        source,
        target,
        archive=True,
        overwrite=True,
        keep_workdir=False,
        include_tones=True,
        separate_stems=False,
    )
    return {
        "input": str(source),
        "outputs": [str(result.output_path) for result in results],
        "warnings": [warning.message for result in results for warning in result.warnings],
        "seconds": round(time.time() - started, 3),
    }


def _safe_delete_output(output_dir: Path, dlc_dir: Path) -> None:
    resolved_output = output_dir.resolve()
    resolved_dlc = dlc_dir.resolve()
    if resolved_output.name.lower() != "feedpaks":
        raise RuntimeError(f"Refusing to delete non-Feedpaks output folder: {resolved_output}")
    if resolved_output.parent != resolved_dlc:
        raise RuntimeError(f"Refusing to delete output outside DLC folder: {resolved_output}")
    if resolved_output.exists():
        shutil.rmtree(resolved_output)
    resolved_output.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel reconvert a DLC PSARC folder into Feedpaks.")
    parser.add_argument(
        "--dlc-dir",
        default=r"E:\Games\RockSmith 2014\Rocksmith 2014 Edition - Remastered\dlc",
        help="Folder containing source PSARC files.",
    )
    parser.add_argument(
        "--output-dir",
        default=r"E:\Games\RockSmith 2014\Rocksmith 2014 Edition - Remastered\dlc\Feedpaks",
        help="Output Feedpaks folder. With --delete-output this must be named Feedpaks under --dlc-dir.",
    )
    parser.add_argument("--workers", type=int, default=max(1, min((os.cpu_count() or 4) - 1, 12)))
    parser.add_argument("--delete-output", action="store_true")
    args = parser.parse_args()

    dlc_dir = Path(args.dlc_dir)
    output_dir = Path(args.output_dir)
    if not dlc_dir.is_dir():
        raise FileNotFoundError(f"DLC folder not found: {dlc_dir}")

    sources = sorted(dlc_dir.glob("*.psarc"))
    if not sources:
        raise RuntimeError(f"No PSARC files found in {dlc_dir}")

    if args.delete_output:
        _safe_delete_output(output_dir, dlc_dir)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    progress_path = output_dir / "bulk-reconvert-progress.jsonl"
    failures_path = output_dir / "bulk-reconvert-failures.csv"
    summary_path = output_dir / "bulk-reconvert-summary.json"
    for path in (progress_path, failures_path, summary_path):
        if path.exists():
            path.unlink()

    total = len(sources)
    workers = max(1, min(int(args.workers), total))
    started = time.time()
    ok = 0
    failed = 0

    with failures_path.open("w", newline="", encoding="utf-8") as failure_file:
        failure_writer = csv.DictWriter(failure_file, fieldnames=["input", "error"])
        failure_writer.writeheader()
        with progress_path.open("a", encoding="utf-8") as progress_file:
            progress_file.write(
                json.dumps(
                    {
                        "event": "start",
                        "total": total,
                        "workers": workers,
                        "dlc_dir": str(dlc_dir),
                        "output_dir": str(output_dir),
                        "time": time.time(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            progress_file.flush()

            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_convert_one, str(path), str(output_dir)): path for path in sources}
                for future in as_completed(futures):
                    source = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001
                        failed += 1
                        failure_writer.writerow({"input": str(source), "error": str(exc)})
                        failure_file.flush()
                        event = {
                            "event": "failed",
                            "input": str(source),
                            "error": str(exc),
                            "done": ok + failed,
                            "total": total,
                            "time": time.time(),
                        }
                    else:
                        ok += 1
                        event = {
                            "event": "converted",
                            "input": result["input"],
                            "outputs": result["outputs"],
                            "warnings": result["warnings"],
                            "seconds": result["seconds"],
                            "done": ok + failed,
                            "total": total,
                            "time": time.time(),
                        }
                    progress_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                    progress_file.flush()
                    if (ok + failed) % 25 == 0 or failed:
                        elapsed = max(0.001, time.time() - started)
                        rate = (ok + failed) / elapsed
                        print(f"{ok + failed}/{total} done, ok={ok}, failed={failed}, {rate:.2f}/s", flush=True)

    summary = {
        "total": total,
        "ok": ok,
        "failed": failed,
        "workers": workers,
        "seconds": round(time.time() - started, 3),
        "output_dir": str(output_dir),
        "progress_log": str(progress_path),
        "failures_csv": str(failures_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
