"""Compact character-avatar rendering shared by selectors.

GameTora trainee artwork is much taller than the tiny selector icon that uses
it.  A centred crop can therefore miss the face entirely.  This helper scales
the portrait until it fills the requested square, keeps the crop horizontally
centred and biases it toward the top of the source before applying a circular
clip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

from ui_qt.asset_catalog import trainee_image_url

if TYPE_CHECKING:
    from ui_qt.image_assets import ImageRepository


def circular_avatar(source: QPixmap, size: int) -> QPixmap:
    """Return ``source`` scaled and cropped to fill a ``size`` px circle."""

    if source.isNull() or size <= 0:
        return QPixmap()
    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - size) // 2)
    # Standing portraits put the face near the top.  Keeping the crop at the
    # top avoids the chin/body crop produced by vertically centring tall art.
    cropped = scaled.copy(x, 0, size, size)

    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result


class AsyncAvatarProvider(QObject):
    'Return cached circular avatars backed by an:class:`ImageRepository`.\n\n    Table models ask for decoration data repeatedly while painting and sorting.\n    Cropping the same standing art on every data() call would be wasteful, so\n    this small adapter caches the rendered avatar per source URL and emits one\n    coarse ``changed`` signal when an async image becomes available.\n    '

    changed = Signal()

    def __init__(
        self,
        repository: "ImageRepository",
        size: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._size = max(1, int(size))
        self._cache: dict[str, QPixmap] = {}
        self._watched_urls: set[str] = set()
        repository.image_ready.connect(self._on_image_ready)

    def avatar(self, card_id: object) -> QPixmap | None:
        url = trainee_image_url(card_id)
        if not url:
            return None
        cached = self._cache.get(url)
        if cached is not None and not cached.isNull():
            return cached
        self._watched_urls.add(url)
        source = self._repository.pixmap(url)
        if source is None or source.isNull():
            return None
        avatar = circular_avatar(source, self._size)
        if avatar.isNull():
            return None
        self._cache[url] = avatar
        return avatar

    def _on_image_ready(self, url: str, pixmap: object) -> None:
        if url not in self._watched_urls or not isinstance(pixmap, QPixmap):
            return
        avatar = circular_avatar(pixmap, self._size)
        if avatar.isNull():
            return
        self._cache[url] = avatar
        self.changed.emit()
