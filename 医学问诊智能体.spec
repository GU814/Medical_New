# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('config.py', '.'), ('database.py', '.'), ('knowledge_base.py', '.'), ('consultation.py', '.'), ('llm_client.py', '.'), ('report_generator.py', '.'), ('init_knowledge.py', '.'), ('data', 'data')],
    hiddenimports=['uvicorn', 'chromadb', 'chromadb.telemetry.product.posthog', 'chromadb.telemetry.product.events'],
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
    a.binaries,
    a.datas,
    [],
    name='医学问诊智能体',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
