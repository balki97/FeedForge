from pathlib import Path

import pytest

from feedback_converter import batch, converter
from feedback_converter.cli import main


@pytest.fixture
def songs(tmp_path, monkeypatch):
    source = tmp_path / "source" / "album.psarc"
    source.parent.mkdir()
    source.write_bytes(b"source")
    entries = [(name, {"title": name, "artist": "Artist", "album": "Album"})
               for name in ("First", "Second")]
    monkeypatch.setattr(converter, "_read_psarc_song_entries", lambda *a, **kw: entries)
    monkeypatch.setattr(converter, "_extract_metadata", lambda content: content)
    monkeypatch.setattr(converter, "_validate_song_audio_entries", lambda *a, **kw: None)
    calls = []

    def convert(source, target, **options):
        assert not target.exists(), "An existing package must never be converted"
        assert options["overwrite"] is False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"new")
        calls.append(target)
        return converter.ConversionResult(target, target, {})

    monkeypatch.setattr(converter, "convert_psarc", convert)
    stat = source.stat()
    data = converter.PsarcPlanningData(source, stat.st_size, stat.st_mtime_ns, entries)
    monkeypatch.setattr(batch, "load_psarc_planning_data", lambda *a, **kw: data)
    return source, data, calls


@pytest.mark.parametrize("layout", ["flat", "artist", "preserve"])
def test_mixed_archive_skips_existing_without_numbered_duplicate(tmp_path, songs, layout):
    source, data, calls = songs
    output = tmp_path / "out"
    plan = converter.plan_loaded_psarc_songs(data, output, output_layout=layout,
                                            source_root=tmp_path, name_template="{title}")
    existing = plan.outputs[0].output_path
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"keep unchanged")
    request = {"items": [{"inputPath": str(source), "sourceRoot": str(tmp_path)}],
               "outputDir": str(output), "outputLayout": layout,
               "nameTemplate": "{title}", "skipExisting": True}
    planned = batch.plan_conversion_request(request)["items"][0]
    assert Path(planned["outputs"][0]["path"]) == existing
    results = converter.convert_psarc_songs(source, output_plan=planned,
                                            skip_existing=True, overwrite=True)
    assert [r.skipped for r in results] == [True, False]
    assert calls == [plan.outputs[1].output_path]
    assert existing.read_bytes() == b"keep unchanged"
    assert not list(output.rglob("* (2).feedpak"))


def test_skip_disabled_retains_numbered_outputs(tmp_path, songs):
    source, data, calls = songs
    output = tmp_path / "out"
    output.mkdir()
    (output / "First.feedpak").write_bytes(b"keep")
    plan = converter.plan_loaded_psarc_songs(data, output, name_template="{title}")
    assert plan.outputs[0].output_path.name == "First (2).feedpak"
    results = converter.convert_psarc_songs(source, output_plan=plan.to_dict())
    assert not any(r.skipped for r in results)
    assert len(calls) == 2


def test_cli_reports_all_skipped_as_success(tmp_path, songs, capsys):
    source, data, calls = songs
    output = tmp_path / "out"
    output.mkdir()
    for name in ("First", "Second"):
        (output / f"{name}.feedpak").write_bytes(b"keep")
    assert main([str(source), "-o", str(output), "--name-template", "{title}",
                 "--skip-existing", "--overwrite"]) == 0
    stdout = capsys.readouterr().out
    assert stdout.count("skipped ") == 2
    assert "wrote " not in stdout
    assert calls == []
