# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\feedback_converter\\cli.py'],
    pathex=[],
    binaries=[
        ('src\\feedback_converter\\tools\\ww2ogg.exe', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\vgmstream-cli.exe', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\oggenc.exe', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\topng.exe', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\avcodec-vgmstream-59.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\avformat-vgmstream-59.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\avutil-vgmstream-57.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\swresample-vgmstream-4.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\libatrac9.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\libcelt-0061.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\libcelt-0110.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\libg719_decode.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\libmpg123-0.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\libspeex-1.dll', 'feedback_converter\\tools'),
        ('src\\feedback_converter\\tools\\libvorbis.dll', 'feedback_converter\\tools'),
    ],
    datas=[
        ('src\\feedback_converter\\tools\\packed_codebooks.bin', 'feedback_converter\\tools'),
        (
            'src\\feedback_converter\\tools\\packed_codebooks_aoTuV_603.bin',
            'feedback_converter\\tools',
        ),
        ('src\\feedback_converter\\data\\equipment.json', 'feedback_converter\\data'),
        ('src\\feedback_converter\\data\\feedback_equipment.json', 'feedback_converter\\data'),
        ('src\\feedback_converter\\data\\feedpak_schemas', 'feedback_converter\\data\\feedpak_schemas'),
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
