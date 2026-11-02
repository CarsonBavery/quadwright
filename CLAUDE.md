# Quadwright

Open-source Python tool that turns OpenStreetMap data into glue-free
wooden campus kits: a base plate plus separately milled buildings.
This is a learning project. Explain non-obvious code in comments.

## Architecture
- Pipeline stages live in quadwright/<stage>/ and only talk through
  files in data/ and the types in quadwright/model.py.
- kit.json is the contract between geometry code and exporters.
- All lengths are millimeters at model scale unless the name ends in _m.
- Campus configs live in configs/campuses/ and are validated by quadwright/config.py.

## Commands
- Setup: scripts/setup.sh (macOS/Linux) or scripts/setup.ps1 (Windows)
- Check everything: scripts/check.sh or scripts/check.ps1
- Tests only: pytest
- CLI: quadwright --help

## Conventions
- Python 3.12, type hints everywhere, ruff for lint and format.
- Every new function gets a pytest test in the mirrored tests/ path.
- Geometry tests use fixtures in tests/fixtures/, never the network.
- Reference requirement ids (FR-04) in test names and commits.

## Rules for Claude
- Propose a plan before editing more than one file.
- Never change config schema without updating the example YAML.
- Do not add dependencies without asking.
- When unsure about fabrication behavior, ask rather than guess.
- Never commit directly to `main`. Create a branch per change
  (`feat/`, `fix/`, `chore/`, `docs/` prefix) before editing.
- Whenever a branch is pushed, open a PR in the same step
  (`gh pr create`, title + summary/test-plan body). Ask before merging.
  `gh` is installed and authenticated on this machine.

## Where to look first
- docs/PROJECT_MAP.md: every module, symbol, unit frame, placeholder
  constant, and on-disk path. Read it before opening source files, and
  update it in the same PR when any of those change.
- docs/ROADMAP.md: milestones M15+, open fabrication decisions, and the
  detail budget (why campus scale limits detail).

## Current state
Model stage only: no mill, so placeholder fab values (clearance_mm 0.15,
pocket depth) are expected, not blockers.
Carson's fab decisions (2026-11-02): base floor is 23mm minimum under the
lowest terrain point (FR-22); buildings merge only if they share a wall
or are <= 0.5mm apart at model scale, and parts narrower than the bit
are dropped and listed (FR-23, ADR-0006).
Done: M0-M14, M5 Joinery, FR-20/21. Open stack: #39 base floor -> #40
merge rule -> #41 dowels-only-when-they-fit -> #42 LIDAR retry/manifest.
unc-charlotte builds clean: 109 parts, all STLs watertight, 33.6mm stock.
uw-madison LIDAR is only partly fetched (USGS 429 quota); re-run fetch.
Next: Phase 1 of docs/ROADMAP.md, starting with M15 `quadwright check`.
