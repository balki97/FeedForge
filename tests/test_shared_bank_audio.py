import struct
from pathlib import Path

import pytest
import soundfile as sf
import numpy as np

from feedback_converter import converter


@pytest.mark.parametrize("shared", [False, True])
def test_main_bank_audio_is_never_preview_only(shared):
    main = "audio/windows/111.wem"
    preview = "audio/windows/222.wem"
    content = {
        "songs/bin/generic/example_lead.sng": b"chart",
        "audio/windows/song_example.bnk": struct.pack("<I", 111),
        "audio/windows/song_example_preview.bnk": struct.pack("<I", 111 if shared else 222),
        main: b"full mix",
    }
    if not shared:
        content[preview] = b"preview"
    selected = converter._content_for_song_group(
        content, "example", {"songs/bin/generic/example_lead.sng"}
    )
    assert converter._content_has_full_mix_audio(selected)
    assert converter._preview_audio_candidates(selected) == ([] if shared else [(preview, b"preview")])
    converter._validate_song_audio_entries([("example", selected)], Path("example.psarc"), rs1_songs_psarc=None)


def test_preview_only_bank_still_rejected():
    content = {
        "audio/windows/song_example_preview.bnk": struct.pack("<I", 222),
        "audio/windows/222.wem": b"preview",
    }
    assert not converter._content_has_full_mix_audio(content)


def test_full_length_preview_encoding_in_subprocess(tmp_path):
    # Isolate native encoder crashes so pytest can report a useful failure.
    import subprocess
    import sys

    source = tmp_path / "full.wav"
    target = tmp_path / "preview.ogg"
    sf.write(source, np.zeros((48000 * 40, 2), dtype="float32"), 48000)
    result = subprocess.run([
        sys.executable, "-c",
        "from pathlib import Path; from feedback_converter.converter import _write_preview_from_full_mix; "
        "import sys; assert _write_preview_from_full_mix(Path(sys.argv[1]), Path(sys.argv[2]))",
        str(source), str(target),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    info = sf.info(target)
    assert info.duration == 30
    assert info.channels == 2
