from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata


project_root = Path.cwd()
resources_dir = project_root / "resources"
data_files = [
    (str(project_root / "LICENSE"), "."),
    (str(resources_dir / "default_course_overrides.json"), "resources"),
    (str(resources_dir / "default_manual_adjustments.json"), "resources"),
    (str(resources_dir / "default_parent_scoring.json"), "resources"),
    (str(resources_dir / "default_skill_priorities.json"), "resources"),
    (str(resources_dir / "support_event_hints.json"), "resources"),
    (str(project_root / "docs" / "THIRD_PARTY.md"), "docs"),
    (str(project_root / "docs" / "WORKBENCH.md"), "docs"),
    (str(project_root / "docs" / "TRAINING_MODEL.md"), "docs"),
    (str(project_root / "docs" / "ROADMAP.md"), "docs"),
    (str(project_root / "licenses" / "UmaParser-MIT.txt"), "licenses"),
    (str(project_root / "licenses" / "UmaWorkbench-MIT.txt"), "licenses"),
]
for icon_file in sorted((resources_dir / "icons").glob("*.svg")):
    data_files.append((str(icon_file), "resources/icons"))
branding_dir = resources_dir / "branding"
windows_icon = branding_dir / "app.ico"
for filename in ("app.ico", "app.png"):
    branding_file = branding_dir / filename
    if branding_file.is_file():
        data_files.append((str(branding_file), "resources/branding"))
for distribution in ("PySide6", "PySide6_Essentials", "shiboken6"):
    try:
        data_files += copy_metadata(distribution)
    except Exception:
        pass

a = Analysis(
    [str(project_root / "qt_app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=data_files,
    hiddenimports=["PySide6.QtNetwork"],
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
    name="UmaLegacyLinkerQt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_root / "windows_version_info_qt.txt"),
    icon=str(windows_icon) if windows_icon.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="UmaLegacyLinkerQt",
)
