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
        self.resize(990, 720)
        root = QVBoxLayout(self)
        heading = QLabel("What would you like to train?")
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        root.addWidget(muted_label("Pick a race role and the skills you want. Find setups compares your collection; you can leave the trainee and lineup open."))
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        def page(title):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            body = QWidget()
            scroll.setWidget(body)
            layout = QVBoxLayout(body)
            self.tabs.addTab(scroll, title)
            return layout
        goal_layout = page("Goal")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Optional plan name")
        goal_layout.addWidget(self.title)
        self.role = QComboBox()
        for label, code in (("Team Trials runner", "TT"), ("Champion Meeting runner", "CM"),
                ("Inheritance parent", "Parent"), ("Inheritance grandparent", "Grandparent")):
            self.role.addItem(label, code)
        self.scenario = QComboBox()
        self.scenario.addItems(("URA", "Unity Cup", "Trackblazer", "Our Grand Concert"))
        self.surface, self.distance_type, self.style = QComboBox(), QComboBox(), QComboBox()
        self.surface.addItems(("Any surface", "Turf", "Dirt"))
        self.surface.setCurrentText("Turf")
        self.distance_type.addItems(("Any distance", "Sprint", "Mile", "Medium", "Long"))
        self.style.addItems(("Any style", "Front Runner", "Pace Chaser", "Late Surger", "End Closer"))
        race = QGridLayout()
        for index, (label, widget) in enumerate((("Purpose", self.role), ("Scenario", self.scenario),
                ("Surface", self.surface), ("Distance", self.distance_type), ("Running style", self.style))):
            widget.setAccessibleName(label)
            race.addWidget(QLabel(label), (index // 3) * 2, index % 3)
            race.addWidget(widget, (index // 3) * 2 + 1, index % 3)
        goal_layout.addLayout(race)
        self.trainee = NamedChoice("Choose trainee (optional)", describe_records(master, "trainees", store.entities("trainees")), repository)
        self.trainee.label.setText("Compare all my trainees")
        goal_layout.addWidget(self.trainee)
        if runner and runner.get("lock_trainee", True):
            self._set_identity(self.trainee, runner.get("card_id"), "card_id")
        if runner:
            if isinstance(runner.get("style"), int):
                self.style.setCurrentIndex(max(0, min(4, runner["style"])))
            division = int(runner.get("division", 0))
            if 1 <= division <= 4:
                self.distance_type.setCurrentIndex(division)
            elif division == 5:
                self.surface.setCurrentText("Dirt")
        goal_layout.addWidget(QLabel("Skills to learn"))
        self.skill_filter = QLineEdit()
        self.skill_filter.setPlaceholderText("Find a skill by name")
        goal_layout.addWidget(self.skill_filter)
        self.skills = QListWidget()
        self.skills.setMinimumHeight(120)
        for (category, identity), name in sorted(master.names.items(), key=lambda item: item[1].casefold()):
            if category == 47:
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, identity)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.skills.addItem(item)
        self.skills.setAccessibleName("Required skills by name")
        self.skill_filter.textChanged.connect(self._filter_skills)
        goal_layout.addWidget(self.skills, 1)
        self.spark_targets = []
        spark_names = {"color:Blue": "Any blue stat spark"}
        colors = {1:"Blue",2:"Pink",3:"Green",4:"Skill",5:"Race",6:"Scenario"}
        for identity, factor in master.factors.items():
            color = colors.get(factor.get("factor_type"), "Other")
            spark_names.setdefault(f"{color}:{factor.get('factor_group_id')}",
                color + " · " + master.names.get((147, identity), "Spark name unavailable"))
        spark_controls = QWidget()
        spark_grid = QGridLayout(spark_controls)
        spark_grid.setContentsMargins(0, 0, 0, 0)
        for index in range(2):
            from ui_qt.components import SearchableComboBox
            choice = SearchableComboBox()
            choice.addItem("Any spark", None)
            for identity, name in sorted(spark_names.items(), key=lambda row:row[1]):
                choice.addItem(name, identity)
            stars = QSpinBox(); stars.setRange(1, 3); stars.setValue(3)
            choice.setAccessibleName(f"Result spark {index + 1}")
            stars.setAccessibleName(f"Result spark {index + 1} minimum stars")
            spark_grid.addWidget(choice,index,0); spark_grid.addWidget(stars,index,1)
            self.spark_targets.append((choice,stars))
        spark_toggle = QPushButton("Result sparks for parent careers (optional)")
        spark_toggle.setCheckable(True); spark_controls.hide(); spark_toggle.toggled.connect(spark_controls.setVisible)
        goal_layout.addWidget(spark_toggle); goal_layout.addWidget(spark_controls)
        if goal and goal["details"].get("required_sparks"):
            for (choice,stars),(identity,minimum) in zip(self.spark_targets, goal["details"]["required_sparks"].items()):
                choice.setCurrentIndex(max(0,choice.findData(identity))); stars.setValue(minimum)
            spark_toggle.setChecked(True)
        targets_toggle = QPushButton("Aptitude and stat targets (optional)")
        targets_toggle.setCheckable(True)
        goal_layout.addWidget(targets_toggle)
        targets = QWidget()
        targets.hide()
        targets_toggle.toggled.connect(targets.setVisible)
        target_layout = QVBoxLayout(targets)
        self.minimum_aptitude = QComboBox()
        for rank in range(1, 9):
            self.minimum_aptitude.addItem(GRADE_LABELS[rank], rank)
        self.minimum_aptitude.setCurrentIndex(6)
        form = QFormLayout()
        form.addRow("Minimum aptitude for the race role", self.minimum_aptitude)
        self.distance = QSpinBox()
        self.distance.setRange(0, 5000)
        self.distance.setSingleStep(100)
        self.distance.setSpecialValueText("Use distance group")
        self.distance.setSuffix(" m")
        form.addRow("Exact distance", self.distance)
        target_layout.addLayout(form)
        apt = QGridLayout()
        self.aptitudes = {}
        for index, (key, label, _group) in enumerate(APTITUDES):
            combo = QComboBox()
            for rank in range(9):
                combo.addItem(GRADE_LABELS[rank], rank)
            combo.setAccessibleName(label + " aptitude target")
            apt.addWidget(QLabel(label), (index // 5) * 2, index % 5)
            apt.addWidget(combo, (index // 5) * 2 + 1, index % 5)
            self.aptitudes[key] = combo
        target_layout.addLayout(apt)
        stat_row = QGridLayout()
        self.stats = {}
        for index, (key, label) in enumerate(STAT_LABELS):
            spin = QSpinBox()
            spin.setRange(0, 20000)
            spin.setSingleStep(50)
            spin.setSpecialValueText("Any")
            spin.setAccessibleName(label + " target")
            stat_row.addWidget(QLabel(label), 0, index)
            stat_row.addWidget(spin, 1, index)
            self.stats[key] = spin
        target_layout.addLayout(stat_row)
        target_layout.addWidget(muted_label("S aptitude needs an in-career inheritance roll."))
        goal_layout.addWidget(targets)

        lineup = page("Lineup")
        lineup.addWidget(muted_label("Leave slots open for suggestions, or pin your choices. Every support deck uses five of your cards and one borrowed card."))
        from uma_workbench.roster_viewer import owned_veterans
        veteran_rows = describe_records(master, "veterans", owned_veterans(store))
        self.parents = [NamedChoice(f"Choose parent {index + 1}", veteran_rows, repository) for index in range(2)]
        form = QFormLayout()
        for index, picker in enumerate(self.parents):
            form.addRow(f"Parent {index + 1}", picker)
        owned = describe_records(master, "supports", store.entities("supports"))
        rentals = describe_records(master, "supports", [{"support_card_id": identity} for identity in master.supports], borrowed=True)
        self.deck = [NamedChoice(f"Choose owned support {index + 1}", owned, repository) for index in range(5)]
        self.borrowed_support = NamedChoice("Choose support to borrow", rentals, repository)
        self.deck.append(self.borrowed_support)
        form.addRow("Borrowed support · required", self.borrowed_support)
        for index, picker in enumerate(self.deck):
            picker.label.setText("Find a rental for me" if index == 5 else "Find for me")
            if index < 5:
                form.addRow(f"My support {index + 1}", picker)
        lineup.addLayout(form)
        lineup.addWidget(muted_label("The rental search includes cards you already own. Check the suggested card is available from your friends."))
        lineup.addStretch()

        self.results = SetupResults(master, repository)
        self.results.use_requested.connect(self._apply_setup)
        self.tabs.addTab(self.results, "Suggested setups")
        advanced_layout = page("More options")
        self.training_options = TrainingOptions()
        self.training_options.enabled.setChecked(False)
        advanced_layout.addWidget(self.training_options)
        self.stop = QLineEdit("Meet the targets I selected, then review the finished runner")
        self.attempts = QSpinBox()
        self.attempts.setRange(1, 1000)
        self.attempts.setValue(10)
        self.dependencies = QListWidget()
        for other_goal in store.goals():
            retained_dependency = other_goal["id"] in (goal or {}).get("details", {}).get("prerequisites", [])
            if retained_dependency or (not other_goal.get("removed") and other_goal["status"] != "Abandoned"):
                item = QListWidgetItem(f"{other_goal['title']} · {other_goal['status']}")
                item.setData(Qt.ItemDataRole.UserRole, other_goal["id"])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.dependencies.addItem(item)
        finish = QFormLayout()
        finish.addRow("When can I stop?", self.stop)
        finish.addRow("Maximum career attempts", self.attempts)
        finish.addRow("Plans to finish first", self.dependencies)
        advanced_layout.addLayout(finish)
        self.advanced_toggle = QCheckBox("Show practice comparison and more options")
        self.advanced_toggle.toggled.connect(lambda on: self.tabs.setTabVisible(3, on))
        root.addWidget(self.advanced_toggle)
        self.tabs.setTabVisible(3, False)
        self.search_progress = QProgressBar()
        self.search_progress.setVisible(False)
        root.addWidget(self.search_progress)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.search_button = buttons.addButton("Find setups", QDialogButtonBox.ButtonRole.ActionRole)
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self.start_search)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save plan")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        if goal:
            self._load_goal(goal)
        if runner:
            for index, identity in enumerate(runner.get("parent_ids", [])[:2]):
                self._set_identity(self.parents[index], identity, "trained_chara_id")

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
        previous = dict(self.existing_goal["details"]) if self.existing_goal else {}
        previous.pop("setup_evidence", None)
        return {**previous, "role": self.role.currentData(), "card_id": self.trainee.identity(), "scenario": self.scenario.currentText(),
            "surface": self.surface.currentText(), "style": self.style.currentText(), "distance": self.distance.value() or None,
            "distance_type": self.distance_type.currentText(), "minimum_aptitude": self.minimum_aptitude.currentData(),
            "aptitudes": {key: combo.currentData() for key, combo in self.aptitudes.items() if combo.currentData()},
            "planning_mode": "chosen" if self.trainee.identity() is not None else "requirements",
            "training": self.training_options.payload(),
            "required_sparks": {choice.currentData():stars.value() for choice,stars in self.spark_targets if choice.currentData()},
            "stats": stats if any(stats.values()) else {}, "skill_ids": self.checked(self.skills),
            "parent_ids": [picker.identity() for picker in self.parents if picker.identity() is not None],
            "deck_ids": [picker.identity() for picker in self.deck if picker.identity() is not None],
            "borrowed_support_id": self.borrowed_support.identity(),
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
                if self._selected_setup.get("career"):
                    payload["setup_evidence"]["career"] = {key:value for key,value in self._selected_setup["career"].items() if key not in ("samples", "timeline")}
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
            "minimum_aptitude", "aptitudes", "skill_ids", "parent_ids", "deck_ids", "borrowed_support_id", "scenario", "training", "career", "required_sparks")}

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
        self.search_button.setText("Find setups")

    def _apply_setup(self, setup):
        if self._signature(self.payload()) != self._search_requirements:
            QMessageBox.information(self, "Requirements changed", "Run the setup search again to compare your updated targets.")
            return
        self._selected_setup = setup
        self._set_identity(self.trainee, setup["card_id"], "card_id")
        for index, picker in enumerate(self.parents):
            identity = setup["parents"][index]["trained_chara_id"] if index < len(setup["parents"]) else None
            self._set_identity(picker, identity, "trained_chara_id")
        own = [row for row in setup["supports"] if not row.get("borrowed")]
        borrowed = next((row for row in setup["supports"] if row.get("borrowed")), None)
        for index, picker in enumerate(self.deck[:5]):
            self._set_identity(picker, own[index]["support_card_id"] if index < len(own) else None, "support_card_id")
        self._set_identity(self.borrowed_support, borrowed["support_card_id"] if borrowed else None, "support_card_id")
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
        for index, identity in enumerate(payload.get("parent_ids", [])[:2]):
            self._set_identity(self.parents[index], identity, "trained_chara_id")
        from uma_workbench.goals import support_slots
        owned_ids = {int(row["support_card_id"]) for row in self.store.entities("supports")}
        try:
            own, borrowed = support_slots(payload, owned_ids)
        except ValueError:
            own, borrowed = tuple(payload.get("deck_ids", [])[:5]), None
            self.results.summary.setText("This older plan used six owned supports. Choose the borrowed slot before saving a complete lineup.")
        for index, identity in enumerate(own[:5]):
            self._set_identity(self.deck[index], identity, "support_card_id")
        self._set_identity(self.borrowed_support, borrowed, "support_card_id")
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
