from __future__ import annotations

import sys
from multiprocessing import freeze_support


def _set_windows_app_user_model_id() -> None:
    """Keep a ``pythonw`` launch associated with the application's icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Rom1foucher.UmaLegacyLinker"
        )
    except (AttributeError, OSError):
        # The packaged app should still start if the optional Windows API is
        # unavailable (for example under a compatibility layer).
        return


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

    from ui_qt.app_icon import application_icon
    from ui_qt.components import install_no_wheel_filter
    from ui_qt.main_window import MainWindow
    from ui_qt.theme import application_stylesheet

    # Qt 6 already follows per-monitor Windows scaling. Keep fractional DPRs
    # explicitly instead of silently rounding 125/150/175% displays to a very
    # different integer scale; dense canvases provide their own user zoom.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _set_windows_app_user_model_id()
    application = QApplication(sys.argv)
    application.setApplicationName("Uma Legacy Linker")
    application.setOrganizationName("UmaLegacyLinker")
    app_icon = application_icon()
    if not app_icon.isNull():
        application.setWindowIcon(app_icon)
    application.setStyle("Fusion")
    application.setStyleSheet(application_stylesheet())
    install_no_wheel_filter(application)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
