# Third-party tools and services

## Veteran extractors

Uma Legacy Linker does not bundle, modify or redistribute an extractor.

### UmaExtractor

Project: [xancia/UmaExtractor](https://github.com/xancia/UmaExtractor)

The application can launch a separately installed `umaextractor.exe`, then
consume the resulting `data.json`.

### umadump

Project: [Werseter/umadump](https://github.com/Werseter/umadump)

umadump is a runtime memory reader and JSON exporter. It validates declared
IL2CPP wrapper layouts against game metadata and exposes additional runtime
data through extensible export fields. Uma Legacy Linker can launch it once
with `--rerun-mode once` from the selected output directory, then consume its
`trained_chara_data.json`.

The launcher selects the backend from the executable or script name. Neither
extractor is bundled with the application.

Software that reads a running game's memory is used at the user's discretion. Review each project's documentation and warnings before use.

## Icons

Project: [Lucide](https://lucide.dev/) ([lucide-icons/lucide](https://github.com/lucide-icons/lucide))

A small set of Lucide SVG icons is vendored under `ui_qt/icons/` and recoloured at
paint time for the desktop theme (`ui_qt/icon_catalog.py`), replacing bare Unicode
glyphs that depended on the host's font-fallback chain. Lucide icons are ISC
licensed, except for a subset inherited from the Feather project (MIT), which
includes two of the vendored files (`database.svg`, `search.svg`):

```
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

---

The following Lucide icons are derived from the Feather project:

[...full list at https://github.com/lucide-icons/lucide/blob/main/LICENSE...]

The MIT License (MIT) (for the icons listed above)

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

## uma.moe

Project: [uma.moe](https://uma.moe/)

Uma Legacy Linker can query the public API or rank an imported JSON response. No uma.moe code or dataset is bundled with the application. The service and its data may change independently from this project.

## Community inheritance reference

The inheritance-probability model is documented against
[Crazyfellow's Parenting/Gene guide](https://docs.google.com/document/d/1Q3IJKbtkplmuY-PAJMNjYiLtasv0eU0aIBEqp8_C3tg/edit?tab=t.0).
That guide attributes the lower observed grandparent proc rate to each carrier's smaller individual
compatibility calculation, not to an additional fixed grandparent multiplier. Uma Legacy Linker
therefore applies the documented type/star base rate multiplied by the carrier's individual
compatibility factor. See [`SCORING.md`](SCORING.md) for the exact application model and configured
rates.

The guide and its underlying community research are credited as references only; their text,
images and datasets are not bundled with this project.
