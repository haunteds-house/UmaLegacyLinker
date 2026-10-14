"""Collection, race evidence and planning inside the fork's native Qt shell."""
from __future__ import annotations

import json
import sqlite3
from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from uma_legacy_linker.application import LinkRequest, run_link
from uma_legacy_linker.error_guidance import actionable_error
from uma_workbench.core import DIVISIONS, STYLES, MasterData, Store, measured_roster
from uma_workbench.goals import validate_training_goal
from uma_workbench.sync import ExportWatcher, check_release, launch_umadump
from ui_qt.components import PageHeader, PathPicker, muted_label
from ui_qt.context import AppContext


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
        self.watcher = None
        self.dumper = None
        self._busy = False
        self._buttons = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.addWidget(PageHeader("Collection and training workbench",
            "Use exported collection and race evidence, then compare inheritance in Lineage Search."))
        actions = QHBoxLayout()
        self._button(actions, "Import dump or JSON", self.import_dump)
        self._button(actions, "Use collection for lineage search", self.prepare_lineage)
        actions.addStretch()
        root.addLayout(actions)
        self.notice = muted_label("Import a dump and select master.mdb to resolve names.")
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
        _, layout = self._tab("Collection")
        row = QHBoxLayout()
        self.collection_kind = QComboBox()
        for label, code in (("Trainees", "trainees"), ("Support cards", "supports"), ("Veterans", "veterans")):
            self.collection_kind.addItem(label, code)
        self.collection_kind.setAccessibleName("Collection type")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name or ID")
        self.filter.setAccessibleName("Filter collection")
        row.addWidget(self.collection_kind)
        row.addWidget(self.filter, 1)
        layout.addLayout(row)
        self.collection = _table(["ID", "Name", "Level / stats", "Skills / factors"])
        layout.addWidget(self.collection)
        self.collection_kind.currentIndexChanged.connect(self.refresh_collection)
        self.filter.textChanged.connect(self.refresh_collection)
        self.collection.cellDoubleClicked.connect(lambda *_: self._details(self.collection))

    def refresh_collection(self, *_):
        kind = self.collection_kind.currentData()
        search = self.filter.text().casefold()
        rows = []
        for item in self.store.entities(kind):
            if kind == "supports":
                identity = item["support_card_id"]
                name = self.master.support_name(identity)
                level = self.master.support_level(item)
                progress = f"Level {level}" if level is not None else f"Exp {item.get('exp', 'unknown')}"
                summary = f"{progress} · {item.get('limit_break_count', 0)} limit breaks"
                detail = ""
            elif kind == "trainees":
                identity = item["card_id"]
                name = self.master.card_name(identity)
                summary = f"Rarity {item.get('rarity', 'unknown')}★ · Awakening {item.get('talent_level', 'unknown')}"
                detail = f"{len(item.get('skill_data_array', []))} skill hint records"
            else:
                identity = item["trained_chara_id"]
                name = self.master.card_name(item["card_id"])
                summary = " / ".join(str(item.get(stat, 0)) for stat in ("speed", "stamina", "power", "guts", "wiz"))
                detail = f"{len(item.get('skill_array', []))} skills · {len(item.get('factor_info_array', []))} factors"
            if search in f"{identity} {name}".casefold():
                rows.append(([identity, name, summary, detail], item))
        _fill(self.collection, rows)

    def _make_trials(self):
        _, layout = self._tab("Team Trials")
        layout.addWidget(muted_label("Measured base points exclude recorded bonuses. Cohorts separate roster, division and style changes."))
        row = QHBoxLayout()
        self.cohort = QComboBox()
        self.cohort.setAccessibleName("Team Trials roster cohort")
        self.distinct_styles = QCheckBox("Require distinct styles in the roster shortlist")
        self.distinct_styles.setChecked(True)
        row.addWidget(self.cohort, 1)
        row.addWidget(self.distinct_styles)
        self._button(row, "Create goal for selected runner", self.goal_from_runner)
        layout.addLayout(row)
        sub = QTabWidget()
        self.tt = _table(["Runner", "Division", "Style", "Races", "Mean base pts", "Win rate", "95% win interval"])
        self.skills = _table(["Runner", "Skill", "Eligible records", "Active records", "Activation rate"])
        self.roster = _table(["Division", "Runner", "Style", "Races", "Mean base pts", "Approx. lower score bound"])
        sub.addTab(self.tt, "Observed runners")
        sub.addTab(self.skills, "Skill activations")
        sub.addTab(self.roster, "Measured roster shortlist")
        layout.addWidget(sub)
        self.roster_note = muted_label("The shortlist only considers veterans with at least three observations. It does not simulate new runners.")
        layout.addWidget(self.roster_note)
        for table in (self.tt, self.skills, self.roster):
            table.cellDoubleClicked.connect(lambda *_, target=table: self._details(target))
        self.cohort.currentIndexChanged.connect(self.refresh_trials)
        self.distinct_styles.toggled.connect(self.refresh_trials)

    def refresh_trials(self, *_):
        cohort = self.cohort.currentData()
        metrics = self.store.metrics(cohort) if cohort else []
        _fill(self.tt, [([self.master.card_name(r["card_id"]), DIVISIONS.get(r["division"], "Unknown"),
            STYLES.get(r["style"], "Unknown"), r["races"], f"{r['mean']:,.0f}", f"{r['win_rate']:.1%}",
            f"{r['win_lo']:.1%}–{r['win_hi']:.1%}"], r) for r in metrics])
        _fill(self.skills, [([self.master.card_name(r["card_id"]), self.master.skill_name(r["skill_id"]),
            r["exposures"], r["active_races"], f"{r['rate']:.1%}"], r) for r in self.store.skill_metrics(cohort) if cohort])
        result = measured_roster(self.store, self.master, distinct_styles=self.distinct_styles.isChecked())
        _fill(self.roster, [([DIVISIONS[r["division"]], self.master.card_name(r["card_id"]),
            STYLES.get(r["style"], "Unknown"), r["races"], f"{r['mean']:,.0f}", f"{r['lower_score']:,.0f}"], r)
            for r in result["selected"]])
        vacancies = ", ".join(f"{DIVISIONS[key]}: {value}" for key, value in result["vacancies"].items() if value)
        self.roster_note.setText(f"{len(result['selected'])}/15 slots supported across all recorded cohorts. "
            + (f"Unfilled: {vacancies}. " if vacancies else "")
            + "The shortlist uses current veterans with three or more observations. Historical comparisons are approximate; teammate interactions are not simulated.")

    def _make_goals(self):
        _, layout = self._tab("Training goals")
        layout.addWidget(muted_label("Record TT, CM, parent and grandparent targets. Prerequisites must be complete before the next career starts."))
        row = QHBoxLayout()
        self._button(row, "New training goal", self.new_goal)
        for label, status in (("Start selected", "In progress"), ("Mark complete", "Complete"), ("Abandon", "Abandoned")):
            self._button(row, label, lambda _checked=False, target=status: self.change_goal(target))
        row.addStretch()
        layout.addLayout(row)
        self.goals = _table(["ID", "Goal", "Role", "Status", "Prerequisites", "Stop condition"])
        layout.addWidget(self.goals)
        self.goals.cellDoubleClicked.connect(lambda *_: self._details(self.goals))
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
            self._error("Select master.mdb before planning a training deck and parents")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("New training goal")
        dialog.resize(740, 720)
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        fields = {}
        defaults = {
            "Title": f"Improve {self.master.card_name(runner['card_id'])}" if runner else "",
            "Role": "TT", "Trainee card ID": str(runner["card_id"]) if runner else "",
            "Scenario": "URA", "Surface": "Turf", "Distance (m)": "",
            "Running style": STYLES.get(runner["style"], "Pace Chaser") if runner else "Pace Chaser",
            "Stats: Spd/Sta/Pow/Guts/Wit": "", "Required skill IDs": "", "Parent veteran IDs": "",
            "Support IDs (up to 6)": "", "Prerequisite goal IDs": "", "Maximum attempts": "10", "Stop condition": "",
        }
        choices = {"Role": ("TT", "CM", "Parent", "Grandparent"), "Surface": ("Turf", "Dirt"),
            "Running style": tuple(STYLES.values()), "Scenario": ("URA", "Unity Cup", "Trackblazer", "Our Grand Concert")}
        for name, value in defaults.items():
            if name in choices:
                field = QComboBox()
                field.addItems(choices[name])
                field.setCurrentText(value)
            else:
                field = QLineEdit(value)
            field.setAccessibleName(name)
            form.addRow(name, field)
            fields[name] = field
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        def value(name):
            field = fields[name]
            return field.currentText() if isinstance(field, QComboBox) else field.text().strip()
        def ids(name):
            return [int(part.strip()) for part in value(name).split(",") if part.strip()]
        def save():
            try:
                stats = [int(part) for part in value("Stats: Spd/Sta/Pow/Guts/Wit").split("/")] if value("Stats: Spd/Sta/Pow/Guts/Wit") else []
                if stats and len(stats) != 5:
                    raise ValueError("Use five stat targets separated by /, or leave them blank")
                payload = {"role": value("Role"), "card_id": int(value("Trainee card ID")), "scenario": value("Scenario"),
                    "surface": value("Surface"), "style": value("Running style"),
                    "distance": int(value("Distance (m)")) if value("Distance (m)") else None,
                    "stats": dict(zip(("speed", "stamina", "power", "guts", "wiz"), stats)),
                    "skill_ids": ids("Required skill IDs"), "parent_ids": ids("Parent veteran IDs"),
                    "deck_ids": ids("Support IDs (up to 6)"), "prerequisites": ids("Prerequisite goal IDs"),
                    "max_attempts": int(value("Maximum attempts")), "stop_condition": value("Stop condition")}
                validate_training_goal(payload, self.store, self.master)
                self.store.save_goal(value("Title"), payload)
                self.refresh()
                dialog.accept()
            except (ValueError, KeyError) as exc:
                self._error(exc)
        buttons.accepted.connect(save)
        dialog.exec()

    def change_goal(self, status):
        goal = _selected(self.goals)
        if goal:
            try:
                self.store.change_goal_status(goal["id"], status)
                self.refresh()
            except ValueError as exc:
                self._error(exc)

    def _make_database(self):
        _, layout = self._tab("Game database")
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
        self.sync_tab, layout = self._tab("Sync")
        form = QFormLayout()
        self.master_picker = PathPicker(mode="file", file_filter="Game database (*.mdb);;All files (*)")
        self.output_picker = PathPicker(mode="directory")
        self.umadump_picker = PathPicker(mode="file", file_filter="Windows executable (*.exe)")
        for name, field in (("Game master.mdb", self.master_picker), ("umadump output folder", self.output_picker),
            ("Upstream umadump.exe", self.umadump_picker)):
            field.edit.setAccessibleName(name)
            field.set_button_text("Browse…")
            form.addRow(name, field)
        self.output_picker.set_text(str(self.store.setting("export_folder", self.store.setting("watch_folder", ""))))
        self.umadump_picker.set_text(str(self.store.setting("umadump_path", "")))
        layout.addLayout(form)
        actions = QHBoxLayout()
        self._button(actions, "Save paths / reload MDB", self.save_paths)
        self.monitor_button = self._button(actions, "Start file monitoring", self.toggle_monitor)
        self._button(actions, "Launch upstream daemon", self.launch_daemon)
        self._button(actions, "Check upstream release", self.check_upstream)
        actions.addStretch()
        layout.addLayout(actions)
        self.sync_note = muted_label("File monitoring reads exported JSON only. An optional launch uses your separate, unmodified upstream umadump release.")
        layout.addWidget(self.sync_note)
        layout.addWidget(muted_label(f"Private workbench data: {self.store.path}"))
        layout.addStretch()

    def _paths_changed(self):
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
            self.sync_note.setText("Paths saved. MDB fingerprint: " + (self.master.sha256 or "not selected"))
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
            self.monitor_button.setText("Start file monitoring")
            self.sync_note.setText("File monitoring stopped")
            return
        try:
            if not self.output_picker.text():
                raise ValueError("Select an umadump output folder")
            self.watcher = ExportWatcher(self.store, self.output_picker.text(), self.watch_result.emit)
            self.watcher.start()
            self.monitor_button.setText("Stop file monitoring")
            self.sync_note.setText("Watching exported JSON for completed file writes")
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
            self.sync_note.setText("Upstream daemon launched in a separate console. Stop it in that console when finished.")
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
            f"{counts.get('veterans', 0)} veterans · {counts.get('races', 0)} TT races")
        self.refresh_collection()
        current = self.cohort.currentData()
        self.cohort.blockSignals(True)
        self.cohort.clear()
        for index, cohort in enumerate(self.store.cohorts(), 1):
            self.cohort.addItem(f"Roster {index} · {str(cohort['cohort'])[:10]} · {cohort['captures']} captures", cohort["cohort"])
        if current:
            self.cohort.setCurrentIndex(max(0, self.cohort.findData(current)))
        self.cohort.blockSignals(False)
        self.refresh_trials()
        _fill(self.goals, [([goal["id"], goal["title"], goal["details"].get("role", ""), goal["status"],
            ", ".join(map(str, goal["details"].get("prerequisites", []))), goal["details"].get("stop_condition", "")], goal)
            for goal in self.store.goals()])
        _fill(self.resources, [([row["name"], row["balance"], row["target"], row["missing"], row["income"],
            row["runs"] if row["runs"] is not None else "Unknown"], row) for row in self.store.resources()])
        career_count = sum(career["snapshots"] for career in self.store.career_summary())
        self.careers.setText(f"{career_count} career observations retained. Inspect completed careers and mark goals complete manually.")
        self.refresh_database()

    def set_busy(self, busy):
        self._busy = busy
        for button in self._buttons:
            button.setEnabled(not busy)

    def shutdown(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
