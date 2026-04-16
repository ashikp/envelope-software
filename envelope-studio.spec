# -*- mode: python ; coding: utf-8 -*-
# Build on the target OS only (Windows or macOS).
#   pip install -e ".[dev]"
#   rm -rf build/envelope-studio dist/EnvelopeStudio
#   pyinstaller -y envelope-studio.spec
#
# Output: dist/EnvelopeStudio/ (folder with executable + Qt libs)

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas, binaries, hiddenimports = collect_all("PySide6")

# Ensure all app modules are bundled (PyInstaller usually resolves these from main.py).
_app_hidden = [
    "envelope_app.auth",
    "envelope_app.csv_import",
    "envelope_app.db",
    "envelope_app.json_import",
    "envelope_app.layout",
    "envelope_app.merge",
    "envelope_app.paths",
    "envelope_app.printing",
    "envelope_app.record_import",
    "envelope_app.version",
    "envelope_app.ui.designer_widget",
    "envelope_app.ui.login_dialog",
    "envelope_app.ui.main_window",
    "envelope_app.ui.theme",
]

a = Analysis(
    ["envelope_app/main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(hiddenimports) + _app_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EnvelopeStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    name="EnvelopeStudio",
)
