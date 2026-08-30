"""Qt-only tests for compact Search-combo trainee avatars."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication, QComboBox

    from ui_qt.asset_catalog import trainee_image_url
    from ui_qt.avatar import circular_avatar
    from ui_qt.combo_avatars import ComboAvatarLoader
except ImportError:
    QApplication = None  # type: ignore[assignment]


@unittest.skipUnless(QApplication is not None, "PySide6 is not installed")
class ComboAvatarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert QApplication is not None
        cls.application = QApplication.instance() or QApplication([])

    def test_circular_avatar_uses_top_biased_crop(self) -> None:
        source = QPixmap(20, 40)
        source.fill(QColor("#ff0000"))
        # Paint the bottom half blue; a vertically centred 20px crop would
        # include it, while the intended top crop stays red around the centre.
        from PySide6.QtGui import QPainter

        painter = QPainter(source)
        painter.fillRect(0, 20, 20, 20, QColor("#0000ff"))
        painter.end()

        image = circular_avatar(source, 20).toImage()
        self.assertEqual(image.pixelColor(10, 10).name().lower(), "#ff0000")
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_cached_pixmap_is_applied_immediately(self) -> None:
        class Repository(QObject):
            image_ready = Signal(str, object)

            def __init__(self, pixmap: QPixmap) -> None:
                super().__init__()
                self._pixmap = pixmap

            def pixmap(self, _url: str) -> QPixmap:
                return self._pixmap

        combo = QComboBox()
        combo.addItem("T.M. Opera O", 101502)
        source = QPixmap(32, 64)
        source.fill(QColor("#4fae4a"))
        loader = ComboAvatarLoader(combo, Repository(source))
        loader.apply([101502])
        self.assertFalse(combo.itemIcon(0).isNull())
        self.assertGreaterEqual(combo.itemIcon(0).pixmap(32, 32).width(), 32)

    def test_pending_pixmap_is_applied_when_repository_signals(self) -> None:
        class Repository(QObject):
            image_ready = Signal(str, object)

            def pixmap(self, _url: str) -> None:
                return None

        combo = QComboBox()
        combo.addItem("T.M. Opera O", 101502)
        repository = Repository()
        loader = ComboAvatarLoader(combo, repository)
        loader.apply([101502])
        self.assertTrue(combo.itemIcon(0).isNull())

        source = QPixmap(32, 64)
        source.fill(QColor("#4a90d9"))
        url = trainee_image_url(101502)
        assert url is not None
        repository.image_ready.emit(url, source)
        self.assertFalse(combo.itemIcon(0).isNull())


if __name__ == "__main__":
    unittest.main()
