from __future__ import annotations

import zipfile
import json

import yaml

import pytest

from feedback_converter.feedpak_validator import (
    FeedpakValidationError,
    require_valid_feedpak,
    validate_feedpak,
)


def test_feedpak_validator_rejects_missing_manifest(tmp_path):
    package = tmp_path / "missing-manifest.feedpak"
    package.mkdir()

    result = validate_feedpak(package)

    assert result.ok is False
    assert result.errors == ["no manifest.yaml at package root"]


def test_feedpak_validator_rejects_unsafe_archive_path(tmp_path):
    package = tmp_path / "unsafe.feedpak"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    result = validate_feedpak(package)

    assert result.ok is False
    assert result.errors == ["unsafe path inside archive: ../outside.txt"]
    assert not (tmp_path / "outside.txt").exists()


def test_require_valid_feedpak_raises_with_validation_report(tmp_path):
    package = tmp_path / "invalid.feedpak"
    package.mkdir()

    with pytest.raises(FeedpakValidationError) as raised:
        require_valid_feedpak(package)

    assert raised.value.result.ok is False
    assert "no manifest.yaml" in str(raised.value)


@pytest.mark.parametrize("payload,valid", [
    ({"version": 1, "hits": [{"t": 0, "p": "snare"}]}, True),
    ({"version": 1, "hits": [{"t": 0}]}, False),
    (None, False),
])
def test_arrangement_drum_tab_validation(tmp_path, payload, valid):
    manifest = {
        "title": "Drums", "artist": "Test", "duration": 1,
        "arrangements": [{"id": "drums", "drum_tab": "drums.json"}],
        "stems": [{"id": "full", "file": "full.ogg"}],
    }
    (tmp_path / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    (tmp_path / "full.ogg").write_bytes(b"audio")
    if payload is not None:
        (tmp_path / "drums.json").write_text(json.dumps(payload))
    report = validate_feedpak(tmp_path)
    assert report.ok is valid, report.errors
    if not valid:
        assert any("drums.json" in error for error in report.errors)
