# -*- mode: python ; coding: utf-8 -*-
#
# Spec do NEXUS. Nao edite o nome do exe a mao: o build.ps1 depende de
# "NEXUS" tanto no EXE quanto no COLLECT.
#
# hiddenimports:
#   certifi  -> o auto-updater exige verificacao real de certificado TLS.
#               Sem certifi empacotado, o PyInstaller nao o inclui e a
#               atualizacao e BLOQUEADA por seguranca no Windows.

a = Analysis(
    ['nexus.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['certifi'],
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
    name='NEXUS',
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
    icon=['nexus.ico'],
    version='version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NEXUS',
)
