# PyInstaller spec for the server alone, which the Electron app carries and starts. Run through packaging/build.py.
# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is provided by PyInstaller

datas = [
    (str(ROOT / "tdtlocal" / "static"), "tdtlocal/static"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE"), "."),
]
python_licence = os.environ.get("TDT_PYTHON_LICENSE")
if python_licence:
    datas.append((python_licence, "licenses"))  # the destination is a folder

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "server.py")],
    pathex=[str(ROOT)],
    datas=datas,
    # The program needs none of these; leaving them out makes the result noticeably smaller.
    excludes=["tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3", "idlelib", "turtle", "curses"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tdt-local-server",
    # With a console so the app can read what it prints (the Registro); the app starts it hidden, so no window appears.
    console=True,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="tdt-local-server", upx=False)  # noqa: F821
