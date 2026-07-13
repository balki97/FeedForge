from __future__ import annotations

import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import yaml
import pytest

from feedback_converter import converter
from feedback_converter import batch
from feedback_converter import inspector
from feedback_converter import cli
from feedback_converter.cli import _single_output_path
from feedback_converter.psarc_format import crypto
from feedback_converter.psarc_format.psarc import read_entry


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def test_psarc_read_entry_bounds_zero_block_to_entry_end():
    bom = ns(entries=[ns(offset=0, zindex=0, length=6)], zlength=[0])

    assert read_entry(BytesIO(b"abcdefNEXT"), 0, bom, end_offset=6) == b"abcdef"


def test_decrypt_psarc_matches_windows_style_sng_paths(monkeypatch):
    calls = []

    def fake_decrypt(data, key):
        calls.append((data, key))
        return b"decrypted"

    monkeypatch.setattr(crypto, "decrypt_sng", fake_decrypt)

    result = crypto.decrypt_psarc({"songs\\bin\\generic\\song_lead.sng": b"encrypted"})

    assert result["songs\\bin\\generic\\song_lead.sng"] == b"decrypted"
    assert calls == [(b"encrypted", crypto.WIN_KEY)]


class FakePSARC:
    def __init__(self, crypto: bool = True):
        self.crypto = crypto

    def parse_stream(self, _fh):
        return {
            "manifests/songs_dlc/test/test.json": json.dumps(
                {
                    "SongName": "Test Song",
                    "ArtistName": "Test Artist",
                    "AlbumName": "Test Album",
                    "SongYear": 2026,
                    "SongLength": 12.5,
                    "PackageAuthor": "Chart Maker",
                    "ArrangementName": "Lead",
                    "SongXml": "songs/arr/test_lead.xml",
                    "Tone_Base": "Clean",
                    "Tone_A": "Clean",
                    "Tone_B": "Drive",
                    "Tones": [
                        {
                            "Name": "Clean",
                            "Key": "Tone_0",
                            "GearList": {
                                "Amp": {
                                    "Key": "Amp_Clean",
                                    "Type": "Amps",
                                    "Category": "Amp",
                                    "KnobValues": {"Gain": 0.2, "Bass": 0.5},
                                },
                                "Cabinet": {"Key": "Cab_212"},
                            },
                        },
                        {
                            "Name": "Drive",
                            "Key": "Tone_1",
                            "GearList": {
                                "PrePedal1": {
                                    "PedalKey": "Pedal_Overdrive",
                                    "Category": "Distortion",
                                    "KnobValues": {"Drive": 0.7},
                                },
                                "Amp": {"Type": "Amp_HighGain", "KnobValues": {"Gain": 0.8}},
                            },
                        },
                    ],
                }
            ).encode(),
            "songs/bin/generic/test_lead.sng": b"fake-sng",
            "audio/windows/test.wem": b"wem-data",
        }


def fake_song():
    note = ns(
        time=1.0,
        string=2,
        fret=5,
        sustain=0.5,
        slideTo=-1,
        slideUnpitchTo=-1,
        bend_time=0.0,
        bends=[],
        leftHand=-1,
        mask=converter.NOTE_MASK_PALMMUTE
        | converter.NOTE_MASK_PINCHHARMONIC
        | converter.NOTE_MASK_MUTE,
        chordId=converter.UINT32_NONE,
        chordNoteId=converter.UINT32_NONE,
    )
    chord = ns(
        time=2.0,
        string=0,
        fret=0,
        sustain=0.25,
        slideTo=-1,
        slideUnpitchTo=-1,
        bend_time=0.0,
        bends=[],
        leftHand=-1,
        mask=converter.NOTE_MASK_PALMMUTE,
        chordId=0,
        chordNoteId=0,
    )
    double_stop_low = ns(
        time=3.0,
        string=1,
        fret=6,
        sustain=0.25,
        slideTo=5,
        slideUnpitchTo=-1,
        bend_time=0.0,
        bends=[],
        leftHand=-1,
        mask=converter.NOTE_MASK_PARENT,
        chordId=converter.UINT32_NONE,
        chordNoteId=converter.UINT32_NONE,
    )
    double_stop_high = ns(
        time=3.0,
        string=2,
        fret=8,
        sustain=0.25,
        slideTo=7,
        slideUnpitchTo=-1,
        bend_time=0.0,
        bends=[],
        leftHand=-1,
        mask=converter.NOTE_MASK_PARENT,
        chordId=converter.UINT32_NONE,
        chordNoteId=converter.UINT32_NONE,
    )
    level = ns(
        difficulty=3,
        notes=[note, chord, double_stop_low, double_stop_high],
        anchors=[ns(time=0.0, fret=1, width=4)],
        fingerprints=[[], []],
    )
    return ns(
        metadata=ns(tuning=[0, 0, 0, 0, 0, 0], capo=0, songLength=12.5),
        chordTemplates=[ns(name="C", frets=[-1, 3, 2, 0, 1, 0], fingers=[-1, 3, 2, 0, 1, 0])],
        chordNotes=[
            ns(
                mask=[
                    0,
                    converter.NOTE_MASK_HARMONIC,
                    converter.NOTE_MASK_FRETHANDMUTE,
                    converter.NOTE_MASK_PALMMUTE,
                    converter.NOTE_MASK_MUTE,
                    converter.NOTE_MASK_PINCHHARMONIC,
                ],
                slideTo=[-1, 4, -1, -1, -1, -1],
                slideUnpitchTo=[-1, -1, -1, 2, -1, -1],
            )
        ],
        beats=[ns(time=0.0, measure=1), ns(time=0.5, measure=0)],
        tones=[ns(time=0.0, id=0), ns(time=5.0, id=1)],
        sections=[ns(name="intro", number=1, startTime=0.0)],
        phraseIterations=[ns(phraseId=0, time=0.0, endTime=12.5)],
        phrases=[ns(maxDifficulty=3)],
        vocals=[ns(time=1.0, length=0.5, lyrics="hello")],
        levels=[level],
    )


def fake_b_standard_song():
    song = fake_song()
    song.metadata.tuning = [-5, -5, -5, -5, -5, -5]
    song.levels[0].notes[0].string = 4
    song.levels[0].notes[0].fret = 1
    song.levels[0].notes[0].slideTo = 3
    song.chordTemplates[0].frets = [0, 2, 2, 1, 0, 0]
    song.chordTemplates[0].fingers = [0, 2, 3, 1, 0, 0]
    return song


def test_song_chart_data_flattens_phrase_max_difficulty_not_global_highest():
    def note(time, fret):
        return ns(
            time=time,
            string=0,
            fret=fret,
            sustain=0.0,
            slideTo=-1,
            slideUnpitchTo=-1,
            bend_time=0.0,
            bends=[],
            leftHand=-1,
            mask=0,
            chordId=converter.UINT32_NONE,
            chordNoteId=converter.UINT32_NONE,
        )

    song = ns(
        chordTemplates=[],
        chordNotes=[],
        phraseIterations=[
            ns(phraseId=0, time=0.0, endTime=10.0),
            ns(phraseId=1, time=10.0, endTime=20.0),
        ],
        phrases=[ns(maxDifficulty=1), ns(maxDifficulty=2)],
        levels=[
            ns(difficulty=0, notes=[note(1.0, 1), note(11.0, 2)], anchors=[], fingerprints=[[], []]),
            ns(difficulty=1, notes=[note(1.0, 3), note(11.0, 4)], anchors=[], fingerprints=[[], []]),
            ns(difficulty=2, notes=[note(1.0, 5), note(11.0, 6)], anchors=[], fingerprints=[[], []]),
        ],
    )

    chart = converter._song_chart_data(song, [])

    assert [item["f"] for item in chart["notes"]] == [3, 6]
    assert [item["f"] for item in chart["phrases"][0]["levels"][-1]["notes"]] == [3]
    assert [item["f"] for item in chart["phrases"][1]["levels"][-1]["notes"]] == [6]


def test_convert_psarc_writes_valid_feedpak_directory(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    monkeypatch.setattr(converter, "PSARC", FakePSARC)
    monkeypatch.setattr(converter, "Song", FakeSong)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")
    output = tmp_path / "converted.feedpak"

    result = converter.convert_psarc(psarc, output, archive=False)

    manifest = yaml.safe_load((output / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["title"] == "Test Song"
    assert manifest["artist"] == "Test Artist"
    assert manifest["stems"][0]["codec"] == "wem"
    assert manifest["lyrics"] == "lyrics.json"
    assert manifest["lyrics_source"] == "authored"
    assert manifest["language"] == "und"
    assert manifest["lyric_tracks"] == [
        {
            "id": "original",
            "file": "lyrics.json",
            "language": "und",
            "kind": "original",
            "lyrics_source": "authored",
            "name": "Original",
        }
    ]
    assert manifest["authors"] == [{"name": "Chart Maker", "role": "charter"}]
    assert manifest["rigs"] == "rigs.json"
    assert (output / "arrangements" / "lead.json").is_file()
    assert (output / "arrangements" / "vocals.json").is_file()
    assert manifest["arrangements"][-1]["type"] == "vocals"
    rigs = json.loads((output / "rigs.json").read_text(encoding="utf-8"))
    assert [rig["name"] for rig in rigs["rigs"]] == ["Clean", "Drive"]
    assert rigs["rigs"][0]["blocks"][0]["role"] == "amp"
    assert rigs["rigs"][0]["blocks"][0]["name"] == "Amp_Clean"
    assert rigs["rigs"][0]["blocks"][0]["params"]["Gain"] == 0.2
    assert rigs["rigs"][0]["blocks"][1]["role"] == "cab"
    assert rigs["rigs"][1]["blocks"][0]["role"] == "drive"
    assert rigs["rigs"][1]["ext"]["source"]["definition"]["Name"] == "Drive"
    arrangement = json.loads((output / "arrangements" / "lead.json").read_text(encoding="utf-8"))
    assert "_rigs" not in arrangement
    assert arrangement["tones"]["base"] == "Clean"
    assert arrangement["tones"]["base_rig"] == "tone-0-clean"
    assert arrangement["tones"]["changes"] == [
        {"t": 0.0, "name": "Clean", "rig": "tone-0-clean"},
        {"t": 5.0, "name": "Drive", "rig": "tone-1-drive"},
    ]
    assert arrangement["stats"] == {"events": 4, "notes": 8}
    assert manifest["arrangements"][0]["event_count"] == 4
    assert manifest["arrangements"][0]["note_count"] == 8
    assert [tone["Name"] for tone in arrangement["tones"]["definitions"]] == ["Clean", "Drive"]
    clean_gear = arrangement["tones"]["definitions"][0]["GearList"]
    drive_gear = arrangement["tones"]["definitions"][1]["GearList"]
    assert clean_gear["Amp"]["Key"] == "Amp_Clean"
    assert clean_gear["Amp"]["PedalKey"] == "Amp_Clean"
    assert clean_gear["Cabinet"]["Type"] == "Cab_212"
    assert clean_gear["Cabinet"]["KnobValues"] == {}
    assert drive_gear["PrePedal1"]["Key"] == "Pedal_Overdrive"
    assert drive_gear["PrePedal1"]["Type"] == "Pedal_Overdrive"
    single_note = arrangement["notes"][0]
    assert single_note["pm"] is True
    assert single_note["hp"] is True
    assert single_note["mt"] is True
    chord_notes = arrangement["chords"][0]["notes"]
    assert all(note["sus"] == 0.25 for note in chord_notes)
    assert chord_notes[0]["sl"] == 4
    assert chord_notes[0]["hm"] is True
    assert chord_notes[1]["fhm"] is True
    assert chord_notes[2]["pm"] is True
    assert chord_notes[2]["slu"] == 2
    assert chord_notes[3]["mt"] is True
    assert chord_notes[4]["hp"] is True
    double_stop_targets = arrangement["notes"][1:3]
    assert double_stop_targets == [
        {"t": 3.0, "s": 1, "f": 6, "sus": 0.25, "sl": 5, "ln": True},
        {"t": 3.0, "s": 2, "f": 8, "sus": 0.25, "sl": 7, "ln": True},
    ]
    assert len(arrangement["chords"]) == 1

    validator = Path("references/feedpak-spec/tools/validate.py")
    if validator.is_file():
        validation = subprocess.run(
            [
                sys.executable,
                str(validator),
                str(result.output_path),
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert validation.returncode == 0, validation.stdout


def test_rs1_multisong_grouping_keeps_song_specific_audio():
    content = {
        "songs/bin/generic/first_lead.sng": b"first-sng",
        "songs/bin/generic/first_bass.sng": b"first-bass-sng",
        "songs/bin/generic/second_lead.sng": b"second-sng",
        "manifests/songs_rs1disc/first_lead.json": json.dumps(
            {"Entries": {"a": {"Attributes": {"SongKey": "First", "SongName": "First Song"}}}}
        ).encode(),
        "manifests/songs_rs1disc/second_lead.json": json.dumps(
            {"Entries": {"b": {"Attributes": {"SongKey": "Second", "SongName": "Second Song"}}}}
        ).encode(),
        "audio/windows/song_first.bnk": b"\x00" * 44 + (123456).to_bytes(4, "little"),
        "audio/windows/song_second.bnk": b"\x00" * 44 + (777777).to_bytes(4, "little"),
        "audio/windows/123456.wem": b"first-audio",
        "audio/windows/777777.wem": b"second-audio",
    }

    groups = converter._song_groups(content)
    assert sorted(groups) == ["first", "second"]

    first = converter._content_for_song_group(content, "first", groups["first"])
    second = converter._content_for_song_group(content, "second", groups["second"])
    assert "audio/windows/123456.wem" in first
    assert "audio/windows/777777.wem" not in first
    assert "audio/windows/777777.wem" in second
    assert "audio/windows/123456.wem" not in second


def test_convert_psarc_without_audio_fails_instead_of_placeholder(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    class NoAudioPSARC(FakePSARC):
        def parse_stream(self, fh):
            content = dict(super().parse_stream(fh))
            content.pop("audio/windows/test.wem")
            return content

    monkeypatch.setattr(converter, "PSARC", NoAudioPSARC)
    monkeypatch.setattr(converter, "Song", FakeSong)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")
    output = tmp_path / "converted.feedpak"

    with pytest.raises(ValueError, match="No audio file found"):
        converter.convert_psarc(psarc, output, archive=False)

    assert not (output / "stems" / "full.wav").exists()


def test_convert_psarc_can_package_demucs_stems(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    def fake_separator(source_audio, stems_dir, *, server_url, api_key, model, requested_stems):
        assert source_audio.name == "full.ogg"
        assert server_url == "http://demucs.local"
        assert api_key == "secret"
        assert model == "bs_roformer_sw"
        assert requested_stems == ["guitar", "drums"]
        (stems_dir / "guitar.ogg").write_bytes(b"OggSguitar")
        (stems_dir / "drums.ogg").write_bytes(b"OggSdrums")
        return [("guitar", "stems/guitar.ogg"), ("drums", "stems/drums.ogg")]

    monkeypatch.setattr(converter, "PSARC", FakePSARC)
    monkeypatch.setattr(converter, "Song", FakeSong)
    monkeypatch.setattr(converter, "_convert_wem_bytes_to_ogg", lambda _data, output: output.write_bytes(b"OggSfull") or True)
    monkeypatch.setattr(converter, "_run_demucs_server", fake_separator)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")
    output = tmp_path / "converted.feedpak"

    result = converter.convert_psarc(
        psarc,
        output,
        archive=False,
        separate_stems=True,
        demucs_url="http://demucs.local",
        demucs_api_key="secret",
        demucs_model="bs_roformer_sw",
        demucs_stems=["guitar", "drums"],
    )

    manifest = result.manifest
    assert manifest["stem_separation"] == {"engine": "demucs", "model": "bs_roformer_sw", "version": "1.0.0"}
    assert [stem["id"] for stem in manifest["stems"]] == ["full", "guitar", "drums"]
    assert manifest["stems"][0]["default"] is False
    assert all(stem["codec"] == "vorbis" for stem in manifest["stems"])
    assert (output / "stems" / "full.ogg").is_file()
    assert (output / "stems" / "guitar.ogg").is_file()
    assert (output / "stems" / "drums.ogg").is_file()


def test_demucs_post_file_includes_selected_model(tmp_path, monkeypatch):
    captured = {}

    def fake_post(endpoint, *, file_path, file_field, fields, headers, timeout):
        captured["endpoint"] = endpoint
        captured["file_path"] = file_path
        return {"status": "complete", "stems": {}}

    source = tmp_path / "full.ogg"
    source.write_bytes(b"OggS")
    monkeypatch.setattr(converter, "_post_multipart_json", fake_post)

    converter._demucs_post_file(
        "http://server.local",
        source,
        ["guitar", "bass"],
        {},
        model="bs_roformer_sw",
    )

    assert captured["endpoint"] == "http://server.local/separate?stems=guitar%2Cbass&model=bs_roformer_sw"


def test_run_demucs_server_cleans_remote_job_after_download(tmp_path, monkeypatch):
    calls = []

    def fake_post(_server_url, _source_audio, _requested_stems, _headers, *, model=""):
        return {"status": "complete", "job_id": "job123", "stems": {"guitar": "/files/job123/guitar.wav"}}

    def fake_download(_server_url, _stem_url, _headers):
        return b"RIFFstem"

    def fake_cleanup(server_url, job_id, headers):
        calls.append((server_url, job_id, headers))

    source = tmp_path / "full.ogg"
    source.write_bytes(b"OggS")
    monkeypatch.setattr(converter, "_demucs_post_file", fake_post)
    monkeypatch.setattr(converter, "_download_demucs_file", fake_download)
    monkeypatch.setattr(converter, "_cleanup_demucs_job", fake_cleanup)

    written = converter._run_demucs_server(
        source,
        tmp_path / "stems",
        server_url="http://demucs.local",
        api_key="secret",
        model="htdemucs_6s",
        requested_stems=["guitar"],
    )

    assert written == [("guitar", "stems/guitar.wav")]
    assert calls == [("http://demucs.local", "job123", {"X-API-Key": "secret"})]


def test_stem_separation_warns_when_model_omits_requested_stems(tmp_path, monkeypatch):
    stems_dir = tmp_path / "stems"
    stems_dir.mkdir()
    full = stems_dir / "full.ogg"
    full.write_bytes(b"OggSfull")

    def fake_separator(source_audio, stems_dir, *, server_url, api_key, model, requested_stems):
        (stems_dir / "bass.ogg").write_bytes(b"OggSbass")
        return [("bass", "stems/bass.ogg")]

    warnings = []
    monkeypatch.setattr(converter, "_run_demucs_server", fake_separator)

    stems, separation = converter._maybe_separate_stems(
        tmp_path,
        {"id": "full", "file": "stems/full.ogg", "codec": "vorbis", "default": True},
        warnings,
        separate_stems=True,
        demucs_url="http://demucs.local",
        demucs_api_key=None,
        demucs_model="htdemucs_ft",
        demucs_stems=["guitar", "bass"],
    )

    assert separation == {"engine": "demucs", "model": "htdemucs_ft", "version": "1.0.0"}
    assert [stem["id"] for stem in stems] == ["full", "bass"]
    assert any("guitar" in warning.message for warning in warnings)


def test_safe_output_stem_transliterates_multi_song_names():
    assert converter._safe_output_stem("Blue Öyster Cult - Mötley Crüe") == "Blue Oyster Cult - Motley Crue"


def test_demucs_url_falls_back_to_feedback_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "feedback"
    config_dir.mkdir()
    (config_dir / "studio_demucs.json").write_text(
        json.dumps({"url": "http://feedback-demucs.local/"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("FEEDFORGE_DEMUCS_URL", raising=False)
    monkeypatch.delenv("DEMUCS_SERVER_URL", raising=False)

    assert converter._resolve_demucs_url(None) == "http://feedback-demucs.local"


def test_demucs_url_falls_back_to_windows_feedback_desktop_config(tmp_path, monkeypatch):
    appdata = tmp_path / "AppData" / "Roaming"
    config_dir = appdata / "feedback-desktop" / "slopsmith-config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(
        json.dumps({"demucs_server_url": "http://windows-demucs.local/"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("CONFIG_DIR", raising=False)
    monkeypatch.delenv("FEEDFORGE_DEMUCS_URL", raising=False)
    monkeypatch.delenv("DEMUCS_SERVER_URL", raising=False)

    assert converter._resolve_demucs_url(None) == "http://windows-demucs.local"


def test_single_cli_output_folder_resolves_inside_existing_folder(tmp_path):
    input_path = tmp_path / "Song.psarc"
    output_dir = tmp_path / "converted"
    output_dir.mkdir()

    assert _single_output_path(input_path, output_dir) == output_dir / "Song.feedpak"


def test_single_cli_output_folder_resolves_inside_new_folder(tmp_path):
    input_path = tmp_path / "Song.psarc"
    output_dir = tmp_path / "converted"

    assert _single_output_path(input_path, output_dir) == output_dir / "Song.feedpak"


def test_single_cli_explicit_output_file_is_preserved(tmp_path):
    input_path = tmp_path / "Song.psarc"
    output_file = tmp_path / "custom.feedpak"

    assert _single_output_path(input_path, output_file) == output_file


def test_batch_output_layout_preserves_source_folders(tmp_path):
    source = tmp_path / "source"
    input_path = source / "Artist" / "Song.psarc"
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"fake")
    output_dir = tmp_path / "out"

    assert batch._batch_output_path(input_path, output_dir, "preserve", source) == output_dir / "Artist" / "Song.feedpak"


def test_batch_output_layout_sanitizes_artist_folder(tmp_path, monkeypatch):
    input_path = tmp_path / "Song.psarc"
    input_path.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(batch, "inspect_psarc", lambda _path: SimpleNamespace(artist='AC/DC: Live?'))

    assert batch._batch_output_path(input_path, output_dir, "artist", None) == output_dir / "AC_DC_ Live_" / "Song.feedpak"


def test_batch_output_name_template_uses_metadata(tmp_path, monkeypatch):
    input_path = tmp_path / "Song.psarc"
    input_path.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(
        batch,
        "inspect_psarc",
        lambda _path: SimpleNamespace(artist="Foo Fighters", title="My Hero", album="The Colour and the Shape", year=1997),
    )

    assert (
        batch._batch_output_path(input_path, output_dir, "flat", None, "{artist} - {title}")
        == output_dir / "Foo Fighters - My Hero.feedpak"
    )


def test_batch_output_name_template_sanitizes_filename(tmp_path, monkeypatch):
    input_path = tmp_path / "Song.psarc"
    input_path.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(batch, "inspect_psarc", lambda _path: SimpleNamespace(artist="AC/DC", title="Live: One?"))

    assert (
        batch._batch_output_path(input_path, output_dir, "flat", None, "{title} - {artist}")
        == output_dir / "Live_ One_ - AC_DC.feedpak"
    )


def test_batch_output_name_template_transliterates_metadata(tmp_path, monkeypatch):
    input_path = tmp_path / "Song.psarc"
    input_path.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(batch, "inspect_psarc", lambda _path: SimpleNamespace(artist="Motörhead", title="Frédéric Crüe"))

    assert (
        batch._batch_output_path(input_path, output_dir, "artist", None, "{artist} - {title}")
        == output_dir / "Motorhead" / "Motorhead - Frederic Crue.feedpak"
    )


def test_tone_rig_blocks_follow_feedpak_chain_order_and_key_names():
    definition = {
        "Name": "Full Chain",
        "GearList": {
            "PrePedal1": {"Key": "Pedal_Drive", "Type": "Pedals", "KnobValues": {}},
            "Amp": {"Key": "Amp_DSL", "Type": "Amps", "KnobValues": {}},
            "PostPedal1": {"Key": "Pedal_Chorus", "Type": "Pedals", "KnobValues": {}},
            "Rack1": {"Key": "Rack_Delay", "Type": "Racks", "KnobValues": {}},
            "Cabinet": {"Key": "Cab_412_57_Cone", "Type": "Cabinets", "KnobValues": {}},
        },
    }

    blocks = converter._tone_blocks_from_definition(definition)

    assert [(block["role"], block["name"]) for block in blocks] == [
        ("drive", "Pedal_Drive"),
        ("amp", "Amp_DSL"),
        ("modulation", "Pedal_Chorus"),
        ("delay", "Rack_Delay"),
        ("cab", "Cab_412_57_Cone"),
    ]


def test_convert_psarc_can_remap_b_standard_to_seven_string(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_b_standard_song()

    monkeypatch.setattr(converter, "PSARC", FakePSARC)
    monkeypatch.setattr(converter, "Song", FakeSong)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")
    output = tmp_path / "converted.feedpak"

    converter.convert_psarc(psarc, output, archive=False, b_standard_to_7_string=True)

    manifest = yaml.safe_load((output / "manifest.yaml").read_text(encoding="utf-8"))
    arrangement = json.loads((output / "arrangements" / "lead.json").read_text(encoding="utf-8"))

    assert manifest["arrangements"][0]["tuning"] == [0, 0, 0, 0, 0, 0, 0]
    assert arrangement["tuning"] == [0, 0, 0, 0, 0, 0, 0]
    assert arrangement["notes"][0]["s"] == 4
    assert arrangement["notes"][0]["f"] == 0
    assert arrangement["notes"][0]["sl"] == 2
    assert len(arrangement["templates"][0]["frets"]) == 7
    assert arrangement["templates"][0]["frets"][0:4] == [0, 2, 2, 1]
    assert arrangement["templates"][0]["frets"][5] == 0


def test_convert_psarc_can_skip_tones(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    monkeypatch.setattr(converter, "PSARC", FakePSARC)
    monkeypatch.setattr(converter, "Song", FakeSong)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")
    output = tmp_path / "converted.feedpak"

    converter.convert_psarc(psarc, output, archive=False, include_tones=False)

    manifest = yaml.safe_load((output / "manifest.yaml").read_text(encoding="utf-8"))
    arrangement = json.loads((output / "arrangements" / "lead.json").read_text(encoding="utf-8"))

    assert "rigs" not in manifest
    assert "tones" not in arrangement
    assert not (output / "rigs.json").exists()


def test_tone_matching_ignores_numeric_substring_keys():
    metadata = {
        "arrangement_tones": [
            {
                "match_keys": ["32187", "3", "bass"],
                "base": "bass_tone",
                "definitions": [{"Name": "bass_tone", "Key": "bass_tone"}],
            },
            {
                "match_keys": ["urn:application:xml:38sprock_lead", "32196", "0", "lead"],
                "base": "lead_dist",
                "definitions": [
                    {"Name": "lead_dist", "Key": "lead_dist"},
                    {"Name": "lead_solo", "Key": "lead_solo"},
                ],
            },
            {
                "match_keys": ["urn:application:xml:38sprock_rhythm", "32189", "1", "rhythm"],
                "base": "rhythm_dist",
                "definitions": [{"Name": "rhythm_dist", "Key": "rhythm_dist"}],
            },
        ]
    }

    lead = converter._tone_info_for_arrangement("songs/bin/generic/38sprock_lead.sng", metadata)
    rhythm = converter._tone_info_for_arrangement("songs/bin/generic/38sprock_rhythm.sng", metadata)
    bass = converter._tone_info_for_arrangement("songs/bin/generic/38sprock_bass.sng", metadata)

    assert lead["base"] == "lead_dist"
    assert rhythm["base"] == "rhythm_dist"
    assert bass["base"] == "bass_tone"


def test_arrangement_ids_prefer_manifest_route_flags_over_file_names():
    metadata = {
        "arrangement_names": converter._arrangement_names(
            [
                {
                    "SongXml": "urn:application:xml:6amsalvation_combo",
                    "ArrangementName": "Combo",
                    "ArrangementProperties": {"pathLead": 1, "pathRhythm": 0, "pathBass": 0},
                },
                {
                    "SongXml": "urn:application:xml:6amsalvation_lead",
                    "ArrangementName": "Lead",
                    "ArrangementProperties": {"pathLead": 0, "pathRhythm": 1, "pathBass": 0},
                },
                {
                    "SongXml": "urn:application:xml:6amsalvation_bass",
                    "ArrangementName": "Bass",
                    "ArrangementProperties": {"pathLead": 0, "pathRhythm": 0, "pathBass": 1},
                },
            ]
        )
    }

    assert converter._arrangement_id("songs/bin/generic/6amsalvation_combo.sng", metadata) == "lead"
    assert converter._arrangement_id("songs/bin/generic/6amsalvation_lead.sng", metadata) == "rhythm"
    assert converter._arrangement_id("songs/bin/generic/6amsalvation_bass.sng", metadata) == "bass"


def test_tone_normalization_drops_empty_knob_keys():
    definition = converter._normalize_tone_definition(
        {
            "Name": "Octave",
            "GearList": {
                "PrePedal1": {
                    "PedalKey": "Pedal_OctaveUp",
                    "KnobValues": {
                        "": 12,
                        "Pedal_OctaveUp_Mix": 100,
                    },
                }
            },
        }
    )

    knobs = definition["GearList"]["PrePedal1"]["KnobValues"]

    assert knobs == {"Pedal_OctaveUp_Mix": 100}


def test_inspector_previews_exported_tones(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    monkeypatch.setattr(inspector, "PSARC", FakePSARC)
    monkeypatch.setattr(inspector, "Song", FakeSong)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")

    preview = inspector.inspect_psarc(psarc)

    assert len(preview.tones) == 1
    tone_arrangement = preview.tones[0]
    assert tone_arrangement.base == "Clean"
    assert tone_arrangement.base_rig == "tone-0-clean"
    assert [tone.name for tone in tone_arrangement.definitions] == ["Clean", "Drive"]
    assert [(change.time, change.name, change.rig) for change in tone_arrangement.changes] == [
        (0.0, "Clean", "tone-0-clean"),
        (5.0, "Drive", "tone-1-drive"),
    ]
    clean_gear = tone_arrangement.definitions[0].gear
    assert [(gear.slot, gear.key, gear.type) for gear in clean_gear] == [
        ("Amp", "Amp_Clean", "Amps"),
        ("Cabinet", "Cab_212", "Cab_212"),
    ]
    assert clean_gear[0].knob_values == {"Gain": 0.2, "Bass": 0.5}

