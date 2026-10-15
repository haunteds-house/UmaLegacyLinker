# Third-party software, services and assets

This document inventories external software, services, references and assets used by Uma Legacy
Linker. It distinguishes material shipped in the repository or Windows bundle from resources
which are only contacted, downloaded or selected by the user at runtime.

It is an engineering inventory, not legal advice. The exact contents of a binary release remain
authoritative: transitive dependencies and their notices must be checked against the built
archive before publication.

## Project licence status

Uma Legacy Linker's original source code, documentation and project-authored
assets are licensed under the GNU General Public License, version 3 only
(`GPL-3.0-only`); see [`LICENSE`](../LICENSE). Copyright (c) 2026 Romain Foucher.

Third-party licences below apply to the corresponding third-party material and
are not replaced by the project licence. Game artwork, recordings of that artwork
and maintainer-supplied branding do not establish new rights to underlying
third-party material.

## Distribution summary

| Component | Relationship to the project | Source checkout | Windows `onedir` bundle | Licence or terms |
| --- | --- | --- | --- | --- |
| Python | Runtime selected by the build | Not vendored | Python runtime and standard library | PSF License Version 2 and component-specific notices |
| PySide6 / Qt | Desktop runtime | Installed from `requirements-qt.txt` | Python bindings, Qt libraries and plugins used by the application | LGPLv3/GPLv3 or Qt commercial terms |
| shiboken6 | PySide6 runtime dependency | Installed transitively | Runtime library used by PySide6 | Qt for Python licensing terms |
| PyYAML | YAML parser for uma.moe OpenAPI discovery | Installed from `requirements.txt` | Bundled by PyInstaller | MIT |
| PyInstaller | Build tool | Installed only for builds | Bootloader and runtime support are embedded; the build package itself is not shipped | GPL-2.0-or-later with Bootloader Exception; runtime hooks under Apache-2.0 |
| Lucide icons | Vendored SVG UI chrome | Nine SVG files | The same nine SVG files | ISC, with four Feather-derived icons under MIT |
| Domain badges | Project-maintained SVGs | Twelve SVG files | The same twelve SVG files | Project-authored; GPL-3.0-only |
| GameTora images | Remote, on-demand artwork | No images vendored | No images pre-bundled; requested files may enter the user's cache | Game and image rights remain with their respective holders |
| Hakuraku images | Fallback character and support artwork | No images vendored | No images pre-bundled; requested files may enter the user's cache | Game and image rights remain with their respective holders |
| Support-event hint associations | Derived factual card-to-skill mappings | `resources/support_event_hints.json` | Same numeric mapping | Source and scope documented below; no source code or event prose copied |
| uma.moe | Remote API and optional imported data | No service code or dataset vendored | No service code or dataset pre-bundled | Service-controlled terms and availability |
| UmaExtractor / umadump | Separately installed extraction tools | Not vendored | Not bundled | Each project's own licence and warnings |
| UmaParser replay layout | Reference for the Python Team Trials replay decoder | MIT notice in `licenses/UmaParser-MIT.txt` | Same notice included | MIT |
| `master.mdb` and game files | User-selected local inputs | Not vendored | Not bundled | Game rights and terms apply |

`pytest` and the GitHub Actions used by the release workflow are development or CI tooling, not
runtime dependencies distributed as part of the application bundle.

The original collection backend and watcher in `uma_workbench/` were provided
under MIT; their [original notice](../licenses/UmaWorkbench-MIT.txt) is retained.
The combined application is distributed under this project's GPL-3.0-only licence.
The replay decoder uses the binary layout and
skill-event interpretation documented in [UmaParser](https://github.com/stratowagon/UmaParser),
especially `UmaParser.Core/DataModel/RaceScenario/Parsers.cs` and
`RaceScenarioData.cs`; its [MIT notice](../licenses/UmaParser-MIT.txt) is retained.
No extractor executable, game database, collection dump or saved website bundle
is distributed. `uma_workbench/sync.py` reads exports and can launch the
separate upstream umadump executable without modifying its extraction process.

## Bundled runtime software

### Python

The official Windows release workflow builds with Python 3.12. PyInstaller packages the Python
interpreter and the standard-library modules reached by the application; a destination machine
does not need a separate Python installation.

Python is distributed under the Python Software Foundation License Version 2, with additional
licences for some incorporated components. The release must carry the licence set belonging to
the exact Python build used to create it.

- Project and licence: <https://docs.python.org/3.12/license.html>
- Build declaration: [`.github/workflows/release-windows.yml`](../.github/workflows/release-windows.yml)

### PySide6, Qt and shiboken6

The desktop application requires `PySide6>=6.8,<6.9`. It directly uses Qt Core, GUI, Widgets,
SVG and Network APIs. PySide6 and shiboken6 are the official Qt for Python bindings and support
libraries.

The community distribution is offered under LGPLv3/GPLv3; commercial Qt packages are governed by
the applicable commercial agreement. Individual Qt modules and bundled third-party components
can carry additional terms, so the wheel and Qt runtime notices for the exact resolved 6.8.x
version are authoritative.

The Windows build deliberately uses a PyInstaller `onedir` layout. Qt DLLs and plugins remain
separate dynamically loaded files. [`UmaLegacyLinkerQt.spec`](../UmaLegacyLinkerQt.spec) also calls
`copy_metadata()` for `PySide6`, `PySide6_Essentials` and `shiboken6`, so their installed
distribution metadata is copied into the release when available.

- Qt for Python: <https://doc.qt.io/qtforpython-6.8/>
- Qt for Python licence inventory: <https://doc.qt.io/qtforpython-6.8/licenses.html>
- Qt licensing: <https://doc.qt.io/qt-6.8/licensing.html>
- Runtime declaration: [`requirements-qt.txt`](../requirements-qt.txt)
- Packaging details: [Architecture](ARCHITECTURE.md)

Before publishing a community-wheel build, verify the actual archive contains the applicable
LGPL/GPL texts, Qt and Qt for Python third-party notices, a way to obtain the corresponding source
for the shipped versions, and no module whose licence is incompatible with the intended release.

### PyYAML

[`uma_legacy_linker/uma_moe.py`](../uma_legacy_linker/uma_moe.py) uses PyYAML only when the discovered uma.moe OpenAPI document is
YAML rather than JSON. It is nevertheless an installed runtime dependency and is included in the
standalone Windows application.

- Project: <https://pyyaml.org/>
- Source and licence: <https://github.com/yaml/pyyaml/blob/main/LICENSE>
- Version range: `PyYAML>=6.0,<7` in [`requirements.txt`](../requirements.txt)

The required MIT notice is reproduced in the [licence notices](#licence-notices) section.

### PyInstaller runtime material

PyInstaller is a build dependency, not an application import. The generated executable does,
however, contain its bootloader and runtime support files. PyInstaller is GPL-2.0-or-later with a
Bootloader Exception that permits distribution of the bootloader as part of another program;
runtime hooks and additional runtime modules are licensed under Apache-2.0.

- Project: <https://pyinstaller.org/>
- Complete licensing terms: <https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>
- Version range: `PyInstaller>=6.10,<7` in
  [`requirements-build-qt.txt`](../requirements-build-qt.txt)

The release must preserve the `COPYING.txt` and any other notices belonging to the exact
PyInstaller version used for the build.

## Application branding

`resources/branding/app.png` and `app.ico` contain the application artwork
supplied by the maintainer. The ICO preserves the supplied small PNG variants
and includes reductions of the 512 px original. No upstream source or licence
was supplied with these images; this inventory does not assign one. They are
separate from the Lucide/Feather SVG assets below.

## Vendored SVG icons

All packaged SVGs live under [`resources/icons/`](../resources/icons/). Their two origins are intentionally
separate in [`ui_qt/icon_catalog.py`](../ui_qt/icon_catalog.py):

- `ICON_FILES` contains nine tintable navigation and chrome icons vendored from
  [Lucide](https://lucide.dev/);
- `FIXED_ICON_FILES` contains twelve project-maintained weather, season and running-style badges
  whose authored colours carry meaning.

The project-maintained badges are **not Lucide assets** and must not be covered by Lucide's
attribution. Conversely, every file registered in `ICON_FILES` is third-party material and must
retain the Lucide/Feather notices below.

### Lucide set

The vendored Lucide files are:

- `arrow-left-right.svg`
- `chevron-left.svg`
- `chevron-right.svg`
- `database.svg`
- `heart.svg`
- `house.svg`
- `search.svg`
- `settings.svg`
- `sliders-horizontal.svg`

Lucide is ISC licensed. According to Lucide's licence inventory, four files in this particular
set derive from Feather and additionally carry Feather's MIT notice:

- `chevron-left.svg`
- `chevron-right.svg`
- `database.svg`
- `search.svg`

Project and complete upstream licence: <https://github.com/lucide-icons/lucide/blob/main/LICENSE>

### Project-maintained badges

The fixed-palette files are `weather-*.svg`, `season-*.svg` and `style-*.svg`, four of each. They
were authored and are maintained within Uma Legacy Linker. Their colours and text labels are
tested as a project UI contract; they are not copies supplied by Lucide, GameTora or the game.

## Network services and on-demand assets

### GameTora artwork

The Qt interface can derive HTTPS URLs for trainee standing art, support-card art, skill icons and
race banners from `master.mdb` identifiers. The current interface displays trainee art,
support-card art, skill icons and race banners.

[`ui_qt/asset_catalog.py`](../ui_qt/asset_catalog.py) restricts image requests to these hosts:

- `gametora.com`
- `www.gametora.com`
- `media.gametora.com`

[`ui_qt/image_assets.py`](../ui_qt/image_assets.py) downloads only images requested by an opened
view, rejects files above 12 MiB and keeps a bounded 256 MiB per-user cache. Online image loading
can be disabled and the cache can be cleared from the interface. Previously cached images may
remain available offline until the user clears that cache.

Individual GameTora downloads and the artwork cache are not stored in the repository
or preloaded into the Windows archive. The maintainer-supplied
recordings in `docs/media/` show the interface, including character artwork; they
are documentation assets and are not included by the PyInstaller recipe. No
licence for the underlying game artwork is assigned by this project.

- Service: <https://gametora.com/umamusume>
- In-application attribution: GameTora as the delivery source; Umamusume game visuals copyright
  Cygames, Inc.

GameTora states that it is not affiliated with the developers of Umamusume and that game material
is copyrighted by Cygames, Inc. Neither access through GameTora nor local caching grants a licence
to redistribute those images.

### Hakuraku artwork and interface reference

If GameTora cannot supply a character or support image, the app requests the
matching WebP from [Hakuraku's public assets](https://github.com/ayaliz/hakuraku/tree/main/public/assets)
on `raw.githubusercontent.com`. Only the specific character/support asset paths
accepted by `asset_catalog.py` are allowed. The same cache, download limit and
offline controls apply. No artwork is pre-bundled.

Hakuraku's named portrait selectors and expandable race cards informed the Qt
collection interface. Its application code and race simulator are not integrated.
Availability of its assets does not assign rights to the underlying game artwork.

### Support-event hint associations

[`resources/support_event_hints.json`](../resources/support_event_hints.json)
records potential support-card-to-skill associations derived from
[Uma-Musume-Auto-Train's support-event data](https://github.com/Kisegami/Uma-Musume-Auto-Train/blob/main/assets/events/support_card.json),
blob `1819f757badde950424dd67d4aae63ebf5592112`. Only numerical card and skill IDs
are retained; no event prose or source code is copied or executed.

These are possible hint routes, including conditional event rewards. They do
not simulate event appearance, mutually exclusive choices, event-chain endings
or acquisition chances. The planner filters the mapping against the user's MDB
and presents event sources separately from regular support hint pools. Names,
aptitudes, prices, awakening costs and Concert costs come from that local MDB.

### uma.moe

Uma Legacy Linker can query the public API at `https://uma.moe/api`, discover its OpenAPI
description at runtime, or rank a JSON response previously imported by the user. The service can
change independently of this project.

No uma.moe application code, API implementation or dataset is bundled. API responses and
normalised candidates may be written to the user's chosen output directory as run evidence; those
runtime files must not be mistaken for project-owned data or added to a release archive.

- Service: <https://uma.moe/>
- API documentation: <https://uma.moe/api/docs>

### Community inheritance reference

The project has used
[Crazyfellow's Parenting/Gene guide](https://docs.google.com/document/d/1Q3IJKbtkplmuY-PAJMNjYiLtasv0eU0aIBEqp8_C3tg/edit?tab=t.0)
as a community reference for inheritance behaviour. Its text, images and underlying research data are
not bundled. [`SCORING.md`](SCORING.md) documents the project's own implemented model and must be
used for the exact formulas and configured values.

## External local tools and inputs

### Veteran extractors

Uma Legacy Linker can launch one of two separately installed tools and consume its JSON output.
Backend selection is derived from the selected executable or script name.

| Tool | Invocation used by the application | Consumed output | Distribution status |
| --- | --- | --- | --- |
| [UmaExtractor](https://github.com/xancia/UmaExtractor) | `--cli`, from the extractor directory | `data.json` | Neither tool nor output is bundled |
| [umadump](https://github.com/Werseter/umadump) | `--rerun-mode once --no-update-check`, from the selected output directory | `trained_chara_data.json` | Neither tool nor output is bundled |

Each extractor has its own requirements, licence, update behaviour and warnings. Software that
reads or intercepts game runtime data is used at the user's discretion. Uma Legacy Linker neither
modifies nor redistributes either extractor.

### Game database, exports and assets

The following are required or optional user-side inputs, never release payloads:

- the current game `master.mdb` selected or detected from a local installation;
- `global-metadata.dat` or other files used directly by an external extractor;
- `data.json` and `trained_chara_data.json` collection exports;
- imported uma.moe response files;
- GameTora images downloaded into the user's cache;
- game executables, libraries, audio, artwork and other game assets.

Generated rankings and diagnostics can contain identifiers, names and values derived from those
inputs. They are user-created runtime outputs, not datasets shipped by the project.

Umamusume: Pretty Derby, its names, trademarks and game assets belong to Cygames, Inc. and/or
their respective rights holders. Uma Legacy Linker is not affiliated with or endorsed by Cygames,
GameTora, uma.moe, UmaExtractor or umadump.

## Release notice controls

The current packaging specification includes the root `LICENSE`, this document,
all registered SVGs and installed
metadata for `PySide6`, `PySide6_Essentials` and `shiboken6`. It does **not** explicitly copy the
Python licence set, the PyYAML licence or PyInstaller's `COPYING.txt`. In addition,
`copy_metadata()` failures for the Qt packages are currently ignored by the specification.

Consequently, the presence of this file is not proof that a release archive contains every
required notice. Before each release:

1. Build from a clean environment and record the exact resolved Python and package versions.
2. Inspect the produced `dist/UmaLegacyLinkerQt` directory, not only the requirement ranges.
3. Verify the exact Python, Qt, Qt for Python, shiboken6, PyYAML and PyInstaller licence files and
   third-party notices are present and readable.
4. Verify Qt libraries and plugins remain separate replaceable files in the `onedir` archive.
5. Confirm the SVG inventory still matches `ICON_FILES` and `FIXED_ICON_FILES`; update this file
   whenever a vendored icon is added, replaced or reclassified.
6. Confirm the archive contains no `master.mdb`, extractor, veteran export, uma.moe response,
   cached GameTora image or other game asset.
7. Treat a missing notice, an unknown transitive binary or an unresolved licence as a release
   blocker.

The release test suite should eventually enforce the notice-file inventory instead of relying on
a manual archive inspection alone.

## Licence notices

The following notices cover the permissively licensed source material copied directly into the
repository or bundled as a Python dependency. They do not replace the complete Python, Qt or
PyInstaller licence sets required in the binary distribution.

### Lucide — ISC License

```text
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

### Feather-derived Lucide icons — MIT License

```text
The MIT License (MIT)

Copyright (c) 2013-present Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### PyYAML — MIT License

```text
Copyright (c) 2017-2021 Ingy döt Net
Copyright (c) 2006-2016 Kirill Simonov

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
