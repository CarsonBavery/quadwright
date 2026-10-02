# Quadwright

![CI](https://github.com/CarsonBavery/quadwright/actions/workflows/ci.yml/badge.svg)

Quadwright turns open map data into glue-free wooden model kits of college
campuses: a base plate plus separately milled buildings that press-fit into
place with wood-only joinery. It is a hobby and learning project built with
Claude Code as a coding partner.

## Quickstart

macOS / Linux:

```bash
./scripts/setup.sh
quadwright validate configs/campuses/example-university.yaml
```

Windows (PowerShell):

```powershell
.\scripts\setup.ps1
quadwright validate configs\campuses\example-university.yaml
```

See [docs/SETUP.md](docs/SETUP.md) for prerequisites and Claude Code tooling.

## Status

| Milestone | Status |
| --- | --- |
| M0 Setup: CI green | In progress |
| M1 Footprints | Planned |
| M2 Heights | Planned |
| M3 First mesh | Planned |

## Data attribution

Map data © OpenStreetMap contributors, available under the
[Open Database License](https://www.openstreetmap.org/copyright).
