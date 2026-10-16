"""Named, illustrated collection choices; numeric keys stay inside records."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLayout, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from uma_workbench.collection import collection_facets
from ui_qt.collection_filters import CollectionFilters

from ui_qt.asset_catalog import support_card_image_url, trainee_image_url
from ui_qt.avatar import circular_avatar
from ui_qt.components import muted_label
from ui_qt.image_assets import ImageRepository

STAT_LABELS = (("speed", "Speed"), ("stamina", "Stamina"), ("power", "Power"), ("guts", "Guts"), ("wiz", "Wit"))
SORT_OPTIONS = {
    "trainees": (("Name A–Z", "name_asc"), ("Name Z–A", "name_desc"),
        ("Rarity: highest", "rarity_desc"), ("Rarity: lowest", "rarity_asc"), ("Awakening: highest", "awakening_desc")),
    "supports": (("Name A–Z", "name_asc"), ("Name Z–A", "name_desc"),
        ("Rarity: highest", "rarity_desc"), ("Rarity: lowest", "rarity_asc"),
        ("Level: highest", "level_desc"), ("Level: lowest", "level_asc"), ("Limit breaks: most", "limit_desc")),
    "veterans": (("Name A–Z", "name_asc"), ("Name Z–A", "name_desc"), ("Rating: highest", "rating_desc"),
        ("Newest first", "newest"), ("Oldest first", "oldest"),
        *((label + ": highest", key + "_desc") for key, label in STAT_LABELS),
        ("Blue sparks: most stars", "blue_desc"), ("Aptitude sparks: most stars", "pink_desc")),
}


def display_name(master, kind, identity):
    name = master.support_name(identity) if kind == "supports" else master.card_name(identity)
    if name.startswith(("Trainee #", "Support #")):
        return "Support card" if kind == "supports" else "Trainee"
    return name


def name_parts(name):
    match = re.fullmatch(r"\[(.*?)\]\s*(.+)", name)
    return (match[2], match[1]) if match else (name, "")


def character_name(master, kind, identity):
    return name_parts(display_name(master, kind, identity))[0]


def describe_records(master, kind, records, *, borrowed=False):
    result = []
    for record in records:
        identity = record.get("support_card_id") if kind == "supports" else record.get("card_id")
        facets = collection_facets(master, kind, record)
        name = display_name(master, kind, identity)
        character, costume = name_parts(name)
        if kind == "supports" and (77, int(identity)) in master.names:
            character = master.names[(77, int(identity))]
            costume = master.names.get((76, int(identity)), "").strip("[]")
        url = support_card_image_url(identity) if kind == "supports" else trainee_image_url(identity)
        if kind == "supports":
            level = master.support_level(record)
            rarity = master.supports.get(int(identity), {}).get("rarity")
            badge = {1: "R", 2: "SR", 3: "SSR"}.get(rarity, "Support")
            limit = int(record.get("limit_break_count", 0))
            summary = f"{facets['support_type']} · Borrowed support" if borrowed else f"Level {level if level is not None else 'unknown'} · {'MLB' if limit == 4 else str(limit) + '/4 limit breaks'}"
        elif kind == "trainees":
            badge = f"{record.get('rarity', '?')}★"
            summary = f"Awakening level {record.get('talent_level', '?')}"
        else:
            badge = "Locked" if record.get("is_locked") else "Veteran"
            summary = " · ".join(f"{label} {record.get(key, '?')}" for key, label in STAT_LABELS[:3])
        result.append({"name": name, "character": character, "costume": costume,
            "summary": summary, "badge": badge, "url": url,
            "sort_values": {"rarity": rarity if kind == "supports" else record.get("rarity"),
                "level": level if kind == "supports" else None,
                "awakening": record.get("talent_level"), "limit": record.get("limit_break_count"),
                "rating": record.get("rank_score"), "time": record.get("create_time", record.get("register_time")),
                **{key: record.get(key) for key, _label in STAT_LABELS},
                "blue": sum(int(master.factors.get(int(f.get("factor_id", 0)), {}).get("rarity", 0))
                    for f in record.get("factor_info_array", []) if master.factors.get(int(f.get("factor_id", 0)), {}).get("factor_type") == 1),
                "pink": sum(int(master.factors.get(int(f.get("factor_id", 0)), {}).get("rarity", 0))
                    for f in record.get("factor_info_array", []) if master.factors.get(int(f.get("factor_id", 0)), {}).get("factor_type") == 2)},
            "kind": kind, "record": record, "borrowed": borrowed, "facets": facets})
    return sorted(result, key=lambda item: (item["character"].casefold(), item["name"].casefold(),
        -int(item["record"].get("rank_score", 0))))


def sort_records(records, order="name_asc"):
    records = sorted(records, key=lambda row: (row["character"].casefold(), row["name"].casefold()))
    if order.startswith("name_"):
        return list(reversed(records)) if order == "name_desc" else records
    key = "time" if order in ("newest", "oldest") else order.rsplit("_", 1)[0]
    known = [row for row in records if row.get("sort_values", {}).get(key) is not None]
    unknown = [row for row in records if row.get("sort_values", {}).get(key) is None]
    return sorted(known, key=lambda row: float(row["sort_values"][key]),
        reverse=order.endswith("_desc") or order == "newest") + unknown


class ArtworkLabel(QLabel):
    def __init__(self, repository: ImageRepository, url, name, *, size=112, support=False, parent=None):
        super().__init__(parent)
        self.repository, self.url, self.size, self.support = repository, url, size, support
        self.setFixedSize(size, size + 28 if support else size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("portraitPlaceholder")
        self.setText(" ".join(word[0] for word in name.replace("[", "").split()[:2]).upper() or "UMA")
        self.setAccessibleName(f"Portrait of {name}")
        self.setToolTip(name)
        repository.image_ready.connect(self._ready)
        repository.image_failed.connect(self._failed)
        source = repository.pixmap(url)
        if source is not None:
            self._show(source)

    def _ready(self, url, source):
        if url == self.url and isinstance(source, QPixmap):
            self._show(source)

    def _show(self, source):
        pixmap = source.scaled(self.size, self.size + 28, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation) if self.support else circular_avatar(source, self.size)
        self.setPixmap(pixmap)

    def _failed(self, url):
        if url == self.url:
            self.setToolTip("Artwork unavailable. Names and collection data are still available.")


class CollectionTile(QFrame):
    activated = Signal(object)

    def __init__(self, descriptor, repository, action="View", parent=None):
        super().__init__(parent)
        self.descriptor = descriptor
        self.setObjectName("collectionTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(195)
        self.setMaximumWidth(290)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)
        head = QHBoxLayout()
        head.addStretch()
        head.addWidget(ArtworkLabel(repository, descriptor["url"], descriptor["name"],
            size=96 if descriptor["kind"] == "supports" else 112, support=descriptor["kind"] == "supports"))
        head.addStretch()
        layout.addLayout(head)
        title = QLabel(descriptor["character"])
        title.setWordWrap(True)
        title.setObjectName("cardName")
        title.setMinimumHeight(26)
        layout.addWidget(title)
        costume = muted_label(descriptor["costume"])
        costume.setMinimumHeight(34)
        layout.addWidget(costume)
        badge = QLabel(descriptor["badge"])
        badge.setObjectName("pillAccent")
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        summary = muted_label(descriptor["summary"])
        summary.setMinimumHeight(36)
        layout.addWidget(summary)
        if descriptor["kind"] == "veterans":
            extra = " · ".join(f"{label} {descriptor['record'].get(key, 0)}" for key, label in STAT_LABELS[3:])
            layout.addWidget(muted_label(extra))
            facets = descriptor.get("facets", {})
            sparks = [facets["spark_labels"][key] + " " + "★" * min(3, stars) for key, stars in facets.get("sparks", {}).items()
                if key in facets.get("spark_labels", {}) and (key.startswith("Blue:") or key.startswith("Pink:"))]
            if sparks:
                layout.addWidget(muted_label(" · ".join(sparks)))
        layout.addStretch()
        button = QPushButton(action)
        button.setAccessibleName(f"{action} {descriptor['name']}")
        button.clicked.connect(lambda: self.activated.emit(descriptor))
        layout.addWidget(button)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.descriptor)
        else:
            super().mouseReleaseEvent(event)


class CollectionGallery(QWidget):
    activated = Signal(object)
    PAGE_SIZE = 24

    def __init__(self, repository, action="View", parent=None):
        super().__init__(parent)
        self.repository, self.action = repository, action
        self.records, self.page, self.selected = [], 0, None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        row = QHBoxLayout()
        self.previous, self.next = QPushButton("Previous"), QPushButton("Next")
        self.page_label = muted_label("")
        self.previous.clicked.connect(lambda: self._page(-1))
        self.next.clicked.connect(lambda: self._page(1))
        row.addWidget(self.previous)
        row.addWidget(self.page_label, 1)
        row.addWidget(self.next)
        layout.addLayout(row)
        self._columns = 0

    def rowCount(self):
        return len(self.records)

    def set_records(self, records):
        self.records, self.page, self.selected = list(records), 0, None
        self._render()

    def _page(self, direction):
        self.page += direction
        self._render()
        self.scroll.verticalScrollBar().setValue(0)

    def _choose(self, descriptor):
        self.selected = descriptor["record"]
        self.activated.emit(descriptor)

    def _render(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._columns = max(1, min(5, max(1, self.scroll.viewport().width() - 24) // 230))
        start = self.page * self.PAGE_SIZE
        visible = self.records[start:start + self.PAGE_SIZE]
        for index, record in enumerate(visible):
            tile = CollectionTile(record, self.repository, self.action)
            tile.activated.connect(self._choose)
            self.grid.addWidget(tile, index // self._columns, index % self._columns)
        if not visible:
            message = muted_label("No matching collection items. Import your collection, or clear the search.")
            message.setMinimumHeight(140)
            self.grid.addWidget(message, 0, 0)
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(start + self.PAGE_SIZE < len(self.records))
        self.page_label.setText(f"{start + 1}–{start + len(visible)} of {len(self.records)}" if visible else "No items")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = max(1, min(5, max(1, self.scroll.viewport().width() - 24) // 230))
        if self._columns != columns:
            self._render()


class CollectionPicker(QDialog):
    def __init__(self, title, records, repository, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(920, 650)
        self.choice = None
        self.records = records
        layout = QVBoxLayout(self)
        header = QLabel(title)
        header.setObjectName("sectionTitle")
        layout.addWidget(header)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by character or card name")
        self.search.setAccessibleName("Search collection names")
        from PySide6.QtWidgets import QComboBox
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Sort collection choices")
        kind = records[0]["kind"] if records else "trainees"
        for label, code in SORT_OPTIONS[kind]:
            self.sort.addItem(label, code)
        filters.addWidget(self.sort)
        layout.addLayout(filters)
        self.facets = CollectionFilters()
        self.facets.set_records(kind, records)
        self.facets.changed.connect(self._refresh)
        layout.addWidget(self.facets)
        self.gallery = CollectionGallery(repository, "Choose")
        layout.addWidget(self.gallery, 1)
        self.gallery.set_records(records)
        self.gallery.activated.connect(self._choose)
        self.search.textChanged.connect(self._refresh)
        self.sort.currentIndexChanged.connect(self._refresh)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh(self, *_):
        text = self.search.text().casefold()
        self.gallery.set_records(sort_records([row for row in self.records
            if text in (row["name"] + " " + row["summary"]).casefold() and self.facets.accepts(row)], self.sort.currentData()))

    def _choose(self, record):
        self.choice = record
        self.accept()


class NamedChoice(QWidget):
    changed = Signal()

    def __init__(self, title, records, repository, parent=None):
        super().__init__(parent)
        self.title, self.records, self.repository = title, records, repository
        self.choice = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("None chosen")
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(100)
        self.label.setObjectName("muted")
        layout.addWidget(self.label, 1)
        self.choose_button = QPushButton("Choose…")
        self.choose_button.setAccessibleName(title)
        self.choose_button.clicked.connect(self.choose)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(lambda: self.set_choice(None))
        layout.addWidget(self.choose_button)
        layout.addWidget(self.clear_button)
        self.portrait = None

    def choose(self):
        dialog = CollectionPicker(self.title, self.records, self.repository, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_choice(dialog.choice)

    def set_choice(self, descriptor):
        self.choice = descriptor
        if self.portrait:
            self.layout().removeWidget(self.portrait)
            self.portrait.deleteLater()
            self.portrait = None
        self.label.setText(descriptor["character"] + "\n" +
            (descriptor["costume"] + " · " if descriptor["costume"] else "") + descriptor["summary"]
            if descriptor else "None chosen")
        if descriptor:
            self.portrait = ArtworkLabel(self.repository, descriptor["url"], descriptor["name"], size=48,
                support=descriptor["kind"] == "supports")
            self.layout().insertWidget(0, self.portrait)
        self.changed.emit()

    def identity(self):
        if not self.choice:
            return None
        row = self.choice["record"]
        return row.get("support_card_id", row.get("trained_chara_id", row.get("card_id")))
