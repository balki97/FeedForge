import hashlib
import json
from pathlib import Path
import zipfile

import guitarpro
from guitarpro import models as gp
import pytest
import yaml

from feedback_converter.cli import main
from feedback_converter.gp5 import export_feedpak_gp5


def package(tmp_path, *, archive=True, lead=None, timeline=None):
    root = tmp_path / "source.feedpak"
    root.mkdir()
    charts = {
        "lead": lead or {"tuning": [-2, 0, 0, 0, 0, 0], "capo": 2,
            "notes": [{"t": 0, "s": 0, "f": 3, "sus": 2.5, "pm": True},
                      {"t": .5, "s": 1, "f": 5, "sus": .5, "vb": True}],
            "chords": [{"t": 3, "id": 0}], "templates": [{"frets": [0, 2, 2, -1, -1, -1]}]},
        "rhythm": {"tuning": [0]*6, "notes": [{"t": 0, "s": 0, "f": 7, "sus": .5}]},
        "bass": {"tuning": [0]*4, "notes": [{"t": 0, "s": 0, "f": 5, "sus": .5}]},
        "drums": {"version": 1, "hits": [{"t": 0, "p": "kick", "v": 110},
                    {"t": 0, "p": "hh_closed"}, {"t": .5, "p": "snare", "g": True}]},
    }
    entries = []
    for role, chart in charts.items():
        (root / f"{role}.json").write_text(json.dumps(chart), encoding="utf-8")
        entries.append({"id": role, "name": role.title(), "type": role,
                        "drum_tab" if role == "drums" else "file": f"{role}.json"})
    (root / "timeline.json").write_text(json.dumps(timeline or {
        "tempos": [{"time": 0, "bpm": 120}, {"time": 2, "bpm": 60}],
        "time_signatures": [{"time": 0, "ts": [4, 4]}, {"time": 2, "ts": [3, 4]}],
    }), encoding="utf-8")
    (root / "manifest.yaml").write_text(yaml.safe_dump({
        "title": "Together", "artist": "Tester", "album": "Album",
        "authors": [{"name": "Charter"}], "arrangements": entries,
        "song_timeline": "timeline.json",
        # This alias must not duplicate the drum track.
        "drum_tab": "drums.json",
    }), encoding="utf-8")
    if not archive:
        return root
    packed = tmp_path / "packed.feedpak"
    with zipfile.ZipFile(packed, "w") as z:
        for file in root.iterdir():
            z.write(file, file.name)
    return packed


def notes(track):
    return [(b.start - 960, n) for m in track.measures for v in m.voices for b in v.beats for n in b.notes]


@pytest.mark.parametrize("archive", [True, False])
def test_combines_parts_and_preserves_music(tmp_path, archive):
    source = package(tmp_path, archive=archive)
    before = hashlib.sha256(source.read_bytes()).hexdigest() if archive else None
    result = export_feedpak_gp5(source, tmp_path / "all.gp5")
    song = guitarpro.parse(str(result.output_path))
    assert result.track_count == 4
    assert [t.name for t in song.tracks] == ["Lead", "Rhythm", "Bass", "Drums"]
    assert (song.title, song.artist, song.album, song.tab) == ("Together", "Tester", "Album", "Charter")
    lead, rhythm, bass, drums = song.tracks
    assert [s.value for s in lead.strings] == [64, 59, 55, 50, 45, 38]
    assert lead.offset == 2
    assert [s.value for s in bass.strings] == [43, 38, 33, 28]
    assert len({t.channel.channel for t in song.tracks}) == 4
    assert drums.isPercussionTrack and drums.channel.channel == 9
    assert [(start, n.value) for start, n in notes(drums)] == [(0, 36), (0, 42), (960, 38)]
    assert notes(drums)[0][1].velocity == 111  # GP5 velocity resolution is eight steps.
    assert notes(drums)[2][1].effect.ghostNote
    assert all(notes(t)[0][0] == 0 for t in song.tracks)
    assert notes(lead)[0][1].effect.palmMute
    assert any(n.effect.vibrato for _, n in notes(lead))
    assert any(start >= 3840 and n.type == gp.NoteType.tie for start, n in notes(lead))
    assert [(h.timeSignature.numerator, h.timeSignature.denominator.value) for h in song.measureHeaders][:2] == [(4, 4), (3, 4)]
    changes = [(b.start-960, b.effect.mixTableChange.tempo.value)
               for m in lead.measures for b in m.voices[0].beats
               if b.effect.mixTableChange and b.effect.mixTableChange.tempo]
    assert changes == [(0, 120), (3840, 60)]
    chord = [(start, n.value) for start, n in notes(lead) if n.type == gp.NoteType.normal and start == 4800]
    assert sorted(chord) == [(4800, 0), (4800, 2), (4800, 2)]
    for track in song.tracks:
        for measure in track.measures:
            assert sum(b.duration.time for b in measure.voices[0].beats) == measure.header.length
    if archive:
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_overwrite_and_cli(tmp_path, capsys):
    source = package(tmp_path)
    target = tmp_path / "out.gp5"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_feedpak_gp5(source, target)
    assert target.read_bytes() == b"keep"
    assert main([str(source), "--export-gp5", "-o", str(target), "--overwrite"]) == 0
    assert len(guitarpro.parse(str(target)).tracks) == 4
    assert f"wrote {target}" in capsys.readouterr().out
    assert main(["not.psarc", "--export-gp5"]) == 1


def test_rejects_unsupported_or_unsafe_data_without_overwriting(tmp_path):
    source = package(tmp_path, archive=False, lead={"tuning": [0]*8, "notes": []})
    target = tmp_path / "keep.gp5"
    target.write_bytes(b"keep")
    with pytest.raises(ValueError, match="seven strings"):
        export_feedpak_gp5(source, target, overwrite=True)
    assert target.read_bytes() == b"keep"
    manifest_path = source / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["arrangements"][0]["file"] = "../outside.json"
    manifest_path.write_text(yaml.safe_dump(manifest))
    with pytest.raises(ValueError, match="unsafe"):
        export_feedpak_gp5(source, target, overwrite=True)


def test_beat_map_triplets_and_top_level_drums(tmp_path):
    source = package(tmp_path, archive=False,
                     lead={"notes": [{"t": 1/6, "s": 0, "f": 3, "sus": 1/6}]},
                     timeline={"beats": [{"time": i*.5, "measure": 1+i//4} for i in range(9)]})
    manifest_path = source / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["arrangements"] = manifest["arrangements"][:3]
    manifest_path.write_text(yaml.safe_dump(manifest))
    song = guitarpro.parse(str(export_feedpak_gp5(source, tmp_path / "triplet.gp5").output_path))
    assert len(song.tracks) == 4
    assert notes(song.tracks[0])[0][0] == 320
    assert notes(song.tracks[0])[0][1].beat.duration.tuplet.enters == 3
    assert song.measureHeaders[0].timeSignature.numerator == 4


def test_padded_rocksmith_bass_and_slides(tmp_path):
    source = package(tmp_path, archive=False,
                     lead={"notes": [{"t": 0, "s": 0, "f": 5, "slu": 0}]})
    bass = {"tuning": [-2, 0, 0, 0, 0, 0], "notes": [{"t": 0, "s": 0, "f": 3}]}
    (source / "bass.json").write_text(json.dumps(bass))
    song = guitarpro.parse(str(export_feedpak_gp5(source, tmp_path / "bass.gp5").output_path))
    assert [s.value for s in song.tracks[2].strings] == [43, 38, 33, 26]
    assert notes(song.tracks[0])[0][1].effect.slides == [gp.SlideType.outDownwards]
