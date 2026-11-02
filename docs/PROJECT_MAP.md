# Project map

A lookup table for the whole codebase: read this before opening files.
It names symbols, not line numbers, so it survives edits. Update it in
the same PR whenever a module, command, constant, or on-disk path is
added or moves.

Pending work is marked with the PR it lives in (none open as of
#34-#38 merging on 2026-11-02, apart from what's noted inline).

## Pipeline at a glance

```
configs/campuses/<c>.yaml --load_config--> CampusConfig
        |
  fetch | sources/osm.py      fetch_buildings, fetch_campus_boundary  -> data/raw/<c>/buildings.geojson, boundary.geojson
        | sources/lidar.py    fetch_campus_lidar                      -> data/raw/<c>/lidar/*.laz
        v
  geo/footprints.py   load_buildings (WGS84 -> local UTM m, boundary filter FR-09)
        | uses resolve/heights.py resolve_height (override > tag > levels > default, FR-05)
        v
  resolve/lidar_heights.py  measure_building_heights + apply_lidar_heights (FR-20, #34)
        v                  list[Building]  (meters, UTM)
  mesh/scale.py       compute_scale_mm_per_m, scale_buildings -> footprints_mm, heights_mm (campus mm)
        v
  parts/merge.py      build_parts: group_nearby_buildings -> group_footprint -> drop narrower_than_tool
        |   parts/tiers.py assign_tier, parts/setups.py assign_setups,
        |   joinery/tenons.py build_joint (needs SpeciesConfig.clearance_mm)
        v                  list[Part]  (part-local mm)
  joinery/cut.py      boss_for_joint (add to part), pocket_cutter_for_part (subtract from flat base)
  mesh/extrude.py     extrude_box, build_base_plate        mesh/terrain.py build_terrain_plate
        v
  outputs/<c>/  parts/*.stl, base.stl, heightmap.png, tier_report.txt, setup_sheets.txt,
                model.glb, model.png (#34), footprints.png (preview)
  data/interim/<c>/kit.json   always written (export/kit.py write_kit) -- the contract
```

Everything orchestrates in `quadwright/cli.py` `build()`. Stages never
import the CLI. They talk through `model.py` types and files under `data/`.

## Units and frames (the most common source of bugs)

| Frame | Units | Where |
| --- | --- | --- |
| WGS84 lon/lat | degrees | raw OSM, `bbox`, boundary polygon (filter runs here) |
| Local UTM | meters (`_m` suffix) | `Building.footprint`, `HeightGrid`; zone from `utm_crs_for_bbox` |
| Campus model | mm, origin = UTM bbox min corner | `footprints_mm`, base plate, `Part.position_on_base` |
| Part-local | mm, origin = part's bbox min corner | `Part.footprint_local`, `Joint.tenon_shape`, part STLs (ADR-0003) |
| LAS tile CRS | state plane, often **US survey feet** (Z too) | `_vertical_unit_to_meters` converts Z by hand |
| glTF export | meters, +Y up | `export/scene.py` `_MM_Z_UP_TO_M_Y_UP` |

`campus_bbox_local` is a slightly rotated quad in UTM, not an
axis-aligned rectangle. The flat base uses the quad and the terrain grid
uses its bounds.

## Modules

| File | Owns | Key symbols | Tests |
| --- | --- | --- | --- |
| `model.py` | domain types, no heavy imports | `Building`, `Part`, `Joint`, `Setup`, `Kit`, `Tier` (MERGE 0, BLOCK 1, ROTATED 2, HERO 3), `HeightSource`, `RoofShape` | via others |
| `config.py` | YAML schema (pydantic, `extra="forbid"`) | `CampusConfig` (campus, scale, tool, materials, heights, tiers, roofs, outputs), `OutputKind`, `load_config`, `SpeciesConfig`, `load_species_config` | `tests/test_config.py` |
| `cli.py` | typer app, `build` orchestration | `validate`, `fetch`, `preview`, `audit`, `build`, `coupon`; stubs `jig`, `sheets` (`_planned`); helpers `_load_campus_buildings`, `_cached_lidar_paths`, `_load_terrain_grid`, `_build_base` | `tests/test_cli.py` |
| `sources/osm.py` | Overpass/Nominatim via osmnx, cache-if-exists | `fetch_buildings`, `fetch_campus_boundary` | `tests/sources/test_osm.py` (mocked) |
| `sources/lidar.py` | USGS 3DEP tiles: `.vpc` index + `0_file_download_links.txt` | `fetch_campus_lidar`, `_overlaps_xy`, `_download` (truncation fix in #35) | `tests/sources/test_lidar.py` |
| `geo/footprints.py` | normalize + reproject + boundary filter | `load_buildings`, `_in_campus_scope` (centroid-in-boundary OR `historic=*` OR named include), `load_campus_boundary`, `campus_bbox_local`, `utm_crs_for_bbox` | `tests/geo/test_footprints.py` |
| `geo/render.py` | matplotlib PNGs | `render_footprints`, `render_heightmap`, `render_model` (#34, two panels: whole + core close-up) | `tests/geo/test_render.py` |
| `resolve/heights.py` | rule-based height | `resolve_height`, `_parse_height_tag` | `tests/resolve/test_heights.py` |
| `resolve/terrain.py` | ground grid from LAS class 2 | `HeightGrid`, `build_height_grid` (per-cell mean, `_fill_empty_cells`), `GROUND_CLASSIFICATION`, `_vertical_unit_to_meters` | `tests/resolve/test_terrain.py` |
| `resolve/lidar_heights.py` (#34) | LoD1 heights from LAS class 6 | `measure_building_heights` (roof p70 - ground p5 in a 0.5-4 m ring), `apply_lidar_heights` (replaces only `levels`/`default`), `_PointsSortedByX` | `tests/resolve/test_lidar_heights.py` |
| `mesh/scale.py` | m -> mm | `compute_scale_mm_per_m` (min of the two axis factors), `to_model_mm`, `scale_buildings` | `tests/mesh/test_scale.py` |
| `mesh/extrude.py` | flat boxes, no booleans (ADR-0004) | `extrude_box` (simplifies at `_SIMPLIFY_MM` 0.001 first; handles MultiPolygon by concatenation), `build_base_plate`, `base_stock_mm` (blank thickness = top z, FR-22), `BASE_PLATE_THICKNESS_MM` | `tests/mesh/test_extrude.py` |
| `mesh/terrain.py` | terrain solid + seating | `build_terrain_plate`, `GroundSurface` protocol, `FlatGround`, `GroundHeightLookup` (exact triangle interp, `min_height_under`) | `tests/mesh/test_terrain.py` |
| `parts/merge.py` | buildings -> Parts (ADR-0006) | `group_nearby_buildings` (flood fill, gap <= `tiers.merge_gap_mm` in model mm), `group_footprint` (closing + bridges -> always one Polygon), `narrower_than_tool` (dropped; CLI lists them as buildings in no part), `build_parts` | `tests/parts/test_merge.py` |
| `parts/tiers.py` | tier rule | `assign_tier`: override > height > rotate threshold -> ROTATED; narrow side < merge threshold -> MERGE; else BLOCK | `tests/parts/test_tiers.py` |
| `parts/setups.py` | tier -> setups | `assign_setups` (BLOCK: top; ROTATED/HERO: top + 4 sides) | `tests/parts/test_setups.py` |
| `parts/report.py` / `sheets.py` | text outputs | `build_tier_report` (+ skipped buildings section), `build_setup_sheets` | `tests/parts/test_report.py`, `test_sheets.py` |
| `joinery/tenons.py` | joint *decision* | `build_joint`, `MissingClearanceError`, `_needs_dowel_fallback`, `_pins_fit` (dowels only if both holes fit; else tenon), `DOWEL_FALLBACK_BELOW_TOOL_DIAMETERS`, `_dowel_points` (#36) | `tests/joinery/test_tenons.py` |
| `joinery/cut.py` | joint *geometry* (the only booleans besides coupon) | `boss_for_joint`, `pocket_cutter_for_part`, `POCKET_DEPTH_MM`, `DOWEL_DIAMETER_MM`, `_OVERSHOOT_MM` | `tests/joinery/test_cut.py` |
| `fab/coupon.py` | clearance test piece | `build_coupon`, `build_manifest`, `DEFAULT_CLEARANCES_MM` | `tests/fab/test_coupon.py` |
| `export/kit.py` | kit.json writer (no reader yet) | `write_kit`, `_part_to_dict`, `_joint_to_dict` | `tests/export/test_kit.py` |
| `export/scene.py` (#34) | assembled campus | `PlacedBuilding`, `seat_building`, `place_buildings`, `build_campus_scene`, `write_glb`, `WALNUT_RGBA`, `MAPLE_SHADES_RGBA` | `tests/export/test_scene.py` |

Empty placeholder packages: `notebooks/`, `ml/` (README only, roof
classifier planned, `pip install -e ".[ml]"` adds scikit-learn).

## Placeholders and tunables (not measured, so check before trusting)

| Constant | Value | File |
| --- | --- | --- |
| `clearance_mm` (maple) | 0.15 placeholder | `configs/species/maple.yaml` |
| `BASE_PLATE_THICKNESS_MM` | 23.0 (Carson's minimum floor, under the lowest terrain point) | `mesh/extrude.py` |
| `POCKET_DEPTH_MM` | 2.0 | `joinery/cut.py` |
| `DOWEL_DIAMETER_MM` | 3.0 | `joinery/cut.py` |
| `DOWEL_FALLBACK_BELOW_TOOL_DIAMETERS` | 2.0 (TODO(carson)) | `joinery/tenons.py` |
| `tiers.merge_gap_mm` | 0.5 (Carson, ADR-0006) | campus YAML / `config.Tiers` |
| `_CLOSING_MARGIN_MM` | 0.01 | `parts/merge.py` |
| `ROOF_PERCENTILE` / `GROUND_PERCENTILE` | 70 / 5 | `resolve/lidar_heights.py` |
| `MIN_ROOF_POINTS` / `MIN_RELATIVE_DENSITY` | 10 / 0.5 | `resolve/lidar_heights.py` |
| terrain cell size | `tool.diameter_mm / scale_mm_per_m` (~22 m at UNC) | `cli._load_terrain_grid` |
| coupon | 20 mm pockets, 10 mm deep, 0.05-0.25 clearances | `fab/coupon.py` |

## Campuses and data on disk

| Campus | Config | Scale | 3.175 mm bit = | Cached data | Built |
| --- | --- | --- | --- | --- | --- |
| example-university | synthetic, no boundary/LIDAR | -- | -- | -- | CI validate only |
| unc-charlotte | `NC_Phase_4..._Mecklenburg_2016` | ~1:7000 | ~22 m real | OSM + boundary + LIDAR | full build: 286 buildings -> 109 parts, 70 dropped; base stock 33.6 mm |
| uw-madison (#37) | `WI_5County_B24` | ~1:9300 | ~30 m real | OSM + boundary + LIDAR | `preview` only |

`data/` and `outputs/` are gitignored and can be regenerated from config +
cache. Tests never touch the network: fixtures are
`tests/fixtures/sample_buildings.geojson` and synthetic LAS written in-test.

## Known gaps (see docs/ROADMAP.md)

- 70 of UNC's 286 buildings drop out at a 3.175 mm bit (narrower than ~22 m real).
- Terrain bases get no pockets (`build` warns and skips), so the real campuses have no joinery.
- Parts are seated at `min_height_under` and sink into slopes. There is no flat landing pad.
- Pocket inside corners ignore tool radius (no dogbone/corner relief).
- Every roof is flat. `roofs.engine` and `RoofShape` are unused. `Part.grain_axis`/`rotation_deg` are never set.
- `kit.json` has no reader, so exporters still re-derive Parts in `cli.build`.

## Workflow facts

- Check everything: `scripts/check.ps1` (Windows) / `scripts/check.sh`. CI (`.github/workflows/ci.yml`) runs ruff check, ruff format --check, pytest, validate example.
- pre-commit runs ruff + whitespace hooks on commit.
- Python `.venv/Scripts/python` on this machine. `requires-python >=3.11`, CI uses 3.12.
- Branch per change (`feat/ fix/ chore/ docs/`), PR on push, ask before merging.
