from __future__ import annotations


BASE_POINT_SIZE = 10.0

# One closed scale shared by QSS, Qt painter code and rich-text diagnostics.
# Keeping the factors explicit makes a future application-level text scale a
# single multiplication instead of another round of per-widget adjustments.
TYPE_SCALE_FACTORS = {
    "micro": 0.8,
    "caption": 0.9,
    "body": 1.0,
    "body_large": 1.1,
    "section": 1.2,
    "heading": 1.4,
    "brand": 1.8,
    "display": 2.2,
}

TYPE_SCALE_PT = {
    role: BASE_POINT_SIZE * factor
    for role, factor in TYPE_SCALE_FACTORS.items()
}

FONT_FAMILY_QSS = '"Segoe UI", "Inter", sans-serif'


def point_size(role: str) -> float:
    """Return the point size for a named typography role."""
    try:
        return TYPE_SCALE_PT[role]
    except KeyError as error:
        raise ValueError(f"Unknown typography role: {role}") from error


def css_point_size(role: str) -> str:
    """Return a compact CSS/QSS point-size token for a named role."""
    return f"{point_size(role):g}pt"
