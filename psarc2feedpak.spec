# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

SRC = Path("src") / "feedback_converter"
TOOLS = SRC / "tools"
DATA = SRC / "data"

TOOLS_DEST = "feedback_converter/tools"
DATA_DEST = "feedback_converter/data"

# Shared, platform-independent data: Wwise codebooks (used by ww2ogg) and the
# equipment/schema JSON bundled with the app.
datas = [
    (str(TOOLS / "packed_codebooks.bin"), TOOLS_DEST),
    (str(TOOLS / "packed_codebooks_aoTuV_603.bin"), TOOLS_DEST),
    (str(DATA / "equipment.json"), DATA_DEST),
    (str(DATA / "feedback_equipment.json"), DATA_DEST),
    (str(DATA / "feedpak_schemas"), f"{DATA_DEST}/feedpak_schemas"),
]

binaries = []

if sys.platform == "win32":
    # Windows-native converter tools (supplied at build time) plus the shared
    # libraries that vgmstream-cli.exe depends on.
    win_tools = [
        "ww2ogg.exe",
        "vgmstream-cli.exe",
        "oggenc.exe",
    ]
    win_libs = [
        "avcodec-vgmstream-59.dll",
        "avformat-vgmstream-59.dll",
        "avutil-vgmstream-57.dll",
        "swresample-vgmstream-4.dll",
        "libatrac9.dll",
        "libcelt-0061.dll",
        "libcelt-0110.dll",
        "libg719_decode.dll",
        "libmpg123-0.dll",
        "libspeex-1.dll",
        "libvorbis.dll",
    ]
    for name in win_tools + win_libs:
        binaries.append((str(TOOLS / name), TOOLS_DEST))
else:
    # Linux-native converter tools (built/fetched via tools/build-linux-tools.sh).
    linux_tools = TOOLS / "linux"
    for name in ("ww2ogg", "vgmstream-cli", "oggenc"):
        candidate = linux_tools / name
        if candidate.exists():
            binaries.append((str(candidate), f"{TOOLS_DEST}/linux"))


a = Analysis(
    [str(SRC / "cli.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=["PIL.DdsImagePlugin", "PIL.PngImagePlugin"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='psarc2feedpak',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='psarc2feedpak',
)
