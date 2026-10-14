from __future__ import annotations

from pathlib import Path

import pytest

from uma_legacy_linker.error_guidance import (
    CONFIG_GUIDANCE,
    DEFAULT_GUIDANCE,
    FILE_GUIDANCE,
    LOCAL_DATA_GUIDANCE,
    NETWORK_GUIDANCE,
    SEARCH_GUIDANCE,
    SECRET_STORAGE_GUIDANCE,
    actionable_error,
    guidance_for_error,
)
from uma_legacy_linker.labels import display_text


@pytest.mark.parametrize(
    ("diagnostic", "guidance"),
    [
        (
            "Factor 'Mile' not found in master.mdb for the uma.moe filter.",
            LOCAL_DATA_GUIDANCE,
        ),
        ('Unable to connect to https://uma.moe.', NETWORK_GUIDANCE),
        (
            "Required parameter unresolved for GET /parents: limit",
            CONFIG_GUIDANCE,
        ),
        ('Invalid JSON response from the local cache.', FILE_GUIDANCE),
        (
            'No valid local parent × remote parent pair.',
            SEARCH_GUIDANCE,
        ),
        ('Unexpected internal error.', DEFAULT_GUIDANCE),
    ],
)
def test_backend_diagnostics_receive_contextual_recovery_actions(
    diagnostic: str,
    guidance: str,
) -> None:
    assert guidance_for_error(diagnostic) == guidance
    rendered = actionable_error(diagnostic)
    assert rendered.startswith(diagnostic + '\n\nWhat to do: ')
    assert rendered.endswith(guidance)


def test_already_actionable_messages_are_not_duplicated() -> None:
    diagnostic = 'Select a valid master.mdb.'

    assert actionable_error(diagnostic) == diagnostic
    assert actionable_error(actionable_error('HTTP 500 on the API.')) == (
        actionable_error('HTTP 500 on the API.')
    )


def test_translation_keeps_exact_diagnostic_and_action_separate() -> None:
    rendered = actionable_error(
        'No valid local parent × remote parent pair.',
        translate=lambda value: str(display_text(value, "en")),
    )

    assert rendered == (
        "No valid local parent × remote parent pair.\n\n"
        "What to do: Broaden the filters or increase the candidate limit, "
        "then retry."
    )


def test_presentation_specific_action_preserves_the_diagnostic() -> None:
    rendered = actionable_error(
        'The key could not be saved.\n\nAccess denied',
        action=SECRET_STORAGE_GUIDANCE,
    )

    assert rendered.startswith('The key could not be saved.\n\nAccess denied')
    assert rendered.endswith(SECRET_STORAGE_GUIDANCE)


def test_every_exception_presentation_boundary_uses_actionable_guidance() -> None:
    ui_paths = [
        Path("ui_qt/main_window.py"),
        Path("ui_qt/online_options.py"),
        Path("ui_qt/pages_home_data.py"),
        Path("ui_qt/pages_search.py"),
        Path("ui_qt/pages_tools.py"),
        Path("ui_qt/pages_transfer.py"),
        Path("ui_qt/pages_weights.py"),
        Path("ui_qt/result_panes.py"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in ui_paths)

    assert "context.t(str(exc))" not in combined
    assert (
        'QMessageBox.critical(self, self.context.t("Error"), str(exc))'
        not in combined
    )
    assert combined.count("actionable_error(") >= 20

    worker_source = Path("ui_qt/workers.py").read_text(encoding="utf-8")
    main_source = Path("ui_qt/main_window.py").read_text(encoding="utf-8")
    cli_source = Path("cli.py").read_text(encoding="utf-8")
    assert "traceback.format_exc()" in worker_source
    assert "actionable_error(message, translate=self.context.t)" in main_source
    assert "actionable_error(exc)" in cli_source
