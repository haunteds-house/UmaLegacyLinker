"""Reusable side-by-side diagnostics for Search and Transfer Helper."""

from __future__ import annotations

from typing import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from uma_legacy_linker.result_comparison import (
    ComparisonDataset,
    ComparisonItem,
    ComparisonMetric,
    format_metric_delta,
    format_metric_value,
    matching_index,
)
from ui_qt.accessibility import describe_control, label_control
from ui_qt.components import ThemedComboBox, muted_label
from ui_qt.context import AppContext
from ui_qt.provenance import provenance_tooltip
from ui_qt.table_typography import enable_tabular_numbers


Renderer = Callable[[ComparisonItem, ComparisonDataset], str]

TRANSFER_STATUS_LABELS = {
    "safe_transfer": "Transfert strictement sûr",
    "recommended_transfer": "Transfert recommandé",
    "review": "À examiner",
    "keep": "Conserver",
    "protected": "Protégé",
}


class ResultComparisonDialog(QDialog):
    def __init__(
        self,
        context: AppContext,
        *,
        title: str,
        left: ComparisonDataset,
        right: ComparisonDataset,
        metrics: Sequence[ComparisonMetric],
        renderer: Renderer,
        left_key: str | None = None,
        right_key: str | None = None,
        match_identities: bool = False,
        lock_left: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.left_dataset = left
        self.right_dataset = right
        self.metrics = tuple(metrics)
        self.renderer = renderer
        self.match_identities = match_identities
        self._syncing = False
        self.setWindowTitle(context.t(title))
        self.resize(1480, 880)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        self.explanation = muted_label(
            context.t(
                "Les valeurs et diagnostics restent ceux des rapports enregistrés ; l’écart est calculé droite moins gauche."
            )
        )
        root.addWidget(self.explanation)

        selectors = QGridLayout()
        selectors.setHorizontalSpacing(14)
        selectors.setVerticalSpacing(5)
        self.left_title = QLabel(left.title)
        self.left_title.setObjectName("sectionTitle")
        self.right_title = QLabel(right.title)
        self.right_title.setObjectName("sectionTitle")
        self.left_combo = ThemedComboBox()
        self.right_combo = ThemedComboBox()
        for item in left.items:
            self.left_combo.addItem(item.label, item.key)
        for item in right.items:
            self.right_combo.addItem(item.label, item.key)
        self.left_combo.setEnabled(not lock_left and len(left.items) > 1)
        self.right_combo.setEnabled(len(right.items) > 1)
        self.left_meta = muted_label("", wrap=True)
        self.right_meta = muted_label("", wrap=True)
        selectors.addWidget(self.left_title, 0, 0)
        selectors.addWidget(self.right_title, 0, 1)
        selectors.addWidget(self.left_combo, 1, 0)
        selectors.addWidget(self.right_combo, 1, 1)
        selectors.addWidget(self.left_meta, 2, 0)
        selectors.addWidget(self.right_meta, 2, 1)
        selectors.setColumnStretch(0, 1)
        selectors.setColumnStretch(1, 1)
        root.addLayout(selectors)

        self.metric_table = QTableWidget(len(self.metrics), 4)
        enable_tabular_numbers(self.metric_table)
        self.metric_table.setHorizontalHeaderLabels(
            [
                context.t("Métrique"),
                left.title,
                right.title,
                context.t("Écart droite − gauche"),
            ]
        )
        self.metric_table.verticalHeader().setVisible(False)
        self.metric_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.metric_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.metric_table.setAlternatingRowColors(True)
        header = self.metric_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.metric_table.setMaximumHeight(330)
        root.addWidget(self.metric_table)

        self.details = QSplitter(Qt.Orientation.Horizontal)
        self.left_detail = QTextBrowser()
        self.right_detail = QTextBrowser()
        for browser in (self.left_detail, self.right_detail):
            browser.setOpenExternalLinks(True)
            browser.setMinimumWidth(520)
            self.details.addWidget(browser)
        self.details.setChildrenCollapsible(False)
        self.details.setStretchFactor(0, 1)
        self.details.setStretchFactor(1, 1)
        root.addWidget(self.details, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(
            context.t("Fermer")
        )
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        left_index = matching_index(left, left_key or "")
        self.left_combo.setCurrentIndex(max(0, left_index))
        if right_key:
            right_index = matching_index(right, right_key)
        elif match_identities and self.left_combo.currentData():
            right_index = matching_index(right, str(self.left_combo.currentData()))
        else:
            right_index = 1 if left is right and len(right.items) > 1 else 0
        self.right_combo.setCurrentIndex(max(0, right_index))
        self.left_combo.currentIndexChanged.connect(self._left_changed)
        self.right_combo.currentIndexChanged.connect(self._render)
        label_control(self.left_title, self.left_combo, self.explanation.text())
        label_control(self.right_title, self.right_combo, self.explanation.text())
        describe_control(
            self.metric_table,
            context.t("Comparaison chiffrée"),
            self.explanation.text(),
        )
        describe_control(
            self.left_detail,
            f"{context.t('Détail')} · {left.title}",
            self.explanation.text(),
        )
        describe_control(
            self.right_detail,
            f"{context.t('Détail')} · {right.title}",
            self.explanation.text(),
        )
        self._render()

    def _selected_item(
        self,
        combo: ThemedComboBox,
        dataset: ComparisonDataset,
    ) -> ComparisonItem | None:
        key = str(combo.currentData() or "")
        return dataset.item(key)

    def _left_changed(self, _index: int) -> None:
        if self.match_identities and not self._syncing:
            self._syncing = True
            try:
                key = str(self.left_combo.currentData() or "")
                index = matching_index(self.right_dataset, key, fallback=-1)
                if index >= 0:
                    self.right_combo.setCurrentIndex(index)
            finally:
                self._syncing = False
        self._render()

    def _display_value(self, value: object, metric: ComparisonMetric) -> str:
        if metric.label == "Verdict":
            value = self.context.t(TRANSFER_STATUS_LABELS.get(str(value), str(value)))
        return format_metric_value(value, metric)

    def _render(self, *_args: object) -> None:
        left_item = self._selected_item(self.left_combo, self.left_dataset)
        right_item = self._selected_item(self.right_combo, self.right_dataset)
        if left_item is None or right_item is None:
            return
        for row_index, metric in enumerate(self.metrics):
            left_value = metric.getter(left_item.row)
            right_value = metric.getter(right_item.row)
            values = (
                self.context.t(metric.label),
                self._display_value(left_value, metric),
                self._display_value(right_value, metric),
                format_metric_delta(left_value, right_value, metric),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.metric_table.setItem(row_index, column, item)
        self.left_detail.setHtml(self.renderer(left_item, self.left_dataset))
        self.right_detail.setHtml(self.renderer(right_item, self.right_dataset))
        self._render_metadata(self.left_meta, self.left_dataset)
        self._render_metadata(self.right_meta, self.right_dataset)

    def _render_metadata(self, label: QLabel, dataset: ComparisonDataset) -> None:
        provenance = dataset.provenance
        label.setText(provenance.revision.path.name if provenance else "")
        label.setToolTip(
            provenance_tooltip(provenance, self.context.t) if provenance else ""
        )
