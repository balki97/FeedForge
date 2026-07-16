from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

from feedback_converter import feedpak


def _write_sample_feedpak(path: Path) -> None:
    root = path.with_suffix(".work")
    (root / "arrangements").mkdir(parents=True)
    (root / "stems").mkdir()
    (root / "arrangements" / "lead.json").write_text(json.dumps({"notes": [{"t": 1.0}]}), encoding="utf-8")
    (root / "rigs.json").write_text(
        json.dumps(
            {
                "version": 1,
                "rigs": [
                    {
                        "id": "lead-rig",
                        "name": "Lead",
                        "instrument": "guitar",
                        "blocks": [
                            {
                                "id": "amp",
                                "role": "amp",
                                "name": "Amp_GB50",
                                "params": {"Gain": 50},
                                "ext": {"source": {"slot": "Amp", "amp": {"Key": "Amp_GB50"}}},
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "stems" / "full.ogg").write_bytes(b"ogg")
    (root / "cover.png").write_bytes(b"png")
    (root / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "feedpak_version": "1.14.0",
                "title": "Old",
                "artist": "Artist",
                "album": "Album",
                "year": 2000,
                "arrangements": [
                    {
                        "id": "lead",
                        "name": "Lead",
                        "file": "arrangements/lead.json",
                        "type": "guitar",
                        "event_count": 1,
                        "note_count": 1,
                    }
                ],
                "stems": [{"id": "full", "file": "stems/full.ogg", "codec": "vorbis", "default": True}],
                "cover": "cover.png",
                "rigs": "rigs.json",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in root.rglob("*"):
            if item.is_file():
                zf.write(item, item.relative_to(root).as_posix())


def _read_manifest(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        return yaml.safe_load(zf.read("manifest.yaml"))


def test_inspect_feedpak_reads_manifest_cover_stems_and_rigs(tmp_path):
    package = tmp_path / "song.feedpak"
    _write_sample_feedpak(package)
    cover_dir = tmp_path / "cover"

    preview = feedpak.inspect_feedpak(package, cover_dir=cover_dir)

    assert preview["source_type"] == "feedpak"
    assert preview["title"] == "Old"
    assert preview["cover_path"].endswith("cover.png")
    assert preview["arrangements"][0]["name"] == "Lead"
    assert preview["stems"][0]["id"] == "full"
    assert preview["tones"][0]["definitions"][0]["gear"][0]["key"] == "Amp_GB50"


def test_update_feedpak_edits_metadata_authors_and_cover(tmp_path):
    package = tmp_path / "song.feedpak"
    output = tmp_path / "edited.feedpak"
    cover = tmp_path / "new.jpg"
    cover.write_bytes(b"jpg")
    _write_sample_feedpak(package)

    result = feedpak.update_feedpak(
        package,
        output,
        metadata={"title": "New Title", "artist": "New Artist", "year": "2026"},
        authors=[{"name": "Charter", "role": "charter"}],
        cover_path=cover,
    )

    assert result.output_path == output
    manifest = _read_manifest(output)
    assert manifest["title"] == "New Title"
    assert manifest["artist"] == "New Artist"
    assert manifest["year"] == 2026
    assert manifest["authors"] == [{"name": "Charter", "role": "charter"}]
    assert manifest["cover"] == "cover.jpg"


def test_feedpak_stem_separation_keeps_full_mix(tmp_path, monkeypatch):
    package = tmp_path / "song.feedpak"
    output = tmp_path / "stems.feedpak"
    _write_sample_feedpak(package)

    def fake_run_demucs(source_audio, stems_dir, *, server_url, api_key, model, requested_stems):
        target = stems_dir / "guitar.ogg"
        target.write_bytes(b"guitar")
        return [("guitar", "stems/guitar.ogg")]

    monkeypatch.setattr(feedpak, "_run_demucs_server", fake_run_demucs, raising=False)
    monkeypatch.setattr("feedback_converter.converter._run_demucs_server", fake_run_demucs)

    result = feedpak.update_feedpak(
        package,
        output,
        separate_stems=True,
        demucs_url="http://127.0.0.1:7865",
        demucs_model="htdemucs_6s",
        demucs_stems=["guitar"],
    )

    assert not result.warnings
    manifest = _read_manifest(output)
    assert [stem["id"] for stem in manifest["stems"]] == ["full", "guitar"]
    with zipfile.ZipFile(output) as zf:
        assert "stems/full.ogg" in zf.namelist()
        assert "stems/guitar.ogg" in zf.namelist()
