from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from feedback_converter.feedpak import inspect_feedpak, update_feedpak  # noqa: E402
from feedback_converter.inspector import inspect_psarc  # noqa: E402


@dataclass(frozen=True)
class PsarcCredit:
    path: Path
    title: str
    artist: str
    authors: list[dict[str, str]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill FeedPak author credits from matching PSARC files.")
    parser.add_argument("--psarc-dir", required=True, type=Path)
    parser.add_argument("--feedpak-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path, default=ROOT / "release" / "feedpak-author-backfill.csv")
    parser.add_argument("--json-report", type=Path, default=ROOT / "release" / "feedpak-author-backfill.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite-existing", action="store_true", help="Replace existing FeedPak authors when the PSARC has credits.")
    args = parser.parse_args()

    psarc_dir = args.psarc_dir
    feedpak_dir = args.feedpak_dir
    psarcs = sorted(psarc_dir.glob("*.psarc"))
    feedpaks = sorted(feedpak_dir.glob("*.feedpak"))
    if not psarcs:
        raise SystemExit(f"No PSARC files found in {psarc_dir}")
    if not feedpaks:
        raise SystemExit(f"No FeedPak files found in {feedpak_dir}")

    psarc_by_stem = {path.stem.lower(): path for path in psarcs}
    credit_cache: dict[Path, PsarcCredit] = {}

    rows: list[dict[str, Any]] = []
    unmatched: list[Path] = []
    direct_jobs = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for feedpak in feedpaks:
            psarc = psarc_by_stem.get(feedpak.stem.lower())
            if psarc:
                direct_jobs.append(pool.submit(process_pair, feedpak, psarc, args.dry_run, args.overwrite_existing))
            else:
                unmatched.append(feedpak)

        for index, future in enumerate(as_completed(direct_jobs), start=1):
            row = future.result()
            rows.append(row)
            psarc_path = Path(row["psarc"]) if row.get("psarc") else None
            if psarc_path and row.get("psarc_title"):
                credit_cache[psarc_path] = PsarcCredit(
                    path=psarc_path,
                    title=str(row.get("psarc_title") or ""),
                    artist=str(row.get("psarc_artist") or ""),
                    authors=json.loads(str(row.get("psarc_authors_json") or "[]")),
                )
            if index % 100 == 0:
                print(f"Processed {index}/{len(direct_jobs)} directly matched FeedPaks...")

    if unmatched:
        print(f"Resolving {len(unmatched)} renamed or unmatched FeedPaks by metadata...")
        ensure_psarc_cache(psarcs, credit_cache, workers=max(1, args.workers))
        by_song = build_song_index(credit_cache.values())
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            jobs = [
                pool.submit(process_renamed_feedpak, feedpak, by_song, args.dry_run, args.overwrite_existing)
                for feedpak in unmatched
            ]
            for future in as_completed(jobs):
                rows.append(future.result())

    rows.sort(key=lambda row: str(row.get("feedpak") or "").lower())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.report, rows)
    args.json_report.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "feedpaks": len(feedpaks),
        "updated": sum(1 for row in rows if row["status"] == "updated"),
        "unchanged": sum(1 for row in rows if row["status"] == "unchanged"),
        "skipped_existing": sum(1 for row in rows if row["status"] == "skipped_existing"),
        "no_author": sum(1 for row in rows if row["status"] == "no_author"),
        "no_match": sum(1 for row in rows if row["status"] == "no_match"),
        "failed": sum(1 for row in rows if row["status"] == "failed"),
        "dry_run": args.dry_run,
        "csv": str(args.report),
        "json": str(args.json_report),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 1


def process_pair(feedpak: Path, psarc: Path, dry_run: bool, overwrite_existing: bool) -> dict[str, Any]:
    try:
        credit = inspect_psarc_credit(psarc)
        feedpak_preview = inspect_feedpak(feedpak)
        existing = normalize_authors(feedpak_preview.get("authors"))
        return apply_credit(feedpak, credit, existing, dry_run=dry_run, overwrite_existing=overwrite_existing)
    except Exception as exc:  # noqa: BLE001
        return base_row(feedpak, psarc, status="failed", error=str(exc))


def process_renamed_feedpak(
    feedpak: Path,
    by_song: dict[tuple[str, str], PsarcCredit],
    dry_run: bool,
    overwrite_existing: bool,
) -> dict[str, Any]:
    try:
        feedpak_preview = inspect_feedpak(feedpak)
        key = song_key(feedpak_preview.get("artist"), feedpak_preview.get("title"))
        credit = by_song.get(key)
        if credit is None:
            return base_row(
                feedpak,
                None,
                feedpak_title=str(feedpak_preview.get("title") or ""),
                feedpak_artist=str(feedpak_preview.get("artist") or ""),
                existing_authors=normalize_authors(feedpak_preview.get("authors")),
                status="no_match",
            )
        existing = normalize_authors(feedpak_preview.get("authors"))
        return apply_credit(feedpak, credit, existing, dry_run=dry_run, overwrite_existing=overwrite_existing)
    except Exception as exc:  # noqa: BLE001
        return base_row(feedpak, None, status="failed", error=str(exc))


def apply_credit(
    feedpak: Path,
    credit: PsarcCredit,
    existing: list[dict[str, str]],
    *,
    dry_run: bool,
    overwrite_existing: bool,
) -> dict[str, Any]:
    authors = normalize_authors(credit.authors)
    row = base_row(
        feedpak,
        credit.path,
        psarc_title=credit.title,
        psarc_artist=credit.artist,
        psarc_authors=authors,
        existing_authors=existing,
    )
    if not authors:
        row["status"] = "no_author"
        return row
    if existing == authors:
        row["status"] = "unchanged"
        return row
    if existing and not overwrite_existing:
        row["status"] = "skipped_existing"
        return row
    row["new_authors"] = authors
    if not dry_run:
        update_feedpak(feedpak, authors=authors, overwrite=True)
    row["status"] = "updated"
    return row


def ensure_psarc_cache(psarcs: list[Path], cache: dict[Path, PsarcCredit], *, workers: int) -> None:
    missing = [path for path in psarcs if path not in cache]
    if not missing:
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = [pool.submit(inspect_psarc_credit, path) for path in missing]
        for index, future in enumerate(as_completed(jobs), start=1):
            try:
                credit = future.result()
                cache[credit.path] = credit
            except Exception as exc:  # noqa: BLE001
                print(f"Skipped PSARC metadata index entry: {exc}", file=sys.stderr)
            if index % 100 == 0:
                print(f"Indexed {index}/{len(missing)} additional PSARCs...")


def inspect_psarc_credit(psarc: Path) -> PsarcCredit:
    preview = inspect_psarc(psarc)
    return PsarcCredit(
        path=psarc,
        title=preview.title,
        artist=preview.artist,
        authors=normalize_authors(preview.authors),
    )


def build_song_index(credits: Any) -> dict[tuple[str, str], PsarcCredit]:
    result: dict[tuple[str, str], PsarcCredit] = {}
    for credit in credits:
        key = song_key(credit.artist, credit.title)
        if key == ("", "") or key in result:
            continue
        result[key] = credit
    return result


def song_key(artist: Any, title: Any) -> tuple[str, str]:
    return normalize_text(artist), normalize_text(title)


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").replace("-", " ").split())


def normalize_authors(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        role = str(item.get("role") or "charter").strip() or "charter"
        key = (name.casefold(), role.casefold())
        if key in seen:
            continue
        seen.add(key)
        rows.append({"name": name, "role": role})
    return rows


def base_row(
    feedpak: Path,
    psarc: Path | None,
    *,
    feedpak_title: str = "",
    feedpak_artist: str = "",
    psarc_title: str = "",
    psarc_artist: str = "",
    psarc_authors: list[dict[str, str]] | None = None,
    existing_authors: list[dict[str, str]] | None = None,
    status: str = "",
    error: str = "",
) -> dict[str, Any]:
    return {
        "feedpak": str(feedpak),
        "psarc": str(psarc or ""),
        "feedpak_title": feedpak_title,
        "feedpak_artist": feedpak_artist,
        "psarc_title": psarc_title,
        "psarc_artist": psarc_artist,
        "existing_authors": authors_text(existing_authors or []),
        "new_authors": "",
        "psarc_authors": authors_text(psarc_authors or []),
        "status": status,
        "error": error,
        "psarc_authors_json": json.dumps(psarc_authors or [], ensure_ascii=False),
    }


def authors_text(authors: list[dict[str, str]]) -> str:
    return "; ".join(f"{author['name']} ({author.get('role') or 'charter'})" for author in authors)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "feedpak",
        "psarc",
        "feedpak_title",
        "feedpak_artist",
        "psarc_title",
        "psarc_artist",
        "existing_authors",
        "psarc_authors",
        "new_authors",
        "status",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
