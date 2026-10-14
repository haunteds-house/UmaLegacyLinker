from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QSize, QThreadPool, Slot
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from uma_legacy_linker.backend_process import ProcessTask
from uma_legacy_linker.error_guidance import actionable_error
from ui_qt.accessibility import describe_control, label_control
from ui_qt.context import AppContext
from uma_legacy_linker.application import APP_NAME, APP_VERSION
from ui_qt.icon_catalog import stateful_icon
from ui_qt.theme import COLORS

NAV_ICON_SIZE = QSize(18, 18)
NAV_ICON_KEYS = {
    "home": "nav-home",
    "data": "nav-data",
    "workbench": "nav-data",
    "search": "nav-search",
    "transfer": "nav-transfer",
    "weights": "nav-weights",
    "tools": "nav-tools",
}
from ui_qt.pages_home_data import DataPage, HomePage
from ui_qt.pages_search import SearchPage
from ui_qt.pages_tools import ToolsPage
from ui_qt.pages_transfer import TransferPage
from ui_qt.pages_weights import WeightsPage
from ui_qt.pages_workbench import WorkbenchPage
from ui_qt.workers import FunctionWorker, ProcessFunctionWorker


TaskWorker = FunctionWorker | ProcessFunctionWorker


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext | None = None):
        super().__init__()
        self.context = context or AppContext()
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: list[TaskWorker] = []
        self._active_worker: TaskWorker | None = None
        self._busy = False
        self._status_source = 'Ready'
        self._nav_order = ["home", "workbench", "data", "search", "transfer", "weights", "tools"]
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_sections: dict[str, QLabel] = {}
        self._pages: dict[str, QWidget] = {}
        self._page_factories: dict[str, Callable[[AppContext], QWidget]] = {
            "home": HomePage,
            "data": DataPage,
            "workbench": WorkbenchPage,
            "search": SearchPage,
            "transfer": TransferPage,
            "weights": WeightsPage,
            "tools": ToolsPage,
        }
        self._shortcuts: list[QShortcut] = []

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1460, 940)
        self.setMinimumSize(1120, 720)

        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(252)
        self.sidebar = sidebar
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 15, 16, 13)
        sidebar_layout.setSpacing(4)

        brand = QLabel("Uma Legacy\nLinker")
        brand.setObjectName("brand")
        sidebar_layout.addWidget(brand)
        badges = QHBoxLayout()
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("versionBadge")
        badges.addWidget(version)
        badges.addStretch(1)
        sidebar_layout.addLayout(badges)
        sidebar_layout.addSpacing(9)

        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        nav_sections = (
            ("overview", ("home",)),
            ("prepare", ("workbench", "data")),
            ("analyse", ("search", "transfer")),
            ("configure", ("weights", "tools")),
        )
        for section_key, page_keys in nav_sections:
            label = QLabel("")
            label.setObjectName("navSection")
            self._nav_sections[section_key] = label
            sidebar_layout.addWidget(label)
            for key in page_keys:
                button = QPushButton()
                button.setObjectName("nav")
                button.setCheckable(True)
                button.setIcon(
                    stateful_icon(
                        NAV_ICON_KEYS[key],
                        off_color=COLORS["muted"],
                        on_color=COLORS["accent"],
                        size=NAV_ICON_SIZE.width(),
                    )
                )
                button.setIconSize(NAV_ICON_SIZE)
                button.clicked.connect(lambda _checked=False, target=key: self.show_page(target))
                nav_group.addButton(button)
                self._nav_buttons[key] = button
                sidebar_layout.addWidget(button)
            sidebar_layout.addSpacing(2)
        sidebar_layout.addStretch(1)

        outer.addWidget(sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)

        self.log_frame = QFrame()
        self.log_frame.setObjectName("panel")
        self.log_frame.setMaximumHeight(280)
        self.log_frame.setVisible(False)
        log_layout = QVBoxLayout(self.log_frame)
        log_layout.setContentsMargins(16, 9, 16, 12)
        log_head = QHBoxLayout()
        self.log_title = QLabel("")
        self.log_title.setObjectName("sectionTitle")
        self.clear_log_button = QPushButton("")
        self.clear_log_button.clicked.connect(lambda: self.log.clear())
        log_head.addWidget(self.log_title)
        log_head.addStretch(1)
        log_head.addWidget(self.clear_log_button)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        log_layout.addLayout(log_head)
        log_layout.addWidget(self.log)
        right_layout.addWidget(self.log_frame)

        status = QFrame()
        status.setObjectName("sidebar")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(14, 7, 14, 7)
        self.status_label = QLabel("")
        self.status_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(180)
        self.progress.setVisible(False)
        self.log_button = QPushButton("")
        self.log_button.setCheckable(True)
        self.log_button.toggled.connect(self.log_frame.setVisible)
        self.cancel_button = QPushButton("")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._request_cancel)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.progress)
        status_layout.addWidget(self.cancel_button)
        status_layout.addWidget(self.log_button)
        right_layout.addWidget(status)
        outer.addWidget(right, 1)

        self._ensure_page("home")
        self._install_shortcuts()
        self.retranslate()
        self.show_page("home")


    def _ensure_page(self, key: str) -> QWidget:
        existing = self._pages.get(key)
        if existing is not None:
            return existing
        page = self._page_factories[key](self.context)
        self._pages[key] = page
        self.stack.addWidget(page)
        navigate_signal = getattr(page, "navigate_requested", None)
        if navigate_signal is not None:
            navigate_signal.connect(self.show_page)
        task_signal = getattr(page, "task_requested", None)
        if task_signal is not None:
            task_signal.connect(self.start_task)
        setter = getattr(page, "set_busy", None)
        if callable(setter):
            setter(self._busy)
        return page

    def _install_shortcuts(self) -> None:
        for index, key in enumerate(self._nav_order, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda target=key: self.show_page(target))
            self._shortcuts.append(shortcut)
        for sequence in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(self._trigger_primary_action)
            self._shortcuts.append(shortcut)

    def _current_page_key(self) -> str | None:
        current = self.stack.currentWidget()
        return next(
            (key for key, page in self._pages.items() if page is current),
            None,
        )

    def _trigger_primary_action(self) -> None:
        if self._busy:
            return
        key = self._current_page_key()
        page = self._pages.get(key or "")
        if page is None:
            return
        actions = {
            "home": lambda: self.show_page("data"),
            "data": getattr(page, "start_extract", None),
            "search": getattr(page, "run_current_family", None),
            "transfer": getattr(page, "start_analysis", None),
            "weights": getattr(page, "save_profile", None),
            "tools": getattr(page, "save_integration", None),
        }
        action = actions.get(key or "")
        if callable(action):
            action()

    def retranslate(self) -> None:
        t = self.context.t
        self.cancel_button.setText(t('Cancel task'))
        labels = {
            "home": 'Home',
            "data": 'Local data',
            "workbench": "Workbench",
            "search": 'Lineage Search',
            "transfer": "Transfer Helper",
            "weights": 'Weights',
            "tools": 'Settings',
        }
        for key, source in labels.items():
            translated = t(source)
            self._nav_buttons[key].setText(translated)
            self._nav_buttons[key].setAccessibleName(translated)
        section_labels = {
            "overview": 'OVERVIEW',
            "prepare": 'PREPARE',
            "analyse": 'ANALYSE',
            "configure": 'CONFIGURE',
        }
        for key, source in section_labels.items():
            self._nav_sections[key].setText(t(source))
        self.log_title.setText(t('Activity log'))
        self.clear_log_button.setText(t('Clear'))
        self.log_button.setText(t('Log'))
        self.status_label.setText(t(self._status_source))
        describe_control(self.clear_log_button, t('Clear log'))
        describe_control(self.log, t('Activity log'))
        describe_control(self.log_button, t('Log'), t('Activity log'))
        describe_control(self.cancel_button, t('Cancel task'))
        describe_control(
            self.progress,
            t('Task progress'),
            t(self._status_source),
        )


    @Slot(str)
    def show_page(self, key: str) -> None:
        # Compatibility for home shortcuts and integrations saved by v1.7.x.
        if key in {"optimizer", "online"}:
            key = "search"
        if key not in self._nav_order:
            return
        page = self._ensure_page(key)
        self.stack.setCurrentWidget(page)
        self._nav_buttons[key].setChecked(True)

    def append_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {self.context.t(message)}")
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def set_status(self, source: str) -> None:
        self._status_source = source
        self.status_label.setText(self.context.t(source))
        self.progress.setAccessibleDescription(self.context.t(source))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for page in self._pages.values():
            setter = getattr(page, "set_busy", None)
            if callable(setter):
                setter(busy)
        self.progress.setVisible(busy)
        if not busy:
            self.progress.setValue(0)

    @Slot(object, str, object)
    def start_task(
        self,
        operation: Callable[..., Any] | ProcessTask,
        title: str,
        on_success: Callable[[object], None],
    ) -> None:
        if self._busy:
            QMessageBox.information(
                self,
                self.context.t('Operation in progress'),
                self.context.t('Wait for the current calculation to finish before starting another one.'),
            )
            return
        self._set_busy(True)
        self._status_source = title
        self.status_label.setText(title)
        self.progress.setValue(1)
        self.progress.setAccessibleDescription(title)
        self.append_log(title)

        worker: TaskWorker
        if isinstance(operation, ProcessTask):
            worker = ProcessFunctionWorker(operation)
        else:
            worker = FunctionWorker(operation)
        self._workers.append(worker)
        self._active_worker = worker
        self.cancel_button.setEnabled(True)
        worker.signals.progress.connect(self._task_progress)
        worker.signals.log.connect(self.append_log)
        worker.signals.result.connect(lambda result: self._task_result(on_success, result))
        worker.signals.error.connect(self._task_error)
        worker.signals.cancelled.connect(self._task_cancelled)
        worker.signals.finished.connect(lambda: self._task_finished(worker))
        self.thread_pool.start(worker)

    def _request_cancel(self) -> None:
        worker = self._active_worker
        if worker is None:
            return
        worker.request_cancel()
        self.cancel_button.setEnabled(False)
        self._status_source = 'Cancellation requested — stopping at the next step…'
        self.status_label.setText(self.context.t(self._status_source))
        self.append_log(self.context.t(self._status_source))

    @Slot()
    def _task_cancelled(self) -> None:
        self._status_source = 'Task cancelled.'
        self.append_log(self.context.t(self._status_source))

    @Slot(int, str)
    def _task_progress(self, value: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, value)))
        self._status_source = message
        self.status_label.setText(self.context.t(message))
        self.progress.setAccessibleDescription(self.context.t(message))

    def _task_result(self, callback: Callable[[object], None], result: object) -> None:
        try:
            callback(result)
        except Exception as exc:
            raw_message = f'Error d’affichage: {exc}'
            self.append_log(raw_message)
            QMessageBox.critical(
                self,
                self.context.t('Error'),
                actionable_error(raw_message, translate=self.context.t),
            )

    @Slot(str, str)
    def _task_error(self, message: str, trace: str) -> None:
        self.append_log(message)
        self.log.appendPlainText(trace)
        self.log_button.setChecked(True)
        QMessageBox.critical(
            self,
            self.context.t('The operation failed'),
            actionable_error(message, translate=self.context.t),
        )

    def _task_finished(self, worker: TaskWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        if worker is self._active_worker:
            self._active_worker = None
        self.cancel_button.setEnabled(False)
        self._set_busy(False)
        self.set_status('Ready')
        for page in self._pages.values():
            refresher = getattr(page, "refresh", None)
            if callable(refresher) and page is self._pages.get("home"):
                refresher()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._busy:
            self._shutdown_pages()
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            self.context.t('Running'),
            self.context.t('A calculation is still running. Close the application now?'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            worker = self._active_worker
            if worker is not None:
                worker.request_cancel(force=True)
            self._shutdown_pages()
            event.accept()
        else:
            event.ignore()

    def _shutdown_pages(self) -> None:
        for page in self._pages.values():
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
