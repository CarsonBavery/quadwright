# ADR-0006: Merge only buildings that share a wall or nearly do

Status: accepted
Date: 2026-11-02

## Context
FR-08 pulled every too-small building into its nearest neighbor up to 3 tool diameters away (9.5 mm, about 66 m of real ground at unc-charlotte's 1:7000). Its unions were still separate islands, so 48 of 65 parts weren't one piece of wood, and one "part" held 29 buildings milled to a single height.

## Decision
Two buildings share a part only if their model-scale footprints are at most `tiers.merge_gap_mm` apart (default 0.5 mm). Touching is 0 mm. Each group's outline is closed (buffer out and back by half the gap), and any islands that are still separate get a gap-wide bridge, so every part is exactly one polygon. Groups narrower than the tool are dropped and listed in `tier_report.txt` and `kit.json`, because the base pocket for them can't be cut with that bit.

## Consequences
Parts stay true to individual buildings, and every part is one solid. More parts, and smaller ones: unc-charlotte goes from 65 parts to 109, and 70 of its 286 buildings are dropped at a 3.175 mm bit. A smaller finishing bit or a larger-scale district kit (ROADMAP M21) is how those come back. Supersedes FR-08's nearest-neighbor merge. ADR-0004's parts-and-tenons design is unchanged.
