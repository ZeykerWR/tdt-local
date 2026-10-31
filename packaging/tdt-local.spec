# PyInstaller spec for the desktop app. Run through packaging/build.py, which also checks the version and licences.
# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is provided by PyInstaller
ICONS = ROOT / "packaging" / "icons"
VERSION = os.environ["TDT_VERSION"]

datas = [
    (str(ROOT / "tdtlocal" / "static"), "tdtlocal/static"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE"), "."),
]
python_licence = os.environ.get("TDT_PYTHON_LICENSE")
if python_licence:
    datas.append((python_licence, "licenses"))  # the destination is a folder

if sys.platform == "win32":
    icon = str(ICONS / "icon.ico")
elif sys.platform == "darwin":
    icon = str(ICONS / "icon.icns")
else:
    icon = str(ICONS / "icon-256.png")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    # The program needs none of these; leaving them out makes the installer noticeably smaller.
    excludes=["tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3", "idlelib", "turtle", "curses"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tdt-local",
    console=False,  # no console window: it logs to a file and has a "Salir" button
    icon=icon,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="tdt-local", upx=False)  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="TDT local.app",
        icon=str(ICONS / "icon.icns"),
        bundle_identifier="io.github.cibernicola.tdt-local",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "TDT local",
            "CFBundleShortVersionString": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.video",
            "NSHumanReadableCopyright": "Copyright 2026 TDT local contributors. Apache License 2.0.",
        },
    )
