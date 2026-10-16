"""Audit active UI text after removal of the bilingual translation catalog."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRENCH_COPY = re.compile(
    r"[àâéèêëîïôùûüçœÀÉÈÊÔŒ]|\b(?:aucune?|fichier|dossier|pondérations?|"
    r"réglages?|introuvable|requiert|précisé|choisis|vétérans?|généré|jusqu)\b"
)


def audit() -> list[str]:
    issues = []
    for path in (ROOT / "ui_qt").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and FRENCH_COPY.search(node.value):
                issues.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value[:100]}")
    if (ROOT / "uma_legacy_linker/i18n.py").exists():
        issues.append("The obsolete translation catalog is still present")
    return issues


if __name__ == "__main__":
    problems = audit()
    print("\n".join(problems) if problems else "English UI text audit passed")
    raise SystemExit(bool(problems))
