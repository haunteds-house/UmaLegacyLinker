from __future__ import annotations

import json
from datetime import datetime
from functools import partial
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
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from backend_process import ProcessTask
from error_guidance import actionable_error
from ui_qt.accessibility import describe_control, label_control
from ui_qt.components import PageHeader, StatusCard, ThemedComboBox, muted_label
from ui_qt.context import AppContext
from ui_qt.core import (
    TransferRequest,
    active_course_overrides_path,
    open_path,
    run_transfer_analysis,
)
from ui_qt.models import Column, ResultTableModel, nested, number
from ui_qt.presentation import transfer_detail_html
from ui_qt.table_typography import enable_tabular_numbers
from ui_qt.view_state import bind_splitter_state, bind_table_view_state
from veteran_identity import (
    canonical_veteran_label,
    canonical_veteran_labels,
    technical_veteran_tooltip,
)


RIGHT = Qt.AlignmentFlag.AlignRight

STATE_EMPTY = "empty"
STATE_RUNNING = "running"
STATE_READY = "ready"
STATE_STALE = "stale"
STATE_LOADED = "loaded"

STATE_LABELS = {
    STATE_EMPTY: "Aucun rapport affiché",
    STATE_RUNNING: "Analyse en cours",
    STATE_READY: "Rapport à jour",
    STATE_STALE: "Rapport périmé — les paramètres ont changé",
    STATE_LOADED: "Rapport chargé depuis le disque",
}


class TransferPage(QWidget):
    task_requested = Signal(object, str, object)

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context
        self._busy = False
        self._records: list[dict[str, Any]] = []
        self._result_state = STATE_EMPTY
        self._result_origin_state = STATE_EMPTY
        self._result_fingerprint = ""
        self._running_fingerprint = ""
        self._state_before_running = STATE_EMPTY
        self._generated_at = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        safety = QFrame()
        safety.setObjectName("panel")
        safety_layout = QGridLayout(safety)
        safety_layout.setContentsMargins(16, 12, 16, 12)
        self.safety_text = muted_label("")
        self.mode_label = QLabel("")
        self.mode_combo = ThemedComboBox()
        self.upcoming_cm_check = QCheckBox("")
        self.upcoming_cm_limit = QSpinBox()
        self.upcoming_cm_limit.setRange(1, 20)
        self.team_trials_check = QCheckBox("")
        self.generic_profiles_check = QCheckBox("")
        self.run_button = QPushButton("")
        self.run_button.setObjectName("primary")
        self.load_button = QPushButton("")
        self.open_button = QPushButton("")
        self.result_state = QLabel("")
        self.result_state.setObjectName("pill")
        self.generated_at = muted_label("", wrap=False)
        safety_layout.addWidget(self.safety_text, 0, 0, 1, 8)
        safety_layout.addWidget(self.mode_label, 1, 0)
        safety_layout.addWidget(self.mode_combo, 1, 1)
        safety_layout.addWidget(self.upcoming_cm_check, 1, 2)
        safety_layout.addWidget(self.upcoming_cm_limit, 1, 3)
        safety_layout.addWidget(self.team_trials_check, 2, 0, 1, 2)
        safety_layout.addWidget(self.generic_profiles_check, 2, 2, 1, 2)
        safety_layout.setColumnStretch(4, 1)
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.addWidget(self.result_state)
        action_layout.addWidget(self.generated_at)
        action_layout.addStretch(1)
        action_layout.addWidget(self.run_button)
        action_layout.addWidget(self.load_button)
        action_layout.addWidget(self.open_button)
        safety_layout.addLayout(action_layout, 3, 0, 1, 8)
        root.addWidget(safety)

        self.upcoming_cm_check.setChecked(
            self.context.store.get("transfer_include_upcoming_cm", "1") in {"1", "true", "True"}
        )
        try:
            cm_limit = int(self.context.store.get("transfer_upcoming_cm_limit", "5"))
        except ValueError:
            cm_limit = 5
        self.upcoming_cm_limit.setValue(max(1, min(20, cm_limit)))
        self.team_trials_check.setChecked(
            self.context.store.get("transfer_include_team_trials", "0") in {"1", "true", "True"}
        )
        self.generic_profiles_check.setChecked(
            self.context.store.get("transfer_include_generic_profiles", "0") in {"1", "true", "True"}
        )
        self.upcoming_cm_limit.setEnabled(self.upcoming_cm_check.isChecked())

        cards = QGridLayout()
        cards.setHorizontalSpacing(10)
        self.safe_card = StatusCard("", "0", "")
        self.recommended_card = StatusCard("", "0", "")
        self.review_card = StatusCard("", "0", "")
        self.keep_card = StatusCard("", "0", "")
        self.protected_card = StatusCard("", "0", "")
        for index, card in enumerate((
            self.safe_card,
            self.recommended_card,
            self.review_card,
            self.keep_card,
            self.protected_card,
        )):
            cards.addWidget(card, 0, index)
            cards.setColumnStretch(index, 1)
        root.addLayout(cards)

        filters = QFrame()
        filters.setObjectName("panel")
        filter_layout = QHBoxLayout(filters)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        self.filter_label = QLabel("")
        self.status_combo = ThemedComboBox()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.count_label = muted_label("")
        filter_layout.addWidget(self.filter_label)
        filter_layout.addWidget(self.status_combo)
        filter_layout.addWidget(self.search, 1)
        filter_layout.addWidget(self.count_label)
        root.addWidget(filters)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableView()
        enable_tabular_numbers(self.table)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.model = ResultTableModel([], self._columns())
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.detail = QTextBrowser()
        self.detail.setMinimumWidth(520)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.detail)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 4)
        self._configure_header()
        bind_splitter_state(
            self.splitter,
            self.context.store,
            "ui_splitter_transfer",
            [700, 560],
        )
        self._save_table_state = bind_table_view_state(
            self.table,
            self.context.store,
            "ui_table_transfer",
            default_hidden=(6, 9, 10),
        )
        root.addWidget(self.splitter, 1)

        self.run_button.clicked.connect(self.start_analysis)
        self.upcoming_cm_check.toggled.connect(self.upcoming_cm_limit.setEnabled)
        self.mode_combo.currentIndexChanged.connect(self._scope_changed)
        self.upcoming_cm_check.toggled.connect(self._scope_changed)
        self.upcoming_cm_limit.valueChanged.connect(self._scope_changed)
        self.team_trials_check.toggled.connect(self._scope_changed)
        self.generic_profiles_check.toggled.connect(self._scope_changed)
        self.load_button.clicked.connect(lambda: self.load_latest(show_errors=True))
        self.open_button.clicked.connect(self.open_output)
        self.status_combo.currentIndexChanged.connect(self._status_filter_changed)
        self.search.textChanged.connect(self.apply_filters)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.context.language_changed.connect(self._language_changed)
        self.context.configuration_changed.connect(self._refresh_freshness)
        self.context.lineage_changed.connect(self._refresh_freshness)
        self.retranslate()
        self.load_latest(show_errors=False)

    def _language_changed(self, _language: str) -> None:
        self.retranslate()

    def _columns(self) -> list[Column]:
        t = self.context.t
        parent_percentile = number("best_parent_percentile", default=100.0)
        grandparent_percentile = number(
            "best_grandparent_percentile", default=100.0
        )
        labels = {
            "safe_transfer": t("Transfert strictement sûr"),
            "recommended_transfer": t("Transfert recommandé"),
            "review": t("À examiner"),
            "keep": t("Conserver"),
            "protected": t("Protégé"),
        }

        def coverage_label(row: dict[str, Any]) -> str:
            replacement = row.get("dominated_by") or {}
            if replacement:
                return canonical_veteran_label(replacement)
            coverage = list(row.get("covered_by_portfolio") or [])
            return ", ".join(
                canonical_veteran_labels(
                    coverage,
                    rank_label=t("Rang").casefold(),
                    blue_label=t("Bleues").casefold(),
                )
            ) or "—"

        def coverage_tooltip(row: dict[str, Any]) -> str:
            replacement = row.get("dominated_by") or {}
            if replacement:
                return technical_veteran_tooltip(replacement)
            return ", ".join(
                tooltip
                for tooltip in (
                    technical_veteran_tooltip(item)
                    for item in row.get("covered_by_portfolio") or []
                )
                if tooltip
            )

        return [
            Column(t("Verdict"), lambda row: labels.get(str(row.get("status")), row.get("status") or "—")),
            Column(
                t("Vétéran"),
                canonical_veteran_label,
                sort_getter=nested("rank_score"),
                tooltip_getter=technical_veteran_tooltip,
            ),
            Column(t("Copies"), nested("same_card_copy_count"), RIGHT),
            Column(t("Meilleur parent"), nested("best_parent_score"), RIGHT),
            Column(
                t("Rang parent"),
                lambda row: f"top {parent_percentile(row):.1f}%",
                RIGHT,
                sort_getter=parent_percentile,
            ),
            Column(t("Meilleur GP"), nested("best_grandparent_score"), RIGHT),
            Column(
                t("Rang GP"),
                lambda row: f"top {grandparent_percentile(row):.1f}%",
                RIGHT,
                sort_getter=grandparent_percentile,
            ),
            Column(
                t("Couverture / remplaçant"),
                coverage_label,
                tooltip_getter=coverage_tooltip,
            ),
            Column(t("Avance moy."), lambda row: (row.get("dominated_by") or {}).get("mean_score_lead", "—"), RIGHT),
            Column(t("Référencé par"), nested("referenced_by_local_veterans"), RIGHT),
            Column(t("ID technique"), nested("trained_chara_id"), RIGHT),
        ]

    def _configure_header(self) -> None:
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(62)
        for index in range(self.model.columnCount()):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
        self.table.resizeColumnsToContents()
        for index in (1, 7):
            if index < self.model.columnCount():
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)

    def retranslate(self) -> None:
        t = self.context.t
        self.header.set_text(
            t("Transfer Helper"),
            t("Identifie les copies redondantes sans jamais modifier l’export source ni prendre une décision à ta place."),
        )
        self.safety_text.setText(
            t("Le socle permanent protège les usages futurs. L’audit exhaustif peut prouver un transfert strictement sûr ; en mode rapide, les redondances restent recommandées.")
        )
        self.mode_label.setText(t("Mode d’analyse"))
        selected_mode = self.mode_combo.currentData() or self.context.store.get("transfer_analysis_mode", "fast")
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        self.mode_combo.addItem(t("Rapide (recommandé)"), "fast")
        self.mode_combo.addItem(t("Audit exhaustif (lent)"), "exhaustive")
        selected_index = self.mode_combo.findData(selected_mode)
        self.mode_combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.mode_combo.blockSignals(False)
        self.upcoming_cm_check.setText(t("Inclure les prochaines CM"))
        self.upcoming_cm_limit.setSuffix(" " + t("CM max."))
        self.team_trials_check.setText(t("Inclure Team Trials"))
        self.generic_profiles_check.setText(t("Inclure les profils génériques"))
        self.run_button.setText(t("Analyser les vétérans locaux"))
        self.load_button.setText(t("Charger le dernier rapport"))
        self.open_button.setText(t("Ouvrir la sortie"))
        self.filter_label.setText(t("Afficher"))
        self.search.setPlaceholderText(t("Rechercher un nom, un score ou un remplaçant…"))
        self.mode_combo.setToolTip(
            t("Le mode rapide repère les redondances ; seul l’audit exhaustif peut conclure à un transfert strictement sûr.")
        )
        self.upcoming_cm_check.setToolTip(
            t("Évalue chaque vétéran dans le contexte des prochaines Champion Meetings configurées.")
        )
        self.upcoming_cm_limit.setToolTip(
            t("Nombre maximal de prochaines Champion Meetings incluses dans l’analyse.")
        )
        self.team_trials_check.setToolTip(
            t("Ajoute les rôles des cinq catégories Team Trials aux usages à préserver.")
        )
        self.generic_profiles_check.setToolTip(
            t("Ajoute des profils génériques pour protéger les usages qui ne dépendent pas d’une course planifiée.")
        )
        self.run_button.setToolTip(
            t("Analyse la collection sans modifier ni supprimer aucun vétéran.")
        )
        self.load_button.setToolTip(
            t("Recharge le dernier rapport Transfer Helper présent dans le dossier de sortie.")
        )
        self.open_button.setToolTip(
            t("Ouvre le dossier contenant le rapport JSON, le CSV et le résumé.")
        )
        self.status_combo.setToolTip(
            t("Filtre le tableau selon le niveau de confiance du diagnostic.")
        )
        self.table.setToolTip(
            t("La couverture désigne le remplaçant ou l’ensemble de vétérans qui préserve les rôles compétitifs de la copie.")
        )
        self.detail.setToolTip(
            t("Le détail explique le verdict, les niches comparées, la dominance et les protections de Sparks appliquées.")
        )
        self.table.horizontalHeader().setToolTip(
            t("Clic droit pour choisir les colonnes affichées ; largeur, ordre et tri sont mémorisés.")
        )
        self.safe_card.setToolTip(
            t("Un remplaçant du même costume et de la même unique couvre toutes les niches viables sans perte de patrimoine Spark protégé.")
        )
        self.recommended_card.setToolTip(
            t("La copie paraît redondante, mais le mode rapide ne fournit pas une preuve suffisante pour la déclarer strictement sûre.")
        )
        self.review_card.setToolTip(
            t("Une niche, une couverture incomplète ou une protection de Spark impose une vérification manuelle.")
        )
        self.keep_card.setToolTip(
            t("La copie conserve au moins un rôle compétitif ou un élément stratégique qui n’est pas suffisamment remplacé.")
        )
        self.protected_card.setToolTip(
            t("Un verrou ou un mémo en jeu interdit toute recommandation de transfert, quel que soit le score.")
        )
        selected = (
            self.status_combo.currentData()
            if self.status_combo.count()
            else self.context.store.get("ui_transfer_status_filter") or None
        )
        self.status_combo.blockSignals(True)
        self.status_combo.clear()
        for label, value in (
            ("Tous les verdicts", None),
            ("Transfert strictement sûr", "safe_transfer"),
            ("Transfert recommandé", "recommended_transfer"),
            ("À examiner", "review"),
            ("Conserver", "keep"),
            ("Protégé", "protected"),
        ):
            self.status_combo.addItem(t(label), value)
        index = self.status_combo.findData(selected)
        self.status_combo.setCurrentIndex(index if index >= 0 else 0)
        self.status_combo.blockSignals(False)
        label_control(
            self.mode_label,
            self.mode_combo,
            self.mode_combo.toolTip(),
        )
        label_control(
            self.filter_label,
            self.status_combo,
            self.status_combo.toolTip(),
        )
        describe_control(
            self.upcoming_cm_check,
            self.upcoming_cm_check.text(),
            self.upcoming_cm_check.toolTip(),
        )
        describe_control(
            self.upcoming_cm_limit,
            f"{self.upcoming_cm_check.text()} · {t('CM max.')}",
            self.upcoming_cm_limit.toolTip(),
        )
        for check in (self.team_trials_check, self.generic_profiles_check):
            describe_control(check, check.text(), check.toolTip())
        describe_control(
            self.search,
            self.search.placeholderText(),
            t("Transfer Helper"),
        )
        describe_control(
            self.table,
            f"{t('Transfer Helper')} · {t('Résultats')}",
            self.table.toolTip(),
        )
        describe_control(
            self.detail,
            f"{t('Transfer Helper')} · {t('Détail')}",
            self.detail.toolTip(),
        )
        self._refresh_cards()
        self._render_result_state()
        self.apply_filters()

    def _scope_values(self) -> dict[str, object]:
        return {
            "analysis_mode": str(self.mode_combo.currentData() or "fast"),
            "include_upcoming_cm_context": self.upcoming_cm_check.isChecked(),
            "upcoming_cm_limit": self.upcoming_cm_limit.value(),
            "include_team_trials": self.team_trials_check.isChecked(),
            "include_generic_profiles": self.generic_profiles_check.isChecked(),
        }

    def _current_fingerprint(self) -> str:
        return self.context.transfer_fingerprint(self._scope_values())

    def _persist_scope(self) -> None:
        scope = self._scope_values()
        self.context.store.update(
            {
                "transfer_analysis_mode": scope["analysis_mode"],
                "transfer_include_upcoming_cm": int(
                    bool(scope["include_upcoming_cm_context"])
                ),
                "transfer_upcoming_cm_limit": scope["upcoming_cm_limit"],
                "transfer_include_team_trials": int(
                    bool(scope["include_team_trials"])
                ),
                "transfer_include_generic_profiles": int(
                    bool(scope["include_generic_profiles"])
                ),
            }
        )

    def _scope_changed(self, *_args: object) -> None:
        self._persist_scope()
        self._refresh_freshness()

    def _status_filter_changed(self, *_args: object) -> None:
        self.context.store.update(
            {"ui_transfer_status_filter": self.status_combo.currentData() or ""}
        )
        self.apply_filters()

    def _set_result_state(self, state: str) -> None:
        self._result_state = state
        self._render_result_state()

    def _render_result_state(self) -> None:
        t = self.context.t
        self.result_state.setText(t(STATE_LABELS[self._result_state]))
        self.result_state.setObjectName(
            "pillWarning" if self._result_state == STATE_STALE else "pillAccent"
        )
        self.result_state.style().unpolish(self.result_state)
        self.result_state.style().polish(self.result_state)
        self.generated_at.setText(
            t("Rapport généré le {date}").replace("{date}", self._generated_at)
            if self._generated_at
            else ""
        )
        describe_control(
            self.result_state,
            self.result_state.text(),
            self.generated_at.text(),
        )

    def _refresh_freshness(self, *_args: object) -> None:
        if self._result_origin_state not in {STATE_READY, STATE_LOADED}:
            return
        state = (
            self._result_origin_state
            if self._current_fingerprint() == self._result_fingerprint
            else STATE_STALE
        )
        self._set_result_state(state)

    @staticmethod
    def _format_generated_at(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return raw

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_freshness()

    def _refresh_cards(self) -> None:
        t = self.context.t
        counts = {
            key: 0
            for key in (
                "safe_transfer",
                "recommended_transfer",
                "review",
                "keep",
                "protected",
            )
        }
        for record in self._records:
            key = str(record.get("status") or "")
            if key in counts:
                counts[key] += 1
        self.safe_card.set_content(t("Strictement sûr"), str(counts["safe_transfer"]), t("Confirmé par audit exhaustif"), "ok")
        self.recommended_card.set_content(t("Recommandé"), str(counts["recommended_transfer"]), t("Redondant dans le portefeuille"), "ok")
        self.review_card.set_content(t("À examiner"), str(counts["review"]), t("Rôle incertain ou Spark à vérifier"), "warning")
        self.keep_card.set_content(t("Conserver"), str(counts["keep"]), t("Nécessaire au portefeuille"), "info")
        self.protected_card.set_content(t("Protégé"), str(counts["protected"]), t("Verrou ou mémo en jeu"), "neutral")

    def set_records(self, records: list[dict[str, Any]]) -> None:
        self._records = list(records)
        self._refresh_cards()
        self.apply_filters()

    def apply_filters(self, *_args: object) -> None:
        status = self.status_combo.currentData()
        query = self.search.text().strip().casefold()
        rows = []
        for record in self._records:
            if status is not None and record.get("status") != status:
                continue
            replacement = record.get("dominated_by") or {}
            coverage = record.get("covered_by_portfolio") or []
            haystack = " ".join(
                str(value or "")
                for value in (
                    record.get("card_name"), record.get("uma_name"),
                    record.get("rank_score"), replacement.get("card_name"),
                    replacement.get("uma_name"), replacement.get("rank_score"),
                    *(item.get("card_name") for item in coverage),
                    *(item.get("rank_score") for item in coverage),
                )
            ).casefold()
            if query and query not in haystack:
                continue
            rows.append(record)
        selected = self.selected_row()
        selected_id = selected.get("trained_chara_id") if selected else None
        self.model.set_columns(self._columns())
        self.model.set_rows(rows)
        sort_column = self.table.horizontalHeader().sortIndicatorSection()
        if sort_column >= 0:
            self.model.sort(
                sort_column,
                self.table.horizontalHeader().sortIndicatorOrder(),
            )
        self.count_label.setText(
            self.context.t("{shown} / {total} vétérans")
            .replace("{shown}", str(len(rows)))
            .replace("{total}", str(len(self._records)))
        )
        target = -1
        if selected_id is not None:
            for index in range(self.model.rowCount()):
                model_row = self.model.row(index) or {}
                if model_row.get("trained_chara_id") == selected_id:
                    target = index
                    break
        if target < 0 and self.model.rowCount():
            target = 0
        if target >= 0:
            self.table.selectRow(target)
        else:
            self.detail.setHtml(transfer_detail_html(None, self.context.language))

    def selected_row(self) -> dict[str, Any] | None:
        indexes = self.table.selectionModel().selectedRows()
        return self.model.row(indexes[0].row()) if indexes else None

    def _selection_changed(self, _selected: QItemSelection, _deselected: QItemSelection) -> None:
        self.detail.setHtml(transfer_detail_html(self.selected_row(), self.context.language))

    def start_analysis(self) -> None:
        priority_text = self.context.store.get("skill_priorities_path")
        analysis_mode = str(self.mode_combo.currentData() or "fast")
        self._persist_scope()
        self._state_before_running = self._result_state
        self._running_fingerprint = self._current_fingerprint()
        self._set_result_state(STATE_RUNNING)
        request = TransferRequest(
            master_path=Path(self.context.master_path).expanduser(),
            veterans_json_path=Path(self.context.veterans_json_path).expanduser(),
            output_dir=Path(self.context.output_dir).expanduser(),
            course_overrides_path=active_course_overrides_path(self.context.course_overrides_path),
            use_custom_scoring=self.context.store.get("use_custom_scoring", "0") in {"1", "true", "True"},
            skill_priorities_path=(Path(priority_text).expanduser() if priority_text else None),
            analysis_mode=analysis_mode,
            include_upcoming_cm_context=self.upcoming_cm_check.isChecked(),
            upcoming_cm_limit=self.upcoming_cm_limit.value(),
            include_team_trials=self.team_trials_check.isChecked(),
            include_generic_profiles=self.generic_profiles_check.isChecked(),
        )
        self.task_requested.emit(
            ProcessTask(partial(run_transfer_analysis, request)),
            self.context.t("Analyse Transfer Helper…"),
            self._analysis_done,
        )

    def _analysis_done(self, result: object) -> None:
        self.set_records(list(getattr(result, "records", ()) or ()))
        self._result_fingerprint = self._running_fingerprint
        self._result_origin_state = STATE_READY
        report_path = getattr(result, "report_json_path", None)
        try:
            payload = json.loads(Path(report_path).read_text(encoding="utf-8-sig"))
            metadata = payload.get("metadata") if isinstance(payload, dict) else {}
        except (OSError, TypeError, json.JSONDecodeError):
            metadata = {}
        self._generated_at = self._format_generated_at(
            (metadata or {}).get("generated_at_utc")
        )
        self._set_result_state(STATE_READY)

    def load_latest(self, *, show_errors: bool = True) -> None:
        path = Path(self.context.output_dir).expanduser() / "transfer_helper_report.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            records = payload.get("records") if isinstance(payload, dict) else None
            if not isinstance(records, list):
                raise ValueError("Le rapport Transfer Helper ne contient pas de liste de résultats.")
            self.set_records([row for row in records if isinstance(row, dict)])
            metadata = payload.get("metadata") or {}
            self._generated_at = self._format_generated_at(
                metadata.get("generated_at_utc")
            )
            self._result_fingerprint = self._current_fingerprint()
            self._result_origin_state = STATE_LOADED
            self._set_result_state(STATE_LOADED)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            if show_errors:
                QMessageBox.information(
                    self,
                    self.context.t("Dernier rapport"),
                    actionable_error(exc, translate=self.context.t),
                )

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.run_button.setEnabled(not busy)
        self.load_button.setEnabled(not busy)
        if not busy and self._result_state == STATE_RUNNING:
            self._set_result_state(self._state_before_running)

    def open_output(self) -> None:
        output = Path(self.context.output_dir).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
            open_path(output)
        except OSError as exc:
            QMessageBox.critical(
                self,
                self.context.t("Erreur"),
                actionable_error(exc, translate=self.context.t),
            )
