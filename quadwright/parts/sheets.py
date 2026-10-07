"""Render a per-part setup checklist for the physical kit (FR-16).

A woodworker's reference for loading each blank into the corner-stop
jig: which orientations it needs and in what order. Per-setup drawings
(one projected view per face-up orientation) are a later increment --
this is the plan, not yet the pictures.
"""

from __future__ import annotations

from quadwright.model import Part


def build_setup_sheets(parts: list[Part]) -> str:
    """Render a human-readable setup checklist, one section per part."""
    lines = [f"Setup sheets: {len(parts)} part(s)", ""]

    for part in parts:
        lines.append(f"{part.id} ({part.tier.name}, {len(part.setups)} setup(s)):")
        for setup in part.setups:
            lines.append(f"  [{setup.index}] face up: {setup.face_up}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
