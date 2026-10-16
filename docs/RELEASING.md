# Releasing

The Windows release is a PyInstaller `onedir` bundle distributed as
`UmaLegacyLinkerQt-win64.zip` plus its `.sha256` file. Extract the whole archive.
The portable test suite is not a substitute for the Windows runtime/layout/build
checks. The [architecture](ARCHITECTURE.md) and [scoring contract](SCORING.md)
define the corresponding implementation invariants.

## Dependencies and version

| File | Purpose |
| --- | --- |
| `requirements.txt` | Backend dependency: PyYAML |
| `requirements-qt.txt` | Includes backend requirements and PySide6 6.8.x |
| `requirements-build-qt.txt` | Includes Qt requirements, PyInstaller and pytest |
| `UmaLegacyLinkerQt.spec` | Entry point, bundled data, metadata and Windows executable recipe |

These are complementary layers, not duplicate installation lists. The workflow
uses Python 3.12; source support is Python 3.10+. Source/frozen resource paths
are defined in `uma_legacy_linker/paths.py`.

Before tagging, align `APP_VERSION` in `uma_legacy_linker/application.py`, the
four-part `filevers`/`prodvers` and three-part string versions in
`windows_version_info_qt.txt`, the newest numbered changelog section and the tag.
`tests/test_release_consistency.py` checks these repository contracts. Keep
unfinished work in `Unreleased`; do not describe an unperformed validation as passed.

## Quality gate

```powershell
py -m pip install -r requirements-build-qt.txt
py -m pytest -q tests --ignore=tests/test_qt_runtime.py
py tests/check_english.py
.\build_windows_qt.ps1 -SkipInstall -RunLayoutAudit
```

The PowerShell script runs the portable suite and English text audit, imports Qt, discovers
every `QtRuntimeSmokeTests` case and runs each in a fresh offscreen process. It
then runs the bilingual layout audit, invokes PyInstaller and produces the ZIP
and SHA-256. Qt platform/font environment values are restored afterward. Inspect
`artifacts/ui-audit` and check any failures before proceeding.

For solver changes, the portable suite includes canonical/sequential/spawn
comparisons and E2 tests. Reproduce representative real searches with the same
MDB, linked export, captured remote pool, resolved weights, budgets and requested
result counts. Compare default E2 finalists with `ULL_G1_RANKING=exact`; verify
that the E2 CSV is the final top while exact CSV covers all evaluated pairs.
Do not advertise historical speedups or universal top recall from fixture tests.

Inspect the built application on Windows: first launch, first Search navigation,
local linking, a representative search, retained-result loading/comparison,
Transfer Helper and cancellation. Include automatic/multiple solver workers and
check that closing/cancelling leaves no child process behind. Validate visual
layout at the Windows DPI settings intended for release. No real collection,
MDB or API credentials are distributed for these checks.

## Application icon

Application branding is supplied through these files:

| Path | Use |
| --- | --- |
| `resources/branding/app.ico` | Windows EXE icon and preferred Qt application/window icon |
| `resources/branding/app.png` | Qt fallback when the ICO is absent or unreadable |

The supplied ICO contains 16, 24, 32, 48, 64, 128 and 256 px RGBA images. The
16–48 px entries preserve the supplied PNG artwork without resampling; the
64–256 px entries are smooth reductions of the supplied 512 px original.
`app.png` preserves that original file, including transparency.

Keep replacement artwork at these exact paths. The `.spec` includes existing
branding files and passes an existing ICO to PyInstaller. Qt loads an available
icon before constructing the main window. With neither file present, startup
and packaging keep their default icon behavior; no empty image is generated.
A PNG alone does not replace the embedded Windows EXE icon.

After supplying artwork, rebuild and inspect the executable, title bar and
taskbar on Windows. Validate the actual multi-size ICO and transparency there.
Windows icon caches may retain an older executable icon after a rebuild.

## Package inspection and publication

Verify runtime resources and the [third-party inventory](THIRD_PARTY.md) against
the actual bundle. The project is licensed under `GPL-3.0-only`. The `.spec`
includes the full `LICENSE` text at the bundle's data root (`_internal/LICENSE`
with the current PyInstaller layout), alongside the existing third-party notices.
Check that it is present in the ZIP. Provide access from the release page to the
corresponding source for that exact build, including the build scripts; retain
source and notice access for the bundled dependencies as described in the inventory.
Do not add proprietary game data or downloaded artwork to the bundle.

A manual **Windows release** workflow run builds artifacts without publishing a
release. Use it to validate the intended release commit before tagging. The
workflow runs only on manual dispatch or `v*` tag pushes, not every main-branch push.

After validation, commit the intended changes and push the matching tag:

```powershell
git tag v1.13.0
git push origin v1.13.0
```

The tag-triggered workflow builds the same package and uploads ZIP/checksum to an
existing release with `--clobber`, or creates a release with generated notes if
none exists. Review its title, notes and prerelease state explicitly. Do not move
an already published tag to silently replace different source code.

Download and extract the published ZIP, then check:

```powershell
Get-FileHash .\UmaLegacyLinkerQt-win64.zip -Algorithm SHA256
Get-Content .\UmaLegacyLinkerQt-win64.zip.sha256
```

The hashes must match. The executable is unsigned: this checksum is not publisher
authentication or an Authenticode signature. Visual QA artifacts are uploaded even
if the build job fails; package artifacts and release publication require success.

## Documentation checks

Keep the README's setup steps, download names and feature descriptions aligned
with the source being released. The release listing includes prereleases; GitHub's
`releases/latest` link points to the latest stable release. Keep demo recordings
under `docs/media/` and check that they still illustrate the described behaviour.
They are documentation assets, not application runtime data. Verify local links
and media paths after edits; update the operational and technical docs when
behaviour changes.
