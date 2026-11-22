import gzip
import io
import json
import subprocess
import urllib.error

import pytest

from feedback_converter import songsterr
from feedback_converter.cli import main


URL = "https://www.songsterr.com/a/wsa/caramel-candid-sugar-on-the-wound-tab-s6843450"


@pytest.mark.parametrize("url", [URL, "https://songsterr.com/api/video-points/1/2/list"])
def test_direct_403_is_actionable_and_does_not_retry(monkeypatch, url):
    def denied(request):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b"policy denial"))

    monkeypatch.setattr(songsterr, "_verified_urlopen", denied)
    monkeypatch.setattr(songsterr.subprocess, "run", lambda *a, **kw: pytest.fail("Denied access must not be retried"))
    with pytest.raises(songsterr.SongsterrAccessError, match="HTTP 403") as error:
        songsterr._get_bytes(url)
    assert "Guitar Pro" in str(error.value)


def early_hints(monkeypatch, result):
    def hints(request):
        raise urllib.error.HTTPError(request.full_url, 103, "Early Hints", {}, None)

    monkeypatch.setattr(songsterr, "_verified_urlopen", hints)
    monkeypatch.setattr(songsterr.shutil, "which", lambda name: "curl")
    calls = []

    def run(command, **options):
        calls.append(command)
        assert command[command.index("--write-out") + 1] == "\n%{http_code}"
        assert options["timeout"] == 30
        assert "--insecure" not in command and "-k" not in command
        return result

    monkeypatch.setattr(songsterr.subprocess, "run", run)
    return calls


def test_early_hints_then_curl_403_preserves_access_error(monkeypatch):
    calls = early_hints(monkeypatch, subprocess.CompletedProcess([], 22, b"\n403", b"curl: (22) HTTP error"))
    with pytest.raises(songsterr.SongsterrAccessError, match="HTTP 403"):
        songsterr._get_bytes(URL)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"json\n200", gzip.compress(b'{"ok":true}')])
def test_curl_status_is_removed_before_returning_or_decompressing(monkeypatch, body):
    early_hints(monkeypatch, subprocess.CompletedProcess([], 0, body + b"\n200", b""))
    expected = gzip.decompress(body) if body.startswith(b"\x1f\x8b") else body
    assert songsterr._get_bytes(URL) == expected


@pytest.mark.parametrize("url", ["https://coverartarchive.org/cover",
                                 "https://dqsljvtekg760.cloudfront.net/part/1/0"])
def test_other_hosts_keep_their_original_http_error(monkeypatch, url):
    def denied(request):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(songsterr, "_verified_urlopen", denied)
    with pytest.raises(urllib.error.HTTPError):
        songsterr._get_bytes(url)


def test_curl_transport_failure_keeps_diagnostics(monkeypatch):
    early_hints(monkeypatch, subprocess.CompletedProcess([], 28, b"\n000", b"curl: request timed out"))
    with pytest.raises(RuntimeError, match="timed out"):
        songsterr._get_bytes(URL)


def test_chart_mirror_errors_keep_the_existing_fallback(monkeypatch):
    calls = []

    def denied(url):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        return b'{"measures": []}'

    monkeypatch.setattr(songsterr, "_get_bytes", denied)
    assert songsterr._download_part({"songId": 1, "revisionId": 2}, 0) == {"measures": []}
    assert len(calls) == 2


def test_video_access_denial_keeps_optional_video_unavailable(monkeypatch):
    def denied(url):
        raise songsterr.SongsterrAccessError("HTTP 403")

    monkeypatch.setattr(songsterr, "_get_bytes", denied)
    assert songsterr._main_video({"songId": 1, "revisionId": 2}) is None


def test_access_error_reaches_desktop_json_response(tmp_path, monkeypatch, capsys):
    from feedback_converter import songsterr_cli

    def denied(url):
        songsterr._check_songsterr_access(url, 403)

    monkeypatch.setattr(songsterr_cli, "analyze", denied)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"action": "analyze", "payload": URL}))
    assert main(["songsterr", str(request)]) == 1
    response = json.loads(capsys.readouterr().out)
    assert response["ok"] is False
    assert "Songsterr refused this request (HTTP 403)" in response["error"]
