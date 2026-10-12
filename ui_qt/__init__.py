"""PySide6 desktop interface for Uma Legacy Linker."""

from __future__ import annotations

# Parent Maker is currently authored directly in English while the rest of the
# Qt interface still uses French source strings plus EXACT_EN translations.
# Register these strings explicitly so the translation audit can distinguish
# intentional English-neutral copy from accidentally untranslated French text.
from uma_legacy_linker.i18n import EXACT_EN

EXACT_EN.update(
    {
        "Parent Maker": "Parent Maker",
        "Choose the Sparks you want on the next parent; rank local/uma.moe parent pairs, then choose the highest-affinity owned target for each pair.": "Choose the Sparks you want on the next parent; rank local/uma.moe parent pairs, then choose the highest-affinity owned target for each pair.",
        "Requested Spark": "Requested Spark",
        "Priority": "Priority",
        "Preferred ★": "Preferred ★",
        "Add": "Add",
        "Remove selected": "Remove selected",
        "Include uma.moe": "Include uma.moe",
        "Results": "Results",
        "Find parents": "Find parents",
        "Parent Maker search…": "Parent Maker search…",
        "Type": "Type",
        "Family": "Family",
        "Select a valid master.mdb and trained-character export on Data first.": "Select a valid master.mdb and trained-character export on Data first.",
        "Add at least one requested Spark first.": "Add at least one requested Spark first.",
    }
)
