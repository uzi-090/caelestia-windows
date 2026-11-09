# -*- mode: python ; coding: utf-8 -*-
"""Portable one-folder build. Invoke through build.ps1 for path safeguards."""
from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import (
    collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata,
)

ROOT = Path(SPECPATH).resolve()
BUILD = Path(os.environ.get("CAELESTIA_BUILD_DIR", str(Path.home() / ".cache/caelestia-windows/build")))
BUILD.mkdir(parents=True, exist_ok=True)
HOOKS = BUILD / "hooks"
HOOKS.mkdir(exist_ok=True)
STARTUP_HOOK = BUILD / 'caelestia_startup_hook.py'
STARTUP_HOOK.write_text('''
import faulthandler, os, sys, threading, traceback
from pathlib import Path
try:
    state = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CaelestiaWindows'
    state.mkdir(parents=True, exist_ok=True)
    startup_log = (state / 'startup-errors.log').open('a', encoding='utf-8', buffering=1)
    faulthandler.enable(startup_log, all_threads=True)
    def startup_exception(kind, error, tb):
        traceback.print_exception(kind, error, tb, file=startup_log)
    sys.excepthook = startup_exception
    def startup_thread_exception(args):
        startup_exception(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = startup_thread_exception
except OSError:
    pass
''', encoding='utf-8')

# QtQml's stock hook collects every installed QML module, including unrelated
# WebEngine/3D plugins. Keep the complete plugin families used by this app.
# The actual Qt DLL dependencies are still resolved by PyInstaller normally.
(HOOKS / "hook-PySide6.QtQml.py").write_text('''
from pathlib import PurePosixPath
from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info
hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()
allowed = {'Controls', 'Effects', 'Layouts', 'NativeStyle', 'Shapes', 'Templates', 'Window'}
def needed(item):
    path = str(item[1]).replace('\\\\', '/')
    tail = path.split('/qml/', 1)[-1].split('/')
    if tail[0] == 'QtQml':
        return True
    if tail[0] != 'QtQuick':
        return False
    return len(tail) == 1 or tail[1] in allowed
binaries += [item for item in qml_binaries if needed(item)]
datas += [item for item in qml_datas if needed(item)]
''', encoding="utf-8")

# Generate the Windows icon from the original Caelestia SVG, without requiring
# an additional image conversion program or modifying the source assets.
ICON = BUILD / "CaelestiaWindows.ico"
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
QSvgRenderer(str(ROOT / "assets/logo.svg")).render(painter)
painter.end()
image.save(str(ICON), "ICO")

datas = [(str(ROOT / "qml"), "qml"), (str(ROOT / "assets"), "assets")]
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    datas.append((str(python_license), "licenses/Python"))
for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "requirements.txt"):
    datas.append((str(ROOT / name), "."))

packages = [
    "PySide6-Essentials", "PySide6-Addons", "shiboken6", "numpy", "psutil",
    "PyAudioWPatch", "Pillow", "materialyoucolor", "winrt-runtime",
    "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections",
    "winrt-Windows.Media", "winrt-Windows.Media.Control", "winrt-Windows.Storage.Streams",
]
for package in packages:
    datas += copy_metadata(package)
datas += collect_data_files("materialyoucolor")

hiddenimports = collect_submodules("winrt") + collect_submodules("materialyoucolor") + [
    "winrt.windows.foundation", "winrt.windows.foundation.collections",
    "winrt.windows.media", "winrt.windows.media.control", "winrt.windows.storage.streams",
    "PySide6.QtSvg", "PySide6.QtQuickControls2", "PySide6.QtQml", "PySide6.QtQuick",
]
binaries = collect_dynamic_libs("winrt")
# These must match CPython's _ssl extension, not an unrelated OpenSSL on PATH.
for name in ('libcrypto-3-x64.dll', 'libssl-3-x64.dll'):
    candidate = Path(sys.base_prefix) / 'DLLs' / name
    if candidate.is_file():
        binaries.append((str(candidate), '.'))

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(HOOKS)],
    hooksconfig={},
    runtime_hooks=[str(STARTUP_HOOK)],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "matplotlib", "scipy", "pandas"],
    noarchive=False,
)
# Qt's Windows wheel uses Windows' unversioned ICU API. A different program's
# ICU (for example Poppler's ucnv_open_78) can share the filename while exposing
# incompatible entry points. Let Qt use Windows11's system ICU.
a.binaries = [item for item in a.binaries
              if Path(item[0]).name.lower() not in {'icuuc.dll', 'icuin.dll', 'icudt78.dll'}]
for i, (name, path, kind) in enumerate(a.binaries):
    if Path(name).name.lower() in {'libcrypto-3-x64.dll', 'libssl-3-x64.dll'}:
        candidate = Path(sys.base_prefix) / 'DLLs' / Path(name).name
        if candidate.is_file():
            a.binaries[i] = (name, str(candidate), kind)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="CaelestiaWindows", icon=str(ICON),
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="app")
