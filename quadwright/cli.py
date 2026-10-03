"""Command-line interface. Run `quadwright --help` to see every command."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from quadwright import __version__
from quadwright.config import CampusConfig, load_config
from quadwright.geo.footprints import campus_bbox_local, load_buildings, load_campus_boundary
from quadwright.geo.render import render_footprints
from quadwright.mesh.extrude import build_base_plate, extrude_box
from quadwright.mesh.scale import compute_scale_mm_per_m, scale_buildings, to_model_mm
from quadwright.model import Building
from quadwright.parts.merge import build_parts
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
    """Download and cache OSM building data and the campus boundary (FR-02, FR-09)."""
    cfg = load_config(config)
    path = fetch_buildings(cfg.campus)
    typer.secho(f"Cached: {path}", fg=typer.colors.GREEN)

    boundary_path = fetch_campus_boundary(cfg.campus)
    if boundary_path is not None:
        typer.secho(f"Cached: {boundary_path}", fg=typer.colors.GREEN)


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
    """List buildings with defaulted heights or roofs. [week 3]"""
    _planned(3)


@app.command()
def build(config: Path = ConfigArg) -> None:
    """Extrude merged, tiered part STLs and the base plate (FR-06, FR-07, FR-09).

    Joinery/kit.json come later.
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
    parts = build_parts(buildings, footprints_mm, heights_mm, cfg.tool.diameter_mm, cfg.tiers)

    out_dir = Path("outputs") / cfg.campus.name
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    for part in parts:
        extrude_box(part.footprint_local, part.height_mm).export(parts_dir / f"{part.id}.stl")

    base_outline_mm = to_model_mm(campus_outline_m, origin_m, scale_mm_per_m)
    build_base_plate(base_outline_mm).export(out_dir / "base.stl")

    typer.secho(
        f"Wrote {len(parts)} part(s) from {len(buildings)} building(s) and base.stl to {out_dir}",
        fg=typer.colors.GREEN,
    )


@app.command()
def coupon(species: str = typer.Option("maple", help="Wood species")) -> None:
    """Generate the tolerance test coupon. [week 6]"""
    _planned(6)


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
