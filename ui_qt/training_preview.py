"""Readable practice assumptions and stat contribution previews."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QProgressBar, QSpinBox, QVBoxLayout, QWidget,
)

from ui_qt.components import muted_label
from ui_qt.collection_widgets import display_name
from uma_workbench.training import DEFAULT_OPTIONS, LABELS, STATS


class TrainingOptions(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        self.enabled = QCheckBox("Compare the training output of suggested setups")
        self.enabled.setChecked(True)
        root.addWidget(self.enabled)
        root.addWidget(muted_label("Use the same practice plan to compare decks. Change these counts to match how you intend to train; they are comparison assumptions."))
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.body)
        self.preset = QComboBox()
        self.preset.addItems(("Even comparison", "Speed and wit", "More stamina practice", "Custom counts"))
        body.addWidget(self.preset)
        grid = QGridLayout()
        self.sessions = {}
        for column, (stat, label) in enumerate(zip(STATS, LABELS)):
            grid.addWidget(QLabel(label), 0, column)
            spin = QSpinBox()
            spin.setRange(0, 78)
            spin.setValue(DEFAULT_OPTIONS["sessions"][stat])
            spin.setAccessibleName(label + " practices planned")
            grid.addWidget(spin, 1, column)
            self.sessions[stat] = spin
            spin.valueChanged.connect(self._counts_changed)
        body.addLayout(grid)
        self.total = muted_label("50 practices planned. Races, rests and outings use other turns.")
        body.addWidget(self.total)
        form = QFormLayout()
        self.facility = QSpinBox()
        self.facility.setRange(1, 5)
        self.facility.setValue(3)
        self.mood = QComboBox()
        for value, label in ((5, "Great"), (4, "Good"), (3, "Normal"), (2, "Bad"), (1, "Awful")):
            self.mood.addItem(label, value)
        self.friendships = QSpinBox()
        self.friendships.setRange(0, 100)
        self.friendships.setSuffix(" %")
        self.friendships.setValue(60)
        self.borrowed_level = QSpinBox()
        self.borrowed_level.setRange(1, 50)
        self.borrowed_level.setValue(50)
        self.borrowed_breaks = QSpinBox()
        self.borrowed_breaks.setRange(0, 4)
        self.borrowed_breaks.setSpecialValueText("No limit breaks")
        self.borrowed_breaks.setValue(4)
        self.later_fans, self.energy, self.max_energy = QSpinBox(), QSpinBox(), QSpinBox()
        self.later_fans.setRange(0, 10000000)
        self.later_fans.setSingleStep(10000)
        self.later_fans.setGroupSeparatorShown(True)
        self.later_fans.setValue(DEFAULT_OPTIONS["later_fans"])
        self.energy.setRange(1, 200)
        self.energy.setValue(DEFAULT_OPTIONS["energy"])
        self.max_energy.setRange(100, 200)
        self.max_energy.setValue(DEFAULT_OPTIONS["max_energy"])
        for label, widget in (("Comparison facility level", self.facility), ("Trainee's mood", self.mood),
                ("Practices after friendships are built", self.friendships),
                ("Fans at the later stage", self.later_fans), ("Energy when practicing", self.energy),
                ("Maximum energy", self.max_energy),
                ("Borrowed support level, if used", self.borrowed_level), ("Borrowed support limit breaks", self.borrowed_breaks)):
            widget.setAccessibleName(label)
            form.addRow(label, widget)
        body.addLayout(form)
        body.addWidget(muted_label("Owned cards use their exported levels and limit breaks. Borrowed effects are capped at the level allowed by the limit breaks you enter."))
        body.addWidget(muted_label("The estimate counts successful practices, support effects and starting bonuses. Race rewards, event rewards, inheritance, shop items and scenario bonuses still need to be earned separately."))
        root.addStretch()
        self.enabled.toggled.connect(self.body.setEnabled)
        self.preset.currentIndexChanged.connect(self._preset)

    def _counts_changed(self):
        if hasattr(self, "total"):
            if not getattr(self, "_setting_preset", False):
                self.preset.setCurrentIndex(3)
            count = sum(spin.value() for spin in self.sessions.values())
            self.total.setText(f"{count} practices planned. " + ("Use at most 78; leave room for races and recovery." if count > 78 else "Races, rests and outings use other turns."))

    def _preset(self, index):
        if index < 3:
            self._setting_preset = True
            values = ((10, 10, 10, 10, 10), (20, 4, 6, 0, 20), (18, 14, 6, 0, 12))[index]
            for spin, value in zip(self.sessions.values(), values):
                spin.setValue(value)
            self._setting_preset = False

    def payload(self):
        return {"enabled": self.enabled.isChecked(), "facility_level": self.facility.value(),
            "motivation": self.mood.currentData(), "friendship_share": self.friendships.value(),
            "sessions": {stat: spin.value() for stat, spin in self.sessions.items()},
            "later_fans": self.later_fans.value(), "energy": self.energy.value(), "max_energy": self.max_energy.value(),
            "borrowed_level": self.borrowed_level.value(), "borrowed_limit_breaks": self.borrowed_breaks.value()}

    def load(self, options):
        values = {**DEFAULT_OPTIONS, **options}
        self.preset.setCurrentIndex(3)
        self.enabled.setChecked(values["enabled"])
        self.body.setEnabled(values["enabled"])
        self.facility.setValue(values["facility_level"])
        self.mood.setCurrentIndex(max(0, self.mood.findData(values["motivation"])))
        self.friendships.setValue(values["friendship_share"])
        self.borrowed_level.setValue(values["borrowed_level"])
        self.borrowed_breaks.setValue(values["borrowed_limit_breaks"])
        self.later_fans.setValue(values["later_fans"])
        self.energy.setValue(values["energy"])
        self.max_energy.setValue(values["max_energy"])
        for stat, spin in self.sessions.items():
            spin.setValue(values["sessions"].get(stat, 10))


class TrainingEstimate(QFrame):
    def __init__(self, estimate, targets, history=None, validation=None, parent=None, *, master=None):
        super().__init__(parent)
        self.setObjectName("subtlePanel")
        root = QVBoxLayout(self)
        heading = QLabel("What this practice plan contributes")
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        count = sum(estimate["options"]["sessions"].values())
        root.addWidget(muted_label(f"Starting stats + support starting bonuses + {count} successful practices. These subtotals are a comparison, not final career stats."))
        grid = QGridLayout()
        self.bars = {}
        for row, (stat, label) in enumerate(zip(STATS, LABELS)):
            subtotal = round(estimate["subtotal"][stat])
            target = targets.get(stat, 0)
            grid.addWidget(QLabel(label), row, 0)
            bar = QProgressBar()
            bar.setRange(0, max(1, target, subtotal) if target else max(1200, subtotal))
            bar.setValue(subtotal)
            bar.setTextVisible(False)
            bar.setAccessibleName(label + " practice subtotal")
            grid.addWidget(bar, row, 1)
            self.bars[stat] = bar
            gap = max(0, round(target - estimate["subtotal"][stat]))
            grid.addWidget(QLabel(f"~{subtotal:,}" + (f" / {target:,}" if target else "")), row, 2)
            grid.addWidget(QLabel(f"{gap:,} more" if gap else ""), row, 3)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)
        root.addWidget(muted_label(f"~{round(estimate['skill_points']):,} skill points from practices. Fill remaining targets with your other career gains."))
        conditions = estimate["options"]
        mood = {5: "Great", 4: "Good", 3: "Normal", 2: "Bad", 1: "Awful"}[conditions["motivation"]]
        root.addWidget(muted_label(f"Facility level {conditions['facility_level']} · {mood} mood · friendships built for {conditions['friendship_share']}% of practices"))
        root.addWidget(muted_label(f"Energy {conditions['energy']}/{conditions['max_energy']} · later-stage fans {conditions['later_fans']:,}"))
        if estimate["notes"]:
            root.addWidget(muted_label(" · ".join(estimate["notes"])))
            if master:
                for support in estimate.get("supports", []):
                    if support["notes"]:
                        root.addWidget(muted_label(display_name(master, "supports", support["support_card_id"]) + ": " + " · ".join(support["notes"])))
        if history and history["rows"]:
            row = history["rows"][0]
            root.addWidget(QLabel("A completed career from your collection"))
            root.addWidget(muted_label(f"Same trainee and scenario · {row['matching_supports']}/6 matching support cards; levels may differ. "
                + " · ".join(f"{label} {row['stats'][stat]:,}" for stat, label in zip(STATS, LABELS))))
            root.addWidget(muted_label("Recorded totals include the whole career. They are context, not a test of this practice-only subtotal."))
        if validation:
            checked = validation["checked"]
            caption = (f"Practice formula check: {validation['exact']}/{checked} exported previews matched. "
                "This does not validate whole-career outcomes." if checked else "No comparable enabled practice previews were found in your exports yet.")
            root.addWidget(muted_label(caption))
