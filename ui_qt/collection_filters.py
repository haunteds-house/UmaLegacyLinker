"""Compact, shared filters for collections and illustrated pickers."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from uma_workbench.collection import matches_filters
from uma_workbench.planning import APTITUDES, GRADE_LABELS


class CollectionFilters(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind, self._options = None, None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        line = QHBoxLayout()
        self.toggle = QPushButton("Filters")
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName("Show collection filters")
        line.addWidget(self.toggle)
        self.summary = QLabel("All collection items")
        self.summary.setObjectName("muted")
        line.addWidget(self.summary, 1)
        self.reset = QPushButton("Clear filters")
        self.reset.clicked.connect(self.clear)
        line.addWidget(self.reset)
        root.addLayout(line)
        self.panel = QScrollArea()
        self.panel.setWidgetResizable(True)
        self.panel.hide()
        body = QWidget()
        self.panel.setWidget(body)
        layout = QVBoxLayout(body)
        self.popup = QDialog(self)
        self.popup.setWindowTitle("Filter collection")
        self.popup.resize(780, 590)
        popup_layout = QVBoxLayout(self.popup)
        popup_layout.addWidget(self.panel, 1)
        done = QPushButton("Show matching items")
        done.setObjectName("primary")
        done.clicked.connect(self.popup.accept)
        popup_layout.addWidget(done)
        self.toggle.toggled.connect(self._show_filters)
        self.popup.finished.connect(lambda: self.toggle.setChecked(False))
        row = QHBoxLayout()
        self.rarity = self._combo("Rarity", [("Any rarity", None), ("1★ / R", 1), ("2★ / SR", 2), ("3★ / SSR", 3), ("4★", 4), ("5★", 5)])
        row.addWidget(self.rarity)
        self.support_controls = QWidget()
        support_row = QHBoxLayout(self.support_controls)
        support_row.setContentsMargins(0, 0, 0, 0)
        self.support_type = self._combo("Support type", [("Any type", None), *((name, name) for name in ("Speed", "Stamina", "Power", "Guts", "Wit", "Pal", "Group"))])
        support_row.addWidget(self.support_type)
        support_row.addWidget(QLabel("Min. level"))
        self.level = self._spin("Minimum support level", 50)
        support_row.addWidget(self.level)
        self.limit_breaks = self._combo("Minimum limit breaks", [("Any limit breaks", 0), ("1+ limit breaks", 1), ("2+ limit breaks", 2), ("3+ limit breaks", 3), ("MLB only", 4)])
        support_row.addWidget(self.limit_breaks)
        row.addWidget(self.support_controls, 1)
        self.locked = QCheckBox("Locked veterans only")
        self.locked.toggled.connect(self._changed)
        row.addWidget(self.locked)
        row.addStretch()
        layout.addLayout(row)
        self.aptitude_controls = QWidget()
        apt = QGridLayout(self.aptitude_controls)
        apt.setContentsMargins(0, 0, 0, 0)
        self.aptitudes = {}
        for index, (key, label, _group) in enumerate(APTITUDES):
            combo = self._combo(label + " minimum aptitude", [("Any", 0), *((GRADE_LABELS[rank] + "+" if rank < 8 else "S", rank) for rank in range(1, 9))])
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(0, 0, 0, 0)
            col.addWidget(QLabel(label))
            col.addWidget(combo)
            apt.addWidget(cell, index // 5, index % 5)
            self.aptitudes[key] = combo
        layout.addWidget(self.aptitude_controls)
        self.spark_controls = QWidget()
        sparks_layout = QGridLayout(self.spark_controls)
        sparks_layout.setContentsMargins(0, 0, 0, 0)
        self.sparks = []
        for index in range(2):
            combo = self._combo(f"Spark {index + 1}", [("Any spark", None)], searchable=True)
            stars = self._spin(f"Spark {index + 1} minimum stars", 18, minimum=1)
            sparks_layout.addWidget(combo, index, 0)
            sparks_layout.addWidget(QLabel("Min. stars"), index, 1)
            sparks_layout.addWidget(stars, index, 2)
            self.sparks.append((combo, stars))
        self.family = QCheckBox("Include both grandparents' sparks")
        self.family.toggled.connect(self._changed)
        sparks_layout.addWidget(self.family, 0, 3, 2, 1)
        layout.addWidget(self.spark_controls)
        self.skill = self._combo("Required skill or skill source", [("Any skill", None)], searchable=True)
        layout.addWidget(self.skill)
        self.stat_controls = QWidget()
        stats_layout = QGridLayout(self.stat_controls)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats = {}
        for index, (key, label) in enumerate((("speed", "Speed"), ("stamina", "Stamina"), ("power", "Power"), ("guts", "Guts"), ("wiz", "Wit"))):
            stats_layout.addWidget(QLabel("Min. " + label), 0, index)
            spin = self._spin("Minimum " + label, 20000)
            spin.setSingleStep(50)
            stats_layout.addWidget(spin, 1, index)
            self.stats[key] = spin
        layout.addWidget(self.stat_controls)

    def _show_filters(self, on):
        self.panel.setVisible(on)
        self.popup.setVisible(on)

    def _combo(self, label, options, *, searchable=False):
        combo = QComboBox()
        combo.setAccessibleName(label)
        combo.setToolTip(label)
        for text, data in options:
            combo.addItem(text, data)
        if searchable:
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
            combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        combo.currentIndexChanged.connect(self._changed)
        return combo

    def _spin(self, label, maximum, minimum=0):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setAccessibleName(label)
        spin.setSpecialValueText("Any" if not minimum else "1")
        spin.valueChanged.connect(self._changed)
        return spin

    def set_records(self, kind, records):
        if kind != self.kind:
            self.kind, self._options = kind, None
            self.blockSignals(True)
            self.clear()
            self.blockSignals(False)
            self.support_controls.setVisible(kind == "supports")
            self.aptitude_controls.setVisible(kind != "supports")
            self.spark_controls.setVisible(kind == "veterans")
            self.stat_controls.setVisible(kind == "veterans")
            self.locked.setVisible(kind == "veterans")
        skills, sparks = {}, {}
        for row in records:
            facets = row.get("facets", {})
            skills.update(facets.get("skills", {}))
            sparks.update(facets.get("spark_labels", {}))
        signature = tuple(sorted(skills.items())), tuple(sorted(sparks.items()))
        if signature == self._options:
            return
        self._options = signature
        def replace(combo, options):
            chosen = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for text, value in options:
                combo.addItem(text, value)
            combo.setCurrentIndex(max(0, combo.findData(chosen)))
            combo.blockSignals(False)
        replace(self.skill, [("Any skill / skill source", None), *((name, identity) for identity, name in sorted(skills.items(), key=lambda item: item[1].casefold()))])
        spark_options = [("Any spark", None), *((f"Any {color.lower()} spark", "color:" + color) for color in ("Blue", "Pink", "Green", "Race", "Skill", "Scenario")), *((name, key) for key, name in sorted(sparks.items(), key=lambda item: item[1].casefold()))]
        for combo, _stars in self.sparks:
            replace(combo, spark_options)

    def payload(self):
        return {"rarity": self.rarity.currentData(), "support_type": self.support_type.currentData() if self.kind == "supports" else None,
            "level": self.level.value() if self.kind == "supports" else 0,
            "limit_breaks": self.limit_breaks.currentData() if self.kind == "supports" else 0,
            "aptitudes": {key: combo.currentData() for key, combo in self.aptitudes.items() if combo.currentData()} if self.kind != "supports" else {},
            "stats": {key: spin.value() for key, spin in self.stats.items() if spin.value()} if self.kind == "veterans" else {},
            "sparks": [(combo.currentData(), stars.value()) for combo, stars in self.sparks if combo.currentData()] if self.kind == "veterans" else [],
            "family": self.family.isChecked(), "skill": self.skill.currentData(),
            "locked": self.kind == "veterans" and self.locked.isChecked()}

    def accepts(self, record):
        return matches_filters(record, self.payload())

    def clear(self):
        for combo in self.findChildren(QComboBox):
            combo.setCurrentIndex(0)
        for spin in self.findChildren(QSpinBox):
            spin.setValue(spin.minimum())
        self.locked.setChecked(False)
        self.family.setChecked(False)
        self._changed()

    def _changed(self, *_):
        # Construction signals may arrive before the remaining fields exist.
        if not hasattr(self, "stats"):
            return
        filters = self.payload()
        count = sum(bool(filters.get(key)) for key in ("rarity", "support_type", "level", "limit_breaks", "skill", "locked"))
        count += len(filters["aptitudes"]) + len(filters["stats"]) + len(filters["sparks"])
        self.toggle.setText(f"Filters ({count})" if count else "Filters")
        self.summary.setText(f"{count} filters · all must match" if count else "All collection items")
        self.changed.emit()
