from __future__ import annotations

from tests.check_i18n import orphaned_translation_keys


def test_translation_registry_has_no_orphaned_entries() -> None:
    assert orphaned_translation_keys() == {"exact": [], "fragment": []}
