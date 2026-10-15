"""Native skill-point, awakening-material and Concert budget tools."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFormLayout, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSpinBox, QDoubleSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui_qt.collection_widgets import NamedChoice, describe_records
from ui_qt.components import muted_label
from uma_workbench.calculators import awakening_costs, concert_budget, concert_songs, material_budget, skill_budget, PERFORMANCE
from uma_workbench.planning import catalog_for


def table(headers):
    result = QTableWidget(0, len(headers))
    result.setHorizontalHeaderLabels(headers)
    result.verticalHeader().hide()
    result.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    result.horizontalHeader().setStretchLastSection(True)
    return result


def amount(value=0, *, unknown=False):
    result = QSpinBox()
    result.setRange(-1 if unknown else 0, 1_000_000_000)
    if unknown:
        result.setSpecialValueText("Enter price")
    result.setValue(value)
    return result


class SkillBudgetWidget(QWidget):
    def __init__(self, master, store, parent=None):
        super().__init__(parent)
        self.master, self.store = master, store
        self.signature = None
        saved = store.setting("skill_budget", {})
        self.selected = set(saved.get("selected", []))
        self.learned = set(saved.get("learned", []))
        self.prices = {int(key): value for key, value in saved.get("prices", {}).items()}
        root = QVBoxLayout(self)
        root.addWidget(muted_label("Choose the skills you want. Prerequisite steps are included once. Enter discounted prices shown in-game and mark skills you already learned."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Skill points available"))
        self.balance = amount(saved.get("balance", 0))
        row.addWidget(self.balance)
        self.reset_learned = QPushButton("Clear learned marks")
        self.reset_learned.clicked.connect(self._clear_learned)
        row.addWidget(self.reset_learned)
        row.addStretch()
        root.addLayout(row)
        split = QSplitter()
        root.addWidget(split, 1)
        choices = QWidget()
        left = QVBoxLayout(choices)
        left.setContentsMargins(0, 0, 0, 0)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find a skill by name")
        left.addWidget(self.filter)
        self.choices = QListWidget()
        left.addWidget(self.choices)
        split.addWidget(choices)
        self.costs = table(["Skill", "Step", "Price I pay", "Learned"])
        split.addWidget(self.costs)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        self.summary = muted_label("Choose the game data file in Setup to load skills and costs.")
        root.addWidget(self.summary)
        self.filter.textChanged.connect(self._filter)
        self.choices.itemChanged.connect(self._selection_changed)
        self.balance.valueChanged.connect(self._totals)

    def refresh(self):
        signature = str(self.master.path), self.master.sha256
        if signature == self.signature:
            return
        self.signature = signature
        self.choices.blockSignals(True)
        self.choices.clear()
        catalog = catalog_for(self.master)
        identities = [identity for identity, row in catalog.skills.items()
            if row.get("group_rate", 0) > 0 and identity in catalog.costs]
        for identity in sorted(identities, key=lambda sid: self.master.skill_name(sid).casefold()):
            item = QListWidgetItem(self.master.skill_name(identity))
            item.setData(Qt.ItemDataRole.UserRole, identity)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if identity in self.selected else Qt.CheckState.Unchecked)
            self.choices.addItem(item)
        self.choices.blockSignals(False)
        self._rebuild()

    def _filter(self, text):
        for index in range(self.choices.count()):
            item = self.choices.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    def use_skills(self, identities):
        self.selected = set(identities)
        self.signature = None
        self.refresh()

    def _selection_changed(self):
        self.selected = {self.choices.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.choices.count())
            if self.choices.item(index).checkState() == Qt.CheckState.Checked}
        self._rebuild()

    def _clear_learned(self):
        self.learned.clear()
        self._rebuild()

    def _rebuild(self):
        catalog = catalog_for(self.master)
        budget = skill_budget(catalog, self.selected)
        self.costs.setRowCount(len(budget["rows"]))
        for index, row in enumerate(budget["rows"]):
            identity = row["skill_id"]
            self.costs.setItem(index, 0, QTableWidgetItem(self.master.skill_name(identity)))
            self.costs.setItem(index, 1, QTableWidgetItem("Prerequisite" if row["prerequisite"] else "Target"))
            price = amount(self.prices.get(identity, row["cost"] if row["cost"] is not None else -1), unknown=True)
            price.setAccessibleName("Price for " + self.master.skill_name(identity))
            price.valueChanged.connect(lambda value, sid=identity: self._price(sid, value))
            self.costs.setCellWidget(index, 2, price)
            learned = QCheckBox("Learned")
            learned.setChecked(identity in self.learned)
            learned.toggled.connect(lambda checked, sid=identity: self._learned(sid, checked))
            self.costs.setCellWidget(index, 3, learned)
        self._totals()

    def _price(self, identity, value):
        if value >= 0:
            self.prices[identity] = value
        else:
            self.prices.pop(identity, None)
        self._totals()

    def _learned(self, identity, checked):
        self.learned.add(identity) if checked else self.learned.discard(identity)
        self._totals()

    def _totals(self):
        result = skill_budget(catalog_for(self.master), self.selected, learned=self.learned,
            paid_prices=self.prices, budget=self.balance.value())
        if not self.master.path:
            self.summary.setText("Choose the game data file in Setup to load skill costs.")
        elif result["unknown"]:
            self.summary.setText(f"Known cost: {result['total']:,} SP. Enter the missing prices before checking affordability.")
        else:
            self.summary.setText(f"Total still to buy: {result['total']:,} SP · Available: {self.balance.value():,} SP · "
                + (f"Short by {result['missing']:,} SP" if result["missing"] else f"{result['remaining']:,} SP left"))
        self.store.set_setting("skill_budget", {"selected": sorted(self.selected), "learned": sorted(self.learned),
            "prices": self.prices, "balance": self.balance.value()})


class AwakeningBudgetWidget(QWidget):
    def __init__(self, master, store, repository, parent=None):
        super().__init__(parent)
        self.master, self.store = master, store
        self.signature = None
        self.balance_inputs, self.rate_inputs, self.items = {}, {}, []
        saved = store.setting("awakening_balances", {})
        self.balances = {int(key): value for key, value in saved.get("balances", {}).items()}
        self.rates = {int(key): value for key, value in saved.get("rates", {}).items()}
        root = QVBoxLayout(self)
        root.addWidget(muted_label("Choose a trainee and awakening target to total the required materials. Enter your balances and average materials earned per run to see what remains."))
        self.trainee = NamedChoice("Choose a trainee for awakening costs", [], repository)
        root.addWidget(self.trainee)
        row = QHBoxLayout()
        self.current, self.target = QSpinBox(), QSpinBox()
        for spin in (self.current, self.target):
            spin.setRange(1, 5)
        self.target.setValue(5)
        row.addWidget(QLabel("Current awakening")); row.addWidget(self.current)
        row.addWidget(QLabel("Target awakening")); row.addWidget(self.target)
        row.addStretch()
        root.addLayout(row)
        self.costs = table(["Material", "Required", "I have", "Per run", "Missing", "Runs needed"])
        header = self.costs.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 72), (2, 88), (3, 94), (4, 68), (5, 132)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            label = self.costs.horizontalHeaderItem(column).text()
            header.resizeSection(column, max(width, header.fontMetrics().horizontalAdvance(label) + 28))
        root.addWidget(self.costs, 1)
        self.summary = muted_label("Choose a trainee to calculate its material costs.")
        root.addWidget(self.summary)
        self.trainee.changed.connect(self._trainee_changed)
        self.current.valueChanged.connect(self._rebuild)
        self.target.valueChanged.connect(self._rebuild)

    def refresh(self):
        rows = self.store.entities("trainees")
        signature = self.master.sha256, tuple((row["card_id"], row.get("talent_level")) for row in rows)
        if signature != self.signature:
            self.signature = signature
            self.trainee.records = describe_records(self.master, "trainees", rows)
            self._rebuild()

    def _trainee_changed(self):
        if self.trainee.choice:
            self.current.setValue(int(self.trainee.choice["record"].get("talent_level", 1)))
        self._rebuild()

    def _rebuild(self):
        self.items = []
        self.costs.setRowCount(0)
        if not self.trainee.identity():
            self.summary.setText("Choose a trainee to calculate its awakening material costs.")
            return
        try:
            result = awakening_costs(self.master, self.trainee.identity(), self.current.value(), self.target.value())
        except ValueError as exc:
            self.summary.setText(str(exc)); return
        self.items = result["items"]
        self.costs.setRowCount(len(self.items))
        self.balance_inputs, self.rate_inputs = {}, {}
        for index, row in enumerate(self.items):
            identity = row["item_id"]
            self.costs.setItem(index, 0, QTableWidgetItem(row["name"]))
            self.costs.setItem(index, 1, QTableWidgetItem(str(row["needed"])))
            for column, mapping, values in ((2, self.balance_inputs, self.balances), (3, self.rate_inputs, self.rates)):
                if column == 3:
                    spin = QDoubleSpinBox()
                    spin.setRange(0, 1_000_000_000)
                    spin.setDecimals(3)
                    spin.setSingleStep(0.1)
                    spin.setValue(float(values.get(identity, 0)))
                else:
                    spin = amount(values.get(identity, 0))
                mapping[identity] = spin
                self.costs.setCellWidget(index, column, spin)
                spin.valueChanged.connect(self._totals)
        self._missing_levels = result["missing_levels"]
        self._totals()

    def _totals(self):
        self.balances.update({identity: spin.value() for identity, spin in self.balance_inputs.items()})
        self.rates.update({identity: spin.value() for identity, spin in self.rate_inputs.items()})
        rows = material_budget(self.items, self.balances, self.rates)
        for index, row in enumerate(rows):
            self.costs.setItem(index, 4, QTableWidgetItem(str(int(row["missing"]))))
            self.costs.setItem(index, 5, QTableWidgetItem(str(row["runs"]) if row["runs"] is not None else "Enter per-run rate"))
        self.summary.setText("Some upgrade levels are missing from this game data; the total is incomplete." if getattr(self, "_missing_levels", [])
            else ("The chosen awakening target is already reached." if not self.items else "Material totals use the selected game data. Runs use your entered earning rates."))
        self.store.set_setting("awakening_balances", {"balances": self.balances, "rates": self.rates})


class ConcertBudgetWidget(QWidget):
    def __init__(self, master, store, parent=None):
        super().__init__(parent)
        self.master, self.store = master, store
        self.signature, self.songs = None, []
        saved = store.setting("concert_budget", {})
        self.wanted, self.bought = set(saved.get("wanted", [])), set(saved.get("bought", []))
        root = QVBoxLayout(self)
        root.addWidget(muted_label("Plan Performance Points for the songs you want. Mark bought songs to remove their costs. Buying a song also requires it to appear in your career."))
        grid = QGridLayout()
        self.balances = []
        for index, name in enumerate(PERFORMANCE):
            grid.addWidget(QLabel(name), 0, index)
            spin = amount((saved.get("balances") or [0] * 5)[index])
            spin.setAccessibleName(name + " performance points")
            spin.valueChanged.connect(self._totals)
            grid.addWidget(spin, 1, index)
            self.balances.append(spin)
        root.addLayout(grid)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find a song by name")
        root.addWidget(self.filter)
        self.costs = table(["Want", "Bought", "Song", "Performance cost", "Mastery effect"])
        root.addWidget(self.costs, 1)
        self.summary = muted_label("Choose the game data file in Setup to load Concert songs.")
        root.addWidget(self.summary)
        self.filter.textChanged.connect(self._filter)

    def refresh(self):
        signature = self.master.sha256, str(self.master.path)
        if signature == self.signature:
            return
        self.signature = signature
        self.songs = concert_songs(self.master)
        self.costs.setRowCount(len(self.songs))
        for index, song in enumerate(self.songs):
            identity = song["id"]
            for column, selected in ((0, self.wanted), (1, self.bought)):
                check = QCheckBox()
                check.setAccessibleName(("Want " if column == 0 else "Bought ") + song["name"])
                check.setChecked(identity in selected)
                check.toggled.connect(lambda checked, sid=identity, group=selected: self._toggle(group, sid, checked))
                self.costs.setCellWidget(index, column, check)
            for column, text in ((2, song["name"]), (3, " · ".join(f"{name} {cost}" for name, cost in zip(PERFORMANCE, song["costs"]) if cost)), (4, song["effect"])):
                self.costs.setItem(index, column, QTableWidgetItem(text))
        self._totals()

    def _filter(self, text):
        for index, song in enumerate(self.songs):
            self.costs.setRowHidden(index, text.casefold() not in song["name"].casefold())

    def _toggle(self, group, identity, checked):
        group.add(identity) if checked else group.discard(identity)
        self._totals()

    def _totals(self):
        if not hasattr(self, "summary"):
            return
        balances = [spin.value() for spin in self.balances]
        result = concert_budget(self.songs, self.wanted, self.bought, balances)
        self.summary.setText(f"{result['songs_to_buy']} planned songs still to buy. Enter current points from your career.\n"
            + " · ".join(f"{name}: {cost} needed, {missing} short" for name, cost, missing in zip(PERFORMANCE, result["costs"], result["missing"])))
        if not self.songs:
            self.summary.setText("Choose a game data file containing Grand Concert songs in Setup.")
        self.store.set_setting("concert_budget", {"wanted": sorted(self.wanted), "bought": sorted(self.bought), "balances": balances})
