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
| M0 Setup: CI green | Done |
| M1 Footprints | Done |
| M2 Heights | Done |
| M3 First mesh | Done |
| M4 Parts (merge touching buildings, assign tiers) | Done |
| M6 Campus boundary filter (real OSM polygon, not just bbox) | Done |
| M7 Terrain (contoured base plate from real LIDAR) | Done |
| M8 Audit (height data quality report) | Done |
| M9 Tier report (parts-by-tier summary output) | Done |
| M10 kit.json (geometry-to-exporters contract) | Done |
| M11 build honors outputs: (warns instead of silently ignoring) | Done |
| M12 heightmap (colorized elevation PNG) | Done |
| M5 Joinery (tenons & pockets) | Planned -- blocked on a measured `clearance_mm` (needs the coupon test) |

## Data attribution

Map data © OpenStreetMap contributors, available under the
[Open Database License](https://www.openstreetmap.org/copyright).

Elevation data (when `campus.lidar_project` is set) is real LIDAR point
cloud data from the USGS 3D Elevation Program (3DEP), public domain.
