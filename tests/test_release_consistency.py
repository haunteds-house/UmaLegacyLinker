"""Keep the Qt-only release surfaces in sync."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from uma_legacy_linker.application import APP_VERSION, app_base_dir, resource_base_dir


ROOT = Path(__file__).resolve().parents[1]


class ReleaseConsistencyTests(unittest.TestCase):
    def test_application_services_are_qt_free_and_rooted_at_project(self) -> None:
        source = (ROOT / "uma_legacy_linker" / "application.py").read_text(
            encoding="utf-8"
        )
        cli_source = (ROOT / "cli.py").read_text(encoding="utf-8")

        self.assertNotIn("PySide6", source)
        self.assertNotIn("from ui_qt", source)
        self.assertNotIn("from ui_qt", cli_source)
        self.assertEqual(app_base_dir(), ROOT)
        self.assertEqual(resource_base_dir(), ROOT / "resources")
        self.assertFalse((ROOT / "ui_qt" / "core.py").exists())

    def test_repository_layout_groups_core_modules_and_bundled_resources(self) -> None:
        core_modules = {
            "application.py",
            "backend_process.py",
            "legacy_linker.py",
            "parent_optimizer.py",
            "scoring_config.py",
            "transfer_helper.py",
            "uma_moe.py",
        }
        resource_files = {
            "default_course_overrides.json",
            "default_manual_adjustments.json",
            "default_parent_scoring.json",
            "default_skill_priorities.json",
        }

        self.assertTrue((ROOT / "uma_legacy_linker" / "__init__.py").is_file())
        self.assertEqual(
            {path.name for path in ROOT.glob("*.py")},
            {"cli.py", "qt_app.py"},
        )
        for filename in core_modules:
            self.assertTrue((ROOT / "uma_legacy_linker" / filename).is_file())
            self.assertFalse((ROOT / filename).exists())
        for filename in resource_files:
            self.assertTrue((ROOT / "resources" / filename).is_file())
            self.assertFalse((ROOT / filename).exists())
        resource_icons = list((ROOT / "resources" / "icons").glob("*.svg"))
        self.assertGreaterEqual(len(resource_icons), 20)
        self.assertFalse(list((ROOT / "ui_qt" / "icons").glob("*.svg")))

    def test_frozen_resource_path_matches_pyinstaller_data_destinations(self) -> None:
        spec = (ROOT / "UmaLegacyLinkerQt.spec").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", temp_dir, create=True),
            ):
                self.assertEqual(resource_base_dir(), Path(temp_dir) / "resources")

        self.assertIn('resources_dir = project_root / "resources"', spec)
        self.assertIn(
            '(str(resources_dir / "default_parent_scoring.json"), "resources")',
            spec,
        )
        self.assertIn('(str(icon_file), "resources/icons")', spec)
        self.assertNotIn('project_root / "default_parent_scoring.json"', spec)
        self.assertNotIn('project_root / "ui_qt" / "icons"', spec)

    def test_release_version_is_current_across_public_surfaces(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        releasing = (ROOT / "docs" / "RELEASING.md").read_text(encoding="utf-8")
        release_headings = re.findall(r"^## (\d+\.\d+\.\d+)\b", changelog, re.MULTILINE)

        self.assertTrue(release_headings)
        self.assertEqual(release_headings[0], APP_VERSION)
        self.assertIn(f"git tag v{APP_VERSION}", releasing)
        self.assertIn(f"git push origin v{APP_VERSION}", releasing)
        self.assertNotRegex(readme, r"git (?:tag|push origin) v\d+\.\d+\.\d+")

    def test_readme_keeps_a_user_first_install_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "https://github.com/Rom1foucher/UmaLegacyLinker/releases/latest",
            readme,
        )
        self.assertIn("UmaLegacyLinkerQt-win64.zip", readme)
        self.assertIn("Extract the **whole ZIP**", readme)
        self.assertIn("py -m pip install -r requirements-qt.txt", readme)
        self.assertIn("py qt_app.py", readme)
        self.assertIn("[User guide](docs/USER_GUIDE.md)", readme)
        self.assertIn("`uma_legacy_linker/`", readme)
        self.assertIn("`resources/`", readme)
        self.assertNotIn("ui_qt/icons/", readme)

    def test_windows_metadata_matches_application_version(self) -> None:
        metadata = (ROOT / "windows_version_info_qt.txt").read_text(encoding="utf-8")
        version = tuple(int(part) for part in APP_VERSION.split(".")) + (0,)

        self.assertIn(f"filevers={version}", metadata)
        self.assertIn(f"prodvers={version}", metadata)
        self.assertIn(f"StringStruct('FileVersion', '{APP_VERSION}')", metadata)
        self.assertIn(f"StringStruct('ProductVersion', '{APP_VERSION}')", metadata)
        self.assertIn("flags=0x0", metadata)
        self.assertNotIn("preview", metadata.lower())

    def test_tagged_workflow_ref_matches_application_version(self) -> None:
        if os.environ.get("GITHUB_REF_TYPE") == "tag":
            self.assertEqual(
                os.environ.get("GITHUB_REF_NAME"),
                f"v{APP_VERSION}",
            )

    def test_release_workflow_runs_the_visual_layout_audit(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "release-windows.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            r".\build_windows_qt.ps1 -SkipInstall -RunLayoutAudit",
            workflow,
        )
        self.assertIn("actions/checkout@v7", workflow)
        self.assertIn("actions/setup-python@v7", workflow)
        self.assertIn("actions/upload-artifact@v7", workflow)

    def test_windows_build_restores_qt_audit_environment(self) -> None:
        script = (ROOT / "build_windows_qt.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("-m pytest -q tests --ignore=tests/test_qt_runtime.py", script)
        self.assertIn("tests/check_i18n.py", script)
        self.assertIn("from tests.test_qt_runtime import QtRuntimeSmokeTests", script)
        self.assertIn("$env:QT_QPA_PLATFORM = \"offscreen\"", script)
        self.assertIn("$env:QT_QPA_FONTDIR = $WindowsFontDir", script)
        self.assertIn("} finally {", script)
        self.assertIn("$env:QT_QPA_PLATFORM = $PreviousQtPlatform", script)
        self.assertIn("$env:QT_QPA_FONTDIR = $PreviousQtFontDir", script)

    def test_removed_tkinter_interface_is_not_packaged_or_advertised(self) -> None:
        spec = (ROOT / "UmaLegacyLinkerQt.spec").read_text(encoding="utf-8")
        package = (ROOT / "ui_qt" / "__init__.py").read_text(encoding="utf-8")
        home = (ROOT / "ui_qt" / "pages_home_data.py").read_text(encoding="utf-8")

        self.assertNotIn('"app"', spec)
        self.assertNotIn("QT_UI_VERSION", package)
        self.assertNotIn("Tkinter reste disponible", home)

    def test_run_bat_launches_without_a_lingering_console(self) -> None:
        script = (ROOT / "run.bat").read_text(encoding="utf-8")
        self.assertIn("where pyw", script)
        self.assertIn('start "" pyw qt_app.py', script)

    def test_qt_entrypoint_supports_spawned_frozen_workers(self) -> None:
        entrypoint = (ROOT / "qt_app.py").read_text(encoding="utf-8")

        self.assertIn("from multiprocessing import freeze_support", entrypoint)
        self.assertRegex(
            entrypoint,
            r'if __name__ == "__main__":\s+freeze_support\(\)\s+raise SystemExit\(main\(\)\)',
        )

    def test_release_docs_and_dependencies_are_qt_only(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        spec = (ROOT / "UmaLegacyLinkerQt.spec").read_text(encoding="utf-8")

        self.assertTrue((ROOT / "docs" / "QT_UI.md").is_file())
        self.assertFalse((ROOT / "docs" / "QT_UI_PREVIEW.md").exists())
        self.assertNotIn("QT_UI_PREVIEW.md", readme)
        self.assertNotIn("QT_UI_PREVIEW.md", spec)
        self.assertFalse((ROOT / "requirements-build.txt").exists())

    def test_tests_are_grouped_and_release_dependencies_cover_pytest(self) -> None:
        requirements = (ROOT / "requirements-build-qt.txt").read_text(encoding="utf-8")

        self.assertFalse(list(ROOT.glob("test_*.py")))
        self.assertFalse((ROOT / "check_i18n.py").exists())
        self.assertTrue((ROOT / "tests" / "__init__.py").is_file())
        self.assertTrue((ROOT / "tests" / "check_i18n.py").is_file())
        self.assertGreaterEqual(len(list((ROOT / "tests").glob("test_*.py"))), 20)
        self.assertRegex(requirements, r"(?m)^pytest(?:\[.*?\])?[<>=]")

    def test_local_markdown_links_resolve(self) -> None:
        markdown_files = [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]
        missing: list[str] = []
        for document in markdown_files:
            text = document.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                target = target.strip().split("#", 1)[0]
                if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                    continue
                resolved = (document.parent / target).resolve()
                if not resolved.exists():
                    missing.append(f"{document.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
