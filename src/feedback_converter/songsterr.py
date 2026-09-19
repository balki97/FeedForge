"""Create spec-valid FeedPaks from Songsterr tab links and song audio."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from difflib import SequenceMatcher
import gzip
import html
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from fractions import Fraction
from .package_io import write_manifest, write_archive
from .feedpak_validator import require_valid_feedpak
from .difficulty import ensure_difficulty
from pathlib import Path


FEEDPAK_VERSION = "1.19.0"
USER_AGENT = "SongsterrFeedPakCreator/0.2 (https://github.com/balki97/FeedForge)"
_PART_CDNS = ("dqsljvtekg760", "d34shlm8p2ums2", "d3cqchs6g3b5ew")
_STATE_RE = re.compile(r'<script[^>]+id=["\']state["\'][^>]*>(.*?)</script>', re.S | re.I)
_PART_RE = re.compile(r"s\d+t(\d+)(?:\D|$)", re.I)


def _get_bytes(url):
    request = urllib.request.Request(str(url), headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html,*/*",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        if not 100 <= exc.code < 200:
            raise
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise
        result = subprocess.run(
            [curl, "-L", "--fail", "--silent", "--show-error", str(url)],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
        data = result.stdout
    return gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data


def _page_state(url):
    text = _get_bytes(url).decode("utf-8")
    match = _STATE_RE.search(text)
    if not match:
        raise ValueError("Songsterr page did not contain tab metadata")
    return json.loads(html.unescape(match.group(1)))


def _part_id(url, meta):
    match = _PART_RE.search(str(url).split("?", 1)[0])
    return int(match.group(1)) if match else int(meta.get("partId", 0))


def _download_part(meta, part_id):
    song_id, revision_id = int(meta["songId"]), int(meta["revisionId"])
    image = str(meta.get("image") or "")
    errors = []
    for domain in _PART_CDNS:
        if image:
            url = f"https://{domain}.cloudfront.net/{song_id}/{revision_id}/{image}/{part_id}.json"
        else:
            url = f"https://{domain}.cloudfront.net/part/{revision_id}/{part_id}"
        try:
            return json.loads(_get_bytes(url))
        except Exception as exc:  # try Songsterr's next public CDN mirror
            errors.append(str(exc))
    raise RuntimeError(f"Could not download Songsterr track {part_id}: {errors[-1]}")


def _main_video(meta):
    if not meta.get("revisionId"):
        return None
    try:
        videos = json.loads(_get_bytes(
            f"https://www.songsterr.com/api/video-points/{meta['songId']}/"
            f"{meta['revisionId']}/list"))
    except Exception:
        return None
    # Solo/backing variants are not complete recordings. Alternatives carry
    # their own sync points and must remain paired with those recordings.
    usable = sorted((video for video in videos if video.get("status") == "done"
                     and video.get("videoId") and video.get("feature") in (None, "", "alternative")),
                    key=lambda video: bool(video.get("feature")))
    return {**usable[0], "alternatives": usable[1:]} if usable else None


def _youtube_metadata(video_url):
    if not video_url:
        return {}
    video_id = video_url.rsplit("/", 1)[-1].split("?", 1)[0]
    result = {"cover_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                               "skip_download": True, "noplaylist": True}) as downloader:
            info = downloader.extract_info(video_url, download=False)
        result.update({
            "album": info.get("album") or "",
            "year": info.get("release_year"),
            "duration": info.get("duration"),
            "cover_url": info.get("thumbnail") or result["cover_url"],
        })
    except Exception:
        pass
    return result


def _release_artwork(artist, title, album="", year=None):
    """Find the song's original studio release and front art."""
    query = f'recording:"{title}" AND artist:"{artist}"'
    url = ("https://musicbrainz.org/ws/2/recording/?" + urllib.parse.urlencode({
        "query": query, "fmt": "json", "limit": 50,
    }))
    try:
        result = json.loads(_get_bytes(url))
    except Exception:
        return {}

    normalized_title = re.sub(r"\W+", "", str(title).casefold())
    normalized_album = re.sub(r"\W+", "", str(album).casefold())
    candidates = []
    seen = set()
    non_studio = {"live", "compilation", "remix", "soundtrack", "spokenword", "audiobook"}
    for recording in result.get("recordings") or []:
        recording_title = re.sub(r"\W+", "", str(recording.get("title") or "").casefold())
        score = int(recording.get("score") or 0)
        for release in recording.get("releases") or []:
            release_id = release.get("id")
            if not release_id or release_id in seen:
                continue
            seen.add(release_id)
            group = release.get("release-group") or {}
            secondary = {str(value).replace(" ", "").casefold()
                         for value in group.get("secondary-types") or []}
            release_year = str(release.get("date") or "")[:4]
            release_album = group.get("title") or release.get("title") or ""
            candidate_rank = (
                recording_title != normalized_title,
                release.get("status") != "Official",
                str(group.get("primary-type") or "").casefold() != "album",
                bool(secondary & non_studio),
                not release_year.isdigit(),
                int(release_year) if release_year.isdigit() else 9999,
                -score,
                bool(normalized_album) and
                re.sub(r"\W+", "", str(release_album).casefold()) != normalized_album,
            )
            candidates.append((candidate_rank, release, group, release_album))

    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0])
    _, best, best_group, best_album = candidates[0]
    best_group_id = best_group.get("id")
    best_album_key = re.sub(r"\W+", "", str(best_album).casefold())
    matching_releases = [item[1] for item in candidates if
                         (best_group_id and item[2].get("id") == best_group_id) or
                         (not best_group_id and re.sub(
                             r"\W+", "", str(item[3]).casefold()) == best_album_key)]
    cover_url = ""
    cover_release_id = ""
    for release in matching_releases[:8]:
        release_id = release.get("id")
        try:
            images = json.loads(_get_bytes(
                f"https://coverartarchive.org/release/{release_id}/")).get("images") or []
        except Exception:
            continue
        front = next((image for image in images if image.get("front")), None)
        if not front:
            continue
        thumbnails = front.get("thumbnails") or {}
        cover_url = thumbnails.get("500") or thumbnails.get("1200") or front.get("image")
        cover_release_id = release_id
        break

    release_year = str(best.get("date") or "")[:4]
    return {
        "album": best_album or album,
        "year": int(release_year) if release_year.isdigit() else year,
        "cover_url": str(cover_url or "").replace("http://", "https://", 1),
        "release_id": cover_release_id or best.get("id") or "",
        "cover_source": "Cover Art Archive" if cover_url else "MusicBrainz",
    }


def _parse_lrc_text(text):
    stamp = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
    events = []
    for line in str(text).splitlines():
        matches = list(stamp.finditer(line))
        words = stamp.sub("", line).strip()
        if not matches or not words:
            continue
        for match in matches:
            fraction = match.group(3) or "0"
            seconds = int(match.group(1)) * 60 + int(match.group(2)) + int(fraction) / 10 ** len(fraction)
            events.append({"t": round(seconds, 3), "w": words + "+"})
    events.sort(key=lambda item: item["t"])
    if not events:
        raise ValueError("The synchronized lyrics contain no timestamped lines.")
    for index, event in enumerate(events):
        next_time = events[index + 1]["t"] if index + 1 < len(events) else event["t"] + 2.0
        event["d"] = round(max(0.05, next_time - event["t"]), 3)
    return events


def _timed_lyric_lines(lines):
    """Keep editable full lines while adding FeedBack-compatible word events."""
    result = []
    for line in lines:
        text = str(line.get("w") or "").removesuffix("+").strip()
        words = text.split()
        if not words:
            continue
        duration = max(.05, float(line.get("d") or 2))
        spoken = min(duration, max(1.0, len(words) * .65))
        weights = [max(1, len(re.sub(r"\W", "", word))) ** .5 for word in words]
        total, cursor, timed = sum(weights), float(line["t"]), []
        for index, (word, weight) in enumerate(zip(words, weights)):
            word_duration = spoken * weight / total
            timed.append({
                "t": round(cursor, 3), "d": round(max(.05, word_duration), 3),
                "w": word + ("+" if index == len(words) - 1 else ""),
            })
            cursor += word_duration
        result.append({**line, "w": text + "+", "words": timed})
    return result


def _lyric_result(record, method, confidence=1.0):
    synced = record.get("syncedLyrics")
    if not synced:
        return {}
    return {
        "id": record.get("id"), "provider": "LRCLIB", "match_method": method,
        "confidence": round(confidence, 3),
        "events": _timed_lyric_lines(_parse_lrc_text(synced)),
        "plain": record.get("plainLyrics") or "",
        "matched_title": record.get("trackName") or "",
        "matched_artist": record.get("artistName") or "",
        "matched_album": record.get("albumName") or "",
        "duration": record.get("duration"),
    }


def _lyric_name(value):
    value = re.sub(r"\([^)]*(?:official|video|audio|live|remaster|feat)[^)]*\)", " ",
                   str(value or ""), flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _lyric_score(record, artist, title, album, duration):
    similarity = lambda left, right: SequenceMatcher(None, _lyric_name(left), _lyric_name(right)).ratio()
    title_score = similarity(record.get("trackName"), title)
    artist_score = similarity(record.get("artistName"), artist)
    album_score = similarity(record.get("albumName"), album) if album else 1.0
    record_duration = record.get("duration")
    duration_score = (max(0.0, 1.0 - abs(float(record_duration) - float(duration)) / 30.0)
                      if record_duration and duration else 1.0)
    total = title_score * .55 + artist_score * .25 + album_score * .1 + duration_score * .1
    return total if title_score >= .62 and artist_score >= .5 else 0.0


def _youtube_caption_lyrics(video_url):
    if not video_url:
        return {}
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                               "skip_download": True, "noplaylist": True}) as downloader:
            info = downloader.extract_info(video_url, download=False)
        groups = [("authored", info.get("subtitles") or {}),
                  ("automatic", info.get("automatic_captions") or {})]
        for kind, tracks in groups:
            ordered = sorted(tracks, key=lambda language: (
                not language.endswith("-orig"), not language.startswith("en"), language))
            if kind == "automatic":
                ordered = [language for language in ordered
                           if language.endswith("-orig") or language.startswith("en")]
            for language in ordered:
                formats = tracks.get(language) or []
                selected = next((item for item in formats if item.get("ext") == "json3"), None)
                if not selected or not selected.get("url"):
                    continue
                payload = json.loads(_get_bytes(selected["url"]))
                events = []
                for event in payload.get("events") or []:
                    words = "".join(segment.get("utf8") or "" for segment in event.get("segs") or [])
                    words = re.sub(r"\s+", " ", words).strip(" ♪\n\t")
                    if not words or re.fullmatch(r"\[[^]]+\]", words):
                        continue
                    start = round(float(event.get("tStartMs", 0)) / 1000, 3)
                    length = round(max(.05, float(event.get("dDurationMs", 2000)) / 1000), 3)
                    if events and events[-1]["w"] == words + "+":
                        continue
                    events.append({"t": start, "d": length, "w": words + "+"})
                if len(events) >= 3:
                    return {
                        "provider": f"YouTube {kind} captions", "match_method": "captions",
                        "confidence": .6 if kind == "authored" else .45,
                        "events": _timed_lyric_lines(events),
                        "matched_title": info.get("title") or "", "matched_artist": "",
                        "matched_album": "", "duration": info.get("duration"),
                        "language": language,
                    }
    except Exception:
        pass
    return {}


def _netease_lyrics(artist, title, album, duration):
    """Use Lyrically's public NetEase bridge only when the catalog match is strong."""
    try:
        search_url = "https://lyrics.paxsenix.org/netease/search?" + urllib.parse.urlencode({
            "q": f"{artist} {title}"})
        songs = json.loads(_get_bytes(search_url)).get("result", {}).get("songs") or []
        candidates = []
        for song in songs:
            record = {
                "trackName": song.get("name"),
                "artistName": ", ".join(item.get("name") or "" for item in song.get("artists") or []),
                "albumName": (song.get("album") or {}).get("name"),
                "duration": float(song.get("duration") or 0) / 1000,
            }
            candidates.append((_lyric_score(record, artist, title, album, duration), song, record))
        score, song, record = max(candidates, default=(0, None, None), key=lambda item: item[0])
        if score < .65:
            return {}
        lyric_url = "https://lyrics.paxsenix.org/netease/lyrics?" + urllib.parse.urlencode({
            "id": song["id"], "v": 2})
        payload = json.loads(_get_bytes(lyric_url))
        raw = (((payload.get("metadata") or {}).get("rawData") or {}).get("lrc") or {}).get("lyric")
        if not raw:
            return {}
        events = _parse_lrc_text(raw)
        events = [event for event in events if not (
            event["t"] < 5 and re.match(
                r"^(?:作词|作曲|编曲|lyricist|composer|arranger)\s*[:：]",
                event["w"], re.I))]
        return {
            "id": song["id"], "provider": "NetEase via Lyrically",
            "match_method": "catalog", "confidence": round(score, 3),
            "events": _timed_lyric_lines(events),
            "matched_title": record["trackName"], "matched_artist": record["artistName"],
            "matched_album": record["albumName"], "duration": record["duration"],
        }
    except Exception:
        return {}


def fetch_synced_lyrics(artist, title, album="", duration=None, video_url=""):
    """Find timed lyrics through exact, tolerant-search, captions, then catalog."""
    if album and duration:
        url = "https://lrclib.net/api/get?" + urllib.parse.urlencode({
            "artist_name": artist, "track_name": title, "album_name": album,
            "duration": round(float(duration)),
        })
        try:
            result = _lyric_result(json.loads(_get_bytes(url)), "exact")
            if result:
                return result
        except Exception:
            pass

    searches = [
        {"track_name": title, "artist_name": artist, **({"album_name": album} if album else {})},
        {"q": f"{artist} {title}"},
    ]
    records = {}
    for query in searches:
        try:
            time.sleep(.25)
            url = "https://lrclib.net/api/search?" + urllib.parse.urlencode(query)
            for record in json.loads(_get_bytes(url)):
                if record.get("syncedLyrics"):
                    records[record.get("id") or json.dumps(record, sort_keys=True)] = record
        except Exception:
            continue
    if records:
        scored = sorted(((_lyric_score(record, artist, title, album, duration), record)
                         for record in records.values()), key=lambda item: item[0], reverse=True)
        if scored[0][0] >= .65:
            result = _lyric_result(scored[0][1], "search", scored[0][0])
            if result:
                return result

    captions = _youtube_caption_lyrics(video_url)
    if captions:
        return captions
    catalog = _netease_lyrics(artist, title, album, duration)
    if catalog:
        return catalog
    return {
        "provider": "", "events": [], "match_method": "none",
        "message": "No reliable timed lyrics were found in the available catalogs or Songsterr video captions.",
    }


def _arrangement_roles(tracks):
    guitar_ids = [int(track.get("partId", index)) for index, track in enumerate(tracks)
                  if track.get("isGuitar")]
    roles = {}
    for index, track in enumerate(tracks):
        pid = int(track.get("partId", index))
        title = f"{track.get('title', '')} {track.get('instrument', '')}".lower()
        if track.get("isDrums"):
            roles[pid] = "drums"
        elif track.get("isBassGuitar"):
            roles[pid] = "bass"
        elif "rhythm" in title:
            roles[pid] = "rhythm"
        elif "lead" in title or "solo" in title:
            roles[pid] = "lead"
        elif track.get("isGuitar"):
            position = guitar_ids.index(pid)
            roles[pid] = "lead" if position == 0 else "rhythm" if position == 1 else "combo"
    return roles


def inspect_songsterr(url, enrich=True):
    """Return the song, supported arrangements, and Songsterr's main video sync."""
    url = str(url).strip()
    current = ((_page_state(url).get("meta") or {}).get("current"))
    if not current:
        raise ValueError("Songsterr tab metadata is unavailable")
    match = re.search(r"-s(\d+)", url, re.I)
    if not match or int(match.group(1)) != int(current["songId"]):
        raise ValueError("Enter a Songsterr song tab link")
    video = _main_video(current)
    video_url = f"https://youtu.be/{video['videoId']}" if video else ""
    video_meta = _youtube_metadata(video_url) if enrich else {}
    release = _release_artwork(
        current.get("artist") or "", current.get("title") or "",
        current.get("album") or "", current.get("year"),
    ) if enrich else {}
    roles = _arrangement_roles(current.get("tracks") or [])
    tracks = []
    for index, track in enumerate(current.get("tracks") or []):
        item = dict(track)
        item["partId"] = int(item.get("partId", index))
        item["supported"] = bool(item.get("isGuitar") or item.get("isBassGuitar")
                                 or item.get("isDrums"))
        item["role"] = roles.get(item["partId"], "")
        tracks.append(item)
    author = current.get("author") or {}
    return {
        "meta": current, "tracks": tracks, "urls": [url],
        "selected_part_id": _part_id(url, current),
        "video_url": video_url,
        "video_candidates": [{"url": f"https://youtu.be/{item['videoId']}",
                              "points": list(item.get("points") or [])}
                             for item in ([video] + video.get("alternatives", []) if video else [])],
        "video_points": list(video.get("points") or []) if video else [],
        "album": release.get("album") or current.get("album") or "",
        "year": release.get("year") or current.get("year"),
        "duration": video_meta.get("duration"),
        "cover_url": release.get("cover_url") or "",
        "cover_source": release.get("cover_source") or "",
        "release_id": release.get("release_id") or "",
        "genres": list(dict.fromkeys(tag.strip() for tag in current.get("tags") or []
                                      if isinstance(tag, str) and tag.strip())),
        "authors": ([{"name": author.get("name") or author.get("profileName"),
                      "role": "transcriber"}]
                    if author.get("name") or author.get("profileName") else []),
    }


def load_songsterr_selection(inspection, part_ids):
    """Download the arrangements selected from an inspection result."""
    meta = inspection["meta"]
    tracks_by_id = {int(track["partId"]): track for track in inspection["tracks"]}
    parts = []
    for pid in dict.fromkeys(map(int, part_ids)):
        track = tracks_by_id.get(pid)
        if not track:
            raise ValueError(f"Songsterr track t{pid} does not exist")
        if not track.get("supported"):
            raise ValueError(f"{track.get('title') or f'Track {pid + 1}'} is not chartable yet")
        part = _download_part(meta, pid)
        part["title"] = track.get("title") or f"Track {pid + 1}"
        parts.append(part)
    if not parts:
        raise ValueError("Select at least one chartable arrangement")
    return {**inspection, "parts": parts}


def load_songsterr(urls):
    """Load the exact public score data used by Songsterr's browser player."""
    urls = [str(url).strip() for url in urls if str(url).strip()]
    if not urls:
        raise ValueError("Enter at least one Songsterr tab link")
    meta = None
    song_id = None
    part_ids = []
    for url in urls:
        current = ((_page_state(url).get("meta") or {}).get("current"))
        if not current:
            raise ValueError("Songsterr tab metadata is unavailable")
        current_song_id = int(current["songId"])
        if song_id is None:
            meta, song_id = current, current_song_id
        match = re.search(r"-s(\d+)", url, re.I)
        if not match or int(match.group(1)) != song_id or current_song_id != song_id:
            raise ValueError("All Songsterr links must belong to the same song")
        pid = _part_id(url, current)
        if pid not in part_ids:
            part_ids.append(pid)
    tracks_by_id = {int(track.get("partId", index)): track
                    for index, track in enumerate(meta.get("tracks") or [])}
    parts = []
    for pid in part_ids:
        if pid not in tracks_by_id:
            raise ValueError(f"Songsterr track t{pid} does not exist")
        part = _download_part(meta, pid)
        part["title"] = tracks_by_id[pid].get("title") or f"Track {pid + 1}"
        parts.append(part)
    video = _main_video(meta)
    return {
        "meta": meta, "parts": parts, "urls": urls,
        "video_url": f"https://youtu.be/{video['videoId']}" if video else "",
        "video_points": list(video.get("points") or []) if video else [],
    }


def _quarter_bpm(event):
    return float(event.get("bpm", 120)) * 4.0 / float(event.get("type", 4) or 4)


def _playback_order(measures):
    order, repeat_start = [], 0
    for index, measure in enumerate(measures):
        if measure.get("repeatStart"):
            repeat_start = index
        order.append(index)
        repeat = int(measure.get("repeat", 0) or 0)
        if repeat > 1:
            # ponytail: alternate endings need a score that actually uses them.
            order.extend(list(range(repeat_start, index + 1)) * (repeat - 1))
            repeat_start = index + 1
    return order


def _curve_seconds(length, start_bpm, end_bpm, linear):
    if not linear or abs(end_bpm - start_bpm) < 1e-9:
        return 240.0 * length / start_bpm
    return 240.0 * length * math.log(end_bpm / start_bpm) / (end_bpm - start_bpm)


def _position_time(info, position):
    position = max(0.0, min(float(position), info["length"]))
    for segment in info["segments"]:
        if position <= segment["p1"]:
            fraction = ((position - segment["p0"]) / (segment["p1"] - segment["p0"])
                        if segment["p1"] > segment["p0"] else 0.0)
            end_bpm = segment["b0"] + (segment["b1"] - segment["b0"]) * fraction
            raw = segment["s0"] + _curve_seconds(
                position - segment["p0"], segment["b0"], end_bpm, segment["linear"])
            return info["start"] + raw * info["scale"]
    return info["start"] + info["raw_duration"] * info["scale"]


def build_timeline(parts, video_points=()):
    """Build exact measure starts, tempo map, meter map, beats, and sections."""
    if not parts:
        raise ValueError("Songsterr returned no tracks")
    primary = parts[0]
    measures = primary.get("measures") or []
    tempo_events = sorted((primary.get("automations") or {}).get("tempo") or [],
                          key=lambda event: (int(event.get("measure", 0)),
                                             float(event.get("position", 0))))
    if not tempo_events:
        tempo_events = [{"measure": 0, "position": 0, "bpm": 120, "type": 4}]
    signature, source_settings, source_starts = [4, 4], [], []
    source_position = 0.0
    for measure in measures:
        if measure.get("signature"):
            signature = [int(x) for x in measure["signature"]]
        length = signature[0] / signature[1]
        source_starts.append(source_position)
        source_settings.append((length, signature[:]))
        source_position += length

    point_map = {}
    for event in tempo_events:
        measure_index = int(event.get("measure", 0))
        if not 0 <= measure_index < len(measures):
            continue
        position = float(event.get("position", 0) or 0)
        length = source_settings[measure_index][0]
        if not 0 <= position <= length:
            raise ValueError(f"Songsterr tempo position {position} is outside measure {measure_index + 1}")
        point_map[source_starts[measure_index] + position] = {
            "bpm": _quarter_bpm(event), "linear": bool(event.get("linear"))}
    point_map.setdefault(0.0, {"bpm": _quarter_bpm(tempo_events[0]), "linear": False})
    tempo_points = sorted((position, value["bpm"], value["linear"])
                          for position, value in point_map.items())
    tempo_positions = [point[0] for point in tempo_points]

    def tempo_segment(position):
        index = max(0, bisect_right(tempo_positions, position) - 1)
        point_position, bpm, linear = tempo_points[index]
        if linear and index + 1 < len(tempo_points):
            next_position, next_bpm, _ = tempo_points[index + 1]
            if next_position > point_position:
                bpm += (next_bpm - bpm) * (position - point_position) / (next_position - point_position)
        return index, bpm, linear

    order = _playback_order(measures)
    points = [float(value) for value in video_points]
    starts, measure_info, beats = [], [], []
    tempos, signatures = [], []
    time = 0.0
    previous_signature = None
    previous_bpm = None
    for playback_index, source_index in enumerate(order):
        length, signature = source_settings[source_index]
        numerator, denominator = signature
        source_start = source_starts[source_index]
        boundaries = ([source_start] +
                      [value for value in tempo_positions if source_start < value < source_start + length] +
                      [source_start + length])
        segments, raw_time = [], 0.0
        for start_position, end_position in zip(boundaries, boundaries[1:]):
            point_index, start_bpm, linear = tempo_segment(start_position)
            if linear and point_index + 1 < len(tempo_points):
                next_position, next_bpm, _ = tempo_points[point_index + 1]
                end_bpm = (start_bpm + (next_bpm - start_bpm)
                           * (end_position - start_position) / (next_position - start_position)
                           if next_position > start_position else next_bpm)
            else:
                end_bpm = start_bpm
            segment = {
                "p0": start_position - source_start, "p1": end_position - source_start,
                "b0": start_bpm, "b1": end_bpm, "linear": linear, "s0": raw_time,
            }
            raw_time += _curve_seconds(end_position - start_position,
                                       start_bpm, end_bpm, linear)
            segments.append(segment)

        # Songsterr occasionally stops its video anchor list before the score ends.
        # Use the reliable prefix, then continue from the authored tempo map.
        start_time = points[playback_index] if playback_index < len(points) else time
        target_duration = raw_time
        if playback_index + 1 < len(points):
            anchored = points[playback_index + 1] - start_time
            if anchored > 0:
                target_duration = anchored
        scale = target_duration / raw_time if raw_time > 0 else 1.0
        info = {
            "start": start_time, "length": length, "segments": segments,
            "scale": scale, "raw_duration": raw_time,
            "signature": signature[:], "source": source_index,
        }
        for segment in segments:
            event_time = _position_time(info, segment["p0"])
            bpm = segment["b0"] / scale
            if previous_bpm is None or abs(bpm - previous_bpm) > 0.0001:
                tempos.append({"time": round(event_time, 6), "bpm": round(bpm, 6)})
                previous_bpm = bpm
        if signature != previous_signature:
            signatures.append({"time": round(start_time, 6), "ts": signature[:]})
        previous_signature = signature[:]
        starts.append(start_time)
        measure_info.append(info)
        for beat in range(numerator):
            beats.append({"time": round(_position_time(info, beat / denominator), 6),
                          "measure": playback_index + 1 if beat == 0 else -1})
        time = start_time + target_duration
    if order:
        beats.append({"time": round(time, 6), "measure": len(order) + 1})

    sections, section_counts = [], {}
    for index, source_index in enumerate(order):
        marker = next((
            (part.get("measures") or [])[source_index].get("marker")
            or (part.get("measures") or [])[source_index].get("section")
            for part in parts if source_index < len(part.get("measures") or [])
            and ((part.get("measures") or [])[source_index].get("marker")
                 or (part.get("measures") or [])[source_index].get("section"))
        ), None)
        if isinstance(marker, dict):
            marker = marker.get("name") or marker.get("text")
        if isinstance(marker, str) and marker.strip():
            name = re.sub(r"\s+(?:#?\d+|[ivx]+)$", "", marker.strip().lower())
            name = re.sub(r"[-_\s]+", " ", name).strip()
            name = {"chours": "chorus", "pre chorus": "prechorus",
                    "post chorus": "postchorus"}.get(name, name)
            section_counts[name] = section_counts.get(name, 0) + 1
            sections.append({"name": name, "number": section_counts[name],
                             "time": round(starts[index], 6)})
    if not sections:
        sections.append({"name": "intro", "number": 1, "time": 0.0})
    elif sections[0]["time"] > 0:
        sections.insert(0, {"name": "intro", "number": 1, "time": 0.0})
    return {
        "version": 1, "tempos": tempos, "time_signatures": signatures,
        "beats": beats, "sections": sections, "measure_info": measure_info,
        "measure_order": order, "duration": time,
    }


def _tuning(part):
    values = list(reversed([int(value) for value in part.get("tuning") or []]))
    count = len(values)
    is_bass = "bass" in str(part.get("instrument", "")).lower()
    if is_bass:
        standard = [23, 28, 33, 38, 43][-count:]
    else:
        standard = [30, 35, 40, 45, 50, 55, 59, 64][-count:]
    return [value - base for value, base in zip(values, standard)]


_CHORD_FORMULAS = (
    ("maj7", (0, 4, 7, 11)), ("7", (0, 4, 7, 10)),
    ("m7", (0, 3, 7, 10)), ("mMaj7", (0, 3, 7, 11)),
    ("m7b5", (0, 3, 6, 10)), ("dim7", (0, 3, 6, 9)),
    ("6", (0, 4, 7, 9)), ("m6", (0, 3, 7, 9)),
    ("", (0, 4, 7)), ("m", (0, 3, 7)), ("dim", (0, 3, 6)),
    ("aug", (0, 4, 8)), ("sus4", (0, 5, 7)),
    ("sus2", (0, 2, 7)), ("5", (0, 7)),
)
_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_DRUM_MIDI = {
    27: "bell", 30: "stack", 35: "kick", 36: "kick", 37: "snare_xstick",
    38: "snare", 40: "snare", 41: "tom_floor", 43: "tom_low",
    45: "tom_mid", 47: "tom_mid", 48: "tom_hi", 50: "tom_hi",
    42: "hh_closed", 44: "hh_pedal", 46: "hh_open",
    49: "crash_l", 57: "crash_r", 55: "splash", 52: "china",
    51: "ride", 59: "ride", 53: "ride_bell", 80: "bell",
    # Songsterr extensions: rim-shot, half-open hat, ride edge, and chokes.
    91: "snare", 92: "hh_open", 93: "ride", 94: "ride",
    95: "splash", 96: "china", 97: "crash_l", 98: "crash_r",
    # FeedBack has no claves lane; cross-stick is the closest playable lane.
    75: "snare_xstick",
    # GM auxiliary percussion stays on distinct, readable custom lanes.
    60: "bongo_hi", 61: "bongo_low", 62: "conga_mute",
    63: "conga_open", 64: "conga_low", 65: "timbale_hi",
    76: "woodblock_hi", 85: "castanets",
}
_DRUM_NAMES = {
    "kick": "Kick", "snare": "Snare", "snare_xstick": "Cross-stick",
    "tom_hi": "High tom", "tom_mid": "Mid tom", "tom_low": "Low tom",
    "tom_floor": "Floor tom", "hh_closed": "Hi-hat (closed)",
    "hh_open": "Hi-hat (open / half-open)", "hh_pedal": "Hi-hat (pedal)",
    "stack": "Stack", "crash_l": "Crash (left)", "crash_r": "Crash (right)",
    "splash": "Splash", "china": "China", "ride": "Ride",
    "ride_bell": "Ride bell", "bell": "Bell",
    "bongo_hi": "High bongo", "bongo_low": "Low bongo",
    "conga_mute": "Muted high conga", "conga_open": "Open high conga",
    "conga_low": "Low conga", "timbale_hi": "High timbale",
    "woodblock_hi": "High wood block", "castanets": "Castanets",
}
_VELOCITIES = {"ppp": 35, "pp": 51, "p": 67, "mp": 80,
               "mf": 87, "f": 95, "ff": 111, "fff": 127}
_CYMBAL_PIECES = {"stack", "crash_l", "crash_r", "splash", "china",
                  "ride", "ride_bell", "bell", "hh_closed", "hh_open"}


def _drum_velocities(measures):
    """Resolve explicit dynamics and Songsterr crescendo runs to MIDI velocity."""
    values = {}
    voice_count = max((len(measure.get("voices") or []) for measure in measures), default=0)
    for voice_index in range(voice_count):
        sequence = [(measure_index, beat_index, beat)
                    for measure_index, measure in enumerate(measures)
                    if voice_index < len(measure.get("voices") or [])
                    for beat_index, beat in enumerate(measure["voices"][voice_index].get("beats") or [])]
        index = 0
        while index < len(sequence):
            measure_index, beat_index, beat = sequence[index]
            gradual = str(beat.get("gradualVelocity") or "")
            if not gradual:
                values[(measure_index, voice_index, beat_index)] = _VELOCITIES.get(
                    str(beat.get("velocity", "")), 100)
                index += 1
                continue
            end = index + 1
            while end < len(sequence) and str(sequence[end][2].get("gradualVelocity") or "") == gradual:
                end += 1
            start_velocity = values.get((sequence[index - 1][0], voice_index, sequence[index - 1][1]), 100) \
                if index else 100
            next_velocity = (_VELOCITIES.get(str(sequence[end][2].get("velocity", "")))
                             if end < len(sequence) else None)
            if next_velocity is None:
                next_velocity = 127 if gradual == "crescendo" else 67
            for offset, (run_measure, run_beat, _beat) in enumerate(sequence[index:end], 1):
                values[(run_measure, voice_index, run_beat)] = round(
                    start_velocity + (next_velocity - start_velocity) * offset / (end - index))
            index = end
    return values


def _chord_name(notes, tuning):
    """Name only exact, unambiguous pitch sets; unknown shapes stay unlabeled."""
    if not tuning or any(note["s"] >= len(tuning) for note in notes):
        return ""
    pitches = [tuning[note["s"]] + note["f"] for note in notes
               if not note.get("mt") and not note.get("ig")]
    pcs = sorted({pitch % 12 for pitch in pitches})
    if not pcs:
        return ""
    if len(pcs) == 1:
        return _NOTE_NAMES[pcs[0]]
    present, matches = set(pcs), []
    for suffix, intervals in _CHORD_FORMULAS:
        if len(intervals) != len(pcs):
            continue
        for root in range(12):
            if all((root + interval) % 12 in present for interval in intervals):
                matches.append((root, suffix))
    if not matches:
        return ""
    bass = min(pitches) % 12
    root, suffix = next((match for match in matches if match[0] == bass), matches[0])
    return _NOTE_NAMES[root] + suffix


def _bend_intent(curve):
    if not curve:
        return 0
    start, end = curve[0]["v"], curve[-1]["v"]
    peak = max(point["v"] for point in curve)
    if start > 0:
        return 3 if end < start else 2
    return 4 if peak > 0 and end == 0 else 0


def _note_techniques(raw, previous_fret, beat, sustain, offset=0.0):
    out = {}
    if raw.get("hp"):
        out["ho" if previous_fret is None or int(raw["fret"]) >= previous_fret else "po"] = True
    mappings = {
        "palmMute": "pm", "letRing": "ln", "vibrato": "vb",
        "leftHandVibrato": "vb",
        "harmonic": "hm", "tapped": "tp", "accentuated": "ac",
        "dead": "mt", "slapped": "slp", "popped": "plk",
    }
    for source, target in mappings.items():
        if raw.get(source) or beat.get(source):
            out[target] = True
    if raw.get("ghost"):
        out["ig"] = True
    bend = raw.get("bend")
    if isinstance(bend, (int, float)) and bend:
        out["bn"] = round(float(bend), 2)
    elif isinstance(bend, dict):
        points = [point for point in bend.get("points") or []
                  if isinstance(point, dict)
                  and isinstance(point.get("position"), (int, float))
                  and isinstance(point.get("tone"), (int, float))]
        tones = [float(bend.get("tone") or 0),
                 *(float(point["tone"]) for point in points)]
        peak = max(tones, default=0) / 50.0
        if peak:
            out["bn"] = round(peak, 2)
        if points:
            out["bnv"] = [
                {"t": round(offset + sustain * float(point["position"]) / 60.0, 4),
                 "v": round(float(point["tone"]) / 50.0, 2)}
                for point in points
            ]
            intent = _bend_intent(out["bnv"])
            if intent:
                out["bt"] = intent
    slide = raw.get("slideTo")
    if isinstance(slide, (int, float)):
        out["sl"] = int(slide)
    elif raw.get("slide"):
        out["_slide"] = raw["slide"]
    return out


def _merge_techniques(note, techniques):
    curve = techniques.pop("bnv", None)
    bend = techniques.pop("bn", None)
    techniques.pop("bt", None)
    note.update(techniques)
    if bend:
        note["bn"] = max(float(note.get("bn", 0)), bend)
    if curve:
        note.setdefault("bnv", []).extend(curve)
        intent = _bend_intent(note["bnv"])
        if intent:
            note["bt"] = intent
        else:
            note.pop("bt", None)


def _resolve_slides(notes, chords):
    timed = [(note["t"], note) for note in notes]
    timed.extend((chord["t"], note) for chord in chords for note in chord["notes"])
    timed.sort(key=lambda item: item[0])
    for index, (_time, note) in enumerate(timed):
        slide = note.pop("_slide", None)
        if slide == "downwards":
            note["slu"] = 0
        elif slide == "upwards":
            note["slu"] = max(24, note["f"])
        elif slide in {"shift", "legato", True}:
            target = next((candidate for later, candidate in timed[index + 1:]
                           if later > _time and candidate["s"] == note["s"]
                           and not candidate.get("mt")), None)
            if target is not None and target["f"] != note["f"]:
                note["sl"] = target["f"]


def part_to_drum_tab(part, timeline):
    """Convert Songsterr drum MIDI identities into FeedPak drum hits."""
    hits = {}
    used = []
    measures = part.get("measures") or []
    velocities = _drum_velocities(measures)
    for measure_index, source_index in enumerate(timeline["measure_order"]):
        measure = measures[source_index]
        info = timeline["measure_info"][measure_index]
        for voice_index, voice in enumerate(measure.get("voices") or []):
            position = Fraction(0)
            for beat_index, beat in enumerate(voice.get("beats") or []):
                raw_duration = beat.get("duration") or [0, 1]
                duration = Fraction(int(raw_duration[0]), int(raw_duration[1]))
                velocity = velocities.get((source_index, voice_index, beat_index), 100)
                text = beat.get("text") or ""
                if isinstance(text, dict):
                    text = text.get("text") or ""
                stack_hint = bool(re.search(r"\b(?:stack|stax)\b", str(text), re.I))
                for note in beat.get("notes") or []:
                    if note.get("rest") or note.get("tie") or "fret" not in note:
                        continue
                    midi = int(note["fret"])
                    piece = _DRUM_MIDI.get(midi, f"songsterr_{midi}")
                    if stack_hint and (piece in _CYMBAL_PIECES or piece.startswith("songsterr_")):
                        piece = "stack"
                    if piece not in used:
                        used.append(piece)
                    accent = int(note.get("accentuated") or 0)
                    note_velocity = min(127, velocity + (28 if accent > 1 else 16 if accent else 0))
                    subdivision = note.get("tremolo") or beat.get("tremolo")
                    unit = (Fraction(int(subdivision[0]), int(subdivision[1]))
                            if isinstance(subdivision, (list, tuple)) and len(subdivision) == 2
                            and int(subdivision[1]) else duration)
                    repetitions = max(1, int(duration / unit)) if unit > 0 else 1
                    for repetition in range(repetitions):
                        event_time = round(_position_time(info, position + unit * repetition), 4)
                        hit = {"t": event_time, "p": piece, "v": note_velocity}
                        if note.get("ghost"):
                            hit["g"] = True
                        if note.get("flam") or beat.get("flam") or beat.get("graceNote"):
                            hit["f"] = True
                        if (midi in {94, 95, 96, 97, 98}
                                or note.get("staccato") and piece in _CYMBAL_PIECES):
                            hit["k"] = 0.08
                        key = (event_time, piece)
                        previous = hits.get(key)
                        if previous is None:
                            hits[key] = hit
                            continue
                        merged = hit if hit["v"] > previous["v"] else previous
                        if hit.get("f") or previous.get("f"):
                            merged["f"] = True
                        if hit.get("k") or previous.get("k"):
                            merged["k"] = max(hit.get("k", 0), previous.get("k", 0))
                        if not (hit.get("g") and previous.get("g")):
                            merged.pop("g", None)
                        hits[key] = merged
                if not beat.get("graceNote"):
                    position += duration
    ordered = sorted(hits.values(), key=lambda hit: (hit["t"], hit["p"]))
    return {
        "type": "drums", "name": part.get("title") or part.get("name") or "Drums",
        "version": 1,
        "kit": [{"id": piece, "name": _DRUM_NAMES.get(piece, piece.replace("_", " ").title())}
                for piece in used],
        "hits": ordered, "stats": {"events": len(ordered), "notes": len(ordered)},
    }


def _anchors(notes, chords, width=4):
    groups = {}
    for note in notes:
        if note["f"] > 0:
            groups.setdefault(note["t"], []).append(note["f"])
    for chord in chords:
        for note in chord["notes"]:
            if note["f"] > 0:
                groups.setdefault(chord["t"], []).append(note["f"])
    ordered = [(time, min(frets), max(frets)) for time, frets in sorted(groups.items())]
    if not ordered:
        return [{"time": 0.0, "fret": 1, "width": width}]
    result, current = [], None
    for time, low, high in ordered:
        if current is None or low < current or high > current + width:
            current = max(1, max(high - width, low - 1))
            if not result or result[-1]["fret"] != current:
                result.append({"time": 0.0 if not result else time,
                               "fret": current, "width": width})
    return result


def part_to_arrangement(part, timeline):
    """Convert Songsterr's structured track into FeedPak wire data."""
    strings = int(part.get("strings") or len(part.get("tuning") or []) or 6)
    notes, chords, templates, handshapes = [], [], [], []
    template_ids = {}
    last_by_string = {}
    measures = part.get("measures") or []
    tuning_midi = list(reversed([int(value) for value in part.get("tuning") or []]))

    for measure_index, source_index in enumerate(timeline["measure_order"]):
        measure = measures[source_index]
        info = timeline["measure_info"][measure_index]
        for voice in measure.get("voices") or []:
            position = Fraction(0)
            for beat in voice.get("beats") or []:
                raw_duration = beat.get("duration") or [0, 1]
                duration = Fraction(int(raw_duration[0]), int(raw_duration[1]))
                event_time = _position_time(info, position)
                event_end = _position_time(info, position + duration)
                position += duration
                fresh = []
                for raw in beat.get("notes") or []:
                    if raw.get("rest") or "string" not in raw:
                        continue
                    string = strings - 1 - int(raw["string"])
                    previous = last_by_string.get(string)
                    if "fret" in raw:
                        fret = int(raw["fret"])
                    elif raw.get("dead"):
                        fret = previous["fret"] if previous else 0
                    else:
                        continue
                    if raw.get("tie") and previous and previous["fret"] == fret:
                        previous["note"]["sus"] = round(max(
                            previous["note"]["sus"], event_end - previous["time"]), 4)
                        _merge_techniques(previous["note"], _note_techniques(
                            raw, previous["fret"], beat, event_end - event_time,
                            event_time - previous["time"]))
                        previous["end"] = event_end
                        continue
                    sustain = event_end - event_time
                    if not beat.get("letRing"):
                        sustain *= 0.95
                    if raw.get("staccato"):
                        sustain *= 0.5
                    if raw.get("dead"):
                        sustain = min(sustain, 0.1)
                    note = {"s": string, "f": fret, "sus": round(max(0.03, sustain), 4)}
                    note.update(_note_techniques(
                        raw, previous["fret"] if previous else None, beat, note["sus"]))
                    fresh.append(note)
                    last_by_string[string] = {"fret": fret, "note": note,
                                              "time": event_time, "end": event_end}
                if not fresh:
                    continue
                time_value = round(event_time, 4)
                if len(fresh) == 1:
                    event = {"t": time_value, **fresh[0]}
                    notes.append(event)
                    last_by_string[event["s"]]["note"] = event
                    continue
                pattern = tuple(next((note["f"] for note in fresh if note["s"] == string), -1)
                                for string in range(strings))
                is_arp = bool(beat.get("arpeggio"))
                template_key = (pattern, is_arp)
                if template_key not in template_ids:
                    template_ids[template_key] = len(templates)
                    label = _chord_name(fresh, tuning_midi)
                    templates.append({"name": label, "displayName": label, "arp": is_arp,
                                      "frets": list(pattern), "fingers": [-1] * strings})
                chord_id = template_ids[template_key]
                chords.append({"t": time_value, "id": chord_id, "hd": False,
                               "notes": fresh})

    notes.sort(key=lambda note: (note["t"], note["s"]))
    chords.sort(key=lambda chord: chord["t"])
    _resolve_slides(notes, chords)
    for chord in chords:
        end = chord["t"] + max((note.get("sus", 0) for note in chord["notes"]), default=0)
        if (handshapes and handshapes[-1]["chord_id"] == chord["id"]
                and chord["t"] <= handshapes[-1]["end_time"] + 0.15):
            handshapes[-1]["end_time"] = round(max(handshapes[-1]["end_time"], end), 4)
        else:
            handshapes.append({"chord_id": chord["id"], "start_time": chord["t"],
                               "end_time": round(end, 4),
                               "arp": templates[chord["id"]]["arp"]})
    arrangement = {
        "name": part.get("title") or part.get("name") or part.get("instrument") or "Guitar",
        "tuning": _tuning(part), "capo": int(part.get("capo", 0) or 0),
        "notes": notes, "chords": chords,
        "anchors": _anchors(notes, chords), "handshapes": handshapes,
        "templates": templates,
    }
    arrangement["stats"] = {
        "events": len(notes) + len(chords),
        "notes": len(notes) + sum(len(chord["notes"]) for chord in chords),
    }
    return arrangement


def songsterr_to_tracks(songsterr):
    timeline = build_timeline(songsterr["parts"], songsterr.get("video_points") or ())
    return [part_to_drum_tab(part, timeline)
            if "drum" in str(part.get("instrument", "")).lower()
            else part_to_arrangement(part, timeline)
            for part in songsterr["parts"]], timeline


def _safe_id(name, used):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "guitar"
    value, number = base, 2
    while value in used:
        value, number = f"{base}-{number}", number + 1
    used.add(value)
    return value


def feedpak_filename(artist, title, album=""):
    name = " - ".join(value.strip() for value in (artist, title, album) if value and value.strip())
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .") or "Songsterr Chart"
    return name + ".feedpak"


def parse_lrc(source):
    """Convert standard line-synced LRC into FeedPak lyric events."""
    return _parse_lrc_text(Path(source).read_text(encoding="utf-8-sig"))


def write_feedpak(arrangements, timeline, audio_path, output_path, *, title, artist,
                  album="", year=None, genres=(), authors=(), cover_path=None,
                  lyrics=(), lyrics_source="user", offset=0.0, source_urls=()):
    """Write the same canonical wire structures used by FeedForge/spec examples."""
    import yaml

    output_path, audio_path = Path(output_path), Path(audio_path)
    staging = Path(tempfile.mkdtemp(prefix="feedforge-songsterr-feedpak_"))
    try:
        (staging / "arrangements").mkdir()
        (staging / "stems").mkdir()
        shutil.copy2(audio_path, staging / "stems" / "full.ogg")
        cover_name = None
        if cover_path and Path(cover_path).is_file():
            suffix = Path(cover_path).suffix.lower()
            if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
                cover_name = f"cover{suffix}"
                shutil.copy2(cover_path, staging / cover_name)
        entries, used, primary_drum = [], set(), None
        max_chart_time = 0.0
        for arrangement in arrangements:
            role = arrangement.get("role") or (
                "drums" if arrangement.get("type") == "drums" else
                "bass" if "bass" in arrangement["name"].lower() else "lead")
            aid = _safe_id(role, used)
            if arrangement.get("type") == "drums":
                wire = {key: json.loads(json.dumps(arrangement[key]))
                        for key in ("version", "name", "kit", "hits")}
                for hit in wire["hits"]:
                    hit["t"] = round(hit["t"] + offset, 4)
                    max_chart_time = max(max_chart_time, hit["t"])
                rel = f"drum_tab_{aid}.json"
                (staging / rel).write_text(
                    json.dumps(wire, separators=(",", ":")), encoding="utf-8")
                primary_drum = primary_drum or rel
                entries.append({
                    "id": aid, "name": arrangement["name"], "type": role,
                    "drum_tab": rel,
                    "event_count": arrangement["stats"]["events"],
                    "note_count": arrangement["stats"]["notes"],
                })
                continue
            wire = json.loads(json.dumps(arrangement))
            for note in wire["notes"]:
                note["t"] = round(note["t"] + offset, 4)
                max_chart_time = max(max_chart_time, note["t"] + note.get("sus", 0))
            for chord in wire["chords"]:
                chord["t"] = round(chord["t"] + offset, 4)
                max_chart_time = max(max_chart_time, chord["t"] + max(
                    (note.get("sus", 0) for note in chord["notes"]), default=0))
            for anchor in wire["anchors"]:
                anchor["time"] = round(anchor["time"] + offset, 4)
            for shape in wire["handshapes"]:
                shape["start_time"] = round(shape["start_time"] + offset, 4)
                shape["end_time"] = round(shape["end_time"] + offset, 4)
            ensure_difficulty(
                wire,
                beats=[{**b, "time": float(b["time"]) + offset} for b in timeline["beats"]],
                sections=[{**s, "time": float(s["time"]) + offset} for s in timeline["sections"]],
                duration=float(timeline["duration"]) + offset,
            )
            rel = f"arrangements/{aid}.json"
            (staging / rel).write_text(json.dumps(wire, separators=(",", ":")), encoding="utf-8")
            entries.append({
                "id": aid, "name": arrangement["name"], "file": rel,
                "tuning": arrangement["tuning"], "capo": arrangement["capo"],
                "type": role,
                "event_count": arrangement["stats"]["events"],
                "note_count": arrangement["stats"]["notes"],
            })

        timeline_wire = json.loads(json.dumps({
            key: value for key, value in timeline.items()
            if key in {"version", "tempos", "time_signatures", "beats", "sections"}
        }))
        for key in ("tempos", "time_signatures", "beats", "sections"):
            for event in timeline_wire[key]:
                event["time"] = round(float(event["time"]) + offset, 6)
        (staging / "song_timeline.json").write_text(
            json.dumps(timeline_wire, separators=(",", ":")), encoding="utf-8")
        duration = max(max_chart_time, float(timeline["duration"]) + offset)
        manifest = {
            "feedpak_version": FEEDPAK_VERSION, "title": title, "artist": artist,
            "duration": round(duration, 3), "arrangements": entries,
            "stems": [{"id": "full", "file": "stems/full.ogg",
                       "codec": "vorbis", "default": True}],
            "song_timeline": "song_timeline.json",
            "origin": {"tool": "FeedForge", "source": "songsterr",
                       "urls": list(source_urls)},
        }
        if album:
            manifest["album"] = album
        if year:
            manifest["year"] = int(year)
        if genres:
            manifest["genres"] = list(genres)
        if authors:
            manifest["authors"] = list(authors)
        if cover_name:
            manifest["cover"] = cover_name
        if lyrics:
            (staging / "lyrics.json").write_text(
                json.dumps(list(lyrics), ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
            manifest.update({
                "language": "und", "lyrics": "lyrics.json", "lyrics_source": lyrics_source,
                "lyric_tracks": [{"id": "original", "file": "lyrics.json",
                                  "language": "und", "kind": "original",
                                  "lyrics_source": lyrics_source, "stem": "full",
                                  "name": "Original"}],
            })
        if primary_drum:
            manifest["drum_tab"] = primary_drum
        write_manifest(staging / "manifest.yaml", manifest)
        require_valid_feedpak(staging)
        write_archive(staging, output_path)
        return output_path
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def prepare_cover(source, work_dir):
    """Download or copy selected release artwork for the FeedPak cover."""
    if not source:
        return None
    local = Path(source)
    if local.is_file():
        suffix = local.suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            return None
        output = Path(work_dir) / f"cover{suffix}"
        shutil.copy2(local, output)
        return output
    try:
        data = _get_bytes(source)
    except Exception:
        return None
    if len(data) < 1024:
        return None
    suffix = ".png" if data.startswith(b"\x89PNG") else ".webp" if data.startswith(b"RIFF") else ".jpg"
    output = Path(work_dir) / f"cover{suffix}"
    output.write_bytes(data)
    return output


def _youtube_browser():
    candidates = (
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def _node_runtime():
    configured = os.environ.get("SONGSTERR_NODE_PATH")
    return configured if configured and Path(configured).is_file() else shutil.which("node")


class YouTubeAudioError(RuntimeError):
    """A source could not be downloaded; another listed recording may work."""


def _download_youtube(source, work_dir):
    import yt_dlp

    template = str(work_dir / "download.%(ext)s")
    errors = []
    # The normal web client can require a PO token and return 403 for otherwise
    # public videos. android_vr is yt-dlp's token-free fallback client.
    browser, node = _youtube_browser(), _node_runtime()
    attempts = [
        ("bestaudio[ext=m4a]/bestaudio", None, False),
        ("bestaudio[ext=webm]/bestaudio", None, False),
        ("bestaudio/best", "android_vr", False),
    ]
    if browser and node:
        attempts.append(("bestaudio/best", "mweb", True))
    for audio_format, player_client, browser_token in attempts:
        for old in work_dir.glob("download.*"):
            old.unlink(missing_ok=True)
        try:
            options = {
                "format": audio_format, "outtmpl": template, "noplaylist": True,
                "retries": 3, "fragment_retries": 3, "quiet": True,
                "no_warnings": True, "noprogress": True,
            }
            if player_client:
                options["extractor_args"] = {"youtube": {"player_client": [player_client]}}
            if browser_token:
                options["extractor_args"]["youtubepot-wpc"] = {
                    "browser_path": [str(browser)]}
                options["js_runtimes"] = {"node": {"path": str(node)}}
            with yt_dlp.YoutubeDL(options) as downloader:
                downloader.extract_info(str(source), download=True)
            candidates = [path for path in work_dir.glob("download.*")
                          if path.suffix not in {".part", ".ytdl"}]
            if candidates:
                return candidates[0]
        except yt_dlp.utils.DownloadError as exc:
            errors.append(str(exc))
    detail = errors[-1] if errors else "no audio file was returned"
    raise YouTubeAudioError(f"Could not download audio from {source}. The video may be unavailable in your region, removed, or inaccessible to the downloader. Choose another video or local audio. {detail}")


def prepare_audio(source, work_dir):
    """Download/copy audio and convert it to the FeedPak's Vorbis stem."""
    import imageio_ffmpeg

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    source_text = str(source)
    if source_text.lower().startswith(("https://", "http://")):
        source_path = _download_youtube(source_text, work_dir)
    else:
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {source_path}")

    output = work_dir / "full.ogg"
    if source_path.suffix.lower() == ".ogg":
        shutil.copy2(source_path, output)
        return output
    result = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(source_path),
        "-vn", "-c:a", "libvorbis", "-q:a", "5", str(output),
    ], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode or not output.exists():
        raise RuntimeError("Audio conversion failed: " + result.stderr[-500:])
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="+")
    parser.add_argument("--audio", required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--offset", type=float, default=0.0)
    args = parser.parse_args(argv)
    song = load_songsterr(args.url)
    arrangements, timeline = songsterr_to_tracks(song)
    work = Path(tempfile.mkdtemp(prefix="feedforge-songsterr-creator_"))
    try:
        audio = prepare_audio(args.audio, work)
        write_feedpak(arrangements, timeline, audio, args.output,
                      title=song["meta"]["title"], artist=song["meta"]["artist"],
                      offset=args.offset, source_urls=song["urls"])
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
