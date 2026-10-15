"""Illustrated setup comparisons for the requirement-based planner."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from ui_qt.collection_widgets import ArtworkLabel, describe_records
from ui_qt.avatar import circular_avatar
from ui_qt.components import muted_label
from uma_workbench.planning import GRADE_LABELS


class SetupResults(QWidget):
    use_requested = Signal(object)

    def __init__(self, master, repository, parent=None):
        super().__init__(parent)
        self.master, self.repository = master, repository
        self.report = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.summary = muted_label("Set skills and aptitudes, then choose ‘Find setups in my collection’. A trainee is optional.")
        root.addWidget(self.summary)
        splitter = self.splitter = QSplitter()
        root.addWidget(splitter, 1)
        self.list = QListWidget()
        self.list.setAccessibleName("Suggested collection setups")
        self.list.setIconSize(QSize(54, 54))
        self.list.setWordWrap(True)
        self.list.setMinimumWidth(250)
        splitter.addWidget(self.list)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        splitter.addWidget(self.scroll)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        self.use_button = QPushButton("Use this setup")
        self.use_button.setObjectName("primary")
        self.use_button.setEnabled(False)
        root.addWidget(self.use_button)
        self.use_button.clicked.connect(self._use)
        self.list.currentRowChanged.connect(self._preview)
        self.repository.image_ready.connect(self._art_ready)

    def set_report(self, report):
        self.clear()
        self.report = report
        for row in report["setups"]:
            descriptor = describe_records(self.master, "trainees", [row["trainee"]])[0]
            skills = len(row["skills"]) - len(row["missing_skills"])
            fit = "Aptitudes fit" if not row["aptitude_gap"] else "Aptitudes need work"
            parents = " · ".join(describe_records(self.master, "veterans", [parent])[0]["character"] for parent in row["parents"])
            text = f"{descriptor['character']}\n{descriptor['costume']}\n{fit} · {skills}/{len(row['skills'])} skill sources\n{parents}"
            item = QListWidgetItem(text)
            item.setSizeHint(QSize(250, 112))
            item.setToolTip(text)
            item.setData(Qt.ItemDataRole.UserRole, (row, descriptor))
            self.list.addItem(item)
            source = self.repository.pixmap(descriptor["url"])
            if source:
                item.setIcon(QIcon(circular_avatar(source, 54)))
        self.summary.setText(f"Compared {report['trainees_examined']} owned trainees and their possible collection setups. "
            + ("Showing the strongest shortlist. " if report["shortlisted"] else "")
            + "Order: aptitude fit, skill sources, complete lineups, trainee skill access, growth, then support levels.")
        if not report["setups"]:
            self.summary.setText("No legal setup found with the fixed choices. Clear the trainee, parent or support choices to widen the search.")
            self.use_button.setEnabled(False)
        else:
            self.splitter.setSizes([300, 650])
            self.list.setCurrentRow(0)

    def clear(self):
        self.report = None
        self.list.clear()
        self.use_button.setEnabled(False)
        previous = self.scroll.takeWidget()
        if previous:
            previous.deleteLater()

    def _art_ready(self, url, pixmap):
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.ItemDataRole.UserRole)[1]["url"] == url:
                item.setIcon(QIcon(circular_avatar(pixmap, 54)))

    def _preview(self, index):
        if index < 0:
            return
        row, descriptor = self.list.item(index).data(Qt.ItemDataRole.UserRole)
        previous = self.scroll.takeWidget()
        if previous:
            previous.deleteLater()
        body = QWidget()
        layout = QVBoxLayout(body)
        head = QHBoxLayout()
        head.addWidget(ArtworkLabel(self.repository, descriptor["url"], descriptor["name"], size=76))
        title = QLabel(descriptor["character"] + "\n" + descriptor["costume"])
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        head.addWidget(title, 1)
        layout.addLayout(head)
        for apt in row["aptitudes"]:
            start = GRADE_LABELS.get(apt["initial"], "Unknown")
            base = GRADE_LABELS.get(apt["base"], "Unknown")
            detail = f"{apt['label']}: {base} → {start} at career start · target {GRADE_LABELS[apt['target']]} · {apt['stars']} inheritance stars"
            if apt["needs_s_roll"]:
                detail += " · S needs an in-career inheritance roll"
            layout.addWidget(muted_label(detail))
        if row["slot_gap"]:
            layout.addWidget(muted_label("This lineup is incomplete: more distinct parents or support characters are needed."))
        layout.addWidget(QLabel("Parents"))
        parent_grid = QGridLayout()
        for index, parent in enumerate(row["parents"]):
            self._member(parent_grid, index, describe_records(self.master, "veterans", [parent])[0])
        layout.addLayout(parent_grid)
        layout.addWidget(QLabel("Support deck"))
        support_grid = QGridLayout()
        for index, support in enumerate(row["supports"]):
            self._member(support_grid, index, describe_records(self.master, "supports", [support], borrowed=bool(support.get("borrowed")))[0])
        layout.addLayout(support_grid)
        layout.addWidget(QLabel("How the selected skills can be obtained"))
        for skill in row["skills"]:
            name = self.master.names.get((47, skill["skill_id"]), "Skill name unavailable")
            sources = []
            for provider in skill["sources"]:
                kind = provider["kind"]
                if kind == "trainee":
                    sources.append("trainee's available skills")
                elif kind == "inheritance":
                    sources.append(self.master.card_name(provider["card_id"]) + " lineage spark")
                else:
                    sources.append(self.master.support_name(provider["support_card_id"]) + (" event" if kind == "support_event" else " hint pool"))
            explanation = "Does not activate for the selected race/style" if skill["incompatible"] else ("; ".join(sources) or "No known source in this setup")
            layout.addWidget(muted_label(name + " — " + explanation))
        layout.addWidget(muted_label("Hints, event rewards and inheritance are possibilities. Choices can end an event chain or conflict with another reward. Stat targets still need a successful career."))
        layout.addStretch()
        self.scroll.setWidget(body)
        self.use_button.setEnabled(True)

    def _member(self, grid, index, descriptor):
        card = QFrame()
        card.setObjectName("subtlePanel")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(ArtworkLabel(self.repository, descriptor["url"], descriptor["name"], size=48,
            support=descriptor["kind"] == "supports"))
        layout.addWidget(muted_label(descriptor["character"] + "\n" + descriptor["summary"]), 1)
        grid.addWidget(card, index // 2, index % 2)

    def _use(self):
        item = self.list.currentItem()
        if item:
            self.use_requested.emit(item.data(Qt.ItemDataRole.UserRole)[0])
