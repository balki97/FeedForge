"""Exercise GP5 export through the frozen converter on every release platform."""
from pathlib import Path
import subprocess
import sys
import tempfile

import guitarpro

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_gp5 import package


def main():
    root = Path(__file__).resolve().parents[1]
    binaries = [p for p in (root / "release").rglob("psarc2feedpak*")
                if p.is_file() and p.name in {"psarc2feedpak", "psarc2feedpak.exe"}
                and p.parent.name == "psarc2feedpak" and p.parent.parent.name == "bin"]
    if not binaries:
        raise RuntimeError("Bundled converter was not found")
    internal = binaries[0].parent / "_internal"
    assert (internal / "guitarpro" / "gp5.py").is_file()
    assert (internal / "licenses" / "PyGuitarPro-LGPL-3.0.txt").is_file()
    assert (internal / "licenses" / "GPL-3.0.txt").is_file()
    with tempfile.TemporaryDirectory(prefix="feedforge-gp5-smoke-") as temp:
        temp = Path(temp)
        source = package(temp)
        output = temp / "all.gp5"
        subprocess.run([str(binaries[0]), str(source), "--export-gp5", "-o", str(output)], check=True)
        song = guitarpro.parse(str(output))
        assert [t.name for t in song.tracks] == ["Lead", "Rhythm", "Bass", "Drums"]
        assert song.tracks[-1].isPercussionTrack
        assert song.tracks[0].offset == 2
        print("Bundled multi-track GP5 export passed")


if __name__ == "__main__":
    main()
