# PyInstaller specification for the Windows x64 desktop build.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller resolves relative paths against this spec's folder, so anchor everything to the project root.
ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

hiddenimports = []
for package in ("yfinance", "curl_cffi", "peewee", "bs4", "openpyxl", "reportlab"):
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        pass

datas = [(os.path.join(ROOT, "assets"), "assets")]
for package in ("reportlab", "openpyxl", "certifi"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

analysis = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook", "IPython"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DrNileshShahStocksFairScope",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(ROOT, "assets", "app_icon.ico"),
    version=os.path.join(ROOT, "packaging", "windows", "version_info.txt"),
    uac_admin=False,
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="DrNileshShahStocksFairScope",
)
