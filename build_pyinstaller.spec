# -*- mode: python ; coding: utf-8 -*-
# BluePhone v1.0 - PyInstaller spec file
# הרץ: pyinstaller build_pyinstaller.spec

import os
block_cipher = None

# Collect all app sub-packages
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = [
    'bleak',
    'bleak.backends.winrt',
    'bleak.backends.winrt.scanner',
    'bleak.backends.winrt.client',
    'sounddevice',
    'PyQt6.QtMultimedia',
    'PyQt6.QtMultimediaWidgets',
    'PyQt6.QtCore',
    'PyQt6.QtWidgets',
    'PyQt6.QtGui',
    'app',
    'app.bluetooth_manager',
    'app.main_window',
    'app.theme_manager',
    'app.tray_manager',
    'app.core',
    'app.core.call_log',
    'app.core.recording_manager',
    'app.core.voicemail_manager',
    'app.core.smart_home_engine',
    'app.core.babysitter_engine',
    'app.core.device_registry',
    'app.core.service_toggles',
    'app.pages',
    'app.pages.about_page',
    'app.pages.call_interface',
    'app.pages.call_page',
    'app.pages.contacts_page',
    'app.pages.devices_page',
    'app.pages.home_page',
    'app.pages.incoming_page',
    'app.pages.settings_page',
    'app.pages.settings_page_main',
    'app.pages.stub_page',
    'app.pages.voicemail',
    'app.pages.babysitter',
    'app.pages.messaging',
    'app.pages.smarthome',
    'app.widgets',
    'vosk',
    'vosk.vosk_cffi',
    'vosk.transcriber',
    'srt',
    'tqdm',
    'requests',
]

datas = [
    ('app/style_light.qss', 'app'),
    ('app/style_dark.qss',  'app'),
    ('app/resources',       'app/resources'),
]

# ── Vosk binary DLLs — required for voice recognition ──
import importlib.util
_vosk_dir = None
spec = importlib.util.find_spec('vosk')
if spec and spec.origin:
    _vosk_dir = os.path.dirname(spec.origin)

vosk_binaries = []
if _vosk_dir:
    for _f in os.listdir(_vosk_dir):
        if _f.lower().endswith('.dll'):
            vosk_binaries.append(
                (os.path.join(_vosk_dir, _f), 'vosk'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=vosk_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BluePhone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # ← no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon='app/resources/icon.ico',
)
