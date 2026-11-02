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
pocket depth, plate thickness) are expected, not blockers.
Done: M0-M14, M5 Joinery (FR-18 decision + FR-19 cutting). In open PRs:
FR-20/21 LIDAR heights + 3D model (#34), UW-Madison config (#37, stacked
on #34), LIDAR download fix (#35), dowel placement fix (#36).
Next: Phase 1 of docs/ROADMAP.md, starting with M15 `quadwright check`.
M16 (plinth parts) changes ADR-0004's design, so propose a plan first.
