"""Turn backend diagnostics into actionable user-facing error messages.

Backend exceptions deliberately keep their precise technical wording because
the CLI, logs and tests use it for diagnosis.  Presentation boundaries append
one concise recovery action instead of forcing every engine to duplicate UI
guidance in each ``raise`` site.
"""

from __future__ import annotations

import re
from collections.abc import Callable


ACTION_PREFIX = "Que faire : "

NETWORK_GUIDANCE = (
    "Vérifie ta connexion, l’URL de l’API et la clé, puis relance."
)
LOCAL_DATA_GUIDANCE = (
    "Vérifie que master.mdb et l’export JSON viennent de la même version du "
    "jeu, relie les données, puis relance."
)
FILE_GUIDANCE = (
    "Vérifie le fichier sélectionné et ses droits d’accès, puis réessaie."
)
SEARCH_GUIDANCE = (
    "Élargis les filtres ou augmente la limite de candidats, puis relance."
)
CONFIG_GUIDANCE = (
    "Rétablis la configuration concernée ou corrige la valeur indiquée, puis "
    "relance."
)
DEFAULT_GUIDANCE = (
    "Corrige les paramètres ou fichiers indiqués, puis relance l’opération."
)
SECRET_STORAGE_GUIDANCE = (
    "Décoche « Mémoriser la clé sur ce PC » ou vérifie l’accès au stockage "
    "local, puis réessaie."
)

_ACTION_VERB = re.compile(
    r"\b(?:sélectionne|vérifie|relance|réessaie|ajoute|configure|corrige|"
    r"choisis|ouvre|utilise|active|désactive|rétablis|importe|supprime|"
    r"réduis|augmente|élargis|attends|crée|assure-toi)\b",
    re.IGNORECASE,
)

_NETWORK_MARKERS = (
    "connexion",
    "connection",
    "timed out",
    "timeout",
    "http ",
    "http:",
    "https:",
    " api ",
    " url ",
    "serveur",
)
_LOCAL_DATA_MARKERS = (
    "master.mdb",
    "veterans_legacy_linked",
    "trained_chara",
    "data.json",
    "facteur",
    "costume",
    "personnage",
    "vétéran",
    "parent local introuvable",
    "grand-parent local introuvable",
)
_SEARCH_MARKERS = (
    "aucun candidat",
    "aucune candidate",
    "aucune paire",
    "aucun parent distant",
    "aucun grand-parent distant",
    "aucun résultat valide",
)
_FILE_MARKERS = (
    "fichier",
    "dossier",
    "json",
    "sqlite",
    "introuvable",
    "lecture",
    "écriture",
    "permission",
    "droits d’accès",
    "no such file",
    "permission denied",
    "file ",
    "directory",
)
_CONFIG_MARKERS = (
    "profil",
    "pondération",
    "poids",
    "paramètre",
    "configuration",
    "override",
    "priorité",
    "seuil",
    "doit être",
    "ne peut pas",
    "requis",
    "courbe",
    "palier",
    "valeur",
    " must ",
    "unknown ",
    "expects ",
)


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
    diagnostic = str(message).strip() or "L’opération a échoué sans détail technique."
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
