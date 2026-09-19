import json
import zipfile
from pathlib import Path

import pytest
from feedback_converter import songsterr, songsterr_cli
from feedback_converter.feedpak import inspect_feedpak, update_feedpak
from feedback_converter.feedpak_validator import validate_feedpak
from feedback_converter.package_io import write_archive


def synthetic_song():
    guitar = {
        'title': 'Synthetic lead', 'instrument': 'Guitar', 'strings': 6,
        'tuning': [64, 59, 55, 50, 45, 40],
        'automations': {'tempo': [{'measure': 0, 'bpm': 120, 'type': 4}]},
        'measures': [{'signature': [4, 4], 'voices': [{'beats': [
            {'duration': [1, 4], 'notes': [{'string': 5, 'fret': 3, 'leftHandVibrato': True,
             'bend': {'points': [{'position': 0, 'tone': 0}, {'position': 60, 'tone': 100}]}}]},
            {'duration': [3, 4], 'notes': []}]}]}]}
    drums = {'title': 'Synthetic drums', 'instrument': 'Drums', 'measures': [
        {'signature': [4, 4], 'voices': [{'beats': [
            {'duration': [1, 4], 'notes': [{'fret': 38, 'ghost': True}]},
            {'duration': [3, 4], 'notes': []}]}]}]}
    return {'parts': [guitar, drums]}


def test_songsterr_package_roundtrips_through_shared_editor(tmp_path):
    tracks, timeline = songsterr.songsterr_to_tracks(synthetic_song())
    audio = tmp_path / 'audio.ogg'
    audio.write_bytes(b'OggS-synthetic-fixture')
    original = tmp_path / 'original.feedpak'
    songsterr.write_feedpak(tracks, timeline, audio, original, title='Synthetic', artist='FeedForge',
                           authors=[{'name': 'Tester', 'role': 'transcriber'}], offset=1.25)
    assert validate_feedpak(original).ok
    preview = inspect_feedpak(original)
    assert len(preview['arrangements']) == 2
    assert preview['authors'][0]['role'] == 'transcriber'
    assert preview['arrangements'][1]['notes'] == 1
    edited = tmp_path / 'edited.feedpak'
    update_feedpak(original, edited, metadata={'title': 'Edited'})
    assert validate_feedpak(edited).ok
    assert inspect_feedpak(edited)['title'] == 'Edited'
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(edited) as after:
        for name in before.namelist():
            if name != 'manifest.yaml':
                assert before.read(name) == after.read(name), name
        chart = json.loads(before.read('arrangements/lead.json'))
        assert chart['notes'][0]['t'] == 1.25
        assert chart['notes'][0]['bn'] == 2
        assert chart['notes'][0]['vb'] is True
        assert json.loads(before.read('drum_tab_drums.json'))['hits'][0]['g'] is True


@pytest.mark.parametrize('url', ['http://songsterr.com/a/wsa/x-s1', 'https://songsterr.com.evil.test/a/wsa/x-s1',
                               'file:///etc/passwd', 'https://user:pass@songsterr.com/a/wsa/x-s1',
                               'https://songsterr.com:5000/a/wsa/x-s1'])
def test_url_boundary_rejects_non_songsterr_sources(url):
    with pytest.raises(ValueError):
        songsterr_cli.validate_url(url)


def test_archive_failure_preserves_previous_output(tmp_path, monkeypatch):
    source = tmp_path / 'stage'
    source.mkdir()
    (source / 'manifest.yaml').write_text('test')
    target = tmp_path / 'song.feedpak'
    target.write_bytes(b'previous package')
    def fail(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(zipfile.ZipFile, 'write', fail)
    with pytest.raises(OSError):
        write_archive(source, target)
    assert target.read_bytes() == b'previous package'
    assert not list(tmp_path.glob('*.tmp'))


def test_invalid_generation_never_replaces_existing_package(tmp_path):
    tracks, timeline = songsterr.songsterr_to_tracks(synthetic_song())
    tracks[0]['notes'][0]['s'] = -20
    audio = tmp_path / 'audio.ogg'
    audio.write_bytes(b'OggS-fixture')
    target = tmp_path / 'song.feedpak'
    target.write_bytes(b'keep me')
    with pytest.raises(ValueError):
        songsterr.write_feedpak(tracks, timeline, audio, target, title='Test', artist='Test')
    assert target.read_bytes() == b'keep me'

def test_edit_failure_does_not_unlink_original(tmp_path, monkeypatch):
    tracks, timeline = songsterr.songsterr_to_tracks(synthetic_song())
    audio = tmp_path / 'audio.ogg'
    audio.write_bytes(b'OggS-fixture')
    original = tmp_path / 'original.feedpak'
    songsterr.write_feedpak(tracks, timeline, audio, original, title='Original', artist='Test')
    before = original.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(zipfile.ZipFile, 'write', fail)
    with pytest.raises(OSError):
        update_feedpak(original, metadata={'title':'Updated'}, overwrite=True)
    assert original.read_bytes() == before


def test_songsterr_creation_uses_shared_stem_editor_and_returns_warnings(tmp_path, monkeypatch):
    from types import SimpleNamespace
    inspection = {'meta': {'title': 'Test', 'artist': 'Test'}, 'video_url': ''}
    monkeypatch.setattr(songsterr_cli, 'inspect_songsterr', lambda *a, **kw: inspection)
    monkeypatch.setattr(songsterr_cli, 'load_songsterr_selection', lambda *a: synthetic_song())
    audio = tmp_path / 'audio.ogg'
    audio.write_bytes(b'OggS-fixture')
    monkeypatch.setattr(songsterr_cli, 'prepare_audio', lambda *a: audio)
    monkeypatch.setattr(songsterr_cli, 'prepare_cover', lambda *a: None)
    calls = []
    def split(output, **options):
        assert validate_feedpak(output).ok
        calls.append(options)
        return SimpleNamespace(warnings=[SimpleNamespace(message='Server unavailable; full mix only')])
    monkeypatch.setattr(songsterr_cli, 'update_feedpak', split)
    payload = dict(url='https://www.songsterr.com/a/wsa/test-s1', selected_parts=[0, 1],
                   audio_path=str(audio), output_path=str(tmp_path / 'test.feedpak'))
    assert not songsterr_cli.create(payload)['warnings']
    assert not calls
    payload.update(separateStems=True, demucsUrl='http://127.0.0.1:7865', demucsModel='htdemucs_6s', demucsStems=['guitar'])
    result = songsterr_cli.create(payload)
    assert result['warnings'] == ['Server unavailable; full mix only']
    assert calls[0]['separate_stems'] is True
    assert calls[0]['demucs_stems'] == ['guitar']
    assert calls[0]['demucs_model'] == 'htdemucs_6s'


@pytest.mark.parametrize('url', [
    'http://youtu.be/abcdefghijk', 'https://youtube.com.evil.test/watch?v=abcdefghijk',
    'https://user:pass@youtube.com/watch?v=abcdefghijk', 'https://youtu.be:444/abcdefghijk',
    'file:///audio.mp3', 'https://youtube.com/playlist?list=test', 'https://youtu.be/short',
])
def test_replacement_video_rejects_non_video_links(url):
    with pytest.raises(ValueError):
        songsterr_cli.audio_source({'video_url': url}, {})


@pytest.mark.parametrize('url', ['https://youtu.be/abcdefghijk?t=20',
                               'https://www.youtube.com/watch?v=abcdefghijk&list=ignored',
                               'https://www.youtube.com/shorts/abcdefghijk'])
def test_replacement_video_is_normalized_without_seek_or_playlist(url):
    assert songsterr_cli.audio_source({'video_url': url}, {'video_url': 'removed'}) == (
        'https://www.youtube.com/watch?v=abcdefghijk')


def test_replacement_preview_and_export_share_audio_and_timing(tmp_path, monkeypatch):
    inspection = {'meta': {'title': 'Test', 'artist': 'Test'}, 'video_url': 'removed'}
    monkeypatch.setattr(songsterr_cli, 'inspect_songsterr', lambda *a, **kw: inspection)
    monkeypatch.setattr(songsterr_cli, 'load_songsterr_selection',
                        lambda *a: {**synthetic_song(), 'video_points': [4, 6]})
    sources = []
    def audio(source, work):
        sources.append(source)
        result = work / 'full.ogg'
        result.write_bytes(b'OggS-fixture')
        return result
    monkeypatch.setattr(songsterr_cli, 'prepare_audio', audio)
    monkeypatch.setattr(songsterr_cli, 'prepare_cover', lambda *a: None)
    payload = dict(url='https://www.songsterr.com/a/wsa/test-s1', selected_parts=[0, 1],
                   video_url='https://youtu.be/abcdefghijk', timing_mode='score',
                   preview_dir=str(tmp_path), output_path=str(tmp_path / 'custom.feedpak'), offset=1.25)
    preview = songsterr_cli.dispatch({'action': 'preview', 'payload': payload})
    assert preview['measures'] == [{'measure': 1, 'time': 0}]
    assert sources == ['https://www.youtube.com/watch?v=abcdefghijk']
    payload['audio_path'] = preview['audio_path']
    songsterr_cli.create(payload)
    assert sources[-1] == preview['audio_path']
    with zipfile.ZipFile(payload['output_path']) as archive:
        assert json.loads(archive.read('arrangements/lead.json'))['notes'][0]['t'] == 1.25
        assert json.loads(archive.read('drum_tab_drums.json'))['hits'][0]['t'] == 1.25
    payload['timing_mode'] = 'songsterr'
    assert songsterr_cli.preview(payload)['measures'][0]['time'] == 4


def test_video_search_returns_candidates_without_claiming_accuracy(monkeypatch):
    import yt_dlp
    class Search:
        def __init__(self, options):
            assert options['extract_flat'] is True
            assert options['skip_download'] is True
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, query, download):
            assert query == 'ytsearch5:Band Song'
            assert download is False
            return {'entries': [
                {'id': 'abcdefghijk', 'title': 'Live', 'duration': 400},
                {'id': 'lmnopqrstuv', 'title': 'Album', 'duration': 203, 'channel': 'Band'},
                {'id': '12345678901', 'title': 'Unknown', 'duration': None},
                {'id': '../invalid', 'duration': 200}, None]}
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Search)
    results = songsterr_cli.dispatch({'action': 'search', 'payload': {
        'artist': 'Band', 'title': 'Song', 'duration': 200}})
    assert len(results) == 3
    assert results[0]['title'] == 'Album'
    assert results[0]['duration_difference'] == 3
    assert results[0]['url'] == 'https://www.youtube.com/watch?v=lmnopqrstuv'
    assert results[-1]['duration_difference'] is None
    assert all('accuracy' not in row for row in results)
    unknown = songsterr_cli.search_videos({'artist': 'Band', 'title': 'Song'})
    assert all(row['duration_difference'] is None for row in unknown)
