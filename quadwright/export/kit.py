"""Serialize the pipeline's Kit into kit.json, the contract for later exporters (FR-13).

CLAUDE.md: "kit.json is the contract between geometry code and exporters."
Downstream stages (setup sheets, heightmaps, joinery) are meant to read
this instead of re-deriving Parts from scratch. Write-only for now --
nothing reads kit.json back yet, so there's no matching load_kit().
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import mapping

from quadwright.model import Joint, Kit, Part, Setup


def write_kit(kit: Kit, path: str | Path) -> Path:
    """Write a Kit to JSON at `path`, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_kit_to_dict(kit), indent=2), encoding="utf-8")
    return path


def _kit_to_dict(kit: Kit) -> dict[str, Any]:
    return {
        "campus": kit.campus,
        "base_plate": mapping(kit.base_plate),
        "parts": [_part_to_dict(p) for p in kit.parts],
        "report": kit.report,
    }


def _part_to_dict(part: Part) -> dict[str, Any]:
    return {
        "id": part.id,
        "building_ids": list(part.building_ids),
        "footprint_local": mapping(part.footprint_local),
        "height_mm": part.height_mm,
        "tier": part.tier.name,
        "position_on_base": list(part.position_on_base),
        "rotation_deg": part.rotation_deg,
        "species": part.species,
        "grain_axis": part.grain_axis,
        "joint": _joint_to_dict(part.joint) if part.joint is not None else None,
        "setups": [_setup_to_dict(s) for s in part.setups],
    }


def _joint_to_dict(joint: Joint) -> dict[str, Any]:
    return {
        "kind": joint.kind,
        "clearance_mm": joint.clearance_mm,
        "tenon_shape": mapping(joint.tenon_shape) if joint.tenon_shape is not None else None,
        "dowel_points": [list(p) for p in joint.dowel_points],
    }


def _setup_to_dict(setup: Setup) -> dict[str, Any]:
    return {"index": setup.index, "face_up": setup.face_up, "mesh_path": setup.mesh_path}
