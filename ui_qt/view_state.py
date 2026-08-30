"""Persistence helpers for expert display preferences.

The scoring configuration and the display configuration deliberately use the
same small settings store but separate key namespaces.  These helpers keep Qt
binary state opaque, versioned and local to the widget that owns it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from PySide6.QtCore import QByteArray, QPoint, Qt, QTimer
from PySide6.QtWidgets import QMenu, QSplitter, QTableView


class SettingsLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...

    def update(self, values: dict[str, object]) -> None: ...


def _encoded(state: QByteArray) -> str:
    return bytes(state.toBase64()).decode("ascii")


def _decoded(value: str) -> QByteArray:
    return QByteArray.fromBase64(value.encode("ascii"))


def _debounced(owner, callback: Callable[[], None], delay_ms: int = 220) -> Callable:
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.timeout.connect(callback)
    timers = getattr(owner, "_view_state_timers", None)
    if timers is None:
        timers = []
        setattr(owner, "_view_state_timers", timers)
    timers.append(timer)

    def schedule(*_args: object) -> None:
        timer.start(delay_ms)

    return schedule


def bind_collapsible_state(
    section,
    store: SettingsLike,
    key: str,
    *,
    default_expanded: bool = False,
) -> None:
    stored = store.get(key, "")
    expanded = stored == "1" if stored in {"0", "1"} else default_expanded
    section.toggle.setChecked(expanded)
    section.toggle.toggled.connect(
        lambda checked: store.update({key: "1" if checked else "0"})
    )


def bind_splitter_state(
    splitter: QSplitter,
    store: SettingsLike,
    key: str,
    default_sizes: Iterable[int],
) -> None:
    restored = False
    stored = store.get(key, "")
    if stored:
        restored = bool(splitter.restoreState(_decoded(stored)))
    if not restored:
        splitter.setSizes([int(value) for value in default_sizes])

    save = _debounced(
        splitter,
        lambda: store.update({key: _encoded(splitter.saveState())}),
    )
    splitter.splitterMoved.connect(save)


def bind_table_view_state(
    table: QTableView,
    store: SettingsLike,
    key: str,
    *,
    default_hidden: Iterable[int] = (),
) -> Callable[[], None]:
    """Restore header layout and add a right-click column visibility menu."""

    header = table.horizontalHeader()
    header.setSectionsMovable(True)
    restored = False
    stored = store.get(key, "")
    if stored:
        restored = bool(header.restoreState(_decoded(stored)))
    if not restored:
        for index in default_hidden:
            if 0 <= int(index) < table.model().columnCount():
                table.setColumnHidden(int(index), True)

    def save_now() -> None:
        store.update({key: _encoded(header.saveState())})

    schedule_save = _debounced(header, save_now)
    header.sectionResized.connect(schedule_save)
    header.sectionMoved.connect(schedule_save)
    header.sortIndicatorChanged.connect(schedule_save)

    header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def show_columns_menu(position: QPoint) -> None:
        menu = QMenu(header)
        visible_count = sum(
            not table.isColumnHidden(index)
            for index in range(table.model().columnCount())
        )
        for logical_index in range(table.model().columnCount()):
            title = str(
                table.model().headerData(
                    logical_index,
                    Qt.Orientation.Horizontal,
                    Qt.ItemDataRole.DisplayRole,
                )
                or logical_index + 1
            )
            action = menu.addAction(title)
            action.setCheckable(True)
            visible = not table.isColumnHidden(logical_index)
            action.setChecked(visible)
            action.setEnabled(not (visible and visible_count <= 1))
            action.toggled.connect(
                lambda checked, index=logical_index: (
                    table.setColumnHidden(index, not checked),
                    save_now(),
                )
            )
        menu.exec(header.mapToGlobal(position))

    header.customContextMenuRequested.connect(show_columns_menu)
    return save_now
