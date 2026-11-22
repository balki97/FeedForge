import subprocess
import urllib.error
import pytest
from feedback_converter import songsterr

@pytest.mark.parametrize('frozen,platform,original,expected', [
    (True, 'linux', None, None),
    (True, 'linux', '/usr/local/lib', '/usr/local/lib'),
    (True, 'linux', '', ''),
    (False, 'linux', None, '/bundle/_internal'),
    (True, 'win32', None, '/bundle/_internal'),
])
def test_curl_uses_system_libraries(monkeypatch, frozen, platform, original, expected):
    monkeypatch.setattr(songsterr.sys, 'frozen', frozen, raising=False)
    monkeypatch.setattr(songsterr.sys, 'platform', platform)
    monkeypatch.setenv('LD_LIBRARY_PATH', '/bundle/_internal')
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.example')
    monkeypatch.delenv('LD_LIBRARY_PATH_ORIG', raising=False)
    if original is not None:
        monkeypatch.setenv('LD_LIBRARY_PATH_ORIG', original)
    def unavailable(request):
        raise urllib.error.HTTPError(request.full_url, 103, 'Early Hints', {}, None)
    monkeypatch.setattr(songsterr, '_verified_urlopen', unavailable)
    monkeypatch.setattr(songsterr.shutil, 'which', lambda name: '/usr/bin/curl')
    def run(command, **kwargs):
        assert kwargs['env'].get('LD_LIBRARY_PATH') == expected
        assert kwargs['env']['HTTPS_PROXY'] == 'http://proxy.example'
        assert '--insecure' not in command and '-k' not in command
        return subprocess.CompletedProcess(command, 0, b'content\n200', b'')
    monkeypatch.setattr(songsterr.subprocess, 'run', run)
    assert songsterr._get_bytes('https://example.com') == b'content'
    assert songsterr.os.environ['LD_LIBRARY_PATH'] == '/bundle/_internal'
