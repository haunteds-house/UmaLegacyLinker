"""Qt-facing presentation helpers for retained output provenance."""

from __future__ import annotations

from typing import Callable

from uma_legacy_linker.output_history import (
    CURRENT_REVISION,
    OutputProvenance,
    OutputRevision,
    format_output_timestamp,
)


def revision_title(revision_key: str, translate: Callable[[str], str]) -> str:
    return translate(
        "Exécution courante"
        if revision_key == CURRENT_REVISION
        else "Exécution précédente"
    )


def revision_menu_label(
    revision: OutputRevision,
    translate: Callable[[str], str],
) -> str:
    timestamp = format_output_timestamp(revision.modified_at_utc)
    title = revision_title(revision.key, translate)
    return f"{title} · {timestamp}" if timestamp else title


def provenance_badge_text(
    provenance: OutputProvenance,
    translate: Callable[[str], str],
) -> str:
    title = translate(
        "Courant"
        if provenance.revision.key == CURRENT_REVISION
        else "Précédent"
    )
    timestamp = format_output_timestamp(
        provenance.generated_at_utc or provenance.revision.modified_at_utc
    )
    return f"{title} · {timestamp}" if timestamp else title


def provenance_tooltip(
    provenance: OutputProvenance,
    translate: Callable[[str], str],
) -> str:
    generated = format_output_timestamp(
        provenance.generated_at_utc or provenance.revision.modified_at_utc
    )
    lines = [
        revision_title(provenance.revision.key, translate),
        f"{translate('Fichier')} : {provenance.revision.path.name}",
    ]
    if generated:
        lines.append(f"{translate('Générée le')} : {generated}")
    if provenance.source:
        lines.append(f"{translate('Source')} : {provenance.source}")
    if provenance.schema_version:
        lines.append(
            f"{translate('Version de schéma')} : {provenance.schema_version}"
        )
    if provenance.sources:
        lines.append(translate("Entrées et empreintes SHA-256"))
        for artifact in provenance.sources:
            identity = artifact.filename or artifact.role
            digest = artifact.sha256 or "—"
            lines.append(f"• {identity} · {digest}")
    return "\n".join(lines)
