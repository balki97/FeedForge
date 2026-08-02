# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


root = Path.cwd()
tools = root / 'src' / 'feedback_converter' / 'tools'
windows_tools = [
    'ww2ogg.exe', 'vgmstream-cli.exe', 'oggenc.exe', 'topng.exe',
    *(item.name for item in tools.glob('*.dll')),
]
tool_names = windows_tools if os.name == 'nt' else ['vgmstream-cli']
native_tools = [name for name in tool_names if (tools / name).is_file()]


a = Analysis(
    [str(root / 'src' / 'feedback_converter' / 'cli.py')],
    pathex=[],
    binaries=[(str(tools / name), 'feedback_converter/tools') for name in native_tools],
    datas=[
        (str(tools / 'packed_codebooks.bin'), 'feedback_converter/tools'),
        (
            str(tools / 'packed_codebooks_aoTuV_603.bin'),
            'feedback_converter/tools',
        ),
        (str(root / 'src' / 'feedback_converter' / 'data' / 'equipment.json'), 'feedback_converter/data'),
        (str(root / 'src' / 'feedback_converter' / 'data' / 'feedback_equipment.json'), 'feedback_converter/data'),
        (str(root / 'src' / 'feedback_converter' / 'data' / 'feedpak_schemas'), 'feedback_converter/data/feedpak_schemas'),
    ],
    hiddenimports=[],
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
