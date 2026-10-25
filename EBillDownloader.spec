# -*- mode: python ; coding: utf-8 -*-
import os
import glob
import sys

compiled_binaries = []
for pyd_path in glob.glob('*.pyd'):
    compiled_binaries.append((pyd_path, '.'))

entry_script = 'launcher.py' if os.path.exists('launcher.py') else 'main.py'

a = Analysis(
    [entry_script],
    pathex=[],
    binaries=compiled_binaries,
    datas=[('assets', 'assets')],
    hiddenimports=[
        'openpyxl',
        'requests',
        'selenium',
        'selenium.webdriver',
        'selenium.webdriver.chrome',
        'selenium.webdriver.chrome.options',
        'selenium.webdriver.chrome.service',
        'selenium.webdriver.chrome.webdriver',
        'selenium.webdriver.common',
        'selenium.webdriver.common.by',
        'selenium.webdriver.common.keys',
        'selenium.webdriver.common.action_chains',
        'selenium.webdriver.common.desired_capabilities',
        'selenium.webdriver.common.print_page_options',
        'selenium.webdriver.support',
        'selenium.webdriver.support.ui',
        'selenium.webdriver.support.expected_conditions',
        'selenium.common',
        'selenium.common.exceptions',
        'webdriver_manager',
        'webdriver_manager.chrome',
        'webdriver_manager.core',
        'webdriver_manager.core.os_manager',
        'webdriver_manager.core.download_manager',
        'webdriver_manager.core.driver_cache_manager',
        'webdriver_manager.core.logger',
        'pypdf',
        'fitz',
        'main'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe_icon = 'assets/app.ico' if sys.platform == 'win32' else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EBillDownloader',
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
    icon=exe_icon,
)
