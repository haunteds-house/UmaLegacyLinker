"""A career plan made from named collection choices."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QScrollArea,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ui_qt.collection_widgets import NamedChoice, STAT_LABELS, describe_records
from ui_qt.components import muted_label
from uma_workbench.goals import validate_training_goal


class TrainingGoalDialog(QDialog):
    def __init__(self, store, master, repository, runner=None, parent=None):
        super().__init__(parent)
        self.store, self.master, self.repository = store, master, repository
        self.setWindowTitle("Plan a career")
        self.resize(950, 660)
        root = QVBoxLayout(self)
        heading = QLabel("What do you want to train?")
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        root.addWidget(muted_label("Choose characters and cards by name. Leave optional targets blank until you know what you want to improve."))
        tabs = self.tabs = QTabWidget()
        root.addWidget(tabs, 1)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Optional name for this plan")
        self.role = QComboBox()
        for label, code in (("Team Trials runner", "TT"), ("Champion Meeting runner", "CM"),
            ("Inheritance parent", "Parent"), ("Inheritance grandparent", "Grandparent")):
            self.role.addItem(label, code)
        self.trainee = NamedChoice("Choose the trainee", describe_records(master, "trainees", store.entities("trainees")), repository)
        if runner:
            match = next((row for row in self.trainee.records if row["record"]["card_id"] == runner["card_id"]), None)
            self.trainee.set_choice(match)
        self.scenario = QComboBox()
        self.scenario.addItems(("URA", "Unity Cup", "Trackblazer", "Our Grand Concert"))
        self.surface = QComboBox()
        self.surface.addItems(("Turf", "Dirt"))
        self.style = QComboBox()
        self.style.addItems(("Front Runner", "Pace Chaser", "Late Surger", "End Closer"))
        self.style.setCurrentText("Pace Chaser")
        if runner:
            self.style.setCurrentIndex(max(0, int(runner.get("style", 2)) - 1))
        self.distance = QSpinBox()
        self.distance.setRange(0, 5000)
        self.distance.setSingleStep(100)
        self.distance.setSpecialValueText("Any distance")
        self.distance.setSuffix(" m")
        target = QWidget()
        form = QFormLayout(target)
        form.setSpacing(14)
        for label, widget in (("Plan name", self.title), ("Use this runner for", self.role), ("Trainee", self.trainee),
            ("Career scenario", self.scenario), ("Surface", self.surface), ("Distance", self.distance), ("Running style", self.style)):
            widget.setAccessibleName(label)
            form.addRow(label, widget)
        tabs.addTab(target, "1 · Choose a runner")

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
        tabs.addTab(targets, "3 · Stat and skill targets")

        finish = QWidget()
        finish_form = QFormLayout(finish)
        self.stop = QLineEdit("Meet the targets I selected, then review the finished runner")
        self.attempts = QSpinBox()
        self.attempts.setRange(1, 1000)
        self.attempts.setValue(10)
        self.dependencies = QListWidget()
        for goal in store.goals():
            if goal["status"] == "Abandoned":
                continue
            item = QListWidgetItem(f"{goal['title']} · {goal['status']}")
            item.setData(Qt.ItemDataRole.UserRole, goal["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.dependencies.addItem(item)
        finish_form.addRow("When can I stop?", self.stop)
        finish_form.addRow("Maximum career attempts", self.attempts)
        finish_form.addRow("Plans to finish first (optional)", self.dependencies)
        tabs.addTab(finish, "4 · Finish conditions")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save career plan")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _filter_skills(self, text):
        for index in range(self.skills.count()):
            item = self.skills.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    @staticmethod
    def checked(list_widget):
        return [list_widget.item(index).data(Qt.ItemDataRole.UserRole) for index in range(list_widget.count())
            if list_widget.item(index).checkState() == Qt.CheckState.Checked]

    def payload(self):
        if self.trainee.identity() is None:
            raise ValueError("Choose the trainee you want to train")
        stats = {key: spin.value() for key, spin in self.stats.items()}
        return {"role": self.role.currentData(), "card_id": self.trainee.identity(), "scenario": self.scenario.currentText(),
            "surface": self.surface.currentText(), "style": self.style.currentText(), "distance": self.distance.value() or None,
            "stats": stats if any(stats.values()) else {}, "skill_ids": self.checked(self.skills),
            "parent_ids": [picker.identity() for picker in self.parents if picker.identity() is not None],
            "deck_ids": [picker.identity() for picker in self.deck if picker.identity() is not None],
            "prerequisites": self.checked(self.dependencies), "max_attempts": self.attempts.value(), "stop_condition": self.stop.text()}

    def save(self):
        try:
            payload = self.payload()
            validate_training_goal(payload, self.store, self.master)
            title = self.title.text().strip() or f"Train {self.trainee.choice['character']} · {self.role.currentText()}"
            self.store.save_goal(title, payload)
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your career plan", str(exc))
