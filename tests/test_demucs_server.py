from __future__ import annotations

from pathlib import Path

import pytest

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


def test_delete_job_removes_upload_and_result_files(tmp_path):
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi test client is not installed")

    storage = tmp_path / "runtime" / "jobs"
    job_id = "abc123"
    upload = storage / "uploads" / f"{job_id}.ogg"
    result = storage / "jobs" / job_id / "guitar.wav"
    upload.parent.mkdir(parents=True)
    result.parent.mkdir(parents=True)
    upload.write_bytes(b"OggS")
    result.write_bytes(b"RIFF")

    client = TestClient(demucs_server.create_app(storage))
    response = client.delete(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "job_id": job_id}
    assert not upload.exists()
    assert not result.exists()
