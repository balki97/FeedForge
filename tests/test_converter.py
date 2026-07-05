from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

from feedback_converter import converter
from feedback_converter import inspector


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


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
    assert manifest["rigs"] == "rigs.json"
    assert (output / "arrangements" / "lead.json").is_file()
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
    if not validator.is_file():
        return

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
