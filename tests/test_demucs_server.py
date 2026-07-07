from __future__ import annotations

from pathlib import Path

from feedback_converter import demucs_server


def test_normalize_stems_filters_unknowns_and_duplicates():
    assert demucs_server.normalize_stems(" guitar, bass, guitar, unknown, vocals ") == [
        "guitar",
        "bass",
        "vocals",
    ]


def test_find_stem_file_prefers_supported_audio_suffix(tmp_path):
    (tmp_path / "guitar.wav").write_bytes(b"wav")

    assert demucs_server._find_stem_file(tmp_path, "guitar") == tmp_path / "guitar.wav"
    assert demucs_server._find_stem_file(tmp_path, "drums") is None


def test_safe_job_id_strips_path_characters():
    assert demucs_server._safe_job_id("../abc-123_x") == "abc-123_x"
