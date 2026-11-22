import hashlib
from io import BytesIO
import json
from types import SimpleNamespace as NS
import wave

import pytest

from feedback_converter import batch, cli, converter
from feedback_converter.converter import _notes_and_chords
from feedback_converter.detection_provenance import NOTE_KEYS,digest


def note(**changes):
    v={k:0 for k in NOTE_KEYS};v.update(time=1.1234568357467651,string=0,fret=3,sustain=.5,
        bend_time=.5,chordId=0xffffffff,chordNoteId=0xffffffff,slideTo=-1,slideUnpitchTo=-1,leftHand=-1,
        fingerPrintId=[65535,65535],mask=0x803040,bends=[NS(time=1.1234568357467651,step=0.),NS(time=1.6234568357467651,step=.5)])
    v.update(changes);return NS(**v)


def context():return dict(source=dict(decodedSha256='a'*64,arrangement='owned_lead.sng'),profile=dict(mode=1,tuning=[0]*6,capo=0))


def test_compiled_source_addition_preserves_original_floats_and_normalized_model_binding():
    n=note();notes,_=_notes_and_chords(NS(chordNotes=[]),NS(notes=[n],difficulty=3),[],native_context=context())
    p=notes[0]['detectionNative'];assert p['data']['note']['time']==n.time!=notes[0]['t']
    assert p['data']['note']['bends'][1]==dict(time=1.6234568357467651,step=.5)
    assert p['modelSha256']==digest(p['model'])and p['dataSha256']==digest(p['data'])
    assert p['source']['difficulty']==3 and p['source']['index']==0
    assert json.loads(json.dumps(p))==p
    legacy,_=_notes_and_chords(NS(chordNotes=[]),NS(notes=[n],difficulty=3),[])
    assert 'detectionNative'not in legacy[0]


def test_original_chord_parent_and_child_masks_survive_lossy_legacy_child_wire():
    n=note(chordId=0,chordNoteId=0,mask=0x83002042)
    child=NS(mask=[0x2000,0x2040,0,0,0,0],slideTo=[-1]*6,slideUnpitchTo=[-1]*6,vibrato=[0]*6,
        bends=[NS(count=0,bendValues=[])for _ in range(6)])
    song=NS(chordNotes=[child],chordTemplates=[NS(frets=[3,5,-1,-1,-1,-1])])
    _,chords=_notes_and_chords(song,NS(notes=[n,n],difficulty=2),[{}],native_context=context())
    assert len(chords)==2 and[ch['detectionNative']['source']['index']for ch in chords]==[0,1]
    p=chords[0]['detectionNative'];assert p['data']['note']['mask']==n.mask
    assert p['data']['children']['mask']==child.mask
    assert chords[0]['notes'][0]['pm'] is True # Existing parent OR remains display-only.
    _,legacy=_notes_and_chords(song,NS(notes=[n,n],difficulty=2),[{}]);assert len(legacy)==1


@pytest.fixture
def original_song():
    chord = note(chordId=0, chordNoteId=0, mask=0x83002042)
    child = NS(mask=[0x2000, 0x2040, 0, 0, 0, 0], slideTo=[-1] * 6,
               slideUnpitchTo=[-1] * 6, vibrato=[0] * 6,
               bends=[NS(count=0, bendValues=[]) for _ in range(6)])
    template = NS(mask=0, frets=[3, 5, -1, -1, -1, -1], fingers=[1, 3, -1, -1, -1, -1],
                  notes=[43, 50, -1, -1, -1, -1], name='Owned')
    level = NS(difficulty=0, notes=[note(), chord, chord], anchors=[], fingerprints=[[], []])
    return NS(metadata=NS(tuning=[0] * 6, capo=0, songLength=2), chordTemplates=[template],
              chordNotes=[child], levels=[level], beats=[], sections=[], phrases=[],
              phraseIterations=[], vocals=[], tones=[])


@pytest.fixture
def original_sng(original_song):
    data = {key: [] for key in (
        'beats', 'phrases', 'chordTemplates', 'chordNotes', 'vocals', 'phraseIterations',
        'phraseExtraInfos', 'newLinkedDiffs', 'actions', 'events', 'tones', 'dna', 'sections', 'levels',
    )}
    data['symbols'] = None
    data['chordTemplates'] = [vars(template) for template in original_song.chordTemplates]
    data['chordNotes'] = [{
        **vars(child),
        'bends': [dict(count=0, bendValues=[dict(time=0., step=0., UNK=0)] * 32) for _ in range(6)],
    } for child in original_song.chordNotes]
    notes = [{**vars(unit), 'bends': [{**vars(point), 'UNK': 0} for point in unit.bends]}
             for unit in original_song.levels[0].notes]
    data['levels'] = [dict(
        difficulty=0, anchors=[], anchor_extensions=[], fingerprints=[[], []], notes=notes,
        averageNotesPerIter=[], notesInIterCountNoIgnored=[], notesInIterCount=[],
    )]
    data['metadata'] = dict(
        maxScores=100., maxNotes=3., maxNotesNoIgnored=3., pointsPerNote=100 / 3,
        firstBeatLength=.5, startTime=0., capo=0, lastConversionDateTime='owned synthetic',
        part=1, songLength=2., tuning=[0] * 6, firstNoteTime=1.1234568357467651,
        firstNoteTime2=1.1234568357467651, maxDifficulty=0,
    )
    return converter.Song.build(data)


@pytest.mark.parametrize('preserve', [False, True])
def test_normal_conversion_keeps_legacy_chord_count_until_exact_scoring_is_requested(
        tmp_path, original_sng, preserve):
    source = tmp_path / 'owned.psarc'
    decoded_sng = original_sng
    audio = BytesIO()
    with wave.open(audio, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b'\0\0' * 16000)
    source.write_bytes(converter.PSARC().build({
        'songs/bin/generic/owned_lead.sng': decoded_sng,
        'audio/windows/123.wem': audio.getvalue(),
        'audio/windows/song_owned.bnk': (123).to_bytes(4, 'little'),
    }))
    output = tmp_path / ('exact.feedpak' if preserve else 'legacy.feedpak')
    result = converter.convert_psarc_songs(source, output, archive=False, include_tones=False,
        preserve_detection_source=preserve)[0]
    arrangement = json.loads((output / 'arrangements/lead.json').read_text())
    assert result.validation.ok
    assert len(arrangement['chords']) == (2 if preserve else 1)
    assert arrangement['stats']['events'] == (3 if preserve else 2)
    assert result.manifest['arrangements'][0]['event_count'] == arrangement['stats']['events']
    if preserve:
        events = arrangement['notes'] + arrangement['chords']
        assert sorted(event['detectionNative']['source']['index'] for event in events) == [0, 1, 2]
        for event in events:
            native = event['detectionNative']
            assert native['source']['decodedSha256'] == hashlib.sha256(decoded_sng).hexdigest()
            assert native['dataSha256'] == digest(native['data'])
            assert native['modelSha256'] == digest(native['model'])
        assert arrangement['templates'][0]['detectionNative']['kind'] == 'template'
        assert arrangement['chords'][0]['detectionNative']['data']['children']['mask'][1] == 0x2040
    else:
        assert all('detectionNative' not in event for key in ('notes', 'chords', 'templates') for event in arrangement[key])
        assert [chord['t'] for chord in arrangement['chords']] == [1.123457]


@pytest.mark.parametrize('inputs', [1, 2])
@pytest.mark.parametrize('preserve', [False, True])
def test_cli_threads_exact_source_option_through_single_and_batch_paths(tmp_path, monkeypatch, inputs, preserve):
    paths = [tmp_path / f'{index}.psarc' for index in range(inputs)]
    for path in paths:
        path.write_bytes(b'owned')
    calls = []
    if inputs == 1:
        monkeypatch.setattr(cli, 'convert_psarc_songs', lambda *args, **options: calls.append(options) or [])
    else:
        monkeypatch.setattr(cli, 'convert_many', lambda *args, **options: calls.append(options) or NS(items=[], ok=True))
    arguments = [str(path) for path in paths]
    if preserve:
        arguments.append('--preserve-detection-source')
    assert cli.main(arguments) == 0
    assert calls[0]['preserve_detection_source'] is preserve


def test_batch_threads_exact_source_option_to_each_archive(tmp_path, monkeypatch):
    source = tmp_path / 'owned.psarc'
    source.write_bytes(b'owned')
    calls = []
    monkeypatch.setattr(batch, 'plan_psarc_songs', lambda *args, **kwargs: NS(to_dict=lambda: {}))
    monkeypatch.setattr(batch, 'convert_psarc_songs', lambda *args, **kwargs: calls.append(kwargs) or [NS()])
    assert batch.convert_many([source], preserve_detection_source=True).ok
    assert calls[0]['preserve_detection_source'] is True
