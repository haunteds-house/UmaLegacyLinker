from __future__ import annotations

from functools import partial
from pathlib import Path
from types import MethodType

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from uma_legacy_linker.account_store import AccountStore, default_account_db_path
from uma_legacy_linker.collection_inventory import (
    collection_file_count,
    resolve_collection_path,
)
from uma_legacy_linker.umadump_import import import_umadump_directory
from ui_qt.components import PathPicker, muted_label, section_label
from ui_qt.pages_home_data import DataPage as BaseDataPage


_PATCHED = False


def _account_db_path(self) -> Path:
    configured = self.context.store.get("account_db_path")
    return Path(configured).expanduser() if configured else default_account_db_path()


def _refresh_account_status(self) -> None:
    db_path = self._account_db_path()
    self.account_database_detail.setToolTip(str(db_path))
    if not db_path.is_file():
        self.account_database_detail.setText("Account database not created yet")
        return
    try:
        with AccountStore(db_path) as store:
            summary = store.summary()
    except Exception as exc:
        self.account_database_detail.setText(f"Account database error: {exc}")
        return
    self.account_database_detail.setText(
        f"{summary.trainee_cards} Umas · {summary.support_cards} supports · "
        f"{summary.active_veterans} veterans · {summary.team_stadium_captures} TT captures · "
        f"{summary.career_archives} careers"
    )


def _refresh_collection_status(self) -> None:
    trainee_path = (
        Path(self.trainee_picker.text()).expanduser()
        if self.trainee_picker.text()
        else None
    )
    support_path = (
        Path(self.support_picker.text()).expanduser()
        if self.support_picker.text()
        else None
    )
    trainee_count = collection_file_count(
        trainee_path,
        ("card_data_array", "cards", "data"),
    )
    support_count = collection_file_count(
        support_path,
        ("support_card_data_array", "supports", "data"),
    )
    self.trainee_status.setText(
        f"{trainee_count} owned trainee cards loaded"
        if trainee_count is not None
        else "Optional — not loaded"
    )
    self.support_status.setText(
        f"{support_count} support cards loaded"
        if support_count is not None
        else "Optional — not loaded"
    )
    self._refresh_account_status()


def _persist_detected_paths(self) -> None:
    updates = {}
    if self.trainee_picker.text():
        updates["trainee_cards_path"] = self.trainee_picker.text()
    if self.support_picker.text():
        updates["support_cards_path"] = self.support_picker.text()
    if self.umadump_picker.text():
        updates["umadump_root"] = self.umadump_picker.text()
    updates["account_db_path"] = str(self._account_db_path())
    if updates:
        self.context.store.update(updates)


def _sync_collection_sources(self) -> None:
    trainee = resolve_collection_path(
        self.context.store.get("trainee_cards_path"),
        self.context.veterans_json_path,
        "card_data",
    )
    support = resolve_collection_path(
        self.context.store.get("support_cards_path"),
        self.context.veterans_json_path,
        "support_card_data",
    )
    if trainee is not None and not self.trainee_picker.text():
        self.trainee_picker.set_text(str(trainee))
    if support is not None and not self.support_picker.text():
        self.support_picker.set_text(str(support))
    configured_root = self.context.store.get("umadump_root")
    if configured_root and Path(configured_root).expanduser().is_dir():
        if not self.umadump_picker.text():
            self.umadump_picker.set_text(configured_root)
    elif not self.umadump_picker.text() and self.context.veterans_json_path:
        veteran_path = Path(self.context.veterans_json_path).expanduser()
        if veteran_path.is_file():
            self.umadump_picker.set_text(str(veteran_path.parent))
    self._persist_detected_paths()
    self._refresh_collection_status()


def _trainee_changed(self, value: str) -> None:
    self.context.store.update({"trainee_cards_path": value.strip()})
    self._refresh_collection_status()
    self.context.configuration_changed.emit()


def _support_changed(self, value: str) -> None:
    self.context.store.update({"support_cards_path": value.strip()})
    self._refresh_collection_status()
    self.context.configuration_changed.emit()


def _umadump_changed(self, value: str) -> None:
    self.context.store.update({"umadump_root": value.strip()})
    self._refresh_collection_status()


def _start_account_import(self) -> None:
    root = Path(self.umadump_picker.text()).expanduser() if self.umadump_picker.text() else None
    if root is None or not root.is_dir():
        QMessageBox.warning(
            self,
            "Account data",
            "Select the folder where the official umadump writes card_data.json, race_replays and career_data.",
        )
        return
    db_path = self._account_db_path()
    self.context.store.update(
        {"umadump_root": str(root), "account_db_path": str(db_path)}
    )
    operation = partial(import_umadump_directory, root, db_path)
    self.task_requested.emit(operation, "Importing umadump account data…", self._account_import_done)


def _account_import_done(self, result: object) -> None:
    self._refresh_account_status()
    summary = getattr(result, "summary", None)
    if summary is None:
        return
    imported = int(getattr(result, "imported_files", 0))
    unchanged = int(getattr(result, "unchanged_files", 0))
    self.account_database_detail.setText(
        f"{summary.trainee_cards} Umas · {summary.support_cards} supports · "
        f"{summary.active_veterans} veterans · {summary.team_stadium_captures} TT captures · "
        f"{summary.career_archives} careers  —  {imported} changed, {unchanged} unchanged"
    )


def _add_inventory_panel(self) -> None:
    panel = QFrame()
    panel.setObjectName("subtlePanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 11, 14, 11)
    layout.setSpacing(7)

    self.inventory_title = section_label("Account and umadump data")
    self.inventory_detail = muted_label(
        "Collection files feed Parent Maker now; the persistent account database also stores races and career snapshots for the wider optimizer."
    )
    layout.addWidget(self.inventory_title)
    layout.addWidget(self.inventory_detail)

    trainee_detected = resolve_collection_path(
        self.context.store.get("trainee_cards_path"),
        self.context.veterans_json_path,
        "card_data",
    )
    support_detected = resolve_collection_path(
        self.context.store.get("support_cards_path"),
        self.context.veterans_json_path,
        "support_card_data",
    )

    self.trainee_label = QLabel("Owned Umas — card_data.json")
    self.trainee_picker = PathPicker(
        str(trainee_detected or ""),
        title="Select card_data.json",
        file_filter="JSON (*.json);;All files (*)",
    )
    self.support_label = QLabel("Support cards — support_card_data.json")
    self.support_picker = PathPicker(
        str(support_detected or ""),
        title="Select support_card_data.json",
        file_filter="JSON (*.json);;All files (*)",
    )
    self.trainee_status = muted_label("")
    self.support_status = muted_label("")

    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(5)
    grid.addWidget(self.trainee_label, 0, 0)
    grid.addWidget(self.support_label, 0, 1)
    grid.addWidget(self.trainee_picker, 1, 0)
    grid.addWidget(self.support_picker, 1, 1)
    grid.addWidget(self.trainee_status, 2, 0)
    grid.addWidget(self.support_status, 2, 1)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    layout.addLayout(grid)

    configured_root = self.context.store.get("umadump_root")
    if not configured_root and self.context.veterans_json_path:
        veteran_path = Path(self.context.veterans_json_path).expanduser()
        if veteran_path.is_file():
            configured_root = str(veteran_path.parent)
    self.umadump_label = QLabel("umadump output folder")
    self.umadump_picker = PathPicker(
        configured_root,
        mode="directory",
        title="Select the umadump output folder",
    )
    self.import_account_button = QPushButton("Import account data")
    self.account_database_detail = muted_label("")
    account_row = QHBoxLayout()
    account_row.addWidget(self.umadump_picker, 1)
    account_row.addWidget(self.import_account_button)
    layout.addWidget(self.umadump_label)
    layout.addLayout(account_row)
    layout.addWidget(self.account_database_detail)

    root = self.layout()
    insert_at = max(0, root.count() - 2)
    root.insertWidget(insert_at, panel)
    self.inventory_panel = panel

    # Attach small helper methods to this BaseDataPage instance. The patch is
    # intentionally additive: existing DataPage tests/contracts remain intact.
    self._account_db_path = MethodType(_account_db_path, self)
    self._refresh_account_status = MethodType(_refresh_account_status, self)
    self._refresh_collection_status = MethodType(_refresh_collection_status, self)
    self._persist_detected_paths = MethodType(_persist_detected_paths, self)
    self._sync_collection_sources = MethodType(_sync_collection_sources, self)
    self._trainee_changed = MethodType(_trainee_changed, self)
    self._support_changed = MethodType(_support_changed, self)
    self._umadump_changed = MethodType(_umadump_changed, self)
    self._start_account_import = MethodType(_start_account_import, self)
    self._account_import_done = MethodType(_account_import_done, self)

    self.trainee_picker.path_changed.connect(self._trainee_changed)
    self.support_picker.path_changed.connect(self._support_changed)
    self.umadump_picker.path_changed.connect(self._umadump_changed)
    self.import_account_button.clicked.connect(self._start_account_import)
    self.context.configuration_changed.connect(self._sync_collection_sources)

    self.trainee_label.setBuddy(self.trainee_picker.edit)
    self.support_label.setBuddy(self.support_picker.edit)
    self.umadump_label.setBuddy(self.umadump_picker.edit)
    self.trainee_picker.set_accessible_label(
        self.trainee_label.text(),
        "Owned trainee-card export used for target and native-skill planning.",
    )
    self.support_picker.set_accessible_label(
        self.support_label.text(),
        "Owned support-card export used for requested-skill hint planning.",
    )
    self.umadump_picker.set_accessible_label(
        self.umadump_label.text(),
        "Folder written by the official umadump daemon. The app only reads its files.",
    )
    self._persist_detected_paths()
    self._refresh_collection_status()


def install_collection_inventory_patch() -> None:
    """Add account-data controls to the existing DataPage without replacing it.

    MainWindow imports DataPage before ParentMakerPage. Patching the existing
    class object keeps that already-bound reference valid and avoids changing
    established navigation/runtime contracts.
    """
    global _PATCHED
    if _PATCHED:
        return
    original_init = BaseDataPage.__init__
    original_sync = BaseDataPage.sync_from_context
    original_set_busy = BaseDataPage.set_busy

    def patched_init(self, context, parent=None):
        original_init(self, context, parent)
        _add_inventory_panel(self)

    def patched_sync(self):
        original_sync(self)
        if hasattr(self, "trainee_picker"):
            self._sync_collection_sources()

    def patched_set_busy(self, busy: bool):
        original_set_busy(self, busy)
        if hasattr(self, "import_account_button"):
            self.import_account_button.setEnabled(not busy)

    BaseDataPage.__init__ = patched_init
    BaseDataPage.sync_from_context = patched_sync
    BaseDataPage.set_busy = patched_set_busy
    _PATCHED = True
