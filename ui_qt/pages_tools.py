from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QCheckBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from uma_legacy_linker.error_guidance import SECRET_STORAGE_GUIDANCE, actionable_error
from uma_legacy_linker.secret_store import SecretStoreError
from ui_qt.accessibility import describe_control, label_control
from ui_qt.components import PageHeader, muted_label, section_label
from ui_qt.context import AppContext


class ToolsPage(QWidget):
    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(14)
        self.header = PageHeader("", "")
        root.addWidget(self.header)

        self.integration_panel = QFrame()
        self.integration_panel.setObjectName("panel")
        integration = QGridLayout(self.integration_panel)
        integration.setContentsMargins(18, 16, 18, 16)
        integration.setHorizontalSpacing(12)
        integration.setVerticalSpacing(8)
        self.integration_title = section_label("")
        self.integration_hint = muted_label("")
        self.api_base_label = QLabel("")
        self.api_base = QLineEdit(context.uma_moe_api_base)
        self.api_key_label = QLabel("")
        self.api_key = QLineEdit(context.uma_moe_api_key)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_key = QPushButton("")
        self.remember_key = QCheckBox("")
        self.remember_key.setChecked(context.uma_moe_remember_api_key)
        self.save_integration_button = QPushButton("")
        self.save_integration_button.setObjectName("primary")
        self.integration_status = muted_label("")
        integration.addWidget(self.integration_title, 0, 0, 1, 3)
        integration.addWidget(self.integration_hint, 1, 0, 1, 3)
        integration.addWidget(self.api_base_label, 2, 0)
        integration.addWidget(self.api_base, 3, 0, 1, 3)
        integration.addWidget(self.api_key_label, 4, 0)
        integration.addWidget(self.api_key, 5, 0, 1, 2)
        integration.addWidget(self.show_key, 5, 2)
        integration.addWidget(self.remember_key, 6, 0, 1, 2)
        integration.addWidget(self.save_integration_button, 6, 2)
        integration.addWidget(self.integration_status, 7, 0, 1, 3)
        integration.setColumnStretch(0, 1)
        integration.setColumnStretch(1, 1)
        root.addWidget(self.integration_panel)
        root.addStretch(1)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)

        self.show_key.clicked.connect(self._toggle_key)
        self.save_integration_button.clicked.connect(self.save_integration)
        context.integration_changed.connect(self._sync_integration)
        self.retranslate()


    def retranslate(self) -> None:
        t = self.context.t
        self.header.set_text(
            t('Settings'),
            t('Configure stable integrations and access secondary technical tools.'),
        )
        self.integration_title.setText(t('uma.moe integration'))
        self.integration_hint.setText(
            t('The URL and key are used by every remote search. They never change scoring weights.')
        )
        self.api_base_label.setText(t('API base URL'))
        self.api_key_label.setText(t('API key'))
        hidden = self.api_key.echoMode() == QLineEdit.EchoMode.Password
        self.show_key.setText(t('Show' if hidden else 'Hide'))
        if os.name == "nt":
            remember_text = 'Remember the key on this PC — encrypted by Windows'
            remember_tooltip = 'The saved key is encrypted by Windows for this user account.'
        else:
            remember_text = 'Remember the key on this PC — unencrypted local file'
            remember_tooltip = (
                'The saved key is stored locally in a file readable only by your user account; it is not encrypted.'
            )
        self.remember_key.setText(t(remember_text))
        self.remember_key.setToolTip(t(remember_tooltip))
        self.save_integration_button.setText(t('Save integration'))
        description = self.integration_hint.text()
        label_control(self.api_base_label, self.api_base, description)
        label_control(self.api_key_label, self.api_key, description)
        describe_control(
            self.show_key,
            self.show_key.text(),
            self.api_key_label.text(),
        )
        describe_control(
            self.remember_key,
            self.remember_key.text(),
            self.remember_key.toolTip(),
        )
        describe_control(
            self.save_integration_button,
            self.save_integration_button.text(),
            description,
        )
        describe_control(
            self.integration_status,
            t('Status'),
            self.integration_status.text(),
        )
        self._update_integration_status()

    def _toggle_key(self) -> None:
        hidden = self.api_key.echoMode() == QLineEdit.EchoMode.Password
        self.api_key.setEchoMode(
            QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password
        )
        self.show_key.setText(self.context.t('Hide' if hidden else 'Show'))
        describe_control(
            self.show_key,
            self.show_key.text(),
            self.api_key_label.text(),
        )

    def _sync_integration(self) -> None:
        self.api_base.setText(self.context.uma_moe_api_base)
        self.api_key.setText(self.context.uma_moe_api_key)
        self.remember_key.setChecked(self.context.uma_moe_remember_api_key)
        self._update_integration_status()

    def _update_integration_status(self, saved: bool = False) -> None:
        t = self.context.t
        if self.api_key.text().strip():
            status = t('API key configured')
        else:
            status = t('No API key configured')
        if saved:
            status = t('Integration saved') + f" · {status}"
        self.integration_status.setText(status)
        self.integration_status.setAccessibleDescription(status)

    def save_integration(self) -> None:
        try:
            self.context.update_uma_moe_integration(
                api_base=self.api_base.text(),
                api_key=self.api_key.text(),
                remember_api_key=self.remember_key.isChecked(),
            )
        except (OSError, SecretStoreError) as exc:
            message = actionable_error(
                f'The key could not be saved.\n\n{exc}',
                action=SECRET_STORAGE_GUIDANCE,
                translate=self.context.t,
            )
            QMessageBox.warning(
                self,
                self.context.t('API key'),
                message,
            )
            return
        self._update_integration_status(saved=True)
