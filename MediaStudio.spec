# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

block_cipher = None

project_dir = Path.cwd()
bin_dir = project_dir / "bin"

# Collect static binaries if present in ./bin
datas = []
if bin_dir.is_dir():
    for bin_file in bin_dir.glob("*"):
        if bin_file.is_file():
            datas.append((str(bin_file), "bin"))

a = Analysis(
    ['main.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'app.common',
        'app.ffmpeg_manager',
        'app.video_tab',
        'audio_app.audio_tab',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='MediaStudio',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='MediaStudio',
    )
    app = BUNDLE(
        coll,
        name='MediaStudio.app',
        icon=None,
        bundle_identifier='com.mediastudio.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'CFBundleShortVersionString': '1.0.0',
            'LSMinimumSystemVersion': '11.0',
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='MediaStudio',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
