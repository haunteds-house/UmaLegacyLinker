from __future__ import annotations

from typing import Any


def accessible_text(value: object) -> str:
    """Return stable single-line text suitable for Qt's accessibility tree."""

    return " ".join(str(value or "").split())


def describe_control(
    control: Any,
    name: object,
    description: object = "",
) -> None:
    """Expose an explicit translated name and description for one control."""

    control.setAccessibleName(accessible_text(name))
    control.setAccessibleDescription(accessible_text(description))


def label_control(
    label: Any,
    control: Any,
    description: object = "",
) -> None:
    """Bind a visible label to its control and mirror it to assistive APIs."""

    label.setBuddy(control)
    describe_control(
        control,
        label.text(),
        description or control.toolTip(),
    )
