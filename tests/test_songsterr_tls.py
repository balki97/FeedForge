import io
import ssl
import urllib.error

import pytest

from feedback_converter import songsterr


def test_certificate_store_failure_retries_with_verified_bundled_roots(monkeypatch):
    calls = []

    def open_url(request, **options):
        calls.append(options)
        if len(calls) == 1:
            raise urllib.error.URLError(ssl.SSLCertVerificationError(1, 'certificate has expired'))
        context = options['context']
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        return io.BytesIO(b'valid response')

    monkeypatch.setattr(songsterr.urllib.request, 'urlopen', open_url)
    assert songsterr._get_bytes('https://www.songsterr.com/test') == b'valid response'
    assert len(calls) == 2


def test_invalid_certificate_stays_blocked_with_actionable_error(monkeypatch):
    def fail(*args, **kwargs):
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, 'certificate has expired'))

    monkeypatch.setattr(songsterr.urllib.request, 'urlopen', fail)
    with pytest.raises(ValueError, match="Check your computer's date/time"):
        songsterr._get_bytes('https://www.songsterr.com/test')


def test_non_certificate_network_errors_are_not_retried(monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise urllib.error.URLError('connection refused')

    monkeypatch.setattr(songsterr.urllib.request, 'urlopen', fail)
    with pytest.raises(urllib.error.URLError, match='connection refused'):
        songsterr._get_bytes('https://www.songsterr.com/test')
    assert len(calls) == 1
