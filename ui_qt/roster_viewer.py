"""Native roster cards, veteran details and a local lineage planner."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QProgressBar, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

from ui_qt.collection_filters import CollectionFilters
from ui_qt.collection_widgets import (
    ArtworkLabel, CollectionGallery, NamedChoice, SORT_OPTIONS, STAT_LABELS,
    describe_records, recorded_datetime, sort_records,
)
from ui_qt.components import muted_label
from ui_qt.image_assets import ImageRepository
from ui_qt.theme import SPARK_COLORS
from uma_workbench.planning import APTITUDES, GRADE_LABELS
from uma_workbench.roster_viewer import (
    immediate_ancestors, lineage_preview, owned_veterans, selection_for_plan,
)


def _copy_label(record):
    value = recorded_datetime(record.get("create_time", record.get("register_time")))
    date = value.strftime("%d %b %Y, %H:%M") if value else "Date not recorded"
    rating = record.get("rank_score")
    return (f"Rating {rating:,} · " if isinstance(rating, (int, float)) else "") + date


def _spark_grid(values, labels):
    body = QWidget()
    grid = QGridLayout(body)
    grid.setContentsMargins(0, 0, 0, 0)
    styles = {"Blue": "blue_stat", "Pink": "red_aptitude", "Green": "unique", "Skill": "white_skill", "Race": "white_race", "Scenario": "scenario"}
    for i, (key, stars) in enumerate(sorted(values.items())):
        bg, border, fg = SPARK_COLORS[styles.get(key.split(":", 1)[0], "other")]
        label = QLabel(f"{labels.get(key, 'Spark name unavailable')} · {stars}★")
        label.setWordWrap(True)
        label.setStyleSheet(f"background:{bg};color:{fg};border:1px solid {border};border-radius:5px;padding:6px;")
        grid.addWidget(label, i // 2, i % 2)
    if not values:
        grid.addWidget(muted_label("No sparks recorded."), 0, 0)
    return body


def _lineage_card(master, images, record, role):
    card = QFrame()
    card.setObjectName("collectionTile")
    root = QVBoxLayout(card)
    root.addWidget(muted_label(role))
    if not record or not record.get("card_id"):
        root.addWidget(QLabel("Not recorded"))
        return card
    descriptor = describe_records(master, "veterans", [record])[0]
    row = QHBoxLayout()
    row.addWidget(ArtworkLabel(images, descriptor["url"], descriptor["name"], size=48))
    name = QLabel(descriptor["name"])
    name.setWordWrap(True)
    row.addWidget(name, 1)
    root.addLayout(row)
    facets = descriptor["facets"]
    root.addWidget(_spark_grid(facets["sparks"], facets["spark_labels"]))
    return card


def _family(master, images, veteran):
    body = QWidget()
    grid = QGridLayout(body)
    grid.addWidget(_lineage_card(master, images, veteran, "This veteran"), 0, 0, 1, 2)
    snapshots = {row.get("position_id"): row for row in veteran.get("succession_chara_array", [])}
    for column, position in enumerate((10, 20)):
        grid.addWidget(_lineage_card(master, images, snapshots.get(position), f"Parent {column + 1}"), 1, column)
        for offset in (1, 2):
            grid.addWidget(_lineage_card(master, images, snapshots.get(position + offset), f"Grandparent {column * 2 + offset}"), 1 + offset, column)
    return body


class VeteranDetails(QDialog):
    plan_requested = Signal(object)
    parent_requested = Signal(int, object)

    def __init__(self, master, images, descriptor, parent=None):
        super().__init__(parent)
        record = descriptor["record"]
        self.setWindowTitle(descriptor["name"])
        self.resize(840, 690)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        overview = QWidget()
        layout = QVBoxLayout(overview)
        head = QHBoxLayout()
        head.addWidget(ArtworkLabel(images, descriptor["url"], descriptor["name"], size=112))
        copy = QVBoxLayout()
        title = QLabel(descriptor["name"])
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(muted_label(_copy_label(record)))
        copy.addWidget(muted_label("Borrowed veteran" if descriptor["borrowed"] else "Your veteran"))
        head.addLayout(copy, 1)
        layout.addLayout(head)
        stats = QGridLayout()
        for i, (key, label) in enumerate(STAT_LABELS):
            value = record.get(key)
            stats.addWidget(QLabel(label), i, 0)
            bar = QProgressBar()
            bar.setRange(0, max(1200, int(value or 0)))
            bar.setValue(int(value or 0))
            bar.setFormat(str(value) if value is not None else "Not recorded")
            stats.addWidget(bar, i, 1)
        layout.addLayout(stats)
        aptitudes = QGridLayout()
        for i, (key, label, _group) in enumerate(APTITUDES):
            text = QLabel(f"{label}  {GRADE_LABELS.get(record.get(key), '—')}")
            text.setObjectName("pillAccent" if record.get(key, 0) >= 7 else "muted")
            aptitudes.addWidget(text, i // 2, i % 2)
        layout.addLayout(aptitudes)
        layout.addWidget(QLabel("This veteran’s sparks"))
        facets = descriptor["facets"]
        layout.addWidget(_spark_grid(facets["sparks"], facets["spark_labels"]))
        layout.addStretch()
        for body, title in ((overview, "Overview"), (_family(master, images, record), "Legacy")):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(body)
            tabs.addTab(scroll, title)
        skills = QListWidget()
        for row in record.get("skill_array", []):
            skills.addItem(master.names.get((47, row["skill_id"]), "Skill name unavailable — choose the game data file in Setup"))
        if not skills.count():
            skills.addItem("No learned skills recorded.")
        tabs.addTab(skills, "Learned skills")
        actions = QHBoxLayout()
        plan = QPushButton("Plan another career")
        plan.setObjectName("primary")
        plan.clicked.connect(lambda: self._plan(record))
        actions.addWidget(plan)
        for i in range(2):
            button = QPushButton(f"Use as parent {i + 1}")
            button.setEnabled(not descriptor["borrowed"])
            button.clicked.connect(lambda _=False, slot=i: self._parent(slot, descriptor))
            actions.addWidget(button)
        root.addLayout(actions)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        root.addWidget(close)

    def _plan(self, record):
        self.accept()
        self.plan_requested.emit(record)

    def _parent(self, slot, descriptor):
        self.accept()
        self.parent_requested.emit(slot, descriptor)


class RosterViewer(QWidget):
    plan_requested = Signal(object)

    def __init__(self, store, master, images=None, parent=None):
        super().__init__(parent)
        self.store, self.master = store, master
        self.images = images or ImageRepository(parent=self)
        self._refreshing = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        browser = QWidget()
        layout = QVBoxLayout(browser)
        layout.addWidget(muted_label("Browse a veteran to see stats, skills, sparks and ancestry, or add it to your lineage plan."))
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a veteran by character or outfit")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search roster")
        row.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Sort roster")
        for label, code in SORT_OPTIONS["veterans"]:
            self.sort.addItem(label, code)
        self.sort.setCurrentIndex(max(0, self.sort.findData(store.setting("native_roster_sort", "name_asc"))))
        row.addWidget(self.sort)
        new = QPushButton("New career plan")
        new.setObjectName("primary")
        new.clicked.connect(lambda: self.plan_requested.emit(None))
        row.addWidget(new)
        layout.addLayout(row)
        self.filters = CollectionFilters()
        layout.addWidget(self.filters)
        self.gallery = CollectionGallery(self.images, "View veteran")
        layout.addWidget(self.gallery, 1)
        self.tabs.addTab(browser, "Veterans")
        planner = self.planner = QScrollArea()
        planner.setWidgetResizable(True)
        body = QWidget()
        planner.setWidget(body)
        self.planner_layout = QVBoxLayout(body)
        self.planner_layout.addWidget(muted_label("Choose a trainee and two parents, or leave choices open and find setups from the skills and aptitudes you want."))
        self.target = NamedChoice("Choose trainee (optional)", [], self.images)
        self.target.label.setText("Compare all my trainees")
        self.planner_layout.addWidget(QLabel("Trainee"))
        self.planner_layout.addWidget(self.target)
        self.parents = [NamedChoice(f"Choose parent {i + 1}", [], self.images) for i in range(2)]
        for i, picker in enumerate(self.parents):
            self.planner_layout.addWidget(QLabel(f"Parent {i + 1}"))
            self.planner_layout.addWidget(picker)
        self.status = muted_label("")
        self.planner_layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.plan_button = QPushButton("Find setups / save plan")
        self.plan_button.setObjectName("primary")
        self.plan_button.clicked.connect(self.plan_target)
        actions.addWidget(self.plan_button)
        self.clear_button = QPushButton("Clear lineup")
        self.clear_button.clicked.connect(self.clear_lineup)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        self.planner_layout.addLayout(actions)
        self.preview = QWidget()
        self.planner_layout.addWidget(self.preview)
        self.planner_layout.addStretch()
        self.tabs.addTab(planner, "Lineage planner")
        self.search.textChanged.connect(self._filter)
        self.sort.currentIndexChanged.connect(self._filter)
        self.filters.changed.connect(self._filter)
        self.gallery.activated.connect(self.open_veteran)
        for picker in [self.target, *self.parents]:
            picker.changed.connect(self._lineup_changed)
        self.refresh(saved=store.setting("native_roster_lineup", {}))

    def refresh(self, *, saved=None):
        selection = saved if saved is not None else self.selection()
        self._refreshing = True
        self.records = describe_records(self.master, "veterans", self.store.entities("veterans"))
        owned_ids = {int(row["trained_chara_id"]) for row in owned_veterans(self.store)}
        for descriptor in self.records:
            descriptor["borrowed"] = int(descriptor["record"]["trained_chara_id"]) not in owned_ids
            descriptor["summary"] += "\n" + _copy_label(descriptor["record"])
            if descriptor["borrowed"]:
                descriptor["badge"] = "Borrowed"
        self.filters.set_records("veterans", self.records)
        self.target.records = describe_records(self.master, "trainees", self.store.entities("trainees"))
        self.target.set_choice(next((row for row in self.target.records if row["record"]["card_id"] == selection.get("target")), None))
        for i, picker in enumerate(self.parents):
            picker.records = [row for row in self.records if not row["borrowed"]]
            ids = selection.get("parent_ids", [])
            identity = ids[i] if i < len(ids) else None
            picker.set_choice(next((row for row in picker.records if row["record"]["trained_chara_id"] == identity), None))
        self._refreshing = False
        self._filter()
        self._lineup_changed()

    def _filter(self, *_):
        query = self.search.text().casefold()
        self.store.set_setting("native_roster_sort", self.sort.currentData())
        self.gallery.set_records(sort_records([row for row in self.records
            if query in (row["name"] + " " + row["summary"]).casefold() and self.filters.accepts(row)], self.sort.currentData()))

    def selection(self):
        return {"target": self.target.identity(), "parent_ids": [picker.identity() for picker in self.parents]}

    def clear_lineup(self):
        self._refreshing = True
        for picker in [self.target, *self.parents]:
            picker.set_choice(None)
        self._refreshing = False
        self._lineup_changed()

    def _lineup_changed(self):
        if self._refreshing:
            return
        selection = self.selection()
        if self.target.choice is None:
            self.target.label.setText("Compare all my trainees")
        self.store.set_setting("native_roster_lineup", selection)
        try:
            selection_for_plan(selection, self.store, self.master)
        except ValueError as exc:
            self.status.setText(str(exc))
            self.plan_button.setEnabled(False)
            self._show_preview(None)
            return
        self.plan_button.setEnabled(True)
        self.status.setText("Your selections stay here between sessions. Find setups carries these exact parent copies into a career plan.")
        target = self.target.choice["record"] if self.target.choice else None
        parents = [picker.choice["record"] for picker in self.parents if picker.choice]
        self._show_preview(lineage_preview(self.master, target, parents))

    def _show_preview(self, preview):
        self.planner_layout.removeWidget(self.preview)
        self.preview.hide()
        self.preview.deleteLater()
        self.preview = QWidget()
        layout = QVBoxLayout(self.preview)
        layout.setContentsMargins(0, 8, 0, 0)
        if preview is not None:
            affinity = preview["affinity"]
            if affinity:
                score = affinity["total"] if affinity["total"] is not None else affinity["base"]
                suffix = "" if affinity["complete"] else " · Partial lineage"
                layout.addWidget(QLabel(f"Compatibility: {score}{suffix}"))
                layout.addWidget(muted_label(f"Character compatibility {affinity['base']} · " +
                    (f"Shared G1 bonus {affinity['g1_bonus']}" if affinity["g1_bonus"] is not None else "G1 records incomplete; race bonuses are not included")))
            else:
                layout.addWidget(muted_label("Choose a trainee and parents to compare compatibility. The game data file supplies relationship values."))
            if self.target.choice:
                layout.addWidget(QLabel("Starting aptitudes"))
                grid = QGridLayout()
                for i, row in enumerate(preview["aptitudes"]):
                    base = GRADE_LABELS.get(row["base"], "—")
                    initial = GRADE_LABELS.get(row["initial"], "—")
                    grid.addWidget(QLabel(f"{row['label']}: {base} → {initial} · {row['stars']}★"), i // 2, i % 2)
                layout.addLayout(grid)
                layout.addWidget(muted_label("Starting aptitude is capped at A. Reaching S needs an inheritance roll during the career."))
            if any(picker.choice for picker in self.parents):
                layout.addWidget(QLabel("Combined stat and aptitude sparks"))
                main = {key: stars for key, stars in preview["sparks"].items() if key.startswith(("Blue:", "Pink:"))}
                layout.addWidget(_spark_grid(main, preview["spark_labels"]))
                more = {key: stars for key, stars in preview["sparks"].items() if key not in main}
                if more:
                    self._disclosure(layout, f"More sparks ({len(more)})", _spark_grid(more, preview["spark_labels"]))
            if preview["skills"]:
                hints = QListWidget()
                hints.setMinimumHeight(160)
                hints.setMaximumHeight(240)
                for identity in preview["skills"]:
                    hints.addItem(self.master.names.get((47, identity), "Skill name unavailable"))
                self._disclosure(layout, f"Possible inherited skill hints ({len(preview['skills'])})", hints)
                layout.addWidget(muted_label("Sparks give a chance of a hint; learned parent skills alone are not a source."))
            branches = QGridLayout()
            for i, picker in enumerate(self.parents):
                if not picker.choice:
                    continue
                record = picker.choice["record"]
                branches.addWidget(_lineage_card(self.master, self.images, record, f"Parent {i + 1}"), 0, i)
                for j, ancestor in enumerate(immediate_ancestors(record)):
                    branches.addWidget(_lineage_card(self.master, self.images, ancestor, f"Grandparent {i * 2 + j + 1}"), j + 1, i)
            layout.addLayout(branches)
        self.planner_layout.insertWidget(self.planner_layout.count() - 1, self.preview)

    @staticmethod
    def _disclosure(layout, title, content):
        button = QPushButton(title)
        button.setCheckable(True)
        content.hide()
        button.toggled.connect(content.setVisible)
        layout.addWidget(button)
        layout.addWidget(content)

    def open_veteran(self, descriptor):
        dialog = VeteranDetails(self.master, self.images, descriptor, self)
        dialog.plan_requested.connect(self._plan_veteran)
        dialog.parent_requested.connect(self._use_parent)
        dialog.exec()

    def _use_parent(self, slot, descriptor):
        self.parents[slot].set_choice(descriptor)
        self.tabs.setCurrentWidget(self.planner)

    def _plan_veteran(self, record):
        owned = {row["card_id"] for row in self.store.entities("trainees")}
        self.plan_requested.emit({"card_id": record["card_id"], "lock_trainee": record["card_id"] in owned})

    def plan_target(self):
        try:
            runner = selection_for_plan(self.selection(), self.store, self.master)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.plan_requested.emit(runner)
