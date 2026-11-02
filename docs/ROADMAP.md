# Roadmap

Written 2026-11-02. The project is staying at the model stage (no mill),
so "working" means **the software can produce a kit that would build**:
every STL is a valid solid, every part is one piece of wood that seats,
and the whole kit passes an automated check. Real cuts come later and
only replace placeholder numbers. They shouldn't change the design.

Two goals, in this order:

1. **Always buildable.** Any campus config produces a kit that passes
   `quadwright check`, every run, with no hand-fixing.
2. **Beyond blocks.** Buildings carry stepped heights and real roof
   shapes instead of LoD1 boxes. Measured detail (LIDAR) comes first,
   estimated detail (rules, then ML) fills the gaps.

## The constraint that shapes everything: the detail budget

A flat end mill can't cut a feature narrower than itself, and at
whole-campus scale the tool is enormous in real-world terms:

| Campus | Scale | 3.175 mm bit | 1 mm bit | 12 m building |
| --- | --- | --- | --- | --- |
| unc-charlotte | ~1:7000 | 22 m | 7 m | 2.6 mm tall (x1.5) |
| uw-madison | ~1:9300 | 30 m | 9 m | ~1.9 mm tall |

A courtyard, a roof ridge, a 15 m wing: at today's settings none of these
survive milling. Better roof algorithms alone can't fix that. There are
three levers, and the roadmap uses all of them:

- **Scale:** a *district kit* covers part of a campus at a larger scale
  (the UNC core at ~1:2500 makes the bit ~8 m).
- **Tool:** a finishing bit (1 mm, or a V-bit for engraving) next to the
  roughing bit.
- **Honest geometry:** generate only the detail the chosen scale and tool
  can resolve, and show it in the preview, so what you see is what the
  mill would make.

Every detail feature below goes through one function that answers "can
this tool at this scale cut it?" (M21). That keeps goal 2 from breaking goal 1.

---

## Phase 0: Land the open stack

| PR | What | Order |
| --- | --- | --- |
| #35 | never cache a truncated LIDAR tile | any time |
| #36 | dowel pins land on material | any time |
| #34 | LIDAR heights + `model_glb`/`model_png` | before #37 |
| #37 | UW-Madison config | after #34 |

Then run a full `quadwright build` on uw-madison. It has only been previewed so far.

## Phase 1: Always buildable

### M15 `quadwright check`: the manufacturability gate (FR-22)
A new `quadwright/check/` stage reads `kit.json` and the STLs, and `build`
runs it at the end (non-zero exit on errors). Every later milestone adds
its own rules here. That's how the "consistently" part of the goal gets enforced.

- Add `load_kit()` so the check reads the contract and doesn't re-derive anything (CLAUDE.md: kit.json is the contract).
- Rules to start with: each part STL is watertight and **one connected body**. Each joint lies on material. No feature is narrower than the tool unless it's tagged as engraving. The pocket doesn't break through the base. Every part's footprint fits inside the base. Parts don't overlap.
- Writes `outputs/<c>/check_report.txt`. Today's UNC kit would fail, which is the point: it gives a baseline to measure progress against.

### M16 Plinth parts: make every part one piece of wood (FR-23, ADR-0006)
48 of UNC's 65 parts are disconnected islands. Give each merged group a
shared ground slab:

- Plinth outline = union of members buffered by a margin, then closed (`buffer(+r).buffer(-r)`), so close buildings join. The slab is milled from the same blank, below the buildings.
- The **plinth outline becomes the tenon**, which is a simpler shape than the old union-of-islands tenons.
- Buildings stay separate on top, each at its own height. That also fixes the "milled to the tallest member" problem: a merged part gets real stepped heights for free.
- ADR-0006 amends ADR-0004 ("each part = one building box" becomes "each part = plinth + buildings").

### M17 Terrain-aware seating: pads and pockets in contoured bases (FR-24)
Today a terrain base gets no joinery and parts sink into slopes.

- For each part, flatten a **landing pad** into the terrain: cut the base down to a plane at `min_height_under` within the plinth outline (plus a small apron), then cut the pocket into that flat floor. This replaces the `terrain_grid is None` special case in `cli.build`.
- Reuses `GroundHeightLookup.min_height_under`. The cutting reuses `pocket_cutter_for_part` with `base_top_mm` per part.

### M18 Tool-radius geometry (FR-25)
A round bit leaves a radius of `tool.radius_mm` in every inside corner of a pocket.

- Either cut **dogbone reliefs** at the pocket's inside corners, or **round the tenon's outside corners** to match. *Fabrication decision: Carson picks.*
- Add an `as_cut(shape, tool)` helper (a morphological opening by the tool radius). Use it in the check and in `model_png`, so the preview shows the shape the mill can actually make.

### M19 Sub-tool feature policy (FR-26)
7 of UNC's 10 dowel parts are narrower than the 3 mm pin itself (one is 0.7 x 1.2 mm).
Decide what a building smaller than the tool becomes. *Fabrication decision: Carson picks.* The options:
- absorb it into the nearest plinth (as a raised bump if it's tall enough),
- engrave it as an outline into the base with the V-bit, or
- drop it and list it in the report.

This also retires the dowel fallback for anything a plinth can carry.

### M20 Repeatability harness (FR-27)
- **CI:** an end-to-end test on a fixture mini-campus (`tests/fixtures/` geojson plus synthetic LAS written in-test, as `test_lidar` already does) through `build` and then `check`, asserting zero errors.
- **Local:** `scripts/regress.ps1` rebuilds every cached real campus and diffs a metrics table (parts, check errors, % measured heights, detail stats) against the last run, so a change that makes UNC worse is caught before merging.

**Done with Phase 1 when:** unc-charlotte and uw-madison both build with zero check errors.

## Phase 2: Beyond blocks

Ordered by detail gained per unit of work. Measured detail comes before estimated detail (ADR-0005).

### M21 Detail budget and district kits (FR-28, ADR-0007)
- `resolvable_mm(scale, tool)` reports the smallest real-world feature, in meters, that survives. `audit` prints it, and every later step calls it before adding detail.
- Config: an optional `tool.finishing` bit, and an optional `campus.focus` sub-area for district kits. *Schema change, so update example-university.yaml in the same PR.*

### M22 Stepped heights, LoD1.3 (FR-29)
Most of the visible "not a block" effect, cheaply:
- **OSM `building:part`** ways with `height`/`min_height` (towers, wings, podiums) become separate stacked extrusions. They're already in the Overpass results; `load_buildings` just doesn't read them.
- **LIDAR height zones:** rasterize each building's class-6 points at the resolvable cell size, cluster the heights into a few levels, then union the cells per level into polygons (shapely only, no new dependency) and extrude them stepped. Zones smaller than the budget merge into their neighbors.

### M23 Measured roof surfaces (FR-30, ADR-0008)
A 3-axis mill cutting a part's top is a heightfield machine, and LIDAR is
a heightfield. So for big parts, mill the top as the DSM clipped to the
footprint, smoothed to the tool radius. This is real detail with nothing
to estimate. Mesh it the same way `build_terrain_plate` builds terrain,
and clip it with manifold3d. ADR-0008 records that part tops stop being
flat boxes.

### M24 Parametric roofs (rules) (FR-31)
For buildings where LIDAR is missing, stale (built after the scan), or too coarse:
- OSM tags first (`roof:shape`, `roof:height`, `roof:direction`), then **plane fitting** on the roof points (numpy least squares/RANSAC: one plane is flat/skillion, two is gabled, four is hipped).
- Generators for flat, skillion, gabled, hipped, pyramidal, and dome on the oriented minimum rectangle. These fill the existing `RoofShape`/`roof_source` fields that nothing uses yet.

### M25 ML roof estimator (FR-32, `ml/`, behind `roofs.engine: ml`)
This is where a model estimates detail the data doesn't measure:
- Labels come free from buildings that carry an OSM `roof:shape` tag. Features come from the LIDAR roof patch (normal histogram, plane count, height spread) and footprint shape.
- ADR-0005 rules: train on one campus, test on another, and ship only if it beats the M24 rules and the majority-class baseline. scikit-learn is already the `[ml]` extra.
- Later: estimate roof shapes for post-scan buildings from footprint alone.

### M26 Hero detail (FR-33)
`HERO` parts get the side setups they already list: V-bit floor lines from
`building:levels`, and the finishing bit on towers and domes. This is the
only place facade detail can survive at campus scale.

**Done with Phase 2 when:** the UNC core district kit shows recognizable
roofs and stepped massing in `model_png`, and still passes `check`.

## Phase 3: Kit experience
- V-bit **part IDs** engraved on each tenon bottom and its matching pocket floor.
- An assembly map PDF/PNG with part outlines numbered on the base.
- Implement the `sheets` command (per-setup drawings) and the `jig` command (corner-stop jig, already in `Setup`).
- Set `Part.grain_axis` along each part's long axis.

## Phase 4: Showcase
- A GitHub Pages gallery: each campus's `model.glb` in a web viewer, plus its check report.
- A third campus from a different region and terrain type, to prove the pipeline generalizes.

---

## Decisions that belong to Carson
Per CLAUDE.md ("ask rather than guess" on fabrication):

| When | Decision |
| --- | --- |
| M16 | plinth thickness and margin; minimum gap that still joins two buildings |
| M17 | pad apron width; whether pads may cut below the base's 6 mm floor |
| M18 | dogbone reliefs vs rounded tenons |
| M19 | sub-tool buildings: absorb, engrave, or drop |
| M21 | finishing bit size; district scale for UNC's core |

## Good hands-on pieces (learning mode)
Each is about 5-10 lines with a real trade-off:
- the M15 rule severities (what counts as an error vs a warning),
- M19's policy function,
- M22's height-clustering tolerance (how different two roof levels must be to stay separate),
- M25's feature set.

## New dependencies
Phases 1-2 need none beyond what's installed. Plane fitting is numpy,
and polygons come from shapely unions of grid cells. Anything that
would want a new package (straight skeleton for complex hipped roofs,
rasterio, scikit-image) gets asked about first.
