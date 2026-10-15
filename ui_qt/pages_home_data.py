from __future__ import annotations

from functools import partial
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from uma_legacy_linker.error_guidance import actionable_error
from ui_qt.components import PageHeader, PathPicker, StatusCard, muted_label, section_label
from ui_qt.context import AppContext
from uma_workbench.core import Store
from uma_legacy_linker.application import (
    CatalogRequest,
    ExtractRequest,
    LinkRequest,
    collection_size,
    latest_rankings_path,
    linked_data_freshness,
    linked_veterans_path,
    open_path,
    run_catalog,
    run_extract_and_link,
    run_link,
)


def _command_card(button: QPushButton) -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName("subtlePanel")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(7)
    detail = muted_label("")
    layout.addWidget(button)
    layout.addWidget(detail)
    layout.addStretch(1)
    return card, detail


class HomePage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context
        self.collection_store = Store()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        self.header = PageHeader("", "")
        root.addWidget(self.header)

        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        self.master_card = StatusCard("", "", "")
        self.collection_card = StatusCard("", "", "")
        self.results_card = StatusCard("", "", "")
        cards.addWidget(self.master_card, 0, 0)
        cards.addWidget(self.collection_card, 0, 1)
        cards.addWidget(self.results_card, 0, 2)
        cards.setColumnStretch(0, 1)
        cards.setColumnStretch(1, 1)
        cards.setColumnStretch(2, 1)
        root.addLayout(cards)

        action_panel = QFrame()
        action_panel.setObjectName("panel")
        action_layout = QVBoxLayout(action_panel)
        action_layout.setContentsMargins(18, 16, 18, 16)
        action_layout.setSpacing(10)
        self.quick_title = section_label("")
        self.quick_detail = muted_label("")
        buttons = QGridLayout()
        self.data_button = QPushButton("")
        self.data_button.setObjectName("primary")
        self.search_button = QPushButton("")
        self.transfer_button = QPushButton("")
        self.refresh_button = QPushButton("")
        buttons.addWidget(self.data_button, 0, 0)
        buttons.addWidget(self.search_button, 0, 1)
        buttons.addWidget(self.transfer_button, 0, 2)
        buttons.addWidget(self.refresh_button, 1, 2)
        for column in range(3):
            buttons.setColumnStretch(column, 1)
        action_layout.addWidget(self.quick_title)
        action_layout.addWidget(self.quick_detail)
        action_layout.addLayout(buttons)
        root.addWidget(action_panel)

        preview_panel = QFrame()
        preview_panel.setObjectName("panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(18, 16, 18, 16)
        self.preview_title = section_label("")
        self.preview_text = muted_label("")
        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_text)
        root.addWidget(preview_panel)
        root.addStretch(1)

        self.data_button.clicked.connect(lambda: self.navigate_requested.emit("setup"))
        self.search_button.clicked.connect(lambda: self.navigate_requested.emit("workbench"))
        self.transfer_button.clicked.connect(lambda: self.navigate_requested.emit("goals"))
        self.refresh_button.clicked.connect(self.refresh)
        self.context.configuration_changed.connect(self._schedule_refresh)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        self.retranslate()
        self.refresh()

    def _schedule_refresh(self) -> None:
        self._refresh_timer.start(120)


    def retranslate(self) -> None:
        t = self.context.t
        self.header.set_text(
            'Your training desk',
            'Your umas, support cards, race results and next career in one place.',
        )
        self.quick_title.setText('Start here')
        self.quick_detail.setText(
            'Set up names once, import your collection, then describe what your next runner needs.',
        )
        self.data_button.setText('1 · Set up and import')
        self.search_button.setText('2 · Browse my collection')
        self.transfer_button.setText('3 · Plan a career')
        self.refresh_button.setText(t('Refresh'))
        self.preview_title.setText('What can I do here?')
        self.preview_text.setText(
            'My collection: recognize trainees and supports by their pictures and names. Open a card to see its details.\n\n'
            'Team Trials: compare recorded results, then search any owned trainee as a replacement.\n\n'
            'Career plans: set skills and aptitudes, compare collection setups, then choose a trainee, parents and supports.\n\n'
            'Lineage linker: use the original inheritance search, lineage viewer and race planner.\n\n'
            'Calculators: budget skill points, awakening materials and Grand Concert songs inside the app.',
        )
        self.refresh()

    def refresh(self) -> None:
        t = self.context.t
        master = Path(self.context.master_path).expanduser()
        if master.is_file():
            self.master_card.set_content(
                'Character names', 'Ready', 'Game data file selected', "ok"
            )
        else:
            self.master_card.set_content(
                'Character names', 'Setup needed', 'Choose the game data file in Setup', "warning"
            )

        counts = self.collection_store.counts()
        if any(counts.get(key, 0) for key in ('trainees', 'supports', 'veterans')):
            self.collection_card.set_content(
                'My collection',
                f"{counts.get('trainees', 0)} trainees",
                f"{counts.get('supports', 0)} supports · {counts.get('veterans', 0)} veterans",
                "ok",
            )
        else:
            self.collection_card.set_content(
                'My collection',
                'Import needed',
                'Use Import my collection to add your exports',
                "warning",
            )
        goals = self.collection_store.goals()
        active = sum(goal['status'] in ('Planned', 'In progress') for goal in goals)
        self.results_card.set_content('Career plans', f'{active} to work on',
            'Choose a trainee to start your next plan' if not active else 'Open Career plans to see your next steps',
            'neutral')


class DataPage(QWidget):
    task_requested = Signal(object, str, object)

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context
        self._busy = False
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        self.header = PageHeader("", "")
        root.addWidget(self.header)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 17, 18, 17)
        panel_layout.setSpacing(11)
        self.files_title = section_label("")
        panel_layout.addWidget(self.files_title)

        self.master_label = QLabel("")
        self.master_picker = PathPicker(
            self.context.master_path,
            title='Select master.mdb',
            file_filter='master.mdb (*.mdb);;All files (*)',
        )
        self.data_label = QLabel("")
        self.data_picker = PathPicker(
            self.context.veterans_json_path,
            title='Select a collection export',
            file_filter='JSON (*.json);;All files (*)',
        )
        self.extractor_label = QLabel("")
        self.extractor_label.setWordWrap(True)
        self.extractor_picker = PathPicker(
            self.context.extractor_path,
            title='Select UmaExtractor or umadump',
            file_filter='Extractor (*.exe *.py);;All files (*)',
        )
        self.output_label = QLabel("")
        self.output_picker = PathPicker(
            self.context.output_dir,
            mode="directory",
            title='Select output directory',
        )
        sources = QGridLayout()
        sources.setHorizontalSpacing(14)
        sources.setVerticalSpacing(7)
        for index, (label, picker) in enumerate(
            (
                (self.master_label, self.master_picker),
                (self.data_label, self.data_picker),
                (self.extractor_label, self.extractor_picker),
                (self.output_label, self.output_picker),
            )
        ):
            row = (index // 2) * 2
            column = index % 2
            sources.addWidget(label, row, column)
            sources.addWidget(picker, row + 1, column)
            sources.setColumnStretch(column, 1)
        panel_layout.addLayout(sources)

        self.prepare_title = section_label("")
        panel_layout.addWidget(self.prepare_title)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.link_button = QPushButton("")
        self.force_link_button = QPushButton("")
        self.extract_button = QPushButton("")
        self.extract_button.setObjectName("primary")
        self.catalog_button = QPushButton("")
        self.open_button = QPushButton("")
        self.extract_card, self.extract_detail = _command_card(self.extract_button)
        self.link_card, self.link_detail = _command_card(self.link_button)
        actions.addWidget(self.extract_card, 1)
        actions.addWidget(self.link_card, 1)
        panel_layout.addLayout(actions)
        resources = QHBoxLayout()
        self.extractor_download = QPushButton("")
        self.umadump_link = QPushButton("")
        resources.addWidget(self.extractor_download)
        resources.addWidget(self.umadump_link)
        resources.addStretch(1)
        panel_layout.addLayout(resources)
        root.addWidget(panel)

        self.result_card = StatusCard("", "", "")
        root.addWidget(self.result_card)

        maintenance = QFrame()
        maintenance.setObjectName("subtlePanel")
        maintenance_layout = QVBoxLayout(maintenance)
        maintenance_layout.setContentsMargins(14, 11, 14, 11)
        maintenance_layout.setSpacing(7)
        self.maintenance_title = section_label("")
        self.maintenance_detail = muted_label("")
        maintenance_actions = QHBoxLayout()
        maintenance_actions.addWidget(self.catalog_button)
        maintenance_actions.addWidget(self.force_link_button)
        maintenance_actions.addStretch(1)
        maintenance_actions.addWidget(self.open_button)
        maintenance_layout.addWidget(self.maintenance_title)
        maintenance_layout.addWidget(self.maintenance_detail)
        maintenance_layout.addLayout(maintenance_actions)
        root.addWidget(maintenance)

        self.help_text = muted_label("")
        root.addWidget(self.help_text)
        root.addStretch(1)

        self.master_picker.path_changed.connect(
            lambda value: self.context.update_paths(master_path=value)
        )
        self.data_picker.path_changed.connect(
            lambda value: self.context.update_paths(veterans_json_path=value)
        )
        self.output_picker.path_changed.connect(
            lambda value: self.context.update_paths(output_dir=value)
        )
        self.extractor_picker.path_changed.connect(
            lambda value: self.context.update_paths(extractor_path=value)
        )
        self.link_button.clicked.connect(lambda: self.start_link())
        self.force_link_button.clicked.connect(lambda: self.start_link(force=True))
        self.extract_button.clicked.connect(self.start_extract)
        self.catalog_button.clicked.connect(self.start_catalog)
        self.open_button.clicked.connect(self.open_output)
        self.extractor_download.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/xancia/UmaExtractor/releases/latest"))
        )
        self.umadump_link.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/Werseter/umadump"))
        )
        self.context.configuration_changed.connect(self.sync_from_context)
        self.retranslate()
        self.refresh_status()


    def sync_from_context(self) -> None:
        self.master_picker.set_text(self.context.master_path)
        self.data_picker.set_text(self.context.veterans_json_path)
        self.extractor_picker.set_text(self.context.extractor_path)
        self.output_picker.set_text(self.context.output_dir)
        self.refresh_status()

    def retranslate(self) -> None:
        t = self.context.t
        self.header.set_text(
            t('Local data'),
            t('Extract or select your collection, then prepare it for analysis.'),
        )
        self.files_title.setText(t('Sources and output'))
        self.prepare_title.setText(t('Prepare collection'))
        self.master_label.setText(t('Current game database — master.mdb'))
        self.data_label.setText(
            t('Exported collection — data.json or trained_chara_data.json')
        )
        self.extractor_label.setText(t('Extractor — UmaExtractor or umadump, optional to create the JSON'))
        self.output_label.setText(t('Output directory'))
        self.master_picker.dialog_title = t('Select master.mdb')
        self.master_picker.file_filter = f"master.mdb (*.mdb);;{t('All files')} (*)"
        self.data_picker.dialog_title = t('Select a collection export')
        self.data_picker.file_filter = f"JSON (*.json);;{t('All files')} (*)"
        self.extractor_picker.dialog_title = t('Select UmaExtractor or umadump')
        self.extractor_picker.file_filter = f"{t('Extractor')} (*.exe *.py);;{t('All files')} (*)"
        self.output_picker.dialog_title = t('Select output directory')
        for picker in (self.master_picker, self.data_picker, self.extractor_picker, self.output_picker):
            picker.set_button_text(t('Browse…'))
        self.extract_button.setText(t('Extract my collection'))
        self.extract_detail.setText(
            t('Run the configured extractor, then automatically link the resulting JSON.')
        )
        self.link_button.setText(t('Link an existing export'))
        self.link_detail.setText(
            t('Use the selected JSON without running an extractor.')
        )
        self.force_link_button.setText(t('Relink anyway'))
        self.catalog_button.setText(t('Generate catalogues'))
        self.open_button.setText(t('Open output'))
        self.maintenance_title.setText(t('Maintenance and files'))
        self.maintenance_detail.setText(
            t('Linking already generates the catalogues; these commands are mainly for diagnostics and recovery.')
        )
        self.extractor_download.setText(t('Download UmaExtractor'))
        self.umadump_link.setText(t('Download umadump'))
        self.help_text.setText(
            t('The original export is never modified: all enriched data is written to the output directory.')
        )
        self.master_picker.setToolTip(
            t('Game database used to resolve costumes, Sparks, skills, and G1 races.')
        )
        self.data_picker.setToolTip(
            t('JSON export of your veterans. It can be created with UmaExtractor or umadump.')
        )
        self.extractor_picker.setToolTip(
            t('External program used only by “Extract my collection”.')
        )
        self.output_picker.setToolTip(
            t('Directory that receives generated JSON, CSV, catalogues, and reports.')
        )
        self.extract_button.setToolTip(
            t('Run the configured extractor, select its JSON output, and link it.')
        )
        self.link_button.setToolTip(
            t('Do not run an extractor: link the selected JSON file directly.')
        )
        self.force_link_button.setToolTip(
            t('Ignore the cache and rebuild every output. Normally unnecessary when the status is “Ready”.')
        )
        self.catalog_button.setToolTip(
            t('Regenerate only the catalogues. Linking already generates them automatically.')
        )
        self.open_button.setToolTip(
            t('Open the directory containing generated files.')
        )
        for label, picker in (
            (self.master_label, self.master_picker),
            (self.data_label, self.data_picker),
            (self.extractor_label, self.extractor_picker),
            (self.output_label, self.output_picker),
        ):
            label.setBuddy(picker.edit)
            picker.set_accessible_label(label.text(), picker.toolTip())
        self.refresh_status()

    def refresh_status(self) -> None:
        t = self.context.t
        output = Path(self.context.output_dir).expanduser()
        linked = linked_veterans_path(output)
        freshness = linked_data_freshness(
            self.context.master_path,
            self.context.veterans_json_path,
            output,
        )
        self.force_link_button.setVisible(linked.is_file())
        if freshness.state == "ready":
            self.result_card.set_content(
                t('Link status'),
                t('Ready'),
                t('The linked artifacts match the selected inputs.'),
                "ok",
            )
        elif freshness.state == "inputs_changed":
            self.result_card.set_content(
                t('Link status'),
                t('Inputs changed'),
                t('The master.mdb or collection export has changed since the last link.'),
                "warning",
            )
        else:
            self.result_card.set_content(
                t('Link status'),
                t('Not generated yet'),
                t('The enriched file will appear here after linking.'),
                "neutral",
            )

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.link_button.setEnabled(not busy)
        self.force_link_button.setEnabled(not busy)
        self.extract_button.setEnabled(not busy)
        self.catalog_button.setEnabled(not busy)

    def start_link(self, *, force: bool = False) -> None:
        self.context.update_paths(
            master_path=self.master_picker.text(),
            veterans_json_path=self.data_picker.text(),
            output_dir=self.output_picker.text(),
        )
        request = LinkRequest(
            Path(self.context.master_path).expanduser(),
            Path(self.context.veterans_json_path).expanduser(),
            Path(self.context.output_dir).expanduser(),
            force_relink=force,
        )
        operation = partial(run_link, request)
        self.task_requested.emit(operation, self.context.t('Linking collection…'), self._link_done)

    def _link_done(self, result: object) -> None:
        self.refresh_status()
        veteran_count = getattr(result, "veteran_count", 0)
        self.result_card.set_content(
            self.context.t('Link status'),
            self.context.t('Ready'),
            self.context.t('{count} enriched veterans').replace("{count}", str(veteran_count)),
            "ok",
        )

    def start_extract(self) -> None:
        self.context.update_paths(
            master_path=self.master_picker.text(),
            output_dir=self.output_picker.text(),
            extractor_path=self.extractor_picker.text(),
        )
        request = ExtractRequest(
            Path(self.context.extractor_path).expanduser(),
            Path(self.context.master_path).expanduser(),
            Path(self.context.output_dir).expanduser(),
        )
        self.task_requested.emit(
            partial(run_extract_and_link, request),
            self.context.t('Extracting and linking…'),
            self._extract_done,
        )

    def _extract_done(self, result: object) -> None:
        data_path = Path(getattr(result, "data_json_path"))
        self.context.update_paths(veterans_json_path=str(data_path))
        self.data_picker.set_text(str(data_path))
        linked = getattr(result, "link_result", None)
        self._link_done(linked)

    def start_catalog(self) -> None:
        self.context.update_paths(
            master_path=self.master_picker.text(), output_dir=self.output_picker.text()
        )
        request = CatalogRequest(
            Path(self.context.master_path).expanduser(),
            Path(self.context.output_dir).expanduser(),
        )
        self.task_requested.emit(
            partial(run_catalog, request),
            self.context.t('Generating catalogues…'),
            self._catalog_done,
        )

    def _catalog_done(self, result: object) -> None:
        count = getattr(result, "skill_count", 0)
        self.result_card.set_content(
            self.context.t('Skill catalogues'),
            self.context.t('Complete'),
            self.context.t('{count} skills indexed').replace("{count}", str(count)),
            "ok",
        )

    def open_output(self) -> None:
        output = Path(self.output_picker.text()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
            open_path(output)
        except OSError as exc:
            QMessageBox.critical(
                self,
                self.context.t('Error'),
                actionable_error(exc, translate=self.context.t),
            )
