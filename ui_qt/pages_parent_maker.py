from __future__ import annotations

import json
from functools import partial
from html import escape
from pathlib import Path
from typing import Any

from PySide6.QtCore import QItemSelection, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from uma_legacy_linker.backend_process import ProcessTask
from uma_legacy_linker.parent_maker import (
    FACTOR_TYPE_LABELS,
    ParentMakerRequest,
    SparkTarget,
    load_parent_maker_factor_options,
    preferred_stars_applicable,
    run_parent_maker,
    spark_family_label,
)
from ui_qt.components import PageHeader, ThemedComboBox, muted_label
from ui_qt.context import AppContext
from ui_qt.models import Column, ResultTableModel, nested, number
from ui_qt.pages_collection_data import install_collection_inventory_patch
from ui_qt.table_typography import enable_tabular_numbers
from ui_qt.view_state import bind_splitter_state, bind_table_view_state


# MainWindow binds the existing DataPage class before importing this module.
# Mutating that class object here lets Local Data expose the two extra umadump
# collection files without changing the established page/navigation contract.
install_collection_inventory_patch()

RIGHT = Qt.AlignmentFlag.AlignRight


def _parent_label(parent: dict[str, Any] | None) -> str:
    if not parent:
        return "—"
    name = str(parent.get("uma_name") or parent.get("card_name") or "Unknown")
    score = parent.get("rank_score")
    origin = str(parent.get("origin") or "local")
    rating = f" [{score}]" if score not in (None, "") else ""
    source = " · uma.moe" if origin == "remote" else ""
    return f"{name}{rating}{source}"


def _target_label(row: dict[str, Any]) -> str:
    target = row.get("target") or {}
    return str(target.get("uma_name") or target.get("card_name") or "—")


def _coverage_label(row: dict[str, Any]) -> str:
    return f"{int(row.get('coverage_count') or 0)}/{int(row.get('coverage_total') or 0)}"


def _spark_rows_html(row: dict[str, Any]) -> str:
    rendered: list[str] = []
    for target in row.get("spark_targets") or []:
        name = escape(str(target.get("family") or target.get("name") or ""))
        factor_type = escape(
            FACTOR_TYPE_LABELS.get(
                str(target.get("factor_type") or ""),
                str(target.get("factor_type") or ""),
            )
        )
        copies = int(target.get("copy_count") or 0)
        direct = int(target.get("direct_copy_count") or 0)
        stars = int(target.get("total_stars") or 0)
        probability = target.get("probability")
        if probability is None:
            metric = f"score {float(target.get('score') or 0):.1f}"
        else:
            metric = f"inherit/hint {100.0 * float(probability):.1f}%"
        rendered.append(
            "<tr>"
            f"<td><b>{name}</b><br><small>{factor_type}</small></td>"
            f"<td>{metric}</td>"
            f"<td>{copies} ({direct} direct)</td>"
            f"<td>{stars}★</td>"
            f"<td>{float(target.get('priority') or 0):.0f}</td>"
            "</tr>"
        )
    return "".join(rendered)


def _support_label(row: dict[str, Any]) -> str:
    name = str(row.get("name") or f"Support {row.get('support_card_id') or ''}")
    level = int(row.get("level") or 0)
    maximum = int(row.get("max_level") or 0)
    lb = int(row.get("limit_break_count") or 0)
    return f"{name} — Lv{level}/{maximum}, LB{lb}"


def _collection_plan_html(row: dict[str, Any]) -> str:
    plan = row.get("collection_plan") or {}
    if not plan or not plan.get("collection_available"):
        return (
            "<h3>Collection synthesis</h3>"
            "<p><small>Add card_data.json and support_card_data.json under Local Data "
            "to include owned Uma and support skill sources.</small></p>"
        )

    source_rows: list[str] = []
    for source in plan.get("skill_sources") or []:
        inherit = 100.0 * float(source.get("inherit_probability") or 0.0)
        native = "yes" if source.get("target_native") else "—"
        supports = int(source.get("owned_support_count") or 0)
        source_rows.append(
            "<tr>"
            f"<td>{escape(str(source.get('name') or ''))}</td>"
            f"<td>{inherit:.1f}%</td><td>{native}</td><td>{supports}</td>"
            "</tr>"
        )

    route_rows: list[str] = []
    for index, seed in enumerate(plan.get("preparation_route") or [], start=1):
        skills = ", ".join(str(value) for value in seed.get("route_skill_families") or [])
        route_rows.append(
            f"<li><b>{index}. {escape(str(seed.get('uma_name') or seed.get('card_name') or 'Uma'))}</b> "
            f"— affinity {int(seed.get('affinity_to_target') or 0)} — "
            f"{escape(skills)}</li>"
        )

    deck_rows: list[str] = []
    for support in plan.get("deck_candidates") or []:
        skills = ", ".join(str(value) for value in support.get("requested_skill_families") or [])
        deck_rows.append(
            f"<li>{escape(_support_label(support))}<br><small>{escape(skills)}</small></li>"
        )

    return (
        "<h3>Collection synthesis</h3>"
        "<table cellspacing='0' cellpadding='4' width='100%'>"
        "<tr><th align='left'>Skill family</th><th align='left'>Inherited</th>"
        "<th align='left'>Target native</th><th align='left'>Owned hint cards</th></tr>"
        + "".join(source_rows)
        + "</table>"
        + (
            "<h4>Suggested preparation order</h4><ol>" + "".join(route_rows) + "</ol>"
            if route_rows
            else ""
        )
        + (
            "<h4>Owned support skill-access candidates</h4><ol>" + "".join(deck_rows) + "</ol>"
            if deck_rows
            else ""
        )
        + f"<p><small>{escape(str(plan.get('method_note') or ''))}</small></p>"
    )


def parent_maker_detail_html(row: dict[str, Any] | None) -> str:
    if not row:
        return (
            "<h3>Parent Maker</h3>"
            "<p>Select a result to inspect Spark coverage, owned skill sources, "
            "and the target chosen for the pair.</p>"
        )
    target = row.get("target") or {}
    affinity = row.get("affinity") or {}
    p1 = row.get("parent_1") or {}
    p2 = row.get("parent_2") or {}

    friend_lines: list[str] = []
    for label, parent in (("P1", p1), ("P2", p2)):
        if str(parent.get("origin") or "") != "remote":
            continue
        code = parent.get("friend_code")
        trainer = parent.get("trainer_name")
        details = " · ".join(str(value) for value in (trainer, code) if value)
        if details:
            friend_lines.append(f"<li><b>{label} remote:</b> {escape(details)}</li>")

    return (
        f"<h2>{escape(str(target.get('uma_name') or target.get('card_name') or 'Target'))}</h2>"
        f"<p><b>Parent Maker score:</b> {float(row.get('score') or 0):.2f}<br>"
        f"<b>Affinity:</b> {int(affinity.get('total') or 0)} "
        f"(base {int(affinity.get('base') or 0)} + G1 {int(affinity.get('g1_bonus') or 0)})<br>"
        f"<b>Coverage:</b> {_coverage_label(row)}</p>"
        f"<p><b>P1:</b> {escape(_parent_label(p1))}<br>"
        f"<b>P2:</b> {escape(_parent_label(p2))}</p>"
        + (f"<ul>{''.join(friend_lines)}</ul>" if friend_lines else "")
        + "<table cellspacing='0' cellpadding='5' width='100%'>"
        "<tr><th align='left'>Requested Spark</th><th align='left'>Estimate</th>"
        "<th align='left'>Copies</th><th align='left'>Stars</th><th align='left'>Priority</th></tr>"
        + _spark_rows_html(row)
        + "</table>"
        + _collection_plan_html(row)
        + "<p><small>White-skill percentages are the chance to inherit the corresponding "
        "skill hint across two Inspiration events, not the chance that the new career "
        "finishes with that Spark. For intermediate parents, Ignited Spirit: Wit/Wit+ "
        "and Racing Spirit: Stamina/Stamina+ are equivalent even when master.mdb labels "
        "them as White skills.</small></p>"
    )


class ParentMakerPage(QWidget):
    task_requested = Signal(object, str, object)

    def __init__(self, context: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._busy = False
        self._factor_options: list[Any] = []
        self._results: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        configuration = QFrame()
        configuration.setObjectName("panel")
        config_layout = QGridLayout(configuration)
        config_layout.setContentsMargins(14, 12, 14, 12)
        config_layout.setHorizontalSpacing(10)
        config_layout.setVerticalSpacing(8)

        self.spark_label = QLabel("")
        self.spark_combo = ThemedComboBox()
        self.priority_label = QLabel("")
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 100)
        self.priority_spin.setValue(100)
        self.stars_label = QLabel("")
        self.stars_spin = QSpinBox()
        self.stars_spin.setRange(1, 9)
        self.stars_spin.setValue(1)
        self.add_button = QPushButton("")
        self.add_button.setObjectName("primary")

        config_layout.addWidget(self.spark_label, 0, 0)
        config_layout.addWidget(self.spark_combo, 1, 0, 1, 3)
        config_layout.addWidget(self.priority_label, 0, 3)
        config_layout.addWidget(self.priority_spin, 1, 3)
        config_layout.addWidget(self.stars_label, 0, 4)
        config_layout.addWidget(self.stars_spin, 1, 4)
        config_layout.addWidget(self.add_button, 1, 5)
        config_layout.setColumnStretch(0, 1)
        config_layout.setColumnStretch(1, 1)
        config_layout.setColumnStretch(2, 1)

        self.target_table = QTableWidget(0, 5)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.target_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.target_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.target_table.verticalHeader().setVisible(False)
        self.target_table.setMaximumHeight(220)
        config_layout.addWidget(self.target_table, 2, 0, 1, 6)

        actions = QHBoxLayout()
        self.remove_button = QPushButton("")
        self.remote_check = QCheckBox("")
        self.remote_check.setChecked(
            self.context.store.get("parent_maker_allow_remote", "1")
            in {"1", "true", "True"}
        )
        self.remote_limit = QSpinBox()
        self.remote_limit.setRange(50, 2000)
        try:
            remote_limit = int(self.context.store.get("parent_maker_remote_limit", "300"))
        except ValueError:
            remote_limit = 300
        self.remote_limit.setValue(max(50, min(2000, remote_limit)))
        self.top_label = QLabel("")
        self.top_spin = QSpinBox()
        self.top_spin.setRange(5, 200)
        try:
            top_n = int(self.context.store.get("parent_maker_top_n", "30"))
        except ValueError:
            top_n = 30
        self.top_spin.setValue(max(5, min(200, top_n)))
        self.search_button = QPushButton("")
        self.search_button.setObjectName("primary")
        self.summary = muted_label("")

        actions.addWidget(self.remove_button)
        actions.addSpacing(12)
        actions.addWidget(self.remote_check)
        actions.addWidget(self.remote_limit)
        actions.addSpacing(12)
        actions.addWidget(self.top_label)
        actions.addWidget(self.top_spin)
        actions.addStretch(1)
        actions.addWidget(self.summary)
        actions.addWidget(self.search_button)
        config_layout.addLayout(actions, 3, 0, 1, 6)
        root.addWidget(configuration)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.results_table = QTableView()
        enable_tabular_numbers(self.results_table)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setShowGrid(False)
        self.model = ResultTableModel([], self._columns())
        self.results_table.setModel(self.model)
        self.results_table.setSortingEnabled(True)
        self.results_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.detail = QTextBrowser()
        self.detail.setMinimumWidth(520)
        self.detail.setHtml(parent_maker_detail_html(None))
        self.splitter.addWidget(self.results_table)
        self.splitter.addWidget(self.detail)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 4)
        bind_splitter_state(
            self.splitter,
            self.context.store,
            "ui_splitter_parent_maker",
            [720, 560],
        )
        self._save_table_state = bind_table_view_state(
            self.results_table,
            self.context.store,
            "ui_table_parent_maker",
        )
        root.addWidget(self.splitter, 1)

        self.add_button.clicked.connect(self.add_target)
        self.remove_button.clicked.connect(self.remove_target)
        self.search_button.clicked.connect(self.start_search)
        self.spark_combo.currentIndexChanged.connect(self._spark_selection_changed)
        self.results_table.selectionModel().selectionChanged.connect(
            self._selection_changed
        )
        self.context.configuration_changed.connect(self._configuration_changed)
        self.context.language_changed.connect(self._language_changed)

        self._load_saved_targets()
        self.refresh_factor_options(show_errors=False)
        self.retranslate()
        self._configure_header()
        self._spark_selection_changed()

    def _columns(self) -> list[Column]:
        t = self.context.t
        return [
            Column(t("Rang"), nested("rank"), RIGHT, number("rank")),
            Column(t("Score"), nested("score"), RIGHT, number("score")),
            Column(t("Couverture"), _coverage_label),
            Column(t("Cible"), _target_label),
            Column(t("Affinité"), nested("affinity", "total"), RIGHT, number("affinity", "total")),
            Column(t("Parent 1"), lambda row: _parent_label(row.get("parent_1"))),
            Column(t("Parent 2"), lambda row: _parent_label(row.get("parent_2"))),
        ]

    def _configure_header(self) -> None:
        header = self.results_table.horizontalHeader()
        header.setMinimumSectionSize(60)
        for index in range(self.model.columnCount()):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
        for index in (3, 5, 6):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)

    def _language_changed(self, _language: str) -> None:
        self.retranslate()

    def _configuration_changed(self, *_args: object) -> None:
        self.refresh_factor_options(show_errors=False)

    def retranslate(self) -> None:
        t = self.context.t
        self.header.set_text(
            t("Parent Maker"),
            t("Choose the Sparks you want on the next parent; rank local/uma.moe parent pairs, then choose the highest-affinity owned target for each pair."),
        )
        self.spark_label.setText(t("Requested Spark"))
        self.priority_label.setText(t("Priority"))
        self.stars_label.setText(t("Preferred ★"))
        self.add_button.setText(t("Add"))
        self.remove_button.setText(t("Remove selected"))
        self.remote_check.setText(t("Include uma.moe"))
        self.top_label.setText(t("Results"))
        self.search_button.setText(t("Find parents"))
        self.target_table.setHorizontalHeaderLabels(
            [t("Type"), t("Spark"), t("Priority"), t("Preferred ★"), t("Family")]
        )
        header = self.target_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.model.set_columns(self._columns())

    def refresh_factor_options(self, *, show_errors: bool) -> None:
        master = Path(self.context.master_path).expanduser()
        if not master.is_file():
            self._factor_options = []
            self.spark_combo.clear()
            return
        try:
            options = load_parent_maker_factor_options(master)
        except Exception as exc:
            self._factor_options = []
            self.spark_combo.clear()
            if show_errors:
                QMessageBox.warning(self, "Parent Maker", str(exc))
            return
        current = self.spark_combo.currentData()
        self._factor_options = options
        self.spark_combo.blockSignals(True)
        self.spark_combo.clear()
        for option in options:
            payload = {
                "factor_type": option.factor_type,
                "name": option.name,
                "max_stars": option.max_stars,
                "family": option.family,
                "uses_preferred_stars": option.uses_preferred_stars,
            }
            self.spark_combo.addItem(option.display_name, payload)
        if current:
            current_family = str(current.get("family") or current.get("name") or "").casefold() if isinstance(current, dict) else ""
            for index in range(self.spark_combo.count()):
                candidate = self.spark_combo.itemData(index)
                candidate_family = str(candidate.get("family") or candidate.get("name") or "").casefold() if isinstance(candidate, dict) else ""
                if candidate_family == current_family:
                    self.spark_combo.setCurrentIndex(index)
                    break
        self.spark_combo.blockSignals(False)
        self._spark_selection_changed()

    def _spark_selection_changed(self, *_args: object) -> None:
        payload = self.spark_combo.currentData()
        enabled = bool(isinstance(payload, dict) and payload.get("uses_preferred_stars"))
        self.stars_spin.setEnabled(enabled and not self._busy)
        if not enabled:
            self.stars_spin.setValue(1)
            self.stars_spin.setToolTip("Not used for White, Scenario, or Race Spark scoring.")
        else:
            self.stars_spin.setToolTip("Preferred inherited star total/tier for this factor type.")

    def _target_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for row in range(self.target_table.rowCount()):
            item = self.target_table.item(row, 1)
            payload = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(payload, dict):
                payloads.append(dict(payload))
        return payloads

    def _set_targets(self, targets: list[dict[str, Any]]) -> None:
        self.target_table.setRowCount(0)
        normalized: list[dict[str, Any]] = []
        for target in targets:
            factor_type = str(target.get("factor_type") or "")
            name = str(target.get("name") or "")
            if not factor_type or not name:
                continue
            family = spark_family_label(factor_type, name)
            # Migrate old saved Unity '+' rows to the collapsed family spelling.
            if family:
                factor_type = "white_skill"
                name = name.rstrip("+").rstrip()
            payload = {
                **target,
                "factor_type": factor_type,
                "name": name,
                "preferred_stars": (
                    int(target.get("preferred_stars") or 1)
                    if preferred_stars_applicable(factor_type)
                    else 1
                ),
            }
            normalized.append(payload)
            row = self.target_table.rowCount()
            self.target_table.insertRow(row)
            values = [
                FACTOR_TYPE_LABELS.get(factor_type, factor_type),
                name,
                str(int(payload.get("priority") or 100)),
                str(int(payload.get("preferred_stars") or 1))
                if preferred_stars_applicable(factor_type)
                else "—",
                family,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setData(Qt.ItemDataRole.UserRole, payload)
                self.target_table.setItem(row, column, item)
        self._save_targets()

    def _load_saved_targets(self) -> None:
        text = self.context.store.get("parent_maker_targets")
        if not text:
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if isinstance(payload, list):
            self._set_targets([row for row in payload if isinstance(row, dict)])

    def _save_targets(self) -> None:
        self.context.store.update(
            {
                "parent_maker_targets": json.dumps(
                    self._target_payloads(), ensure_ascii=False, separators=(",", ":")
                )
            }
        )

    def add_target(self) -> None:
        payload = self.spark_combo.currentData()
        if not isinstance(payload, dict):
            self.refresh_factor_options(show_errors=True)
            payload = self.spark_combo.currentData()
        if not isinstance(payload, dict):
            return
        factor_type = str(payload.get("factor_type") or "")
        name = str(payload.get("name") or "")
        family = str(payload.get("family") or "")
        targets = self._target_payloads()
        key = (factor_type, (family or name).casefold())
        targets = [
            row
            for row in targets
            if (
                str(row.get("factor_type") or ""),
                (spark_family_label(str(row.get("factor_type") or ""), str(row.get("name") or "")) or str(row.get("name") or "")).casefold(),
            )
            != key
        ]
        targets.append(
            {
                "factor_type": factor_type,
                "name": name,
                "priority": self.priority_spin.value(),
                "preferred_stars": (
                    self.stars_spin.value()
                    if preferred_stars_applicable(factor_type)
                    else 1
                ),
                "equivalents": [],
            }
        )
        self._set_targets(targets)

    def remove_target(self) -> None:
        selected = self.target_table.selectionModel().selectedRows()
        if not selected:
            return
        self.target_table.removeRow(selected[0].row())
        self._save_targets()

    def _request_targets(self) -> tuple[SparkTarget, ...]:
        return tuple(
            SparkTarget(
                factor_type=str(row.get("factor_type") or ""),
                name=str(row.get("name") or ""),
                priority=float(row.get("priority") or 0),
                preferred_stars=int(row.get("preferred_stars") or 1),
                equivalents=tuple(row.get("equivalents") or ()),
            )
            for row in self._target_payloads()
        )

    def start_search(self) -> None:
        master = Path(self.context.master_path).expanduser()
        veterans = Path(self.context.veterans_json_path).expanduser()
        if not master.is_file() or not veterans.is_file():
            QMessageBox.warning(
                self,
                self.context.t("Parent Maker"),
                self.context.t("Select a valid master.mdb and trained-character export on Data first."),
            )
            return
        targets = self._request_targets()
        if not targets:
            QMessageBox.information(
                self,
                self.context.t("Parent Maker"),
                self.context.t("Add at least one requested Spark first."),
            )
            return
        self.context.store.update(
            {
                "parent_maker_allow_remote": int(self.remote_check.isChecked()),
                "parent_maker_remote_limit": self.remote_limit.value(),
                "parent_maker_top_n": self.top_spin.value(),
            }
        )
        trainee_text = self.context.store.get("trainee_cards_path")
        support_text = self.context.store.get("support_cards_path")
        request = ParentMakerRequest(
            master_path=master,
            veterans_json_path=veterans,
            output_dir=Path(self.context.output_dir).expanduser(),
            targets=targets,
            card_data_path=Path(trainee_text).expanduser() if trainee_text else None,
            support_card_data_path=Path(support_text).expanduser() if support_text else None,
            allow_remote=self.remote_check.isChecked(),
            remote_limit=self.remote_limit.value(),
            top_n=self.top_spin.value(),
            api_base=self.context.uma_moe_api_base,
            token=self.context.uma_moe_api_key,
        )
        self.task_requested.emit(
            ProcessTask(partial(run_parent_maker, request)),
            self.context.t("Parent Maker search…"),
            self._search_done,
        )

    def _search_done(self, result: object) -> None:
        self._results = list(getattr(result, "top_results", ()) or ())
        self.model.set_rows(self._results)
        if self._results:
            self.results_table.selectRow(0)
        else:
            self.detail.setHtml(parent_maker_detail_html(None))
        local = int(getattr(result, "local_parent_count", 0) or 0)
        remote = int(getattr(result, "remote_parent_count", 0) or 0)
        pairs = int(getattr(result, "evaluated_pair_count", 0) or 0)
        collection = getattr(result, "collection_summary", None) or {}
        collection_text = ""
        if collection:
            collection_text = (
                f" · {int(collection.get('trainee_cards') or 0)} Umas"
                f" · {int(collection.get('support_cards') or 0)} supports"
            )
        self.summary.setText(
            f"{local} local · {remote} remote · {pairs} pairs{collection_text}"
        )

    def _selection_changed(
        self, _selected: QItemSelection, _deselected: QItemSelection
    ) -> None:
        indexes = self.results_table.selectionModel().selectedRows()
        row = self.model.row(indexes[0].row()) if indexes else None
        self.detail.setHtml(parent_maker_detail_html(row))

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        enabled = not self._busy
        for control in (
            self.spark_combo,
            self.priority_spin,
            self.add_button,
            self.remove_button,
            self.remote_check,
            self.remote_limit,
            self.top_spin,
            self.search_button,
        ):
            control.setEnabled(enabled)
        self._spark_selection_changed()
