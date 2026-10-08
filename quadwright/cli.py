"""Command-line interface. Run `quadwright --help` to see every command."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import trimesh
import typer
from pydantic import ValidationError
from shapely.geometry import Polygon

from quadwright import __version__
from quadwright.config import CampusConfig, load_config
from quadwright.export.kit import write_kit
from quadwright.fab.coupon import build_coupon, build_manifest
from quadwright.geo.footprints import campus_bbox_local, load_buildings, load_campus_boundary
from quadwright.geo.render import render_footprints, render_heightmap
from quadwright.mesh.extrude import BASE_PLATE_THICKNESS_MM, build_base_plate, extrude_box
from quadwright.mesh.scale import compute_scale_mm_per_m, scale_buildings, to_model_mm
from quadwright.mesh.terrain import build_terrain_plate
from quadwright.model import Building, Kit
from quadwright.parts.merge import build_parts
from quadwright.parts.report import build_tier_report
from quadwright.parts.sheets import build_setup_sheets
from quadwright.resolve.terrain import HeightGrid, build_height_grid
from quadwright.sources.lidar import fetch_campus_lidar
from quadwright.sources.osm import fetch_buildings, fetch_campus_boundary

app = typer.Typer(help="Quadwright: wooden campus kits from open map data.", no_args_is_help=True)

ConfigArg = typer.Argument(..., exists=True, dir_okay=False, help="Campus YAML file")


@app.command()
def version() -> None:
    """Print the installed Quadwright version."""
    typer.echo(__version__)


@app.command()
def validate(config: Path = ConfigArg) -> None:
    """Check a campus config against the schema (FR-01)."""
    try:
        cfg = load_config(config)
    except (ValidationError, ValueError) as exc:
        typer.secho(f"INVALID: {config}", fg=typer.colors.RED, err=True)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    size = (
        f"{cfg.scale.target_size_mm[0]:g} x {cfg.scale.target_size_mm[1]:g} mm"
        if cfg.scale.target_size_mm
        else f"1:{cfg.scale.ratio:g}"
    )
    typer.secho(f"OK: {cfg.campus.name}", fg=typer.colors.GREEN)
    typer.echo(f"  scale: {size}, vertical x{cfg.scale.vertical_exaggeration:g}")
    typer.echo(f"  tool: {cfg.tool.diameter_mm:g} mm {cfg.tool.type}")
    typer.echo(f"  woods: {cfg.materials.base} base, {cfg.materials.buildings} parts")


def _planned(week: int) -> None:
    typer.secho(f"Not built yet: planned for week {week} (see the handbook).", fg="yellow")
    raise typer.Exit(code=2)


@app.command()
def fetch(config: Path = ConfigArg) -> None:
    """Download and cache OSM buildings, the campus boundary, and LIDAR (FR-02, FR-09, FR-10)."""
    cfg = load_config(config)
    path = fetch_buildings(cfg.campus)
    typer.secho(f"Cached: {path}", fg=typer.colors.GREEN)

    boundary_path = fetch_campus_boundary(cfg.campus)
    if boundary_path is not None:
        typer.secho(f"Cached: {boundary_path}", fg=typer.colors.GREEN)

    lidar_paths = fetch_campus_lidar(cfg.campus)
    if lidar_paths:
        typer.secho(
            f"Cached: {len(lidar_paths)} LIDAR tile(s) in {lidar_paths[0].parent}",
            fg=typer.colors.GREEN,
        )


def _load_campus_buildings(cfg: CampusConfig, config_path: Path) -> list[Building]:
    """Load cached buildings for a campus, filtered to its boundary if one was fetched."""
    raw_path = Path("data/raw") / cfg.campus.name / "buildings.geojson"
    if not raw_path.exists():
        typer.secho(f"No cached data for {cfg.campus.name}.", fg=typer.colors.RED, err=True)
        typer.echo(f"Run first: quadwright fetch {config_path}", err=True)
        raise typer.Exit(code=1)

    boundary_path = Path("data/raw") / cfg.campus.name / "boundary.geojson"
    boundary = load_campus_boundary(boundary_path) if boundary_path.exists() else None
    return load_buildings(
        raw_path, cfg.campus.bbox, cfg.heights, boundary, cfg.campus.include_outside_boundary
    )


@app.command()
def preview(config: Path = ConfigArg) -> None:
    """Draw a 2D map of building footprints (FR-03, FR-04, FR-05, FR-09). Tiers come later."""
    cfg = load_config(config)
    buildings = _load_campus_buildings(cfg, config)
    out_path = Path("outputs") / cfg.campus.name / "footprints.png"
    render_footprints(buildings, out_path)
    typer.secho(f"Wrote {out_path} ({len(buildings)} buildings)", fg=typer.colors.GREEN)


@app.command()
def audit(config: Path = ConfigArg) -> None:
    """Report height data quality: how many buildings got a real value vs. the campus default.

    Roof auditing isn't here yet -- roof shape resolution doesn't exist
    yet either (every building is still a flat-topped box).
    """
    cfg = load_config(config)
    buildings = _load_campus_buildings(cfg, config)

    by_source = Counter(b.height_source for b in buildings)
    typer.echo(f"Height sources ({len(buildings)} buildings):")
    for source in ("tag", "levels", "override", "lidar", "default"):
        count = by_source.get(source, 0)
        if count:
            typer.echo(f"  {source:<10} {count:>4}  ({100 * count / len(buildings):.1f}%)")

    defaulted_named = sorted(
        b.name for b in buildings if b.height_source == "default" and b.name is not None
    )
    if defaulted_named:
        typer.echo()
        typer.echo(
            f"Named buildings with a defaulted height ({len(defaulted_named)}) -- "
            "add a heights.overrides entry if you know the real value:"
        )
        for name in defaulted_named:
            typer.echo(f"  {name}")


@app.command()
def build(config: Path = ConfigArg) -> None:
    """Write the campus config's requested `outputs:`.

    (FR-06, FR-07, FR-09, FR-10, FR-12, FR-15, FR-16.)

    part_stl: merged, tiered part STLs, block-local (ADR-0003). base_stl:
    a contoured terrain block when campus.lidar_project is set and
    cached (run `fetch` first), a flat slab otherwise -- terrain changes
    what parts sit on, not the machining files themselves. tier_report:
    a parts-by-tier summary (FR-12). heightmap: a colorized PNG of the
    elevation grid -- only possible when campus.lidar_project is set
    (prints a warning and skips otherwise, rather than failing the
    whole build). setup_sheets: a per-part machining checklist, from
    each part's tier-derived Setups (FR-16) -- the plan, not yet
    rendered per-setup drawings.
    data/interim/<campus>/kit.json (FR-13) always gets written -- it's
    the pipeline's own contract, not a user-selectable output.

    Joinery comes later.
    """
    cfg = load_config(config)
    buildings = _load_campus_buildings(cfg, config)
    campus_outline_m = campus_bbox_local(cfg.campus.bbox)
    min_x_m, min_y_m, max_x_m, max_y_m = campus_outline_m.bounds
    origin_m = (min_x_m, min_y_m)
    scale_mm_per_m = compute_scale_mm_per_m(cfg.scale, max_x_m - min_x_m, max_y_m - min_y_m)

    footprints_mm, heights_mm = scale_buildings(
        buildings, origin_m, scale_mm_per_m, cfg.scale.vertical_exaggeration
    )
    parts = build_parts(
        buildings,
        footprints_mm,
        heights_mm,
        cfg.tool.diameter_mm,
        cfg.tiers,
        cfg.materials.buildings,
    )

    out_dir = Path("outputs") / cfg.campus.name

    if "part_stl" in cfg.outputs:
        parts_dir = out_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        for part in parts:
            extrude_box(part.footprint_local, part.height_mm).export(parts_dir / f"{part.id}.stl")
        typer.secho(f"Wrote {len(parts)} part STL(s) to {parts_dir}", fg=typer.colors.GREEN)

    # Loaded once, at most -- building it reads every cached LIDAR tile,
    # so base_stl and heightmap share one grid instead of each paying
    # that cost separately.
    terrain_grid: HeightGrid | None = None
    if ("base_stl" in cfg.outputs or "heightmap" in cfg.outputs) and cfg.campus.lidar_project:
        terrain_grid = _load_terrain_grid(cfg, scale_mm_per_m)

    if "base_stl" in cfg.outputs:
        out_dir.mkdir(parents=True, exist_ok=True)
        base_path = out_dir / "base.stl"
        _build_base(cfg, campus_outline_m, origin_m, scale_mm_per_m, terrain_grid).export(base_path)
        typer.secho(f"Wrote {base_path}", fg=typer.colors.GREEN)

    if "heightmap" in cfg.outputs:
        if terrain_grid is None:
            typer.secho(
                f"heightmap requested but campus.lidar_project isn't set for "
                f"{cfg.campus.name}; skipping.",
                fg="yellow",
            )
        else:
            heightmap_path = out_dir / "heightmap.png"
            render_heightmap(terrain_grid, heightmap_path)
            typer.secho(f"Wrote {heightmap_path}", fg=typer.colors.GREEN)

    if "tier_report" in cfg.outputs:
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "tier_report.txt"
        report_path.write_text(build_tier_report(parts), encoding="utf-8")
        typer.secho(f"Wrote {report_path}", fg=typer.colors.GREEN)

    if "setup_sheets" in cfg.outputs:
        out_dir.mkdir(parents=True, exist_ok=True)
        sheets_path = out_dir / "setup_sheets.txt"
        sheets_path.write_text(build_setup_sheets(parts), encoding="utf-8")
        typer.secho(f"Wrote {sheets_path}", fg=typer.colors.GREEN)

    base_outline_mm = to_model_mm(campus_outline_m, origin_m, scale_mm_per_m)
    kit = Kit(
        campus=cfg.campus.name,
        base_plate=base_outline_mm,
        parts=parts,
        report={"building_count": len(buildings), "part_count": len(parts)},
    )
    kit_path = write_kit(kit, Path("data/interim") / cfg.campus.name / "kit.json")
    typer.secho(f"Wrote {kit_path}", fg=typer.colors.GREEN)

    typer.echo(f"{len(parts)} part(s) from {len(buildings)} building(s).")


def _load_terrain_grid(cfg: CampusConfig, scale_mm_per_m: float) -> HeightGrid:
    """Load and grid cached LIDAR tiles. Only call this when campus.lidar_project is set."""
    lidar_dir = Path("data/raw") / cfg.campus.name / "lidar"
    lidar_paths = sorted(lidar_dir.glob("*.laz")) if lidar_dir.exists() else []
    if not lidar_paths:
        typer.secho(f"No cached LIDAR for {cfg.campus.name}.", fg=typer.colors.RED, err=True)
        typer.echo("Run first: quadwright fetch", err=True)
        raise typer.Exit(code=1)

    # A grid cell finer than one tool-diameter (in real-world terms, at
    # this model's scale) buys nothing -- the mill can't resolve it
    # anyway, and it would just bloat the mesh. At unc-charlotte's scale
    # this is ~22m vs. the naive 2m default (a ~100x fewer cells, 322MB
    # -> ~3MB of actual STL).
    cell_size_m = cfg.tool.diameter_mm / scale_mm_per_m
    return build_height_grid(lidar_paths, cfg.campus.bbox, cell_size_m)


def _build_base(
    cfg: CampusConfig,
    campus_outline_m: Polygon,
    origin_m: tuple[float, float],
    scale_mm_per_m: float,
    terrain_grid: HeightGrid | None,
) -> trimesh.Trimesh:
    """Build the base plate: a terrain block if a grid was loaded, a flat slab otherwise."""
    if terrain_grid is not None:
        return build_terrain_plate(
            terrain_grid, scale_mm_per_m, cfg.scale.vertical_exaggeration, BASE_PLATE_THICKNESS_MM
        )

    base_outline_mm = to_model_mm(campus_outline_m, origin_m, scale_mm_per_m)
    return build_base_plate(base_outline_mm)


@app.command()
def coupon(species: str = typer.Option("maple", help="Wood species")) -> None:
    """Generate the tolerance-test coupon: a pocket blank and matching test tenons (FR-17).

    Cut both, test-fit each tenon in its pocket, and record the
    clearance that felt snug-but-removable in
    configs/species/<species>.yaml's clearance_mm -- that measured
    value is what M5 Joinery is blocked on.
    """
    coupon_result = build_coupon()
    out_dir = Path("outputs") / "coupon" / species
    out_dir.mkdir(parents=True, exist_ok=True)

    pockets_path = out_dir / "pockets.stl"
    tenons_path = out_dir / "tenons.stl"
    manifest_path = out_dir / "manifest.txt"
    coupon_result.pockets.export(pockets_path)
    coupon_result.tenons.export(tenons_path)
    manifest_path.write_text(build_manifest(coupon_result.clearances_mm), encoding="utf-8")

    typer.secho(f"Wrote {pockets_path}", fg=typer.colors.GREEN)
    typer.secho(f"Wrote {tenons_path}", fg=typer.colors.GREEN)
    typer.secho(f"Wrote {manifest_path}", fg=typer.colors.GREEN)


@app.command()
def jig(blank: str = typer.Option(..., help="Blank size, e.g. 60x40x30")) -> None:
    """Generate the corner-stop jig. [week 7]"""
    _planned(7)


@app.command()
def sheets(config: Path = ConfigArg) -> None:
    """Render per-part setup sheets and the kit summary. [week 8]"""
    _planned(8)


if __name__ == "__main__":
    app()
