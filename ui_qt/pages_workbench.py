"""Collection, race evidence and planning inside the fork's native Qt shell."""
from __future__ import annotations

import json
import sqlite3
from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal, QSize
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QListWidget,
)

from uma_legacy_linker.application import LinkRequest, run_link
from uma_legacy_linker.error_guidance import actionable_error
from uma_workbench.core import DIVISIONS, STYLES, MasterData, Store, measured_roster
from uma_workbench.goals import validate_training_goal
from uma_workbench.sync import ExportWatcher, check_release, launch_umadump
from ui_qt.components import PageHeader, PathPicker, muted_label
from ui_qt.context import AppContext
from ui_qt.collection_widgets import ArtworkLabel, CollectionGallery, STAT_LABELS, character_name, describe_records, display_name
from ui_qt.training_goal_dialog import TrainingGoalDialog
from ui_qt.image_assets import ImageRepository, online_images_enabled
from ui_qt.avatar import AsyncAvatarProvider


def _table(headers, parent=None):
    table = QTableWidget(0, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.setAccessibleName(" / ".join(headers))
    table.setAccessibleDescription("Select a row; double-click to inspect its recorded data.")
    return table


def _fill(table, rows):
    table.setRowCount(len(rows))
    for index, (cells, payload) in enumerate(rows):
        for column, value in enumerate(cells):
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, payload)
            table.setItem(index, column, item)


def _selected(table):
    item = table.item(table.currentRow(), 0)
    return item.data(Qt.ItemDataRole.UserRole) if item is not None else None


class WorkbenchPage(QWidget):
    task_requested = Signal(object, str, object)
    navigate_requested = Signal(str)
    watch_result = Signal(object)

    def __init__(self, context: AppContext, parent=None, *, store=None):
        super().__init__(parent)
        self.context = context
        self.store = store or Store()
        self.master = MasterData()
        self.images = ImageRepository(enabled=online_images_enabled(context), parent=self)
        self.avatars = AsyncAvatarProvider(self.images, 48, self)
        self.avatars.changed.connect(self._update_runner_portraits)
        self.watcher = None
        self.dumper = None
        self._busy = False
        self._buttons = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.addWidget(PageHeader("Your collection and career plans",
            "Browse your umas, review their races, and decide what to train next."))
        actions = QHBoxLayout()
        self._button(actions, "Import my collection", self.import_dump)
        self._button(actions, "Find inheritance parents", self.prepare_lineage)
        actions.addStretch()
        root.addLayout(actions)
        self.notice = muted_label("")
        root.addWidget(self.notice)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._make_collection()
        self._make_trials()
        self._make_goals()
        self._make_database()
        self._make_resources()
        self._make_sync()
        self.watch_result.connect(self._import_done)
        self.context.configuration_changed.connect(self._paths_changed)
        self._paths_changed()
        self.tabs.setTabVisible(3, False)
        self.context.configuration_changed.connect(self._update_advanced_visibility)
        self._update_advanced_visibility()
        self.refresh()

    def _button(self, layout, text, action):
        button = QPushButton(text)
        button.clicked.connect(action)
        button.setAccessibleName(text)
        self._buttons.append(button)
        layout.addWidget(button)
        return button

    def _tab(self, name):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 14, 10, 10)
        self.tabs.addTab(page, name)
        return page, layout

    def _details(self, table):
        payload = _selected(table)
        if payload is None:
            return
        if table is not self.database:
            veteran = next((row for row in self.store.entities("veterans")
                if row.get("trained_chara_id") == payload.get("veteran_id")), None)
            descriptor = describe_records(self.master, "veterans", [veteran or payload])[0]
            self._view_collection(descriptor, observation=payload)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Recorded data")
        dialog.resize(820, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(json.dumps(payload, ensure_ascii=False, indent=2))
        text.setReadOnly(True)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _error(self, message):
        QMessageBox.warning(self, "Check the selected data", actionable_error(message))

    def _make_collection(self):
        _, layout = self._tab("My collection")
        layout.addWidget(muted_label("Choose a character or support card to see its stats, skills and inheritance. Search by name; portraits load as you browse."))
        row = QHBoxLayout()
        self.collection_kind = QComboBox()
        for label, code in (("Trainees", "trainees"), ("Support cards", "supports"), ("Veterans", "veterans")):
            self.collection_kind.addItem(label, code)
        self.collection_kind.setAccessibleName("Collection type")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find a character or card by name")
        self.filter.setAccessibleName("Search collection names")
        row.addWidget(self.collection_kind)
        row.addWidget(self.filter, 1)
        layout.addLayout(row)
        self.collection = CollectionGallery(self.images)
        layout.addWidget(self.collection, 1)
        self.collection.activated.connect(self._view_collection)
        self.collection_kind.currentIndexChanged.connect(self.refresh_collection)
        self.filter.textChanged.connect(self.refresh_collection)


    def refresh_collection(self, *_):
        kind = self.collection_kind.currentData()
        search = self.filter.text().casefold()
        records = describe_records(self.master, kind, self.store.entities(kind))
        self.collection.set_records([row for row in records if search in (row["name"] + " " + row["summary"]).casefold()])

    def _view_collection(self, descriptor, observation=None):
        record = descriptor["record"]
        dialog = QDialog(self)
        dialog.setWindowTitle(descriptor["name"])
        dialog.resize(860, 640)
        root = QVBoxLayout(dialog)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        overview = QWidget()
        layout = QVBoxLayout(overview)
        head = QHBoxLayout()
        head.addWidget(ArtworkLabel(self.images, descriptor["url"], descriptor["name"], size=170, support=descriptor["kind"] == "supports"))
        copy = QVBoxLayout()
        title = QLabel(descriptor["character"])
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        copy.addWidget(title)
        if descriptor["costume"]:
            copy.addWidget(muted_label(descriptor["costume"]))
        copy.addWidget(muted_label(descriptor["summary"]))
        copy.addWidget(muted_label(descriptor["badge"]))
        if descriptor["kind"] == "veterans":
            for key, label in STAT_LABELS:
                copy.addWidget(QLabel(f"{label}: {record.get(key, 'Not recorded')}"))
        if observation:
            copy.addWidget(muted_label(DIVISIONS.get(observation.get("division"), "") + " · "
                + STYLES.get(observation.get("style"), "")))
            if "mean" in observation:
                copy.addWidget(QLabel(f"{observation['mean']:,.0f} average points · {observation['races']} recorded races"))
                copy.addWidget(muted_label(f"Won {observation.get('win_rate', 0):.0%} of recorded races. More recordings improve this comparison."))
            elif "skill_id" in observation:
                copy.addWidget(QLabel(self.master.names.get((47, observation["skill_id"]), "Skill name unavailable")))
                copy.addWidget(muted_label(f"Activated in {observation['active_races']} of {observation['exposures']} recorded races with this skill ({observation['rate']:.0%})."))
        head.addLayout(copy, 1)
        layout.addLayout(head)
        skills = record.get("skill_array", record.get("skill_data_array", []))
        layout.addWidget(QLabel("Learned skills" if descriptor["kind"] == "veterans" else "Skill hints"))
        names = QListWidget()
        for skill in skills:
            identity = skill.get("skill_id")
            if identity:
                name = self.master.skill_name(identity)
                names.addItem(name if not name.startswith("Skill #") else "Skill name unavailable — finish game-data setup")
        if not skills:
            names.addItem("No skill records in this export")
        layout.addWidget(names, 1)
        if record.get("factor_info_array"):
            factors = []
            for factor in record["factor_info_array"]:
                identity = factor.get("factor_id")
                name = self.master.names.get((147, identity), "Inheritance spark")
                factors.append(f"{name} {'★' * int(factor.get('level', 0))}".strip())
            layout.addWidget(muted_label("Inheritance: " + " · ".join(factors)))
        if descriptor["kind"] == "trainees":
            button = QPushButton("Plan a career with this trainee")
            button.setObjectName("primary")
            button.clicked.connect(lambda: self._plan_trainee(dialog, record))
            layout.addWidget(button)
        elif observation:
            button = QPushButton("Plan a career to improve this runner")
            button.setObjectName("primary")
            button.clicked.connect(lambda: self._plan_trainee(dialog, record))
            layout.addWidget(button)
        overview_scroll = QScrollArea()
        overview_scroll.setWidgetResizable(True)
        overview_scroll.setWidget(overview)
        tabs.addTab(overview_scroll, "Overview")
        raw = QPlainTextEdit(json.dumps({"collection": record, "race_summary": observation} if observation else record,
            ensure_ascii=False, indent=2))
        raw.setReadOnly(True)
        tabs.addTab(raw, "Technical data")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)
        dialog.exec()

    def _plan_trainee(self, dialog, record):
        dialog.accept()
        self.new_goal({"card_id": record["card_id"], "style": 2})


    def _make_trials(self):
        _, layout = self._tab("Team Trials")
        layout.addWidget(muted_label("Compare your recorded Team Trials races. Points shown exclude bonuses. More races give a more reliable comparison. Select a runner to plan another career."))
        row = QHBoxLayout()
        self.cohort = QComboBox()
        self.cohort.setAccessibleName("Team Trials roster cohort")
        self.distinct_styles = QCheckBox("Require distinct styles in the roster shortlist")
        self.distinct_styles.setChecked(True)
        row.addWidget(self.cohort, 1)
        row.addWidget(self.distinct_styles)
        self._button(row, "Train a better version", self.goal_from_runner)
        layout.addLayout(row)
        sub = QTabWidget()
        self.tt = _table(["Runner", "Division", "Style", "Races", "Average points", "Win rate", "Win-rate range"])
        self.skills = _table(["Runner", "Skill", "Races with this skill", "Races activated", "Activation rate"])
        self.roster = _table(["Division", "Runner", "Style", "Races", "Average points", "Cautious points estimate"])
        sub.addTab(self.tt, "Observed runners")
        sub.addTab(self.skills, "Skill activations")
        sub.addTab(self.roster, "Measured roster shortlist")
        layout.addWidget(sub)
        self.tt.setIconSize(QSize(48, 48))
        self.skills.setIconSize(QSize(48, 48))
        self.roster.setIconSize(QSize(48, 48))
        self.tt.verticalHeader().setDefaultSectionSize(60)
        self.skills.verticalHeader().setDefaultSectionSize(58)
        self.roster.verticalHeader().setDefaultSectionSize(60)
        self.tt.hideColumn(6)
        self.trial_focus = muted_label("")
        layout.addWidget(self.trial_focus)
        self.roster_note = muted_label("The shortlist only considers veterans with at least three observations. It does not simulate new runners.")
        layout.addWidget(self.roster_note)
        for table in (self.tt, self.skills, self.roster):
            table.cellDoubleClicked.connect(lambda *_, target=table: self._details(target))
        self.cohort.currentIndexChanged.connect(self.refresh_trials)
        self.distinct_styles.toggled.connect(self.refresh_trials)

    def refresh_trials(self, *_):
        cohort = self.cohort.currentData()
        metrics = self.store.metrics(cohort) if cohort else []
        _fill(self.tt, [([character_name(self.master, "veterans", r["card_id"]), DIVISIONS.get(r["division"], "Unknown"),
            STYLES.get(r["style"], "Unknown"), r["races"], f"{r['mean']:,.0f}", f"{r['win_rate']:.1%}",
            f"{r['win_lo']:.1%}–{r['win_hi']:.1%}"], r) for r in metrics])
        _fill(self.skills, [([character_name(self.master, "veterans", r["card_id"]), self.master.names.get((47, r["skill_id"]), "Skill name unavailable"),
            r["exposures"], r["active_races"], f"{r['rate']:.1%}"], r) for r in self.store.skill_metrics(cohort) if cohort])
        result = measured_roster(self.store, self.master, distinct_styles=self.distinct_styles.isChecked())
        _fill(self.roster, [([DIVISIONS[r["division"]], character_name(self.master, "veterans", r["card_id"]),
            STYLES.get(r["style"], "Unknown"), r["races"], f"{r['mean']:,.0f}", f"{r['lower_score']:,.0f}"], r)
            for r in result["selected"]])
        vacancies = ", ".join(f"{DIVISIONS[key]}: {value}" for key, value in result["vacancies"].items() if value)
        if metrics:
            focus = min(metrics, key=lambda item: item["mean"])
            name = character_name(self.master, "veterans", focus["card_id"])
            self.trial_focus.setText(f"Lowest recorded average: {name} in {DIVISIONS.get(focus['division'], 'this division')} — {focus['mean']:,.0f} points over {focus['races']} races. Select a runner, then choose ‘Train a better version’. This is a comparison of recorded results.")
        else:
            self.trial_focus.setText("No Team Trials races yet. Record a few races with umadump, then import the exports or enable live updates in Setup.")
        self._update_runner_portraits()
        self.roster_note.setText(f"{len(result['selected'])}/15 slots supported across all recorded cohorts. "
            + (f"Unfilled: {vacancies}. " if vacancies else "")
            + "This suggested roster uses veterans seen in at least three races. Empty places need more race recordings; it does not predict new runners or team interactions.")

    def _make_goals(self):
        _, layout = self._tab("Career plans")
        layout.addWidget(muted_label("A career plan records who to train, which parents and supports to use, and when the result is good enough. Start by choosing a trainee."))
        row = QHBoxLayout()
        self._button(row, "Plan a career", self.new_goal)
        for label, status in (("Start selected", "In progress"), ("Mark complete", "Complete"), ("Abandon", "Abandoned")):
            self._button(row, label, lambda _checked=False, target=status: self.change_goal(target))
        row.addStretch()
        layout.addLayout(row)
        self.goals = _table(["Internal key", "Career plan", "Purpose", "Progress", "Finish these plans first", "When to stop"])
        layout.addWidget(self.goals)
        self.goals.cellDoubleClicked.connect(lambda *_: self._view_goal())
        self.goals.hideColumn(0)
        self.careers = muted_label("")
        layout.addWidget(self.careers)

    def goal_from_runner(self):
        runner = _selected(self.tt)
        if runner:
            self.new_goal(runner)

    def new_goal(self, runner=None):
        if isinstance(runner, bool):
            runner = None
        if not self.master.path:
            self.tabs.setCurrentWidget(self.sync_tab)
            self._error("Finish setup by choosing the game's data file. It lets the app show character, card and skill names.")
            return
        dialog = TrainingGoalDialog(self.store, self.master, self.images, runner, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.tabs.setCurrentIndex(2)


    def change_goal(self, status):
        goal = _selected(self.goals)
        if goal:
            try:
                self.store.change_goal_status(goal["id"], status)
                self.refresh()
            except ValueError as exc:
                self._error(exc)

    def _make_database(self):
        _, layout = self._tab("Advanced game data")
        row = QHBoxLayout()
        self.database_kind = QComboBox()
        self.database_kind.addItems(MasterData.TABLES)
        self.database_query = QLineEdit()
        self.database_query.setPlaceholderText("Name, ID or raw field")
        self.database_kind.setAccessibleName("Game database table")
        self.database_query.setAccessibleName("Search game database")
        row.addWidget(self.database_kind)
        row.addWidget(self.database_query, 1)
        self._button(row, "Search", self.refresh_database)
        layout.addLayout(row)
        self.database = _table(["ID", "Name", "Technical summary"])
        layout.addWidget(self.database)
        layout.addWidget(muted_label("Effects and conditions use raw client fields from your selected MDB. Double-click a row for all fields."))
        self.database_kind.currentIndexChanged.connect(self.refresh_database)
        self.database_query.returnPressed.connect(self.refresh_database)
        self.database.cellDoubleClicked.connect(lambda *_: self._details(self.database))

    def refresh_database(self, *_):
        if not self.master.path:
            _fill(self.database, [])
            return
        try:
            _fill(self.database, [([row.get("id", row.get("factor_id", "")), row["name"],
                json.dumps({key: val for key, val in row.items() if key != "name"}, ensure_ascii=False)[:220]], row)
                for row in self.master.browse(self.database_kind.currentText(), self.database_query.text())])
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._error(exc)

    def _make_resources(self):
        _, layout = self._tab("Resources")
        layout.addWidget(muted_label("Enter balances and verified earning rates manually; the current dump does not provide shop inventories or currency balances."))
        links = QHBoxLayout()
        for label, url in (("Grand Concert calculator", "https://uma.guide/grand-live-calculator/"),
            ("GameTora", "https://gametora.com/umamusume"), ("Bestderby", "https://uma-bestderby.com/")):
            self._button(links, label, lambda _checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
        links.addStretch()
        layout.addLayout(links)
        row = QHBoxLayout()
        self._button(row, "Add milestone", self.new_resource)
        self._button(row, "Remove selected milestone", self.remove_resource)
        row.addStretch()
        layout.addLayout(row)
        self.resources = _table(["Resource", "Balance", "Target", "Missing", "Per run", "Runs needed"])
        layout.addWidget(self.resources)

    def new_resource(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Resource milestone")
        layout = QFormLayout(dialog)
        fields = {}
        for name, initial in (("Resource", ""), ("Balance", "0"), ("Target", "0"), ("Per run (0 = unknown)", "0")):
            field = QLineEdit(initial)
            field.setAccessibleName(name)
            layout.addRow(name, field)
            fields[name] = field
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def save():
            try:
                self.store.save_resource(fields["Resource"].text(), float(fields["Balance"].text()),
                    float(fields["Target"].text()), float(fields["Per run (0 = unknown)"].text()))
                self.refresh()
                dialog.accept()
            except ValueError as exc:
                self._error(exc)
        buttons.accepted.connect(save)
        dialog.exec()

    def remove_resource(self):
        resource = _selected(self.resources)
        if resource:
            self.store.remove_resource(resource["id"])
            self.refresh()

    def _make_sync(self):
        self.sync_tab, layout = self._tab("Setup")
        layout.addWidget(muted_label("First choose your game's master.mdb file to load character, support and skill names. Then use ‘Import my collection’ above to add your umadump ZIP or JSON exports."))
        form = QFormLayout()
        self.master_picker = PathPicker(mode="file", file_filter="Game database (*.mdb);;All files (*)")
        self.output_picker = PathPicker(mode="directory")
        self.umadump_picker = PathPicker(mode="file", file_filter="Windows executable (*.exe)")
        for name, field in (("Game data file (loads names)", self.master_picker), ("Folder where umadump saves exports", self.output_picker),
            ("Your umadump program", self.umadump_picker)):
            field.edit.setAccessibleName(name)
            field.set_button_text("Browse…")
            form.addRow(name, field)
        self.output_picker.set_text(str(self.store.setting("export_folder", self.store.setting("watch_folder", ""))))
        self.umadump_picker.set_text(str(self.store.setting("umadump_path", "")))
        layout.addLayout(form)
        actions = QHBoxLayout()
        self._button(actions, "Save setup", self.save_paths)
        self.monitor_button = self._button(actions, "Start live updates", self.toggle_monitor)
        actions.addStretch()
        layout.addLayout(actions)
        extra = QHBoxLayout()
        self._button(extra, "Open umadump", self.launch_daemon)
        self._button(extra, "Check for umadump updates", self.check_upstream)
        extra.addStretch()
        layout.addLayout(extra)
        self.sync_note = muted_label("Live updates watch the export folder for new collection and race recordings. Open umadump starts your existing copy in a separate window.")
        layout.addWidget(self.sync_note)
        self.artwork_toggle = QCheckBox("Show character portraits and support artwork")
        self.artwork_toggle.setChecked(online_images_enabled(self.context))
        self.artwork_toggle.toggled.connect(self._artwork_changed)
        layout.addWidget(self.artwork_toggle)
        layout.addWidget(muted_label("Pictures load from GameTora, with Hakuraku as a backup, and are kept for offline browsing. Game data and collection exports stay on your computer."))
        layout.addStretch()

    def _paths_changed(self):
        enabled = online_images_enabled(self.context)
        self.images.set_enabled(enabled)
        self.artwork_toggle.blockSignals(True)
        self.artwork_toggle.setChecked(enabled)
        self.artwork_toggle.blockSignals(False)
        path = self.context.master_path or self.store.setting("master_path", "")
        self.master_picker.set_text(str(path))
        if path and (not self.master.path or str(self.master.path) != str(Path(path).expanduser().resolve())):
            try:
                self.master.load(path)
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.notice.setText(str(exc))
        self.refresh()

    def save_paths(self):
        try:
            path = self.master_picker.text()
            if path:
                self.master.load(path)
            self.store.set_setting("master_path", path)
            self.store.set_setting("export_folder", self.output_picker.text())
            self.store.set_setting("umadump_path", self.umadump_picker.text())
            self.context.update_paths(master_path=path)
            self.refresh()
            self.sync_note.setText("Setup saved. Character, card and skill names are ready." if self.master.path else "Choose the game data file to load names.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._error(exc)

    def import_dump(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import umadump exports", "", "Dump or collection (*.zip *.json);;All files (*)")
        if paths:
            self.import_paths(paths)

    def import_paths(self, paths):
        def operation(logger=None, progress=None, checkpoint=None):
            result = {"imported": 0, "unchanged": 0, "ignored": 0, "errors": [], "warnings": []}
            for path in paths:
                if checkpoint:
                    checkpoint()
                current = self.store.import_path(path)
                for key in ("imported", "unchanged", "ignored"):
                    result[key] += current[key]
                for key in ("errors", "warnings"):
                    result[key].extend(current[key])
            return result
        self.task_requested.emit(operation, "Importing exported collection and race data…", self._import_done)

    def _import_done(self, result):
        self.refresh()
        errors, warnings = result.get("errors", []), result.get("warnings", [])
        message = f"{result.get('imported', 0)} imported · {result.get('unchanged', 0)} unchanged"
        if errors or warnings:
            message += "\n" + "\n".join(errors + warnings)
        self.sync_note.setText(message)
        self.notice.setText(self.notice.text() + " · " + message.splitlines()[0])

    def toggle_monitor(self):
        if self.watcher:
            self.shutdown()
            self.monitor_button.setText("Start live updates")
            self.sync_note.setText("Live updates stopped")
            return
        try:
            if not self.output_picker.text():
                raise ValueError("Select an umadump output folder")
            self.watcher = ExportWatcher(self.store, self.output_picker.text(), self.watch_result.emit)
            self.watcher.start()
            self.monitor_button.setText("Stop live updates")
            self.sync_note.setText("Live updates are on. New exports will appear here automatically.")
        except (ValueError, OSError) as exc:
            self.watcher = None
            self._error(exc)

    def launch_daemon(self):
        try:
            if self.dumper is not None and self.dumper.poll() is None:
                self.sync_note.setText("The upstream daemon launched by this app is already running")
                return
            if not self.output_picker.text():
                raise ValueError("Select an umadump output folder")
            self.dumper = launch_umadump(self.umadump_picker.text(), self.output_picker.text())
            if self.watcher is None:
                self.toggle_monitor()
            self.sync_note.setText("umadump is open in a separate window. Close that window when you finish recording.")
        except (ValueError, OSError) as exc:
            self._error(exc)

    def check_upstream(self):
        path = self.umadump_picker.text()
        def operation(logger=None, progress=None):
            return check_release(path or None)
        def complete(result):
            match = result["matches_latest"]
            integrity = "Executable matches the latest upstream hash." if match else (
                "Executable differs from the latest upstream hash." if match is False else "No hash comparison is available.")
            self.sync_note.setText(f"Latest upstream release: {result['tag']}. {integrity} Update from {result['page']}.")
        self.task_requested.emit(operation, "Checking the upstream umadump release…", complete)

    def prepare_lineage(self):
        try:
            if not self.master.path:
                raise ValueError("Select master.mdb first")
            export = self.store.lineage_export()
            self.context.update_paths(master_path=str(self.master.path), veterans_json_path=str(export))
            request = LinkRequest(self.master.path, export, Path(self.context.output_dir).expanduser())
            self.task_requested.emit(partial(run_link, request), "Linking the imported collection for inheritance…", self._lineage_done)
        except (ValueError, OSError) as exc:
            self._error(exc)

    def _lineage_done(self, _result):
        self.context.configuration_changed.emit()
        self.navigate_requested.emit("search")

    def refresh(self):
        counts = self.store.counts()
        self.notice.setText(f"{counts.get('trainees', 0)} trainees · {counts.get('supports', 0)} supports · "
            f"{counts.get('veterans', 0)} veterans · {counts.get('races', 0)} Team Trials races"
            + (" · Choose the game data file in Setup to load names." if not self.master.path else ""))
        self.refresh_collection()
        current = self.cohort.currentData()
        self.cohort.blockSignals(True)
        self.cohort.clear()
        for index, cohort in enumerate(self.store.cohorts(), 1):
            self.cohort.addItem(f"Team {index} · {cohort['captures']} race recordings", cohort["cohort"])
        if current:
            self.cohort.setCurrentIndex(max(0, self.cohort.findData(current)))
        self.cohort.blockSignals(False)
        self.refresh_trials()
        _fill(self.goals, [([goal["id"], goal["title"], {"TT": "Team Trials", "CM": "Champion Meeting", "Parent": "Parent", "Grandparent": "Grandparent"}.get(goal["details"].get("role"), "Career"), goal["status"],
            ", ".join(next((other["title"] for other in self.store.goals() if other["id"] == identity), "Previous plan") for identity in goal["details"].get("prerequisites", [])), goal["details"].get("stop_condition", "")], goal)
            for goal in self.store.goals()])
        _fill(self.resources, [([row["name"], row["balance"], row["target"], row["missing"], row["income"],
            row["runs"] if row["runs"] is not None else "Unknown"], row) for row in self.store.resources()])
        career_count = sum(career["snapshots"] for career in self.store.career_summary())
        self.careers.setText(f"{career_count} career observations retained. Inspect completed careers and mark goals complete manually.")
        self.refresh_database()

    def _artwork_changed(self, enabled):
        self.context.store.update({"online_images": "1" if enabled else "0"})
        self.context.configuration_changed.emit()

    def _update_runner_portraits(self):
        for table in (getattr(self, "tt", None), getattr(self, "skills", None), getattr(self, "roster", None)):
            if table is None:
                continue
            column = 1 if table is getattr(self, "roster", None) else 0
            for index in range(table.rowCount()):
                item = table.item(index, column)
                if item is None:
                    continue
                record = item.data(Qt.ItemDataRole.UserRole)
                item.setToolTip(display_name(self.master, "veterans", record.get("card_id")))
                portrait = self.avatars.avatar(record.get("card_id"))
                if portrait is not None:
                    item.setIcon(QIcon(portrait))

    def _view_goal(self):
        goal = _selected(self.goals)
        if not goal:
            return
        details = goal["details"]
        dialog = QDialog(self)
        dialog.setWindowTitle(goal["title"])
        dialog.resize(740, 610)
        root = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel(goal["title"]))
        layout.addWidget(muted_label(goal["status"] + " · " + details.get("scenario", "")))
        trainee = describe_records(self.master, "trainees", [{"card_id": details["card_id"]}])[0]
        layout.addWidget(ArtworkLabel(self.images, trainee["url"], trainee["name"], size=100))
        layout.addWidget(QLabel(trainee["name"]))
        supports = [display_name(self.master, "supports", identity) for identity in details.get("deck_ids", [])]
        layout.addWidget(muted_label("Support deck: " + (" · ".join(supports) or "Not chosen yet")))
        veteran_map = {int(row["trained_chara_id"]): row for row in self.store.entities("veterans")}
        parents = [display_name(self.master, "veterans", veteran_map[identity]["card_id"]) for identity in details.get("parent_ids", []) if identity in veteran_map]
        layout.addWidget(muted_label("Parents: " + (" · ".join(parents) or "Not chosen yet")))
        targets = [f"{label}: {details.get('stats', {}).get(key)}" for key, label in STAT_LABELS if details.get("stats", {}).get(key)]
        layout.addWidget(muted_label("Stat targets: " + (" · ".join(targets) or "None set")))
        skills = [self.master.names.get((47, identity), "Skill name unavailable") for identity in details.get("skill_ids", [])]
        layout.addWidget(muted_label("Required skills: " + (" · ".join(skills) or "None set")))
        layout.addWidget(muted_label("When to stop: " + details.get("stop_condition", "")))
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)
        dialog.exec()

    def _update_advanced_visibility(self):
        self.tabs.setTabVisible(3, self.context.store.get("advanced_tools", "0") == "1")

    def set_busy(self, busy):
        self._busy = busy
        for button in self._buttons:
            button.setEnabled(not busy)

    def shutdown(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
