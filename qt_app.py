from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is required to run Uma Legacy Linker. "
            "Install it with: python -m pip install -r requirements-qt.txt",
            file=sys.stderr,
        )
        return 2

    from ui_qt.components import install_no_wheel_filter
    from ui_qt.main_window import MainWindow
    from ui_qt.theme import application_stylesheet

    # Qt 6 already follows per-monitor Windows scaling. Keep fractional DPRs
    # explicitly instead of silently rounding 125/150/175% displays to a very
    # different integer scale; dense canvases provide their own user zoom.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = QApplication(sys.argv)
    application.setApplicationName("Uma Legacy Linker")
    application.setOrganizationName("UmaLegacyLinker")
    application.setStyle("Fusion")
    application.setStyleSheet(application_stylesheet())
    install_no_wheel_filter(application)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
