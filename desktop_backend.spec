# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["desktop_backend/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("configs", "configs"),
        ("Profile_file", "Profile_file"),
        ("power_spectrum", "power_spectrum"),
        ("defect_injector", "defect_injector"),
        ("physics_modules", "physics_modules"),
        ("utils", "utils"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="vtcm-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
