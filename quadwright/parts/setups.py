"""Pick the machining setups a part needs, by tier (FR-16).

The Tier enum's own comments already spell out the rule (see
quadwright.model.Tier): BLOCK is "top setup only", ROTATED is "top plus
side setups". This just turns that into real Setup instances.
"""

from __future__ import annotations

from quadwright.model import Setup, Tier

# HERO's "hand-tuned" refers to which buildings get that tier -- a human
# picks them via tiers.overrides -- not to a different setup count. A
# landmark is exactly the kind of part that benefits from full side
# detail, so it gets the same setups as ROTATED.
_FULL_SETUP_TIERS = (Tier.ROTATED, Tier.HERO)
_SIDE_FACES = ("north", "south", "east", "west")


def assign_setups(tier: Tier) -> tuple[Setup, ...]:
    """Build the ordered Setup tuple for a part of this tier."""
    faces = ("top", *_SIDE_FACES) if tier in _FULL_SETUP_TIERS else ("top",)
    return tuple(Setup(index=i, face_up=face) for i, face in enumerate(faces))
