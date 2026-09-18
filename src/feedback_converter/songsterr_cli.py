"""JSON bridge used by the Electron desktop shell."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import math
import urllib.parse
from pathlib import Path
from .feedpak import update_feedpak

from .songsterr import (
    feedpak_filename,
    fetch_synced_lyrics,
    inspect_songsterr,
    load_songsterr_selection,
    prepare_audio,
    prepare_cover,
    songsterr_to_tracks,
    write_feedpak,
    parse_lrc,
)


def progress(stage, **details):
    print("FEEDFORGE_PROGRESS " + json.dumps({"stage": stage, **details}), file=sys.stderr, flush=True)


def validate_url(value):
    value = str(value or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname not in {"songsterr.com", "www.songsterr.com"}
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.path.startswith("/a/wsa/") or len(value) > 2048):
        raise ValueError("Paste an HTTPS Songsterr tab link.")
    return value


def analyze(url):
    url = validate_url(url)
    progress("Reading song, arrangements and release artwork")
    song = inspect_songsterr(url)
    meta = song["meta"]
    progress("Finding synchronized lyrics")
    lyrics = fetch_synced_lyrics(
        meta.get("artist") or "", meta.get("title") or "",
        song.get("album") or "", song.get("duration"), song.get("video_url") or "",
    )
    tracks = [{key: track.get(key) for key in (
        "partId", "title", "instrument", "supported", "role",
        "isGuitar", "isBassGuitar", "isDrums",
    )} for track in song["tracks"]]
    authors = song.get("authors") or []
    return {
        "url": url, "song_id": meta.get("songId"),
        "title": meta.get("title") or "", "artist": meta.get("artist") or "",
        "album": song.get("album") or "", "year": song.get("year"),
        "duration": song.get("duration"), "video_url": song.get("video_url") or "",
        "cover_url": song.get("cover_url") or "", "cover_source": song.get("cover_source") or "",
        "release_id": song.get("release_id") or "", "genres": song.get("genres") or [],
        "author": ", ".join(item.get("name") or "" for item in authors if item.get("name")),
        "tracks": tracks, "selected_part_id": song["selected_part_id"], "lyrics": lyrics,
        "output_name": feedpak_filename(meta.get("artist") or "", meta.get("title") or "",
                                         song.get("album") or ""),
    }


def create(payload):
    validate_url(payload.get("url"))
    offset = float(payload.get("offset") or 0)
    if not math.isfinite(offset):
        raise ValueError("Chart offset must be a finite number of seconds.")
    progress("Downloading selected arrangements", title=payload.get("title"))
    inspection = inspect_songsterr(payload["url"], enrich=False)
    selected = list(dict.fromkeys(int(value) for value in payload["selected_parts"]))
    song = load_songsterr_selection(inspection, selected)
    arrangements, timeline = songsterr_to_tracks(song)
    roles = {int(key): value for key, value in (payload.get("roles") or {}).items()}
    names = {int(key): str(value).strip()
             for key, value in (payload.get("names") or {}).items() if str(value).strip()}
    for part_id, arrangement in zip(selected, arrangements):
        arrangement["role"] = roles.get(part_id) or arrangement.get("role")
        if arrangement["role"] and arrangement["role"] not in {"lead", "rhythm", "combo", "bass", "drums"}:
            raise ValueError("Unsupported arrangement role")
        arrangement["name"] = names.get(part_id) or arrangement.get("name")

    work = Path(tempfile.mkdtemp(prefix="feedforge-songsterr-audio-"))
    try:
        progress("Preparing audio", title=payload.get("title"))
        if not (payload.get("audio_path") or inspection.get("video_url")):
            raise ValueError("This song has no synchronized video. Choose a local audio file.")
        audio = prepare_audio(payload.get("audio_path") or inspection.get("video_url"), work)
        progress("Preparing artwork", title=payload.get("title"))
        cover = prepare_cover(payload.get("cover_path") or payload.get("cover_url"), work)
        author = str(payload.get("author") or "").strip()
        progress("Building and validating FeedPak", title=payload.get("title"))
        output = write_feedpak(
            arrangements, timeline, audio, payload["output_path"],
            title=payload.get("title") or inspection["meta"]["title"],
            artist=payload.get("artist") or inspection["meta"]["artist"],
            album=payload.get("album") or "", year=payload.get("year"),
            genres=payload.get("genres") or (),
            authors=([{"name": author, "role": "transcriber"}] if author else ()),
            cover_path=cover, lyrics=payload.get("lyrics") or (),
            lyrics_source="authored", source_urls=[payload["url"]],
            offset=offset,
        )
        warnings = (["Selected artwork could not be loaded; package has no cover."]
                    if (payload.get("cover_path") or payload.get("cover_url")) and not cover else [])
        if payload.get("separateStems"):
            progress("Separating audio stems", title=payload.get("title"))
            result = update_feedpak(
                output, separate_stems=True, overwrite=True,
                demucs_url=payload.get("demucsUrl"), demucs_api_key=payload.get("demucsApiKey"),
                demucs_model=payload.get("demucsModel"), demucs_stems=payload.get("demucsStems"),
            )
            warnings.extend(warning.message for warning in result.warnings)
        return {"output_path": str(output), "arrangements": len(arrangements),
                "lyrics": sum(str(event.get("w") or "").endswith("+")
                              for event in payload.get("lyrics") or ()),
                "warnings": warnings}
    finally:
        try:
            shutil.rmtree(work)
        except OSError as exc:
            progress("Temporary audio cleanup failed", detail=str(exc))


def dispatch(request):
    """Deliberate JSON contract shared by development and packaged FeedForge."""
    action, payload = request.get("action"), request.get("payload")
    if action == "analyze":
        return analyze(payload)
    if action == "create":
        return create(payload)
    if action == "lyrics":
        return fetch_synced_lyrics(payload.get("artist", ""), payload.get("title", ""),
                                  payload.get("album", ""), payload.get("duration"),
                                  payload.get("video_url", ""))
    if action == "lrc":
        return parse_lrc(payload)
    raise ValueError("Unknown Songsterr operation")


def create_batch(payloads):
    results = []
    for payload in payloads:
        try:
            results.append({"ok": True, **create(payload)})
        except Exception as exc:
            results.append({
                "ok": False,
                "title": payload.get("title") or payload.get("url") or "Song",
                "error": str(exc),
            })
    return {
        "results": results,
        "created": sum(bool(item["ok"]) for item in results),
        "failed": sum(not item["ok"] for item in results),
    }


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    analyze_parser = commands.add_parser("analyze")
    analyze_parser.add_argument("url")
    create_parser = commands.add_parser("create")
    create_parser.add_argument("payload", type=Path)
    batch_parser = commands.add_parser("batch")
    batch_parser.add_argument("payload", type=Path)
    lyrics_parser = commands.add_parser("lyrics")
    lyrics_parser.add_argument("--artist", required=True)
    lyrics_parser.add_argument("--title", required=True)
    lyrics_parser.add_argument("--album", default="")
    lyrics_parser.add_argument("--duration", type=float)
    lyrics_parser.add_argument("--video-url", default="")
    args = parser.parse_args(argv)
    if args.command == "analyze":
        result = analyze(args.url)
    elif args.command == "create":
        result = create(json.loads(args.payload.read_text(encoding="utf-8")))
    elif args.command == "batch":
        result = create_batch(json.loads(args.payload.read_text(encoding="utf-8")))
    else:
        result = fetch_synced_lyrics(
            args.artist, args.title, args.album, args.duration, args.video_url)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
