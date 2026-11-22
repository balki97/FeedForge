"""Verify legacy and exact-source conversion through the bundled executable."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave
from zipfile import ZipFile

from feedback_converter.psarc_format.psarc import PSARC

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_detection_provenance import original_sng, original_song


def main():
    root = Path(__file__).resolve().parents[1]
    binaries = [path for path in (root / 'release').rglob('psarc2feedpak*')
                if path.is_file() and path.name in {'psarc2feedpak', 'psarc2feedpak.exe'}
                and path.parent.name == 'psarc2feedpak' and path.parent.parent.name == 'bin']
    if not binaries:
        raise RuntimeError('Bundled converter was not found')
    sng = original_sng.__wrapped__(original_song.__wrapped__())
    audio = BytesIO()
    with wave.open(audio, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b'\0\0' * 16000)
    with tempfile.TemporaryDirectory(prefix='feedforge-source-smoke-') as temp:
        temp = Path(temp)
        source = temp / 'owned.psarc'
        source.write_bytes(PSARC().build({
            'songs/bin/generic/owned_lead.sng': sng,
            'audio/full.wav': audio.getvalue(),
        }))
        for preserve in (False, True):
            target = temp / ('exact.feedpak' if preserve else 'legacy.feedpak')
            command = [str(binaries[0]), str(source), '-o', str(target), '--no-tones']
            if preserve:
                command.append('--preserve-detection-source')
            subprocess.run(command, check=True)
            with ZipFile(target) as archive:
                assert archive.testzip() is None
                arrangement = json.loads(archive.read('arrangements/lead.json'))
            assert len(arrangement['chords']) == (2 if preserve else 1)
            events = arrangement['notes'] + arrangement['chords']
            assert len(events) == (3 if preserve else 2)
            if preserve:
                assert sorted(event['detectionNative']['source']['index'] for event in events) == [0, 1, 2]
                assert all(event['detectionNative']['source']['decodedSha256'] == sha256(sng).hexdigest()
                           for event in events)
            else:
                assert all('detectionNative' not in event for event in events)
        print('Bundled legacy-default and exact original-event conversion passed')


if __name__ == '__main__':
    main()
