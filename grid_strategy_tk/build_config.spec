# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/app.py'],  # 主程序入口
    pathex=[],
    binaries=[],
    datas=[
        ('data/cache', 'data/cache'),  # 包含缓存目录
        ('data/results', 'data/results'),  # 包含结果目录
        ('src/assets', 'src/assets'),  # 包含资源文件
        ('src/locales', 'src/locales'),  # 包含本地化文件
    ],
    hiddenimports=[
        'akshare',
        'pandas',
        'numpy',
        'optuna',
        'plotly',
        'matplotlib',
        'tkinter',
        'ttkbootstrap',
        'PIL',
        'pypinyin',
        'sklearn',
        'scipy',
        'json',
        'datetime',
        'calendar',
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GridStrategyTK',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 如果不需要控制台窗口，改为False
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='file_version_info.txt'
) 