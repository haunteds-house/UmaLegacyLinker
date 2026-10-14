"""Turn backend diagnostics into actionable user-facing error messages.

Backend exceptions deliberately keep their precise technical wording because
the CLI, logs and tests use it for diagnosis.  Presentation boundaries append
one concise recovery action instead of forcing every engine to duplicate UI
guidance in each ``raise`` site.
"""

from __future__ import annotations

import re
from collections.abc import Callable


ACTION_PREFIX = 'What to do: '

NETWORK_GUIDANCE = (
    'Check your connection, API URL and key, then try again.'
)
LOCAL_DATA_GUIDANCE = (
    'Check that master.mdb and the JSON export come from the same game version, link the data again, then retry.'
)
FILE_GUIDANCE = (
    'Check the selected file and its access permissions, then try again.'
)
SEARCH_GUIDANCE = (
    'Broaden the filters or increase the candidate limit, then retry.'
)
CONFIG_GUIDANCE = (
    'Restore the affected configuration or correct the indicated value, then retry.'
)
DEFAULT_GUIDANCE = (
    'Correct the indicated settings or files, then run the operation again.'
)
SECRET_STORAGE_GUIDANCE = (
    'Clear ‘Remember the key on this PC’ or check access to local storage, then try again.'
)

_ACTION_VERB = re.compile(
    r"\b(?:select|check|retry|add|configure|correct|choose|open|use|enable|disable|"
    r"restore|import|remove|reduce|increase|broaden|wait|create)\b", re.IGNORECASE,
)
_NETWORK_MARKERS = ("connection", "timed out", "timeout", "http ", "http:", "https:", " api ", " url ", "server")
_LOCAL_DATA_MARKERS = ("master.mdb", "veterans_legacy_linked", "trained_chara", "data.json", "factor", "costume", "character", "veteran", "local parent not found", "local grandparent not found")
_SEARCH_MARKERS = ("no candidate", "no pair", "no valid local parent", "no remote parent", "no remote grandparent", "no valid result")
_FILE_MARKERS = ("json", "sqlite", "not found", "reading", "writing", "permission", "access rights", "no such file", "file ", "directory")
_CONFIG_MARKERS = ("profile", "weight", "parameter", "configuration", "override", "priority", "threshold", "must be", "cannot", "required", "curve", "tier", "value", " must ", "unknown ", "expects ")


def guidance_for_error(message: str) -> str:
    """Choose the most useful generic recovery action for a diagnostic."""
    folded = f" {message.casefold()} "
    for markers, guidance in (
        (_NETWORK_MARKERS, NETWORK_GUIDANCE),
        (_LOCAL_DATA_MARKERS, LOCAL_DATA_GUIDANCE),
        (_SEARCH_MARKERS, SEARCH_GUIDANCE),
        (_FILE_MARKERS, FILE_GUIDANCE),
        (_CONFIG_MARKERS, CONFIG_GUIDANCE),
    ):
        if any(marker in folded for marker in markers):
            return guidance
    return DEFAULT_GUIDANCE


def actionable_error(
    message: object,
    *,
    action: str | None = None,
    translate: Callable[[str], str] | None = None,
) -> str:
    """Preserve a diagnostic and append one recovery action when it lacks one.

    An explicit ``action`` is used for presentation-specific recovery such as
    secret storage.  Otherwise already-actionable engine messages remain
    untouched and every other diagnostic receives a classified fallback.
    """
    diagnostic = str(message).strip() or 'The operation failed without technical details.'
    if ACTION_PREFIX.casefold() in diagnostic.casefold():
        return translate(diagnostic) if translate is not None else diagnostic
    if action is None and _ACTION_VERB.search(diagnostic):
        return translate(diagnostic) if translate is not None else diagnostic
    guidance = action or guidance_for_error(diagnostic)
    if translate is not None:
        diagnostic = translate(diagnostic)
        prefix = translate(ACTION_PREFIX)
        guidance = translate(guidance)
    else:
        prefix = ACTION_PREFIX
    return f"{diagnostic}\n\n{prefix}{guidance}"
