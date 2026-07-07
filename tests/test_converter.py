from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import yaml

from feedback_converter import converter
from feedback_converter import inspector
from feedback_converter import rig_builder_seed
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


def test_convert_psarc_can_package_demucs_stems(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    def fake_separator(source_audio, stems_dir, *, server_url, api_key, requested_stems):
        assert source_audio.name == "full.ogg"
        assert server_url == "http://demucs.local"
        assert api_key == "secret"
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
        demucs_stems=["guitar", "drums"],
    )

    manifest = result.manifest
    assert manifest["stem_separation"] == {"engine": "demucs", "model": "server", "version": "1.0.0"}
    assert [stem["id"] for stem in manifest["stems"]] == ["full", "guitar", "drums"]
    assert manifest["stems"][0]["default"] is False
    assert all(stem["codec"] == "vorbis" for stem in manifest["stems"])
    assert (output / "stems" / "full.ogg").is_file()
    assert (output / "stems" / "guitar.ogg").is_file()
    assert (output / "stems" / "drums.ogg").is_file()


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


def test_inspector_previews_rig_builder_routes(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    db_dir = tmp_path / "feedback-desktop" / "slopsmith-config"
    db_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_dir / "nam_tone.db")
    conn.executescript(
        """
        CREATE TABLE presets (
          id INTEGER PRIMARY KEY,
          name TEXT,
          model_file TEXT,
          ir_file TEXT,
          input_gain REAL,
          output_gain REAL,
          gate_threshold REAL,
          settings_json TEXT
        );
        CREATE TABLE tone_mappings (
          id INTEGER PRIMARY KEY,
          filename TEXT,
          tone_key TEXT,
          preset_id INTEGER
        );
        CREATE TABLE preset_pieces (
          id INTEGER PRIMARY KEY,
          preset_id INTEGER,
          slot_order INTEGER,
          slot TEXT,
          rs_gear_type TEXT,
          kind TEXT,
          file TEXT,
          params_json TEXT,
          tone3000_id INTEGER,
          assigned_mode TEXT,
          bypassed INTEGER,
          vst_path TEXT,
          vst_format TEXT,
          vst_state TEXT
        );
        """
    )
    conn.execute("INSERT INTO presets VALUES (1, ?, '', '', 1, 1, -60, '{}')", ("input.feedpak::Clean",))
    conn.execute("INSERT INTO tone_mappings VALUES (1, ?, 'Clean', 1)", ("input.feedpak",))
    conn.execute(
        "INSERT INTO preset_pieces VALUES (1, 1, 0, 'amp', 'Amp_Clean', 'vst', NULL, '{}', NULL, 'auto', 0, ?, 'VST3', NULL)",
        (r"C:\Plugin\Amp.vst3",),
    )
    conn.execute(
        "INSERT INTO preset_pieces VALUES (2, 1, 1, 'cabinet', 'Cab_212', 'none', NULL, '{}', NULL, 'auto', 0, NULL, NULL, NULL)",
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(inspector, "PSARC", FakePSARC)
    monkeypatch.setattr(inspector, "Song", FakeSong)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")

    preview = inspector.inspect_psarc(psarc)

    assert len(preview.rig_builder) == 1
    route = preview.rig_builder[0]
    assert route.tone_key == "Clean"
    assert route.status == "partial"
    assert [(stage.slot, stage.gear, stage.kind, stage.asset, stage.status) for stage in route.stages] == [
        ("amp", "Amp_Clean", "vst", "Amp.vst3", "ready"),
        ("cabinet", "Cab_212", "none", "", "missing"),
    ]


def test_seed_rig_builder_routes_writes_playable_rows(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    db_dir = tmp_path / "feedback-desktop" / "slopsmith-config"
    db_dir.mkdir(parents=True)
    (db_dir / "nam_irs" / "other").mkdir(parents=True)
    (db_dir / "nam_irs" / "other" / "greenback 212 1 mono.wav").write_bytes(b"ir")
    db_path = db_dir / "nam_tone.db"

    data_dir = tmp_path / "rig_builder" / "data"
    vst_dir = tmp_path / "rig_builder" / "vst" / "amps"
    data_dir.mkdir(parents=True)
    vst_dir.mkdir(parents=True)
    (vst_dir / "Amp.vst3").write_bytes(b"vst")
    (data_dir / "rs_gear_to_vst.json").write_text(
        json.dumps({"Amp_Clean": [{"name": "Amp", "format": "VST3", "bundled": "vst/amps/Amp.vst3"}]}),
        encoding="utf-8",
    )
    (data_dir / "rs_cab_mic_map.json").write_text(
        json.dumps({"Cab_212": {"5c": {"effect_name": "Cab_212", "ir_file": "rocksmith/cab_212.wav"}}}),
        encoding="utf-8",
    )
    (data_dir / "rs_knob_to_vst_param.json").write_text(
        json.dumps({"Amp_Clean": {"amp": {"Gain": {"param": "Gain", "scale": 0.01}}}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(rig_builder_seed, "PSARC", FakePSARC)
    monkeypatch.setattr(rig_builder_seed, "Song", FakeSong)
    monkeypatch.setattr(rig_builder_seed, "_rig_builder_data_dir", lambda: data_dir)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")

    result = rig_builder_seed.seed_rig_builder_routes(psarc)

    assert result.song_key == "input.feedpak"
    assert any(tone.tone_key == "Tone_0" for tone in result.tones)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT tm.filename, tm.tone_key, pp.slot, pp.rs_gear_type, pp.kind, pp.file, pp.vst_path, pp.vst_state "
        "FROM tone_mappings tm JOIN preset_pieces pp ON pp.preset_id = tm.preset_id "
        "WHERE tm.tone_key = 'Tone_0' ORDER BY pp.slot_order"
    ).fetchall()
    conn.close()

    assert rows[0][0:5] == ("input.feedpak", "Tone_0", "amp", "Amp_Clean", "vst")
    assert rows[0][6].endswith("Amp.vst3")
    assert rows[0][7] is not None
    assert rows[1][2:6] == ("cabinet", "Cab_212", "ir", "other/greenback 212 1 mono.wav")


def test_seed_rig_builder_routes_uses_tone3000_capture_ids(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    db_dir = tmp_path / "feedback-desktop" / "slopsmith-config"
    db_dir.mkdir(parents=True)
    (db_dir / "nam_irs" / "other").mkdir(parents=True)
    (db_dir / "nam_irs" / "other" / "greenback 212 1 mono.wav").write_bytes(b"ir")
    db_path = db_dir / "nam_tone.db"

    data_dir = tmp_path / "rig_builder" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "default_captures.json").write_text(
        json.dumps({"Amp_Clean": {"kind": "nam", "model_id": 123, "tone3000_id": 456}}),
        encoding="utf-8",
    )
    (data_dir / "rs_gear_to_vst.json").write_text("{}", encoding="utf-8")
    (data_dir / "rs_cab_mic_map.json").write_text("{}", encoding="utf-8")
    (data_dir / "rs_knob_to_vst_param.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(rig_builder_seed, "PSARC", FakePSARC)
    monkeypatch.setattr(rig_builder_seed, "Song", FakeSong)
    monkeypatch.setattr(rig_builder_seed, "_rig_builder_data_dir", lambda: data_dir)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")

    result = rig_builder_seed.seed_rig_builder_routes(psarc)

    assert any(tone.tone_key == "Tone_0" and tone.status == "ready" for tone in result.tones)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT kind, file, tone3000_id, assigned_mode FROM preset_pieces WHERE rs_gear_type = 'Amp_Clean'"
    ).fetchone()
    conn.close()

    assert row == ("nam", None, 456, "feedforge")


def test_seed_rig_builder_routes_marks_unmapped_gear_pending_for_feedback_fallback(tmp_path, monkeypatch):
    class FakeSong:
        @staticmethod
        def parse(_data):
            return fake_song()

    db_dir = tmp_path / "feedback-desktop" / "slopsmith-config"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "nam_tone.db"

    data_dir = tmp_path / "rig_builder" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "default_captures.json").write_text("{}", encoding="utf-8")
    (data_dir / "rs_to_real.json").write_text("{}", encoding="utf-8")
    (data_dir / "rs_gear_to_vst.json").write_text("{}", encoding="utf-8")
    (data_dir / "rs_cab_mic_map.json").write_text("{}", encoding="utf-8")
    (data_dir / "rs_knob_to_vst_param.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(rig_builder_seed, "PSARC", FakePSARC)
    monkeypatch.setattr(rig_builder_seed, "Song", FakeSong)
    monkeypatch.setattr(rig_builder_seed, "_rig_builder_data_dir", lambda: data_dir)

    psarc = tmp_path / "input.psarc"
    psarc.write_bytes(b"fake")

    result = rig_builder_seed.seed_rig_builder_routes(psarc)

    pending = [tone for tone in result.tones if tone.tone_key == "Tone_0"]
    assert pending and pending[0].status == "partial"
    assert "Amp_Clean" in pending[0].missing
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT pp.slot, pp.rs_gear_type, pp.kind, pp.file, pp.tone3000_id "
        "FROM tone_mappings tm JOIN preset_pieces pp ON pp.preset_id = tm.preset_id "
        "WHERE tm.filename = 'input.feedpak' AND tm.tone_key = 'Tone_0' "
        "ORDER BY pp.slot_order"
    ).fetchall()
    conn.close()

    assert rows[0] == ("amp", "Amp_Clean", "none", None, None)
    assert rows[1] == ("cabinet", "Cab_212", "none", None, None)
    settings = json.loads((db_dir / "rig_builder_settings.json").read_text(encoding="utf-8"))
    assert settings["curated_only"] is False


def test_rig_builder_data_dir_accepts_portable_root(tmp_path, monkeypatch):
    portable_root = tmp_path / "FeedBackPortable"
    data_dir = portable_root / "resources" / "slopsmith" / "plugins" / "rig_builder" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "rs_gear_to_vst.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("FEEDFORGE_RIG_BUILDER_DATA_DIR", str(portable_root))

    assert inspector._rig_builder_data_dir() == data_dir
