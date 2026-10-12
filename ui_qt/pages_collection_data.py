from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from uma_legacy_linker.collection_inventory import (
    collection_file_count,
    resolve_collection_path,
)
from ui_qt.components import PathPicker, muted_label, section_label
from ui_qt.pages_home_data import DataPage as BaseDataPage


class DataPage(BaseDataPage):
    """Local Data page with the extra collection sources Parent Maker consumes."""

    def __init__(self, context, parent=None):
        super().__init__(context, parent)

        panel = QFrame()
        panel.setObjectName("subtlePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(7)

        self.inventory_title = section_label("Owned Umas and support cards")
        self.inventory_detail = muted_label(
            "Parent Maker uses these exports to find native skill sources and owned support hint sources. "
            "If they sit beside trained_chara_data.json, they are detected automatically."
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

        root = self.layout()
        # BaseDataPage ends with help text + stretch. Put collection inventory
        # immediately before those lower-priority elements.
        insert_at = max(0, root.count() - 2)
        root.insertWidget(insert_at, panel)
        self.inventory_panel = panel

        self.trainee_picker.path_changed.connect(self._trainee_changed)
        self.support_picker.path_changed.connect(self._support_changed)
        self.context.configuration_changed.connect(self._sync_collection_sources)

        self.trainee_label.setBuddy(self.trainee_picker.edit)
        self.support_label.setBuddy(self.support_picker.edit)
        self.trainee_picker.set_accessible_label(
            self.trainee_label.text(),
            "Owned trainee-card export used for target and native-skill planning.",
        )
        self.support_picker.set_accessible_label(
            self.support_label.text(),
            "Owned support-card export used for requested-skill hint planning.",
        )
        self._persist_detected_paths()
        self._refresh_collection_status()

    def _persist_detected_paths(self) -> None:
        updates = {}
        if self.trainee_picker.text():
            updates["trainee_cards_path"] = self.trainee_picker.text()
        if self.support_picker.text():
            updates["support_cards_path"] = self.support_picker.text()
        if updates:
            self.context.store.update(updates)

    def _trainee_changed(self, value: str) -> None:
        self.context.store.update({"trainee_cards_path": value.strip()})
        self._refresh_collection_status()
        self.context.configuration_changed.emit()

    def _support_changed(self, value: str) -> None:
        self.context.store.update({"support_cards_path": value.strip()})
        self._refresh_collection_status()
        self.context.configuration_changed.emit()

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
        self._persist_detected_paths()
        self._refresh_collection_status()

    def _refresh_collection_status(self) -> None:
        trainee_path = Path(self.trainee_picker.text()).expanduser() if self.trainee_picker.text() else None
        support_path = Path(self.support_picker.text()).expanduser() if self.support_picker.text() else None
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

    def sync_from_context(self) -> None:
        super().sync_from_context()
        if hasattr(self, "trainee_picker"):
            self._sync_collection_sources()
