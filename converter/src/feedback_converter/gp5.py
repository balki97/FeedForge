"""Export the full-difficulty FeedPak charts together on a shared GP5 timeline."""
from bisect import bisect_right
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile

import guitarpro
from guitarpro import models as gp

from .converter import ConversionWarning, _safe_output_stem
from .feedpak import _open_feedpak, _read_manifest


@dataclass
class Gp5ExportResult:
    output_path: Path
    track_count: int
    warnings: list[ConversionWarning] = field(default_factory=list)


# FeedPak piece identities, including the Songsterr extensions emitted by FeedForge.
DRUM_MIDI = {
    "kick": 36, "snare": 38, "snare_rim": 37, "snare_side": 37,
    "hihat_closed": 42, "hihat_open": 46, "hihat_pedal": 44,
    "tom_high": 50, "tom_mid": 47, "tom_low": 43,
    "crash": 49, "crash_2": 57, "ride": 51, "ride_bell": 53,
    "china": 52, "splash": 55, "stack": 52, "cowbell": 56,
    "tambourine": 54, "clap": 39,
    "snare_xstick": 37, "hh_closed": 42, "hh_open": 46, "hh_pedal": 44,
    "tom_hi": 50, "tom_floor": 41, "crash_l": 49, "crash_r": 57,
    "bell": 80, "bongo_hi": 60, "bongo_low": 61, "conga_mute": 62,
    "conga_open": 63, "conga_low": 64, "timbale_hi": 65,
    "woodblock_hi": 76, "castanets": 85,
}


def _number(value, label):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"Invalid {label}: must be finite")
    return value


def _read_chart(root, relative):
    path = (root / str(relative)).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or unsafe FeedPak chart path: {relative}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"FeedPak chart must be an object: {relative}")
    return data


class _Clock:
    def __init__(self, timeline, origin, warn):
        tempos = timeline.get("tempos") or []
        beats = sorted(timeline.get("beats") or [], key=lambda b: b["time"])
        if not tempos and len(beats) > 1:
            tempos = [{"time": a["time"], "bpm": 60 / (b["time"] - a["time"])}
                      for a, b in zip(beats, beats[1:]) if b["time"] > a["time"]]
        if not tempos:
            warn("No tempo or beat map was available; used 120 BPM.")
        points = {}
        for event in tempos:
            time = _number(event["time"], "tempo time")
            bpm = _number(event["bpm"], "tempo")
            if not 1 <= bpm <= 1000:
                raise ValueError("GP5 export requires tempos between 1 and 1000 BPM")
            points[time] = bpm
        if not points:
            points[0.0] = 120.0
        first = min(points)
        points.setdefault(min(0.0, origin, first), points[first])
        self.times = sorted(points)
        self.bpms = [points[t] for t in self.times]
        self.ticks = [0.0]
        for i in range(1, len(self.times)):
            self.ticks.append(self.ticks[-1] + (self.times[i] - self.times[i-1]) * self.bpms[i-1] * 16)
        self.origin = self.raw(origin)
        self.changes = {}
        previous = None
        for time, bpm in zip(self.times, self.bpms):
            tick = max(0, self.at(time))
            rounded = round(bpm)
            if rounded != previous:
                self.changes[tick] = rounded
                previous = rounded
        self.changes[0] = round(self.bpms[max(0, bisect_right(self.times, origin) - 1)])

    def raw(self, time):
        index = max(0, bisect_right(self.times, time) - 1)
        return self.ticks[index] + (time - self.times[index]) * self.bpms[index] * 16

    def at(self, time):
        # GP5 durations include straight and triplet values; 20 ticks is a 128th triplet.
        return int(round((self.raw(_number(time, "event time")) - self.origin) / 20)) * 20


def _events(chart, drums):
    if drums:
        return [{**hit, "sus": 0} for hit in chart.get("hits") or []]
    events = [dict(note) for note in chart.get("notes") or []]
    templates = chart.get("templates") or []
    for chord in chart.get("chords") or []:
        notes = chord.get("notes")
        if not notes:
            template = templates[int(chord["id"])]
            notes = [{"s": s, "f": fret} for s, fret in enumerate(template["frets"]) if fret >= 0]
        for note in notes:
            events.append({**chord, **note, "t": chord["t"]})
    return sorted(events, key=lambda event: event["t"])


def _effect(event):
    effect = gp.NoteEffect(
        palmMute=bool(event.get("pm")), letRing=bool(event.get("ln")),
        vibrato=bool(event.get("vb")), hammer=bool(event.get("ho") or event.get("po")),
        ghostNote=bool(event.get("ig") or event.get("g")),
        accentuatedNote=bool(event.get("ac")),
    )
    if event.get("hm"):
        effect.harmonic = gp.NaturalHarmonic()
    if "sl" in event:
        effect.slides = [gp.SlideType.shiftSlideTo]
    elif "slu" in event:
        effect.slides = [gp.SlideType.outUpwards if event["slu"] > event["f"] else gp.SlideType.outDownwards]
    curve = event.get("bnv") or []
    bend = float(event.get("bn") or 0)
    if curve or bend:
        sustain = float(event.get("sus") or 0)
        points = [gp.BendPoint(max(0, min(12, round(float(p["t"]) / sustain * 12))),
                               round(float(p["v"]) * 2)) for p in curve] if sustain > 0 else []
        effect.bend = gp.BendEffect(gp.BendType.bend, round(bend * 2), points or [gp.BendPoint(0, 0), gp.BendPoint(12, round(bend * 2))])
    return effect


def _durations():
    durations = []
    for value in (1, 2, 4, 8, 16, 32, 64, 128):
        for dotted in (False, True):
            for tuplet in (gp.Tuplet(), gp.Tuplet(3, 2)):
                duration = gp.Duration(value, dotted, tuplet)
                if duration.time >= 20 and duration.time % 20 == 0:
                    durations.append(duration)
    return sorted(durations, key=lambda d: d.time, reverse=True)


def _fill_track(track, events, clock, tempo_changes, warn):
    groups = {}
    for event in events:
        start = clock.at(event["t"])
        if start < 0:
            raise ValueError("A chart event occurs before the score starts")
        groups.setdefault(start, []).append(event)
    starts = sorted(groups)
    next_start = dict(zip(starts, starts[1:] + [starts[-1] + 960])) if starts else {}
    active = {}
    durations = _durations()
    for measure in track.measures:
        left = measure.start - 960
        right = left + measure.header.length
        boundaries = {left, right}
        boundaries.update(t for t in starts if left <= t < right)
        boundaries.update(t for t in tempo_changes if left <= t < right)
        # Carry sustains across barlines; end points also split other strings' beats.
        boundaries.update(end for _, end in active.values() if left < end < right)
        for start in [t for t in starts if left <= t < right]:
            for event in groups[start]:
                end = clock.at(float(event["t"]) + max(0, _number(event.get("sus", 0), "sustain")))
                if left < end < right:
                    boundaries.add(end)
        cursor = left
        ordered = sorted(boundaries)
        while cursor < right:
            active = {s: pair for s, pair in active.items() if pair[1] > cursor}
            fresh = groups.get(cursor, [])
            if track.isPercussionTrack:
                if len(fresh) > 7:
                    raise ValueError(f"{track.name}: GP5 supports at most seven simultaneous drum hits")
                for s, event in enumerate(fresh, 1):
                    active[s] = (event, min(next_start[cursor], cursor + 240))
            else:
                seen = set()
                for event in fresh:
                    s = len(track.strings) - int(event["s"])
                    if not 1 <= s <= len(track.strings) or not 0 <= int(event["f"]) <= 99:
                        raise ValueError(f"{track.name}: invalid string or fret")
                    if s in seen:
                        warn(f"{track.name}: notes on the same string collided after timing quantization; kept the last note.")
                    seen.add(s)
                    end = clock.at(float(event["t"]) + max(0, float(event.get("sus") or 0)))
                    if end <= cursor:
                        end = min(next_start[cursor], cursor + 960)
                    active[s] = (event, max(cursor + 20, end))
            next_boundary = ordered[bisect_right(ordered, cursor)]
            next_boundary = min(next_boundary, *(end for _, end in active.values())) if active else next_boundary
            length = next_boundary - cursor
            duration = next(d for d in durations if d.time <= length)
            beat = gp.Beat(measure.voices[0], start=cursor + 960, duration=duration,
                           status=gp.BeatStatus.normal if active else gp.BeatStatus.rest)
            if cursor in tempo_changes:
                beat.effect.mixTableChange = gp.MixTableChange(tempo=gp.MixTableItem(tempo_changes[cursor]))
            for s, (event, _) in sorted(active.items()):
                is_new = any(event is e for e in fresh)
                if track.isPercussionTrack:
                    if not is_new:
                        continue
                    piece = str(event["p"])
                    value = DRUM_MIDI.get(piece)
                    if value is None and piece.startswith("songsterr_"):
                        value = int(piece.removeprefix("songsterr_"))
                    if value is None or not 0 <= value <= 127:
                        raise ValueError(f"Unknown drum piece: {piece}")
                else:
                    value = int(event["f"])
                note_type = (gp.NoteType.dead if event.get("mt") else gp.NoteType.normal) if is_new else gp.NoteType.tie
                note = gp.Note(beat, string=s, value=value, type=note_type,
                               velocity=max(15, min(127, 15 + round((int(event.get("v", 95)) - 15) / 16) * 16)),
                               effect=_effect(event) if is_new else gp.NoteEffect())
                beat.notes.append(note)
            if not beat.notes:
                beat.status = gp.BeatStatus.rest
            measure.voices[0].beats.append(beat)
            cursor += duration.time
            if track.isPercussionTrack:
                active.clear()


def export_feedpak_gp5(input_path: Path, output: Path | None = None, *, overwrite=False) -> Gp5ExportResult:
    input_path = Path(input_path)
    warnings = []

    def warn(message):
        if not any(w.message == message for w in warnings):
            warnings.append(ConversionWarning(message))

    with _open_feedpak(input_path) as root:
        manifest = _read_manifest(root)
        charts = []
        drum_files = set()
        for entry in manifest.get("arrangements") or []:
            drums = entry.get("type") == "drums" or bool(entry.get("drum_tab"))
            relative = entry.get("drum_tab") if drums else entry.get("file")
            if entry.get("type") in {"vocals", "vocal", "keys", "piano"} or not relative:
                warn(f"Skipped {entry.get('name') or entry.get('id')}: GP5 export supports fretted strings and drums.")
                continue
            chart = _read_chart(root, relative)
            charts.append((entry, chart, drums, _events(chart, drums)))
            if drums:
                drum_files.add(relative)
        if manifest.get("drum_tab") and manifest["drum_tab"] not in drum_files:
            chart = _read_chart(root, manifest["drum_tab"])
            charts.append(({"name": chart.get("name") or "Drums", "type": "drums"}, chart, True, _events(chart, True)))
        if not charts:
            raise ValueError("FeedPak has no guitar, bass, or drum charts to export")
        if len(charts) > 64:
            raise ValueError("GP5 supports at most 64 tracks")
        timeline = (_read_chart(root, manifest["song_timeline"]) if manifest.get("song_timeline") else {})
        if not timeline:
            timeline = next((chart for _, chart, _, _ in charts if chart.get("beats") or chart.get("tempos")), {})
        first_event = min((float(e["t"]) for _, _, _, events in charts for e in events), default=0)
        beats = sorted(timeline.get("beats") or [], key=lambda b: b["time"])
        origin = min(0.0, first_event)
        if beats and 0 < float(beats[0]["time"]) <= first_event:
            origin = float(beats[0]["time"])
            warn(f"Removed {origin:g} seconds of leading audio-only silence from the score.")
        clock = _Clock(timeline, origin, warn)
        end = max((clock.at(float(e["t"]) + max(0, float(e.get("sus") or 0))) + 960
                   for _, _, _, events in charts for e in events), default=3840)
        song = gp.Song(title=str(manifest.get("title") or input_path.stem),
                       artist=str(manifest.get("artist") or ""), album=str(manifest.get("album") or ""),
                       tempo=clock.changes[0], tracks=[], measureHeaders=[])
        song.tab = ", ".join(str(a.get("name") or "") for a in manifest.get("authors") or [] if isinstance(a, dict))
        song.notice = ["Exported by FeedForge. Timings quantized to GP5 notation; tempos rounded to whole BPM."]
        warn("GP5 timings are quantized; tempos use whole BPM. Audio, tone rigs, difficulty ladders and game-only techniques are not included.")
        signatures = {max(0, clock.at(s["time"])): s["ts"] for s in timeline.get("time_signatures") or []}
        if not signatures and beats:
            downbeats = [i for i, b in enumerate(beats) if b.get("measure", -1) > 0
                         and (i == 0 or b["measure"] != beats[i-1].get("measure"))]
            for a, b in zip(downbeats, downbeats[1:]):
                signatures[max(0, clock.at(beats[a]["time"]))] = [b-a, 4]
        cursor, signature = 0, [4, 4]
        while cursor < max(3840, end):
            past = [t for t in signatures if t <= cursor]
            if past:
                signature = signatures[max(past)]
            numerator, denominator = map(int, signature)
            if not 1 <= numerator <= 32 or denominator not in (1, 2, 4, 8, 16, 32, 64):
                raise ValueError(f"Unsupported GP5 time signature: {signature}")
            header = gp.MeasureHeader(number=len(song.measureHeaders)+1, start=cursor+960,
                                      timeSignature=gp.TimeSignature(numerator, gp.Duration(denominator)))
            song.measureHeaders.append(header)
            cursor += header.length
            if len(song.measureHeaders) > 10000:
                raise ValueError("Score exceeds the GP5 export limit of 10000 measures")
        channels = iter(c for c in range(16) if c != 9)
        for index, (entry, chart, drums, events) in enumerate(charts, 1):
            bass = entry.get("type") == "bass" or "bass" in str(entry.get("name", "")).lower()
            tuning = chart.get("tuning") or entry.get("tuning") or [0] * (4 if bass else 6)
            if bass and len(tuning) == 6:
                # Rocksmith pads four/five-string bass tuning arrays to six entries.
                count = max(4, max((int(e["s"]) + 1 for e in events), default=0))
                tuning = tuning[:count]
            if not drums and not 1 <= len(tuning) <= 7:
                raise ValueError("GP5 supports at most seven strings per track; an eight-string chart cannot be exported losslessly")
            channel = 9 if drums else next(channels, None)
            if channel is None:
                raise ValueError("GP5 export supports at most 15 independently voiced string tracks")
            standard = ([23, 28, 33, 38, 43] if len(tuning) <= 5 else [18, 23, 28, 33, 38, 43, 48]) if bass else [35, 40, 45, 50, 55, 59, 64]
            base = standard[-len(tuning):]
            if len(base) != len(tuning):
                raise ValueError("Unsupported bass string count")
            strings = [gp.GuitarString(i+1, pitch + int(offset)) for i, (pitch, offset) in enumerate(reversed(list(zip(base, tuning))))]
            track = gp.Track(song, number=index, name=str(entry.get("name") or chart.get("name") or entry.get("id") or f"Track {index}"),
                             strings=strings if not drums else [gp.GuitarString(i, 0) for i in range(1, 8)],
                             isPercussionTrack=drums, offset=int(chart.get("capo", entry.get("capo", 0)) or 0),
                             channel=gp.MidiChannel(channel=channel, effectChannel=channel, instrument=0 if drums else 33 if bass else 25),
                             measures=[])
            if chart.get("centOffset"):
                warn(f"{track.name}: GP5 cannot preserve cent tuning offsets.")
            track.measures = [gp.Measure(track, header) for header in song.measureHeaders]
            song.tracks.append(track)
            _fill_track(track, events, clock, clock.changes if index == 1 else {}, warn)
        # GP5 stores text in the legacy Windows character set.
        for obj, fields in [(song, ("title", "artist", "album", "tab")),
                            *((track, ("name",)) for track in song.tracks)]:
            for name in fields:
                value = getattr(obj, name)
                encoded = value.encode("cp1252", errors="replace").decode("cp1252")
                if encoded != value:
                    warn("Some text contains characters GP5 cannot store; replaced them with question marks.")
                    setattr(obj, name, encoded)
        target = Path(output) if output is not None else input_path.with_suffix(".gp5")
        if target.suffix.lower() != ".gp5":
            target /= _safe_output_stem(input_path.stem) + ".gp5"
        if target.resolve() == input_path.resolve() or target.resolve().is_relative_to(root.resolve()):
            raise ValueError("GP5 output must be outside the source FeedPak")
        if target.exists() and not overwrite:
            raise FileExistsError(f"Output already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(suffix=".gp5", dir=target.parent)
        os.close(descriptor)
        try:
            guitarpro.write(song, temporary, version=(5, 1, 0))
            if overwrite:
                os.replace(temporary, target)
            else:
                # Exclusive creation keeps another export from being overwritten after the check.
                with target.open("xb") as destination, open(temporary, "rb") as source:
                    destination.write(source.read())
        finally:
            Path(temporary).unlink(missing_ok=True)
    return Gp5ExportResult(target, len(song.tracks), warnings)
