"""Command-line interface. Run `quadwright --help` to see every command."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from quadwright import __version__
from quadwright.config import load_config
from quadwright.geo.footprints import load_buildings
from quadwright.geo.render import render_footprints
from quadwright.sources.osm import fetch_buildings

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
    """Download and cache OSM building data for the campus (FR-02)."""
    cfg = load_config(config)
    path = fetch_buildings(cfg.campus)
    typer.secho(f"Cached: {path}", fg=typer.colors.GREEN)


@app.command()
def preview(config: Path = ConfigArg) -> None:
    """Draw a 2D map of building footprints (FR-03, FR-04, FR-05). Tiers come later."""
    cfg = load_config(config)
    raw_path = Path("data/raw") / cfg.campus.name / "buildings.geojson"
    if not raw_path.exists():
        typer.secho(f"No cached data for {cfg.campus.name}.", fg=typer.colors.RED, err=True)
        typer.echo(f"Run first: quadwright fetch {config}", err=True)
        raise typer.Exit(code=1)

    buildings = load_buildings(raw_path, cfg.campus.bbox, cfg.heights)
    out_path = Path("outputs") / cfg.campus.name / "footprints.png"
    render_footprints(buildings, out_path)
    typer.secho(f"Wrote {out_path} ({len(buildings)} buildings)", fg=typer.colors.GREEN)


@app.command()
def audit(config: Path = ConfigArg) -> None:
    """List buildings with defaulted heights or roofs. [week 3]"""
    _planned(3)


@app.command()
def build(config: Path = ConfigArg) -> None:
    """Run the full pipeline and write the kit. [week 4]"""
    _planned(4)


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
