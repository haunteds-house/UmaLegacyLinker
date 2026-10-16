"""Keep combo-box trainee avatars in sync with the async image cache."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QComboBox

from ui_qt.asset_catalog import trainee_image_url
from ui_qt.avatar import circular_avatar
from ui_qt.image_assets import ImageRepository


ICON_SIZE = 32


class ComboAvatarLoader:
    'Apply trainee artwork to combo items by position as images become ready.\n\n    Call:meth:`apply` after each repopulation with the same ordered card-id\n    sequence as the combo items.  Cached images are installed immediately;\n    downloads already go through the shared:class:`ImageRepository`.\n    '

    def __init__(self, combo: QComboBox, repository: ImageRepository) -> None:
        self._combo = combo
        self._repository = repository
        self._pending: dict[str, list[int]] = {}
        repository.image_ready.connect(self._on_image_ready)

    def apply(self, card_ids: Sequence[object]) -> None:
        """Synchronise the combo icons with ``card_ids`` in item order."""

        self._pending.clear()
        for index, card_id in enumerate(card_ids):
            url = trainee_image_url(card_id)
            if not url:
                continue
            pixmap = self._repository.pixmap(url)
            if pixmap is not None:
                self._set_icon(index, pixmap)
            else:
                self._pending.setdefault(url, []).append(index)

    def _on_image_ready(self, url: str, pixmap: object) -> None:
        indexes = self._pending.pop(url, None)
        if not indexes or not isinstance(pixmap, QPixmap):
            return
        for index in indexes:
            self._set_icon(index, pixmap)

    def _set_icon(self, index: int, pixmap: QPixmap) -> None:
        if 0 <= index < self._combo.count():
            avatar = circular_avatar(pixmap, ICON_SIZE)
            if not avatar.isNull():
                self._combo.setItemIcon(index, QIcon(avatar))
