from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from backend_process import ProcessTask
from error_guidance import actionable_error
from lineage_planner import LineagePlannerError, write_lineage_planner_export
from output_history import (
    CURRENT_REVISION,
    OutputProvenance,
    PREVIOUS_REVISION,
    available_output_revisions,
    read_json_output_revision,
)
from parent_optimizer import (
    OptimizerError,
    load_ace_options,
    load_track_options,
)
from result_comparison import (
    SEARCH_METRICS,
    ComparisonDataset,
    intersect_datasets,
    search_comparison_dataset,
    search_payload_rows,
)
from uma_moe import UmaMoeError
from ui_qt.accessibility import describe_control, label_control
from ui_qt.asset_catalog import trainee_image_url
from ui_qt.avatar import circular_avatar
from ui_qt.components import (
    PageHeader,
    SearchableComboBox,
    SummarySection,
    SummaryVisualRow,
    muted_label,
    section_label,
)
from ui_qt.combo_avatars import ComboAvatarLoader
from ui_qt.comparison_dialog import ResultComparisonDialog
from ui_qt.context import AppContext, LineageContextState
from ui_qt.core import (
    OnlineSearchRequest,
    OptimizationRequest,
    VeteranOption,
    latest_rankings_path,
    load_local_veteran_options,
    open_path,
    run_online_search,
    run_optimization,
)
from ui_qt.icon_catalog import icon, native_pixmap
from ui_qt.image_assets import image_repository
from ui_qt.lineage_settings import (
    CONDITION_ICON_KEYS,
    PROFILE_ICON_KEYS,
    LineageRaceEditor,
)
from ui_qt.online_options import (
    GRANDPARENT_MODE,
    PARENT_MODE,
    OnlineModeSection,
    OnlineRetrievalSection,
)
from ui_qt.result_families import (
    BRANCHES,
    FAMILY_ORDER,
    FAMILY_RUN_LABELS,
    FUTURE,
    LOCAL_FAMILIES,
    ONLINE_FAMILIES,
    ONLINE_GP,
    ONLINE_PARENT,
    PAIRS,
    ResultFamilyTabs,
    family_for_local_kind,
    family_for_online_mode,
    local_kind_for_family,
    online_mode_for_family,
)
from ui_qt.result_panes import OnlineResultsPane, ResultPane
from ui_qt.view_state import bind_collapsible_state
from ui_qt.presentation import online_detail_html, profile_summary, result_detail_html
from ui_qt.provenance import (
    provenance_badge_text,
    provenance_tooltip,
    revision_menu_label,
)
from ui_qt.theme import COLORS

RAIL_COLLAPSED_KEY = "search_rail_collapsed"
RAIL_WIDTH = 344
# Below this workspace width the rail and a result pane cannot both stay
# readable, so the rail starts collapsed unless the user decided otherwise.
NARROW_WORKSPACE_WIDTH = 1360
SUMMARY_AVATAR_SIZE = 36
SUMMARY_DOMAIN_ICON_SIZE = 26


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class SearchPage(QWidget):
    """Single lineage workspace with one context and two explicit sources."""

    task_requested = Signal(object, str, object)

    def __init__(self, context: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._busy = False
        self._syncing_lineage = False
        self._ace_options: list[Any] = []
        self._local_options: list[VeteranOption] = []
        self._track_options: list[object] = []
        self._card_to_chara: dict[int, int] = {}
        self._last_ace: dict[str, Any] | None = None
        self._last_future_parent: dict[str, Any] | None = None
        self._last_profile: dict[str, Any] = {}
        self._active_result_kind = ""
        self._rail_state_restored = False
        self._rail_preference = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 18)
        root.setSpacing(10)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        # The workspace is split rather than stacked. Configuration used to sit
        # above the results and claim a fixed slice of height on every visit,
        # leaving the tables and their rich-text diagnostics — the part actually
        # read — whatever remained. A collapsible rail lets the results own the
        # full height while keeping every setting one click away.
        self.workspace = QSplitter(Qt.Orientation.Horizontal)
        self.workspace.setChildrenCollapsible(False)
        self.workspace.setHandleWidth(6)

        self.rail = QWidget()
        # The splitter must not squeeze the rail below its content: a squeezed
        # rail hides settings behind an invisible horizontal scroll instead of
        # simply being closed.
        self.rail.setMinimumWidth(RAIL_WIDTH)
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(0, 0, 6, 0)
        rail_layout.setSpacing(8)
        self.rail_title = section_label("")
        rail_layout.addWidget(self.rail_title)

        self.rail_scroll = QScrollArea()
        self.rail_scroll.setWidgetResizable(True)
        self.rail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        rail_body = QWidget()
        rail_body_layout = QVBoxLayout(rail_body)
        rail_body_layout.setContentsMargins(0, 0, 0, 0)
        rail_body_layout.setSpacing(8)

        self.section_objective = SummarySection("")
        objective = QGridLayout()
        objective.setHorizontalSpacing(12)
        objective.setVerticalSpacing(6)
        self.ace_label = QLabel("")
        self.ace_combo = SearchableComboBox()
        self.target_label = QLabel("")
        self.target_combo = SearchableComboBox()
        self.ace_combo.setIconSize(QSize(32, 32))
        self.target_combo.setIconSize(QSize(32, 32))
        repository = image_repository(context)
        self._image_repository = repository
        self._summary_image_urls: set[str] = set()
        self._ace_avatars = ComboAvatarLoader(self.ace_combo, repository)
        self._target_avatars = ComboAvatarLoader(self.target_combo, repository)
        repository.image_ready.connect(self._on_summary_image_ready)
        self.top_label = QLabel("")
        for label in (self.ace_label, self.target_label, self.top_label):
            label.setWordWrap(True)
        self.top_spin = QSpinBox()
        self.top_spin.setRange(5, 200)
        self.top_spin.setValue(context.lineage_state().top_n)
        self.refresh_button = QPushButton("")
        objective.addWidget(self.ace_label, 0, 0, 1, 2)
        objective.addWidget(self.ace_combo, 1, 0, 1, 2)
        objective.addWidget(self.target_label, 2, 0, 1, 2)
        objective.addWidget(self.target_combo, 3, 0, 1, 2)
        objective.addWidget(self.top_label, 4, 0)
        objective.addWidget(self.top_spin, 5, 0)
        objective.addWidget(self.refresh_button, 5, 1)
        objective.setColumnStretch(0, 1)
        objective.setColumnStretch(1, 1)
        self.section_objective.content_layout.addLayout(objective)
        self.section_objective.toggle.setChecked(True)
        rail_body_layout.addWidget(self.section_objective)

        # The editor keeps owning its controls and their synchronisation; the
        # rail only decides where its two groups are shown.
        self.race_editor = LineageRaceEditor(context, self, host_sections=True)
        self.race_editor.shared_hint.setVisible(False)
        self.race_editor.panel.setObjectName("subtlePanel")

        self.section_course = SummarySection("")
        self.section_course.content_layout.addWidget(self.race_editor.panel)
        rail_body_layout.addWidget(self.section_course)

        self.section_conditions = SummarySection("", resettable=True)
        self.section_conditions.content_layout.addWidget(
            self.race_editor.advanced_body
        )
        rail_body_layout.addWidget(self.section_conditions)

        # Shared retrieval first, then one section per remote search: the split
        # mirrors what each setting describes, so the rail no longer implies
        # two independent configurations over one shared set of keys.
        self.section_retrieval = OnlineRetrievalSection(context)
        rail_body_layout.addWidget(self.section_retrieval)
        self.section_online_parent = OnlineModeSection(context, PARENT_MODE)
        rail_body_layout.addWidget(self.section_online_parent)
        self.section_online_gp = OnlineModeSection(context, GRANDPARENT_MODE)
        rail_body_layout.addWidget(self.section_online_gp)

        for section, key, default_expanded in (
            (self.section_objective, "ui_section_search_objective", True),
            (self.section_course, "ui_section_search_course", False),
            (self.section_conditions, "ui_section_search_conditions", False),
            (self.section_retrieval, "ui_section_search_retrieval", False),
            (
                self.section_online_parent,
                "ui_section_search_online_parent",
                False,
            ),
            (self.section_online_gp, "ui_section_search_online_gp", False),
        ):
            bind_collapsible_state(
                section,
                self.context.store,
                key,
                default_expanded=default_expanded,
            )

        rail_body_layout.addStretch(1)
        self.rail_scroll.setWidget(rail_body)
        rail_layout.addWidget(self.rail_scroll, 1)
        self.workspace.addWidget(self.rail)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(10, 0, 0, 0)
        main_layout.setSpacing(10)
        ribbon = QHBoxLayout()
        ribbon.setSpacing(8)
        self.rail_toggle = QToolButton()
        self.rail_toggle.setCheckable(True)
        self.rail_toggle.setAutoRaise(True)
        self.rail_toggle.setIconSize(QSize(16, 16))
        self.context_summary = muted_label("")
        ribbon.addWidget(self.rail_toggle)
        ribbon.addWidget(self.context_summary, 1)
        main_layout.addLayout(ribbon)
        self.workspace.addWidget(main)
        self.workspace.setStretchFactor(0, 0)
        self.workspace.setStretchFactor(1, 1)
        root.addWidget(self.workspace, 1)

        # One toolbar that adapts to the active family, rather than five run
        # buttons and two menus competing above the results.
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.run_button = QPushButton("")
        self.run_button.setObjectName("primary")
        self.load_button = QPushButton("")
        self.history_menu = QMenu(self.load_button)
        self.history_menu.aboutToShow.connect(self._rebuild_history_menu)
        self.load_button.setMenu(self.history_menu)
        self.compare_button = QPushButton("")
        self.export_button = QPushButton("")
        self.import_button = QPushButton("")
        self.local_gp_pairs_button = QPushButton("")
        self.options_button = QPushButton("")
        self.open_button = QPushButton("")
        self.result_badge = QLabel("")
        self.result_badge.setObjectName("pillAccent")
        self.result_badge.setVisible(False)
        # Stated in words next to the result, not only as a tab glyph: the
        # question "does this still match my settings?" is asked while reading
        # the table, not while scanning the tab bar.
        self.stale_badge = QLabel("")
        self.stale_badge.setObjectName("pillWarning")
        self.stale_badge.setVisible(False)
        self.provenance_badge = QLabel("")
        self.provenance_badge.setObjectName("pill")
        self.provenance_badge.setVisible(False)
        self.results_context = muted_label("")
        self.online_badge = QLabel("")
        self.online_badge.setObjectName("pill")
        self.local_badge = QLabel("")
        self.local_badge.setObjectName("pillAccent")
        for widget in (
            self.run_button,
            self.load_button,
            self.compare_button,
            self.export_button,
            self.import_button,
            self.local_gp_pairs_button,
            self.options_button,
            self.open_button,
        ):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        main_layout.addLayout(toolbar)

        # The result context sits on its own row: sharing one with the buttons
        # made a long profile summary squeeze them at narrow widths.
        status = QHBoxLayout()
        status.setSpacing(8)
        status.addWidget(self.result_badge)
        status.addWidget(self.provenance_badge)
        status.addWidget(self.stale_badge)
        status.addWidget(self.results_context, 1)
        status.addWidget(self.local_badge)
        status.addWidget(self.online_badge)
        main_layout.addLayout(status)

        result_frame = QFrame()
        result_frame.setObjectName("panel")
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(10, 9, 10, 10)
        result_layout.setSpacing(7)
        self.pair_results = ResultPane("pair", context)
        self.branch_results = ResultPane("branch", context)
        self.future_results = ResultPane("future", context)
        # Two instances: a grandparent search must stop overwriting the parent
        # results it is meant to complement.
        self.online_parent_results = OnlineResultsPane(
            context, view_key=ONLINE_PARENT
        )
        self.online_gp_results = OnlineResultsPane(context, view_key=ONLINE_GP)
        self.families = ResultFamilyTabs(
            context,
            {
                PAIRS: self.pair_results,
                BRANCHES: self.branch_results,
                FUTURE: self.future_results,
                ONLINE_PARENT: self.online_parent_results,
                ONLINE_GP: self.online_gp_results,
            },
        )
        result_layout.addWidget(self.families, 1)
        main_layout.addWidget(result_frame, 1)

        self.refresh_button.clicked.connect(
            lambda: self.refresh_options(show_errors=True)
        )
        self.rail_toggle.toggled.connect(self._rail_toggled)
        self.section_conditions.reset_requested.connect(
            self.race_editor.clear_static_conditions
        )
        self.section_retrieval.changed.connect(self._refresh_online_validation)
        self.section_online_parent.changed.connect(self._refresh_online_validation)
        self.section_online_gp.changed.connect(self._refresh_online_validation)
        context.online_options_changed.connect(self._refresh_freshness)
        self.ace_combo.currentIndexChanged.connect(self._ace_changed)
        self.target_combo.currentIndexChanged.connect(self._lineage_selection_changed)
        self.top_spin.valueChanged.connect(self._lineage_selection_changed)
        self.race_editor.changed.connect(self._refresh_context)
        self.families.current_changed.connect(self._family_changed)
        self.run_button.clicked.connect(self.run_current_family)
        self.import_button.clicked.connect(self.import_current_family)
        self.options_button.clicked.connect(self.open_current_family_options)
        self.local_gp_pairs_button.clicked.connect(
            lambda: self.start_online("grandparent", local_pairs=True)
        )
        self.export_button.clicked.connect(self.export_selected_pair)
        self.compare_button.clicked.connect(self.compare_current_candidates)
        self.open_button.clicked.connect(self.open_output)
        context.lineage_changed.connect(self._sync_lineage_context)
        context.lineage_changed.connect(self._refresh_freshness)
        context.configuration_changed.connect(self._schedule_refresh)
        context.configuration_changed.connect(self._refresh_freshness)
        context.integration_changed.connect(self._refresh_integration)
        context.language_changed.connect(self._language_changed)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._initial_refresh)
        self._initial_refresh_timer = QTimer(self)
        self._initial_refresh_timer.setSingleShot(True)
        self._initial_refresh_timer.timeout.connect(self._initial_refresh)
        self._initial_result_timer = QTimer(self)
        self._initial_result_timer.setSingleShot(True)
        self._initial_result_timer.timeout.connect(self._initial_result)

        self.retranslate()
        self._sync_lineage_context()
        self._initial_refresh_timer.start(0)
        self._initial_result_timer.start(80)

    def showEvent(self, event) -> None:
        # Width-based inference has to wait for a real geometry: during
        # construction the page is not in its window yet and reports Qt's
        # default size, which would collapse the rail on every machine.
        super().showEvent(event)
        if not self._rail_state_restored:
            self._rail_state_restored = True
            self._restore_rail_state()
        # Cheaply catches overrides files edited outside the app since the
        # page was last visible.
        self._refresh_freshness()

    def _restore_rail_state(self) -> None:
        """Apply the stored rail preference, or infer one from the width."""
        stored = self.context.store.get(RAIL_COLLAPSED_KEY, "")
        if stored in {"0", "1"}:
            self._rail_preference = stored == "1"
        else:
            self._rail_preference = self._workspace_is_narrow()
        self._apply_rail_state()

    def _workspace_is_narrow(self) -> bool:
        window = self.window()
        width = window.width() if window is not None else 0
        return 0 < width < NARROW_WORKSPACE_WIDTH

    def _apply_rail_state(self) -> None:
        """Show the rail when the preference asks for it *and* it fits.

        Below the threshold the rail and a result pane cannot both hold their
        minimum width, and a splitter resolves that by squeezing everything —
        clipped toolbars and a rail scrolling sideways behind a hidden bar.
        Yielding to the width keeps the workspace readable; the preference is
        remembered and takes effect again as soon as the window has room.
        """
        collapsed = self._rail_preference or self._workspace_is_narrow()
        self.rail.setVisible(not collapsed)
        if self.rail_toggle.isChecked() != collapsed:
            self.rail_toggle.blockSignals(True)
            self.rail_toggle.setChecked(collapsed)
            self.rail_toggle.blockSignals(False)
        if not collapsed:
            self.workspace.setSizes([RAIL_WIDTH, max(1, self.width() - RAIL_WIDTH)])
        self._retranslate_rail_toggle()

    def set_rail_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        self._rail_preference = bool(collapsed)
        self._apply_rail_state()
        if persist:
            self.context.store.update({RAIL_COLLAPSED_KEY: "1" if collapsed else "0"})

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._rail_state_restored:
            self._apply_rail_state()

    def _rail_toggled(self, collapsed: bool) -> None:
        self.set_rail_collapsed(collapsed)

    def _retranslate_rail_toggle(self) -> None:
        t = self.context.t
        collapsed = self.rail_toggle.isChecked()
        self.rail_toggle.setText(t("Contexte"))
        self.rail_toggle.setIcon(
            icon("rail-expand" if collapsed else "rail-collapse", COLORS["muted"], size=16)
        )
        self.rail_toggle.setToolTip(
            t("Afficher le contexte") if collapsed else t("Masquer le contexte")
        )
        describe_control(
            self.rail_toggle,
            self.rail_toggle.toolTip(),
            self.context_summary.text(),
        )

    def _initial_refresh(self) -> None:
        self.refresh_options(show_errors=False)

    def _initial_result(self) -> None:
        self.load_latest(show_errors=False)

    def _language_changed(self, _language: str) -> None:
        self.retranslate()

    def _schedule_refresh(self) -> None:
        self._refresh_timer.start(120)

    def refresh_options(self, *, show_errors: bool = True) -> None:
        try:
            master = Path(self.context.master_path).expanduser()
            data = Path(self.context.veterans_json_path).expanduser()
            self._ace_options = list(load_ace_options(master))
            self._local_options = load_local_veteran_options(master, data)
            self._track_options = list(load_track_options(master))
        except Exception as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.context.t("Configuration incomplète"),
                    actionable_error(exc, translate=self.context.t),
                )
            self._refresh_source_badges()
            return
        self._card_to_chara = {
            option.card_id: option.chara_id for option in self._ace_options
        }
        state = self.context.lineage_state()
        self._syncing_lineage = True
        try:
            for combo, selected in (
                (self.ace_combo, state.ace_card_id),
                (self.target_combo, state.future_parent_card_id),
            ):
                combo.blockSignals(True)
                combo.clear()
                for option in self._ace_options:
                    combo.addItem(option.display_name, option.card_id)
                index = combo.findData(selected)
                combo.setCurrentIndex(
                    index if index >= 0 else (0 if combo.count() else -1)
                )
                combo.blockSignals(False)
            self._ensure_distinct_parent()
        finally:
            self._syncing_lineage = False
        card_ids = [option.card_id for option in self._ace_options]
        self._ace_avatars.apply(card_ids)
        self._target_avatars.apply(card_ids)
        self.race_editor.set_track_options(
            sorted(self._track_options, key=lambda item: item.name.casefold())
        )
        self.section_retrieval.set_ace_options(self._ace_options)
        for section in (self.section_online_parent, self.section_online_gp):
            section.set_options(self._ace_options, self._local_options)
        self._refresh_online_validation()
        self._lineage_selection_changed()
        self._refresh_source_badges()

    def _ensure_distinct_parent(self) -> None:
        ace_id = _integer(self.ace_combo.currentData())
        parent_id = _integer(self.target_combo.currentData())
        ace_chara = self._card_to_chara.get(ace_id)
        if ace_chara is None or self._card_to_chara.get(parent_id) != ace_chara:
            return
        for index in range(self.target_combo.count()):
            candidate = _integer(self.target_combo.itemData(index))
            if self._card_to_chara.get(candidate) != ace_chara:
                self.target_combo.setCurrentIndex(index)
                return

    def _ace_changed(self, _index: int) -> None:
        if self._syncing_lineage:
            return
        self._ensure_distinct_parent()
        self._lineage_selection_changed()

    def _lineage_selection_changed(self, *_args: object) -> None:
        if self._syncing_lineage:
            return
        changes: dict[str, object] = {"top_n": self.top_spin.value()}
        ace_id = _integer(self.ace_combo.currentData())
        target_id = _integer(self.target_combo.currentData())
        if ace_id:
            changes["ace_card_id"] = ace_id
        if target_id:
            changes["future_parent_card_id"] = target_id
        self.context.update_lineage(**changes)
        self._refresh_context()

    def _sync_lineage_context(
        self, _state: LineageContextState | None = None
    ) -> None:
        state = self.context.lineage_state()
        corrected_parent = 0
        self._syncing_lineage = True
        try:
            for combo, selected in (
                (self.ace_combo, state.ace_card_id),
                (self.target_combo, state.future_parent_card_id),
            ):
                index = combo.findData(selected)
                if index >= 0 and combo.currentIndex() != index:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(index)
                    combo.blockSignals(False)
            self._ensure_distinct_parent()
            corrected_parent = _integer(self.target_combo.currentData())
            self.top_spin.blockSignals(True)
            self.top_spin.setValue(state.top_n)
            self.top_spin.blockSignals(False)
        finally:
            self._syncing_lineage = False
        if corrected_parent and corrected_parent != state.future_parent_card_id:
            self.context.update_lineage(future_parent_card_id=corrected_parent)
        else:
            self._refresh_context()

    def _refresh_context(self, *_args: object) -> None:
        state = self.context.lineage_state()
        profile = self.race_editor.current_profile()
        condition_parts = [
            self.context.t(value)
            for value in (
                state.rotation,
                state.season,
                state.weather,
                state.ground_condition,
            )
            if value and value != "Non précisé"
        ]
        text = profile_summary(profile, self.context.language)
        text += f" · {self.race_editor.current_course_label()}"
        if condition_parts:
            text += " · " + " / ".join(condition_parts)
        self.context_summary.setText(text)
        self.rail_toggle.setAccessibleDescription(text)
        self._refresh_section_summaries(state, profile)

    def _compact_ace_summary(self, card_id: int, fallback: str) -> str:
        """Return the card identity without repeating the base Uma name.

        The searchable combos intentionally use ``Uma — card`` so similarly
        named costumes remain easy to find. In the compact context rail the
        field label already states the role, and repeating the base name makes
        long summaries considerably harder to scan.
        """
        for option in self._ace_options:
            if option.card_id == card_id:
                name = option.card_name.strip() or option.uma_name.strip()
                return f"{name} ({option.card_id})"
        return fallback.strip()

    def _summary_avatar(self, card_id: int) -> QPixmap:
        """Return a cached circular avatar, reserving its slot while loading."""

        url = trainee_image_url(card_id)
        if not url:
            return QPixmap()
        self._summary_image_urls.add(url)
        source = self._image_repository.pixmap(url)
        if source is not None:
            return circular_avatar(source, SUMMARY_AVATAR_SIZE)

        # Keep the text aligned while the async repository fetches the image;
        # the image_ready signal refreshes the summary once the portrait lands.
        placeholder = QPixmap(SUMMARY_AVATAR_SIZE, SUMMARY_AVATAR_SIZE)
        placeholder.fill(Qt.GlobalColor.transparent)
        return placeholder

    def _summary_profile_icons(self, profile: dict[str, str]) -> tuple[QPixmap, ...]:
        icon_key = PROFILE_ICON_KEYS.get("style", {}).get(profile.get("style", ""))
        if not icon_key:
            return ()
        return (native_pixmap(icon_key, SUMMARY_DOMAIN_ICON_SIZE),)

    def _summary_condition_icons(self) -> tuple[QPixmap, ...]:
        icons: list[QPixmap] = []
        for kind, combo in (
            ("season", self.race_editor.season_combo),
            ("weather", self.race_editor.weather_combo),
        ):
            canonical = combo.currentData()
            lookup_value = canonical[0] if isinstance(canonical, list) and canonical else canonical
            icon_key = CONDITION_ICON_KEYS.get(kind, {}).get(lookup_value)
            if icon_key:
                icons.append(native_pixmap(icon_key, SUMMARY_DOMAIN_ICON_SIZE))
        return tuple(icons)

    def _on_summary_image_ready(self, url: str, _pixmap: object) -> None:
        if url in self._summary_image_urls:
            self._refresh_context()

    def _refresh_section_summaries(
        self, state: LineageContextState, profile: dict[str, str]
    ) -> None:
        """Keep every collapsed section readable and visually scannable.

        One labelled fact stays on each line. Where the underlying control has
        a stable visual language, the collapsed summary now repeats it too:
        character portraits for the two lineage roles, a running-style badge for
        the profile, and season/weather for static conditions.
        """
        t = self.context.t
        self._summary_image_urls.clear()
        ace_id = _integer(self.ace_combo.currentData())
        target_id = _integer(self.target_combo.currentData())

        objective_rows: list[SummaryVisualRow] = []
        objective_lines: list[str] = []
        if ace_id:
            text = (
                f"{t('Ace visé')}: "
                + self._compact_ace_summary(ace_id, self.ace_combo.currentText())
            )
            objective_lines.append(text)
            objective_rows.append(SummaryVisualRow(text, (self._summary_avatar(ace_id),)))
        if target_id:
            text = (
                f"{t('Parent à produire')}: "
                + self._compact_ace_summary(
                    target_id, self.target_combo.currentText()
                )
            )
            objective_lines.append(text)
            objective_rows.append(SummaryVisualRow(text, (self._summary_avatar(target_id),)))
        results_text = f"{t('Résultats')}: {state.top_n}"
        objective_lines.append(results_text)
        objective_rows.append(SummaryVisualRow(results_text))
        if ace_id:
            self.section_objective.set_visual_summary(
                objective_rows, plain_text="\n".join(objective_lines)
            )
        else:
            self.section_objective.set_summary(t("Aucun Ace sélectionné"))

        profile_text = f"{t('Profil')}: {profile_summary(profile, self.context.language)}"
        race_text = f"{t('Course')}: {self.race_editor.current_course_label()}"
        self.section_course.set_visual_summary(
            (
                SummaryVisualRow(profile_text, self._summary_profile_icons(profile)),
                SummaryVisualRow(race_text),
            ),
            plain_text=f"{profile_text}\n{race_text}",
        )

        static_labels = self.race_editor.static_condition_labels()
        static_rows: list[SummaryVisualRow] = []
        static_lines: list[str] = []
        if self.race_editor.track_combo.currentIndex() > 0:
            text = f"{t('Piste')}: {self.race_editor.track_combo.currentText()}"
            static_lines.append(text)
            static_rows.append(SummaryVisualRow(text))
        condition_values = [
            t(value)
            for value in (
                state.rotation,
                state.season,
                state.weather,
                state.ground_condition,
            )
            if value and value != "Non précisé"
        ]
        if condition_values:
            text = f"{t('Conditions')}: {' · '.join(condition_values)}"
            static_lines.append(text)
            static_rows.append(SummaryVisualRow(text, self._summary_condition_icons()))
        overrides: list[str] = []
        if self.race_editor.custom_scoring.isChecked():
            overrides.append(t("pondérations personnalisées"))
        if self.race_editor.priority_picker.text().strip():
            overrides.append(t("priorités white personnalisées"))
        if overrides:
            text = f"{t('Personnalisation')}: {' · '.join(overrides)}"
            static_lines.append(text)
            static_rows.append(SummaryVisualRow(text))
        if static_rows:
            self.section_conditions.set_visual_summary(
                static_rows, plain_text="\n".join(static_lines)
            )
        else:
            self.section_conditions.set_summary(t("Aucune condition fixée"))
        self.section_conditions.set_modified(bool(static_labels), t("Modifié"))

    def _refresh_online_validation(self) -> None:
        """Surface a costume conflict where it can be fixed, not on a save click."""
        allowed = self.section_retrieval.allowed_ids()
        excluded = self.section_retrieval.excluded_ids()
        for section in (self.section_online_parent, self.section_online_gp):
            section.show_validation(section.validation_error(allowed, excluded))

    def _refresh_source_badges(self) -> None:
        self.local_badge.setText(
            self.context.t("{count} vétérans").replace(
                "{count}", str(len(self._local_options))
            )
        )
        self._refresh_integration()

    def _refresh_integration(self) -> None:
        status = (
            self.context.t("API configurée")
            if self.context.uma_moe_api_key
            else self.context.t("Clé API absente")
        )
        self.online_badge.setText(status)

    def open_conditions(self) -> None:
        """Reveal the static conditions instead of opening a modal editor.

        Kept as a named entry point so any caller asking for "the conditions"
        lands on them, now that they live in the rail rather than in a dialog.
        """
        self.set_rail_collapsed(False)
        self.section_conditions.toggle.setChecked(True)
        self.rail_scroll.ensureWidgetVisible(self.section_conditions)
        self._refresh_context()

    def _selected_ids(self) -> tuple[int, int]:
        self.ace_combo.resolve_current_text()
        self.target_combo.resolve_current_text()
        return (
            _integer(self.ace_combo.currentData()),
            _integer(self.target_combo.currentData()),
        )

    def _optimization_request(self, kind: str) -> OptimizationRequest:
        ace_id, target_id = self._selected_ids()
        if ace_id <= 0:
            raise OptimizerError("Sélectionne l’Ace cible.")
        if kind == "future" and target_id <= 0:
            raise OptimizerError("Sélectionne le parent à produire.")
        if (
            kind == "future"
            and self._card_to_chara.get(ace_id) == self._card_to_chara.get(target_id)
        ):
            raise OptimizerError(
                "L'Ace et le parent à produire doivent être deux personnages différents."
            )
        profile = self.race_editor.current_profile()
        return OptimizationRequest(
            master_path=Path(self.context.master_path).expanduser(),
            veterans_json_path=Path(self.context.veterans_json_path).expanduser(),
            output_dir=Path(self.context.output_dir).expanduser(),
            ace_card_id=ace_id,
            future_parent_card_id=target_id,
            surface=profile["surface"],
            distance=profile["distance"],
            style=profile["style"],
            course_overrides_path=self.race_editor.course_overrides_path(),
            course_key=self.race_editor.current_course_key(),
            course_conditions=self.race_editor.selected_conditions(),
            top_n=self.top_spin.value(),
            use_custom_scoring=self.race_editor.custom_scoring.isChecked(),
            skill_priorities_path=self.race_editor.skill_priorities_path(),
            search_kind=kind,
        )

    def start_local(self, kind: str) -> None:
        try:
            request = self._optimization_request(kind)
        except (OptimizerError, ValueError) as exc:
            QMessageBox.warning(
                self,
                self.context.t("Configuration incomplète"),
                actionable_error(exc, translate=self.context.t),
            )
            return
        labels = {
            "pairs": "Recherche des paires finales locales…",
            "branches": "Classement des parents locaux…",
            "future": "Classement des grands-parents locaux…",
        }
        self.context.update_lineage(
            ace_card_id=request.ace_card_id,
            future_parent_card_id=request.future_parent_card_id,
            top_n=request.top_n,
        )
        self.task_requested.emit(
            ProcessTask(partial(run_optimization, request)),
            self.context.t(labels[kind]),
            lambda result: self._local_done(result, kind),
        )

    def _local_done(self, result: object, kind: str) -> None:
        self._last_ace = getattr(result, "ace", None)
        self._last_future_parent = getattr(result, "future_parent", None)
        self._last_profile = dict(getattr(result, "profile", None) or {})
        if kind == "pairs":
            self.pair_results.set_rows(
                list(getattr(result, "top_parent_pairs", ()) or ()),
                self._last_profile,
                lineage_root=self._last_ace,
            )
        elif kind == "branches":
            self.branch_results.set_rows(
                list(getattr(result, "top_parent_candidates", ()) or ()),
                self._last_profile,
                lineage_root=self._last_ace,
            )
        else:
            self.future_results.set_rows(
                list(getattr(result, "top_future_grandparents", ()) or ()),
                self._last_profile,
                lineage_root=self._last_future_parent,
            )
        self._show_results(
            family_for_local_kind(kind),
            f"local:{kind}",
            self._last_profile,
            provenance=self._result_provenance(result),
        )

    def _mode_section(self, mode: str) -> OnlineModeSection:
        return (
            self.section_online_parent
            if mode == PARENT_MODE
            else self.section_online_gp
        )

    def _online_options_values(self, mode: str) -> dict[str, Any]:
        """Assemble one search's options from the shared and per-mode sections."""
        values = dict(self.section_retrieval.values())
        values.update(self._mode_section(mode).values())
        return values

    def _online_options_snapshot(self, mode: str) -> dict[str, Any]:
        """Read widgets quickly; normalization and copying happen in the worker."""
        values = dict(self.section_retrieval.snapshot_values())
        values.update(self._mode_section(mode).snapshot_values())
        return values

    def open_online_options(self, mode: str | None = None) -> None:
        """Reveal a mode's options instead of opening a modal editor."""
        mode = mode or self.context.store.get("uma_moe_search_mode", PARENT_MODE)
        section = self._mode_section(
            PARENT_MODE if mode == PARENT_MODE else GRANDPARENT_MODE
        )
        self.set_rail_collapsed(False)
        section.toggle.setChecked(True)
        self.rail_scroll.ensureWidgetVisible(section)

    def start_online_import(self, mode: str | None = None) -> None:
        mode = mode or self.context.store.get("uma_moe_search_mode", "parent")
        self.start_online(mode, use_import=True)

    def start_online(
        self,
        mode: str,
        *,
        use_import: bool = False,
        local_pairs: bool = False,
    ) -> None:
        mode = "parent" if mode == "parent" else "grandparent"
        try:
            ace_id, target_id = self._selected_ids()
            if ace_id <= 0:
                raise UmaMoeError("Sélectionne l’Ace cible.")
            if mode == "grandparent" and target_id <= 0:
                raise UmaMoeError("Sélectionne le parent à produire.")
            options = self._online_options_snapshot(mode)
            profile = self.race_editor.current_profile()
            request = OnlineSearchRequest(
                search_mode=mode,
                master_path=Path(self.context.master_path).expanduser(),
                veterans_json_path=Path(self.context.veterans_json_path).expanduser(),
                output_dir=Path(self.context.output_dir).expanduser(),
                ace_card_id=ace_id,
                target_parent_card_id=(target_id if mode == "grandparent" else None),
                fixed_local_id=None,
                automatic_pairs=True,
                local_pool_size=1,
                remote_pool_size=1,
                surface=profile["surface"],
                distance=profile["distance"],
                style=profile["style"],
                course_overrides_path=self.race_editor.course_overrides_path(),
                course_key=self.race_editor.current_course_key(),
                course_conditions=self.race_editor.selected_conditions(),
                top_n=self.top_spin.value(),
                use_import=use_import,
                response_path=None,
                api_base=self.context.uma_moe_api_base,
                uql="",
                auto_uql=True,
                uql_options=None,
                limit=1,
                required_parent_card_id=None,
                token=self.context.uma_moe_api_key,
                use_custom_scoring=self.race_editor.custom_scoring.isChecked(),
                skill_priorities_path=self.race_editor.skill_priorities_path(),
                local_pair_mode=local_pairs,
                deferred_options=options,
            )
        except (UmaMoeError, OptimizerError, ValueError) as exc:
            QMessageBox.warning(
                self,
                self.context.t("Configuration incomplète"),
                actionable_error(exc, translate=self.context.t),
            )
            return
        self.context.store.update(
            {
                "uma_moe_search_mode": mode,
                "uma_moe_response_path": options["response_path"],
            }
        )
        updates: dict[str, object] = {
            "ace_card_id": request.ace_card_id,
            "top_n": request.top_n,
        }
        if request.target_parent_card_id:
            updates["future_parent_card_id"] = request.target_parent_card_id
        self.context.update_lineage(**updates)
        label = (
            "Classement des paires de GP locales…"
            if local_pairs
            else "Recherche et classement uma.moe…"
        )
        self.task_requested.emit(
            ProcessTask(partial(run_online_search, request)),
            self.context.t(label),
            lambda result: self._online_done(result, request),
        )

    def _online_done(self, result: object, request: OnlineSearchRequest) -> None:
        profile = {
            "surface": request.surface,
            "distance": request.distance,
            "style": request.style,
        }
        family = family_for_online_mode(request.search_mode)
        pane = (
            self.online_parent_results
            if family == ONLINE_PARENT
            else self.online_gp_results
        )
        pane.set_result(result, profile)
        source = "local" if request.local_pair_mode else "uma.moe"
        self._show_results(
            family,
            f"{source}:online_{request.search_mode}",
            profile,
            provenance=self._result_provenance(result),
        )
        response = request.output_dir / "uma_moe_api_response.json"
        if not request.use_import and response.is_file():
            self.context.store.update({"uma_moe_response_path": str(response)})

    def _show_results(
        self,
        family: str,
        kind: str,
        profile: dict[str, Any] | None,
        *,
        loaded: bool = False,
        provenance: OutputProvenance | None = None,
    ) -> None:
        """Record a family's result and bring it forward.

        Recording is per family, so a result is never destroyed by running a
        different one; only the visible tab changes.
        """
        self._active_result_kind = kind
        view = self.families.view(family)
        view.mark_result(
            loaded=loaded,
            kind=kind,
            profile=profile,
            fingerprint=self.context.family_fingerprint(family),
            provenance=provenance,
        )
        self.families.set_current_family(family)
        self.families.refresh_freshness()
        self._refresh_toolbar()

    def _refresh_freshness(self, *_args: object) -> None:
        """Re-compare every family's result against the current inputs."""
        self.families.refresh_freshness()
        self._refresh_toolbar()

    def _family_changed(self, family: str) -> None:
        self._refresh_toolbar()
        self._sync_mode_sections(family)

    def _sync_mode_sections(self, family: str) -> None:
        """Let the active tab decide which mode's options are in view.

        The tab already carries the parent/grandparent choice, so a second
        selector for the same state could only drift out of sync with it. The
        sibling section collapses rather than hiding: its header keeps its
        values readable, and no section ever moves.
        """
        if family not in ONLINE_FAMILIES:
            return
        self.context.store.update(
            {"uma_moe_search_mode": online_mode_for_family(family)}
        )
        active = self._mode_section(online_mode_for_family(family))
        for section in (self.section_online_parent, self.section_online_gp):
            section.toggle.setChecked(section is active)

    def _refresh_toolbar(self) -> None:
        """Expose exactly the verbs the visible family supports."""
        t = self.context.t
        family = self.families.current_family()
        view = self.families.view(family)
        self.run_button.setText(t(FAMILY_RUN_LABELS[family]))
        online = family in ONLINE_FAMILIES
        self.import_button.setVisible(online)
        self.options_button.setVisible(online)
        self.local_gp_pairs_button.setVisible(family == ONLINE_GP)
        self.export_button.setVisible(family == PAIRS and view.has_result())
        self.online_badge.setVisible(online)
        self.local_badge.setVisible(not online)
        self.result_badge.setVisible(bool(view.result_kind))
        labels = {
            "local:pairs": "Local · paires finales",
            "local:branches": "Local · parents",
            "local:future": "Local · grands-parents",
            "uma.moe:online_parent": "uma.moe · parents distants",
            "uma.moe:online_grandparent": "uma.moe · grands-parents distants",
            "local:online_grandparent": "Local · paires de grands-parents",
        }
        self.result_badge.setText(
            t(labels.get(view.result_kind, view.result_kind))
        )
        self.provenance_badge.setVisible(view.provenance is not None)
        self.provenance_badge.setText(
            provenance_badge_text(view.provenance, t)
            if view.provenance is not None
            else ""
        )
        self.provenance_badge.setToolTip(
            provenance_tooltip(view.provenance, t)
            if view.provenance is not None
            else ""
        )
        describe_control(
            self.provenance_badge,
            t("Traçabilité"),
            self.provenance_badge.toolTip(),
        )
        pane = self._result_pane(family)
        self.compare_button.setVisible(view.has_result())
        self.compare_button.setEnabled(
            not self._busy and pane.model.rowCount() >= 2
        )
        self.results_context.setText(
            profile_summary(dict(view.profile), self.context.language)
            if view.has_result()
            else ""
        )
        self.run_button.setEnabled(not self._busy)
        stale = view.is_stale()
        self.stale_badge.setVisible(stale)
        self.results_context.setToolTip(
            t("Le contexte a changé depuis ce calcul") if stale else ""
        )
        self.results_context.setAccessibleDescription(
            " · ".join(
                part
                for part in (self.results_context.text(), self.results_context.toolTip())
                if part
            )
        )

    def run_current_family(self) -> None:
        """The one verb of the visible view; also bound to Ctrl+Enter."""
        if self._busy:
            return
        family = self.families.current_family()
        if family in LOCAL_FAMILIES:
            self.start_local(local_kind_for_family(family))
        else:
            self.start_online(online_mode_for_family(family))

    def import_current_family(self) -> None:
        family = self.families.current_family()
        if family in ONLINE_FAMILIES:
            self.start_online(online_mode_for_family(family), use_import=True)

    def open_current_family_options(self) -> None:
        family = self.families.current_family()
        if family in ONLINE_FAMILIES:
            self.open_online_options(online_mode_for_family(family))

    def _result_output_path(self, family: str) -> Path:
        output = Path(self.context.output_dir).expanduser()
        if family == ONLINE_PARENT:
            return output / "uma_moe_parent_pairs.json"
        if family == ONLINE_GP:
            return output / "uma_moe_grandparent_pairs.json"
        return latest_rankings_path(output)

    def _result_provenance(self, result: object) -> OutputProvenance | None:
        path = getattr(result, "rankings_json_path", None)
        if path is None:
            return None
        try:
            _payload, provenance = read_json_output_revision(
                Path(path), CURRENT_REVISION
            )
            return provenance
        except (OSError, TypeError, json.JSONDecodeError, ValueError):
            return None

    def _rebuild_history_menu(self) -> None:
        self.history_menu.clear()
        revisions = available_output_revisions(
            self._result_output_path(self.families.current_family())
        )
        if not revisions:
            action = self.history_menu.addAction(
                self.context.t("Aucune exécution enregistrée")
            )
            action.setEnabled(False)
            return
        for revision in revisions:
            action = self.history_menu.addAction(
                revision_menu_label(revision, self.context.t)
            )
            action.triggered.connect(
                lambda _checked=False, key=revision.key: self.load_revision(
                    key, show_errors=True
                )
            )
        revision_keys = {revision.key for revision in revisions}
        if {CURRENT_REVISION, PREVIOUS_REVISION}.issubset(revision_keys):
            self.history_menu.addSeparator()
            compare = self.history_menu.addAction(
                self.context.t("Comparer courant ↔ précédent")
            )
            compare.triggered.connect(self.compare_history)

    def _result_pane(self, family: str):
        return {
            PAIRS: self.pair_results,
            BRANCHES: self.branch_results,
            FUTURE: self.future_results,
            ONLINE_PARENT: self.online_parent_results,
            ONLINE_GP: self.online_gp_results,
        }[family]

    @staticmethod
    def _pane_rows(pane: QWidget) -> list[dict[str, Any]]:
        model = getattr(pane, "model")
        return [
            row
            for index in range(model.rowCount())
            if (row := model.row(index)) is not None
        ]

    def _comparison_renderer(self, family: str):
        def render(item, dataset: ComparisonDataset) -> str:
            if family in ONLINE_FAMILIES:
                return online_detail_html(
                    item.row,
                    dataset.mode,
                    self.context.language,
                    dataset.profile,
                )
            return result_detail_html(
                item.row,
                local_kind_for_family(family),
                self.context.language,
                dataset.profile,
            )

        return render

    def _show_comparison_error(self, message: str) -> None:
        QMessageBox.information(
            self,
            self.context.t("Comparaison"),
            self.context.t(message),
        )

    def compare_current_candidates(self) -> None:
        family = self.families.current_family()
        pane = self._result_pane(family)
        rows = self._pane_rows(pane)
        if len(rows) < 2:
            self._show_comparison_error(
                "Cette vue doit contenir au moins deux candidats à comparer."
            )
            return
        view = self.families.view(family)
        base = search_comparison_dataset(
            family,
            rows,
            title=self.context.t("Résultat affiché"),
            profile=view.profile,
            provenance=view.provenance,
        )
        left = ComparisonDataset(
            self.context.t("Candidat A"),
            base.items,
            profile=base.profile,
            mode=base.mode,
            provenance=base.provenance,
        )
        right = ComparisonDataset(
            self.context.t("Candidat B"),
            base.items,
            profile=base.profile,
            mode=base.mode,
            provenance=base.provenance,
        )
        selected = pane.selected_row()
        selected_rank = selected.get("_rank") if selected else None
        left_index = next(
            (
                index
                for index, item in enumerate(left.items)
                if item.row.get("_rank") == selected_rank
            ),
            0,
        )
        right_index = (left_index + 1) % len(right.items)
        ResultComparisonDialog(
            self.context,
            title="Comparer deux candidats",
            left=left,
            right=right,
            metrics=SEARCH_METRICS,
            renderer=self._comparison_renderer(family),
            left_key=left.items[left_index].key,
            right_key=right.items[right_index].key,
            parent=self,
        ).exec()

    def compare_history(self) -> None:
        family = self.families.current_family()
        path = self._result_output_path(family)
        try:
            current_payload, current_provenance = read_json_output_revision(
                path, CURRENT_REVISION
            )
            previous_payload, previous_provenance = read_json_output_revision(
                path, PREVIOUS_REVISION
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                self.context.t("Comparaison"),
                actionable_error(exc, translate=self.context.t),
            )
            return
        current_profile = (
            (current_payload.get("metadata") or {}).get("profile")
            if family in ONLINE_FAMILIES
            else current_payload.get("profile")
        )
        previous_profile = (
            (previous_payload.get("metadata") or {}).get("profile")
            if family in ONLINE_FAMILIES
            else previous_payload.get("profile")
        )
        current = search_comparison_dataset(
            family,
            search_payload_rows(family, current_payload),
            title=self.context.t("Exécution courante"),
            profile=current_profile if isinstance(current_profile, dict) else {},
            provenance=current_provenance,
        )
        previous = search_comparison_dataset(
            family,
            search_payload_rows(family, previous_payload),
            title=self.context.t("Exécution précédente"),
            profile=previous_profile if isinstance(previous_profile, dict) else {},
            provenance=previous_provenance,
        )
        current, previous = intersect_datasets(current, previous)
        if not current.items:
            self._show_comparison_error(
                "Aucun candidat identifiable n’est commun aux deux exécutions."
            )
            return
        ResultComparisonDialog(
            self.context,
            title="Comparer avant / après recalcul",
            left=previous,
            right=current,
            metrics=SEARCH_METRICS,
            renderer=self._comparison_renderer(family),
            match_identities=True,
            parent=self,
        ).exec()

    def load_latest(self, *, show_errors: bool = True) -> None:
        self.load_revision(CURRENT_REVISION, show_errors=show_errors)

    def load_revision(
        self,
        revision_key: str,
        *,
        show_errors: bool = True,
    ) -> None:
        """Load one retained generation for the visible result family.

        Scoped to the active family rather than picking the newest file of any
        kind: with one result slot per family, a global "latest" would drop a
        result into whichever tab happened to be in front.
        """
        family = self.families.current_family()
        path = self._result_output_path(family)
        revisions = {
            revision.key: revision
            for revision in available_output_revisions(path)
        }
        selected = revisions.get(revision_key)
        if selected is None:
            if show_errors:
                QMessageBox.information(
                    self,
                    self.context.t("Dernier résultat"),
                    self.context.t(
                        "Cette vue n’a pas encore de calcul enregistré sur le disque."
                    ),
                )
            return
        try:
            payload, provenance = read_json_output_revision(
                self._result_output_path(family), revision_key
            )
        except Exception as exc:
            if show_errors:
                QMessageBox.warning(
                    self,
                    self.context.t("Dernier résultat"),
                    actionable_error(exc, translate=self.context.t),
                )
            return
        if family in ONLINE_FAMILIES:
            mode = online_mode_for_family(family)
            metadata = payload.get("metadata") or {}
            profile = metadata.get("profile") or {}
            pane = (
                self.online_parent_results
                if family == ONLINE_PARENT
                else self.online_gp_results
            )
            pane.set_payload(payload, mode)
            is_local_gp = str(metadata.get("pair_mode") or "").startswith("local_")
            source = "local" if is_local_gp else "uma.moe"
            self._show_results(
                family,
                f"{source}:online_{mode}",
                profile,
                loaded=True,
                provenance=provenance,
            )
            return
        ace = payload.get("ace") if isinstance(payload.get("ace"), dict) else None
        future_parent = (
            payload.get("future_parent")
            if isinstance(payload.get("future_parent"), dict)
            else None
        )
        profile = (
            payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
        )
        self._last_ace = ace
        self._last_future_parent = future_parent
        self._last_profile = dict(profile)
        rows_by_family = {
            PAIRS: (list(payload.get("top_parent_pairs") or []), ace),
            BRANCHES: (list(payload.get("top_parent_candidates") or []), ace),
            FUTURE: (
                list(payload.get("top_future_grandparents") or []),
                future_parent,
            ),
        }
        rows, root = rows_by_family[family]
        if not rows:
            if show_errors:
                QMessageBox.information(
                    self,
                    self.context.t("Dernier résultat"),
                    self.context.t(
                        "Le dernier calcul local ne couvre pas cette vue."
                    ),
                )
            return
        panes = {
            PAIRS: self.pair_results,
            BRANCHES: self.branch_results,
            FUTURE: self.future_results,
        }
        panes[family].set_rows(rows, profile, lineage_root=root)
        self._show_results(
            family,
            f"local:{local_kind_for_family(family)}",
            profile,
            loaded=True,
            provenance=provenance,
        )

    def export_selected_pair(self) -> None:
        row = self.pair_results.selected_row()
        if not row or not self._last_ace:
            QMessageBox.information(
                self,
                self.context.t("Export"),
                self.context.t("Sélectionne d'abord une paire à exporter."),
            )
            return
        parent_1 = row.get("parent_1") or {}
        parent_2 = row.get("parent_2") or {}
        ace_id = _integer(self._last_ace.get("card_id"))
        p1_id = _integer(parent_1.get("card_id"))
        p2_id = _integer(parent_2.get("card_id"))
        suggested = (
            Path(self.context.output_dir).expanduser()
            / f"local_lineage_{ace_id}_{p1_id}_{p2_id}.json"
        )
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self.context.t("Exporter la paire vers uma.moe Lineage Planner"),
            str(suggested),
            "JSON (*.json)",
        )
        if not filename:
            return
        try:
            path = write_lineage_planner_export(
                filename,
                self._last_ace,
                parent_1,
                parent_2,
                master_path=self.context.master_path,
                veterans_json_path=self.context.veterans_json_path,
            )
        except (OSError, ValueError, LineagePlannerError) as exc:
            QMessageBox.critical(
                self,
                self.context.t("Erreur d’export"),
                actionable_error(exc, translate=self.context.t),
            )
            return
        QMessageBox.information(
            self,
            self.context.t("Export terminé"),
            self.context.t("Fichier créé : {path}").replace("{path}", str(path)),
        )

    def set_busy(self, busy: bool) -> None:
        """One worker at a time: every run action is disabled while it runs."""
        self._busy = busy
        for widget in (
            self.refresh_button,
            self.run_button,
            self.import_button,
            self.local_gp_pairs_button,
            self.load_button,
            self.compare_button,
        ):
            widget.setEnabled(not busy)
        if not busy:
            for family in FAMILY_ORDER:
                self.families.view(family).clear_running()
        self.families.refresh_states()
        self._refresh_toolbar()

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

    def retranslate(self) -> None:
        t = self.context.t
        self.header.set_text(
            t("Recherche de lignées"),
            t(
                "Définis le contexte une seule fois, puis lance chaque onglet quand tu en as besoin."
            ),
        )
        self.rail_title.setText(t("Contexte commun"))
        self.section_objective.set_title(t("Objectif"))
        self.section_course.set_title(t("Course et profil"))
        self.section_conditions.set_title(t("Conditions statiques"))
        self.section_conditions.set_reset_text(
            t("Réinitialiser"),
            t("Remet les conditions statiques sur « Non précisé »."),
        )
        self._retranslate_rail_toggle()
        self.refresh_button.setText(t("Actualiser"))
        self.ace_label.setText(t("Ace visé"))
        self.target_label.setText(
            t("Parent à produire") + " · " + t("pour les recherches GP")
        )
        self.top_label.setText(t("Résultats"))
        self.export_button.setText(t("Exporter…"))
        self.load_button.setText(t("Historique"))
        self.load_button.setToolTip(
            t("Charge l’exécution courante ou l’unique exécution précédente conservée sur le disque.")
        )
        self.compare_button.setText(t("Comparer…"))
        self.compare_button.setToolTip(
            t("Compare côte à côte deux candidats du résultat affiché.")
        )
        self.import_button.setText(t("Reclasser JSON…"))
        self.import_button.setToolTip(
            t(
                "Reclasse une réponse JSON uma.moe déjà téléchargée avec les réglages actuels, sans appel à l’API."
            )
        )
        self.options_button.setText(t("Options…"))
        self.local_gp_pairs_button.setText(t("GP locaux"))
        self.open_button.setText(t("Sortie"))
        self.stale_badge.setText(t("Obsolète"))
        objective_description = self.section_objective.toggle.text()
        label_control(self.ace_label, self.ace_combo, objective_description)
        label_control(self.target_label, self.target_combo, objective_description)
        label_control(self.top_label, self.top_spin, objective_description)
        describe_control(
            self.refresh_button,
            self.refresh_button.text(),
            objective_description,
        )
        describe_control(
            self.results_context,
            t("Contexte"),
            self.results_context.text(),
        )
        self.families.retranslate()
        self._refresh_toolbar()
        self.section_retrieval.retranslate()
        self.section_online_parent.retranslate()
        self.section_online_gp.retranslate()
        self._refresh_online_validation()
        self.pair_results.retranslate()
        self.branch_results.retranslate()
        self.future_results.retranslate()
        self.online_parent_results.retranslate()
        self.online_gp_results.retranslate()
        self._refresh_context()
        self._refresh_source_badges()
