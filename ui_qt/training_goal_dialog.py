"""A career plan made from named collection choices."""
from __future__ import annotations

from functools import partial
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QScrollArea,
    QHBoxLayout, QGridLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget, QProgressBar, QPushButton,
)

from ui_qt.collection_widgets import NamedChoice, STAT_LABELS, describe_records
from ui_qt.components import muted_label
from uma_workbench.goals import validate_training_goal
from uma_workbench.planning import APTITUDES, GRADE_LABELS, catalog_for, find_setups
from ui_qt.setup_results import SetupResults
from ui_qt.training_preview import TrainingOptions
from ui_qt.workers import FunctionWorker


class TrainingGoalDialog(QDialog):
    def __init__(self, store, master, repository, runner=None, parent=None, *, goal=None):
        super().__init__(parent)
        self.store, self.master, self.repository = store, master, repository
        self.existing_goal = goal
        self._search_worker = None
        self._search_requirements = None
        self._selected_setup = None
        self.setWindowTitle("Plan a career")
        self.resize(990, 680)
        root = QVBoxLayout(self)
        heading = QLabel("What does your next runner need?")
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        root.addWidget(muted_label("Set skills and aptitudes, then search your collection. Leave the trainee empty to compare different characters; chosen parents and supports stay fixed during search."))
        tabs = self.tabs = QTabWidget()
        root.addWidget(tabs, 1)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Optional name for this plan")
        self.role = QComboBox()
        for label, code in (("Team Trials runner", "TT"), ("Champion Meeting runner", "CM"),
            ("Inheritance parent", "Parent"), ("Inheritance grandparent", "Grandparent")):
            self.role.addItem(label, code)
        self.trainee = NamedChoice("Fix a trainee (optional)", describe_records(master, "trainees", store.entities("trainees")), repository)
        if runner and runner.get("lock_trainee", True):
            match = next((row for row in self.trainee.records if row["record"]["card_id"] == runner["card_id"]), None)
            self.trainee.set_choice(match)
        self.scenario = QComboBox()
        self.scenario.addItems(("URA", "Unity Cup", "Trackblazer", "Our Grand Concert"))
        self.surface = QComboBox()
        self.surface.addItems(("Any surface", "Turf", "Dirt"))
        self.surface.setCurrentText("Turf")
        self.distance_type = QComboBox()
        self.distance_type.addItems(("Any distance", "Sprint", "Mile", "Medium", "Long"))
        self.style = QComboBox()
        self.style.addItems(("Any style", "Front Runner", "Pace Chaser", "Late Surger", "End Closer"))
        if runner:
            self.style.setCurrentIndex(max(0, min(4, int(runner.get("style", 0)))))
            division = int(runner.get("division", 0))
            if 1 <= division <= 4:
                self.distance_type.setCurrentIndex(division)
            elif division == 5:
                self.surface.setCurrentText("Dirt")
        self.minimum_aptitude = QComboBox()
        for rank in range(1, 9):
            self.minimum_aptitude.addItem(GRADE_LABELS[rank], rank)
        self.minimum_aptitude.setCurrentIndex(6)
        self.distance = QSpinBox()
        self.distance.setRange(0, 5000)
        self.distance.setSingleStep(100)
        self.distance.setSpecialValueText("Any distance")
        self.distance.setSuffix(" m")
        target = QWidget()
        form = QFormLayout(target)
        form.setSpacing(14)
        for label, widget in (("Plan name", self.title), ("Use this runner for", self.role), ("Fixed trainee (optional)", self.trainee),
            ("Career scenario", self.scenario), ("Surface", self.surface), ("Distance group", self.distance_type),
            ("Exact distance (optional)", self.distance), ("Running style", self.style),
            ("Minimum aptitude for these choices", self.minimum_aptitude)):
            widget.setAccessibleName(label)
            form.addRow(label, widget)
        target_scroll = QScrollArea()
        target_scroll.setWidgetResizable(True)
        target_scroll.setWidget(target)
        tabs.addTab(target_scroll, "1 · Requirements")

        lineup = QWidget()
        lineup_layout = QVBoxLayout(lineup)
        lineup_layout.addWidget(muted_label("Choose up to two parents and six supports. One support may be borrowed. Cards from the trainee's character cannot be used in the deck."))
        veteran_rows = describe_records(master, "veterans", store.entities("veterans"))
        self.parents = [NamedChoice(f"Choose parent {index + 1}", veteran_rows, repository) for index in range(2)]
        form = QFormLayout()
        for index, picker in enumerate(self.parents):
            form.addRow(f"Parent {index + 1}", picker)
        lineup_layout.addLayout(form)
        owned = store.entities("supports")
        supports = describe_records(master, "supports", owned)
        owned_ids = {row["support_card_id"] for row in owned}
        borrowed = describe_records(master, "supports", [{"support_card_id": identity} for identity in master.supports if identity not in owned_ids], borrowed=True)
        self.borrowed_toggle = QCheckBox("Include cards I could borrow in the support picker")
        lineup_layout.addWidget(self.borrowed_toggle)
        self.deck = [NamedChoice(f"Choose support {index + 1}", supports, repository) for index in range(6)]
        deck_layout = QFormLayout()
        for index, picker in enumerate(self.deck):
            deck_layout.addRow(f"Support {index + 1}", picker)
        lineup_layout.addLayout(deck_layout)
        lineup_layout.addStretch()
        self.borrowed_toggle.toggled.connect(lambda on: [setattr(picker, "records", supports + borrowed if on else supports) for picker in self.deck])
        lineup_scroll = QScrollArea()
        lineup_scroll.setWidgetResizable(True)
        lineup_scroll.setWidget(lineup)
        tabs.addTab(lineup_scroll, "2 · Parents and supports")

        targets = QWidget()
        targets_layout = QVBoxLayout(targets)
        targets_layout.addWidget(muted_label("Optional individual aptitude targets override the minimum on the first tab. S needs an in-career inheritance roll."))
        aptitudes = QGridLayout()
        self.aptitudes = {}
        for index, (key, label, _group) in enumerate(APTITUDES):
            combo = QComboBox()
            for rank in range(9):
                combo.addItem(GRADE_LABELS[rank], rank)
            combo.setAccessibleName(label + " aptitude target")
            aptitudes.addWidget(QLabel(label), (index // 5) * 2, index % 5)
            aptitudes.addWidget(combo, (index // 5) * 2 + 1, index % 5)
            self.aptitudes[key] = combo
        targets_layout.addLayout(aptitudes)
        targets_layout.addWidget(muted_label("Optional stat targets. “Any” means you have not set a target for that stat."))
        stats_layout = QHBoxLayout()
        self.stats = {}
        for key, label in STAT_LABELS:
            box = QWidget()
            column = QVBoxLayout(box)
            column.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(0, 20000)
            spin.setSingleStep(50)
            spin.setSpecialValueText("Any")
            spin.setAccessibleName(label + " target")
            column.addWidget(spin)
            self.stats[key] = spin
            stats_layout.addWidget(box)
        targets_layout.addLayout(stats_layout)
        targets_layout.addWidget(QLabel("Skills you want this runner to learn"))
        self.skill_filter = QLineEdit()
        self.skill_filter.setPlaceholderText("Find a skill by name")
        targets_layout.addWidget(self.skill_filter)
        self.skills = QListWidget()
        for (category, identity), name in sorted(master.names.items(), key=lambda item: item[1].casefold()):
            if category != 47:
                continue
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, identity)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.skills.addItem(item)
        self.skills.setAccessibleName("Required skills by name")
        self.skill_filter.textChanged.connect(self._filter_skills)
        targets_layout.addWidget(self.skills, 1)
        tabs.addTab(targets, "3 · Aptitudes and skills")

        self.training_options = TrainingOptions()
        training_scroll = QScrollArea()
        training_scroll.setWidgetResizable(True)
        training_scroll.setWidget(self.training_options)
        tabs.addTab(training_scroll, "4 · Practice plan")

        finish = QWidget()
        finish_form = QFormLayout(finish)
        self.stop = QLineEdit("Meet the targets I selected, then review the finished runner")
        self.attempts = QSpinBox()
        self.attempts.setRange(1, 1000)
        self.attempts.setValue(10)
        self.dependencies = QListWidget()
        for other_goal in store.goals():
            if other_goal["status"] == "Abandoned":
                continue
            item = QListWidgetItem(f"{other_goal['title']} · {other_goal['status']}")
            item.setData(Qt.ItemDataRole.UserRole, other_goal["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.dependencies.addItem(item)
        finish_form.addRow("When can I stop?", self.stop)
        finish_form.addRow("Maximum career attempts", self.attempts)
        finish_form.addRow("Plans to finish first (optional)", self.dependencies)
        tabs.addTab(finish, "5 · Finish conditions")
        self.results = SetupResults(master, repository)
        self.results.use_requested.connect(self._apply_setup)
        tabs.addTab(self.results, "6 · Suggested setups")
        self.search_progress = QProgressBar()
        self.search_progress.setVisible(False)
        root.addWidget(self.search_progress)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.search_button = buttons.addButton("Find setups in my collection", QDialogButtonBox.ButtonRole.ActionRole)
        self.search_button.clicked.connect(self.start_search)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save career plan")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        if goal:
            self._load_goal(goal)

    def _filter_skills(self, text):
        for index in range(self.skills.count()):
            item = self.skills.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    @staticmethod
    def checked(list_widget):
        return [list_widget.item(index).data(Qt.ItemDataRole.UserRole) for index in range(list_widget.count())
            if list_widget.item(index).checkState() == Qt.CheckState.Checked]

    def payload(self):
        stats = {key: spin.value() for key, spin in self.stats.items()}
        return {"role": self.role.currentData(), "card_id": self.trainee.identity(), "scenario": self.scenario.currentText(),
            "surface": self.surface.currentText(), "style": self.style.currentText(), "distance": self.distance.value() or None,
            "distance_type": self.distance_type.currentText(), "minimum_aptitude": self.minimum_aptitude.currentData(),
            "aptitudes": {key: combo.currentData() for key, combo in self.aptitudes.items() if combo.currentData()},
            "planning_mode": "chosen" if self.trainee.identity() is not None else "requirements",
            "training": self.training_options.payload(),
            "stats": stats if any(stats.values()) else {}, "skill_ids": self.checked(self.skills),
            "parent_ids": [picker.identity() for picker in self.parents if picker.identity() is not None],
            "deck_ids": [picker.identity() for picker in self.deck if picker.identity() is not None],
            "prerequisites": self.checked(self.dependencies), "max_attempts": self.attempts.value(), "stop_condition": self.stop.text()}

    def save(self):
        try:
            payload = self.payload()
            validate_training_goal(payload, self.store, self.master)
            title = self.title.text().strip() or (f"Train {self.trainee.choice['character']} · {self.role.currentText()}"
                if self.trainee.choice else f"Find a {self.role.currentText().lower()} setup")
            if self._selected_setup and getattr(self, "_selected_setup_signature", None) == self._signature(payload):
                payload["setup_evidence"] = {key: self._selected_setup[key] for key in
                    ("missing_skills", "aptitude_gap", "slot_gap", "requires_s_roll")}
                payload["setup_evidence"]["training"] = self._selected_setup.get("training")
                payload["setup_evidence"]["master_sha256"] = self.master.sha256
            if self.existing_goal:
                self.store.update_goal(self.existing_goal["id"], title, payload)
            else:
                self.store.save_goal(title, payload)
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your career plan", str(exc))

    @staticmethod
    def _signature(payload):
        return {key: payload.get(key) for key in ("card_id", "surface", "style", "distance", "distance_type", "stats",
            "minimum_aptitude", "aptitudes", "skill_ids", "parent_ids", "deck_ids", "scenario", "training")}

    def start_search(self):
        if self._search_worker:
            self._search_worker.request_cancel()
            return
        try:
            requirements = self.payload()
            validate_training_goal(requirements, self.store, self.master)
            catalog = catalog_for(self.master)
        except ValueError as exc:
            QMessageBox.warning(self, "Check your requirements", str(exc))
            return
        self._search_requirements = self._signature(requirements)
        self.tabs.setCurrentWidget(self.results)
        self.results.clear()
        self.results.summary.setText("Comparing owned trainees, parent lineages and legal support decks…")
        self.search_progress.setValue(0)
        self.search_progress.setVisible(True)
        self.search_button.setText("Cancel setup search")
        worker = self._search_worker = FunctionWorker(partial(find_setups, self.store, self.master, requirements, catalog=catalog))
        worker.signals.result.connect(self.results.set_report)
        worker.signals.error.connect(lambda message, _trace: self.results.summary.setText(message))
        worker.signals.progress.connect(lambda value, _message: self.search_progress.setValue(value))
        worker.signals.cancelled.connect(lambda: self.results.summary.setText("Setup search cancelled. Your requirements are still here."))
        worker.signals.finished.connect(self._search_finished)
        QThreadPool.globalInstance().start(worker)

    def _search_finished(self):
        self._search_worker = None
        self.search_progress.setVisible(False)
        self.search_button.setText("Find setups in my collection")

    def _apply_setup(self, setup):
        if self._signature(self.payload()) != self._search_requirements:
            QMessageBox.information(self, "Requirements changed", "Run the setup search again to compare your updated targets.")
            return
        self._selected_setup = setup
        self._set_identity(self.trainee, setup["card_id"], "card_id")
        for index, picker in enumerate(self.parents):
            identity = setup["parents"][index]["trained_chara_id"] if index < len(setup["parents"]) else None
            self._set_identity(picker, identity, "trained_chara_id")
        if any(row.get("borrowed") for row in setup["supports"]):
            self.borrowed_toggle.setChecked(True)
        for index, picker in enumerate(self.deck):
            identity = setup["supports"][index]["support_card_id"] if index < len(setup["supports"]) else None
            self._set_identity(picker, identity, "support_card_id")
        self._selected_setup_signature = self._signature(self.payload())
        self.tabs.setCurrentIndex(1)

    @staticmethod
    def _set_identity(picker, identity, key):
        picker.set_choice(next((row for row in picker.records if int(row["record"][key]) == int(identity)), None)
            if identity is not None else None)

    def _load_goal(self, goal):
        payload = goal["details"]
        self.training_options.load(payload.get("training", {}))
        self.title.setText(goal["title"])
        self.role.setCurrentIndex(max(0, self.role.findData(payload.get("role"))))
        for combo, key in ((self.scenario, "scenario"), (self.surface, "surface"),
                (self.style, "style"), (self.distance_type, "distance_type")):
            combo.setCurrentText(payload.get(key, combo.currentText()))
        self.minimum_aptitude.setCurrentIndex(max(0, self.minimum_aptitude.findData(payload.get("minimum_aptitude", 7))))
        self.distance.setValue(payload.get("distance") or 0)
        self._set_identity(self.trainee, payload.get("card_id"), "card_id")
        for key, spin in self.stats.items():
            spin.setValue(payload.get("stats", {}).get(key, 0))
        for key, combo in self.aptitudes.items():
            combo.setCurrentIndex(max(0, combo.findData(payload.get("aptitudes", {}).get(key, 0))))
        for index in range(self.skills.count()):
            item = self.skills.item(index)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in payload.get("skill_ids", []) else Qt.CheckState.Unchecked)
        for pickers, field_name, identity_key in ((self.parents, "parent_ids", "trained_chara_id"), (self.deck, "deck_ids", "support_card_id")):
            for index, identity in enumerate(payload.get(field_name, [])):
                if field_name == "deck_ids" and not any(row["record"][identity_key] == identity for row in pickers[index].records):
                    self.borrowed_toggle.setChecked(True)
                self._set_identity(pickers[index], identity, identity_key)
        self.stop.setText(payload.get("stop_condition", self.stop.text()))
        self.attempts.setValue(payload.get("max_attempts", 10))
        for index in range(self.dependencies.count()):
            item = self.dependencies.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == goal["id"]:
                item.setHidden(True)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            elif item.data(Qt.ItemDataRole.UserRole) in payload.get("prerequisites", []):
                item.setCheckState(Qt.CheckState.Checked)

    def reject(self):
        if self._search_worker:
            self._search_worker.request_cancel()
        super().reject()
