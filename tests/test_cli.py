import json
import shutil
from pathlib import Path

import trimesh
import yaml
from typer.testing import CliRunner

from quadwright.cli import app
from quadwright.mesh.extrude import BASE_PLATE_THICKNESS_MM

runner = CliRunner()
EXAMPLE = str(Path(__file__).parents[1] / "configs" / "campuses" / "example-university.yaml")
FIXTURE = Path(__file__).parent / "fixtures" / "sample_buildings.geojson"


def _config_with_outputs(tmp_path: Path, outputs: list[str]) -> str:
    """A copy of example-university.yaml with its outputs: list replaced."""
    data = yaml.safe_load(Path(EXAMPLE).read_text())
    data["outputs"] = outputs
    config_path = tmp_path / "custom.yaml"
    config_path.write_text(yaml.safe_dump(data))
    return str(config_path)


def _cache_fixture_buildings(tmp_path: Path) -> None:
    cache_dir = tmp_path / "data" / "raw" / "example-university"
    cache_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, cache_dir / "buildings.geojson")


def _write_species_config(
    tmp_path: Path, species: str = "maple", clearance_mm: float = 0.15
) -> None:
    """A measured-clearance species config, so `build` doesn't hit MissingClearanceError.

    example-university.yaml's materials.buildings is "maple" -- the real
    configs/species/maple.yaml still has clearance_mm: null (no coupon cut
    yet), so CLI tests need their own fixture value here, same way they
    fixture buildings.geojson instead of hitting the real network/cache.
    """
    species_dir = tmp_path / "configs" / "species"
    species_dir.mkdir(parents=True, exist_ok=True)
    (species_dir / f"{species}.yaml").write_text(
        yaml.safe_dump({"species": species, "clearance_mm": clearance_mm})
    )


def test_validate_example_succeeds():
    result = runner.invoke(app, ["validate", EXAMPLE])
    assert result.exit_code == 0
    assert "OK: example-university" in result.output


def test_validate_bad_config_fails(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("campus: {name: x}\n")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1


def test_planned_commands_exit_cleanly():
    result = runner.invoke(app, ["sheets", EXAMPLE])
    assert result.exit_code == 2


def test_fr04_preview_without_fetch_fails_with_a_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate from any real data/raw in the repo
    result = runner.invoke(app, ["preview", EXAMPLE])
    assert result.exit_code == 1
    assert "quadwright fetch" in result.output


def test_fr06_build_without_fetch_fails_with_a_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate from any real data/raw in the repo
    result = runner.invoke(app, ["build", EXAMPLE])
    assert result.exit_code == 1
    assert "quadwright fetch" in result.output


def test_fr11_audit_without_fetch_fails_with_a_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolate from any real data/raw in the repo
    result = runner.invoke(app, ["audit", EXAMPLE])
    assert result.exit_code == 1
    assert "quadwright fetch" in result.output


def test_fr11_audit_reports_height_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache_dir = tmp_path / "data" / "raw" / "example-university"
    cache_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, cache_dir / "buildings.geojson")

    result = runner.invoke(app, ["audit", EXAMPLE])

    assert result.exit_code == 0
    # "Old Main" matches example-university.yaml's heights.overrides; the
    # fixture's other building has no name tag and no height tag, so it
    # falls through to the campus default. Only *named* defaulted
    # buildings get listed (only they can get a heights.overrides fix),
    # and there are none here, so that section shouldn't appear at all.
    assert "override" in result.output
    assert "default" in result.output
    assert "Named buildings" not in result.output


def test_fr11_audit_lists_named_buildings_with_a_defaulted_height(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache_dir = tmp_path / "data" / "raw" / "example-university"
    cache_dir.mkdir(parents=True)
    feature = {
        "type": "Feature",
        "properties": {"element": "way", "id": 999, "building": "yes", "name": "Mystery Hall"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-79.998, 35.004],
                    [-79.997, 35.004],
                    [-79.997, 35.005],
                    [-79.998, 35.005],
                    [-79.998, 35.004],
                ]
            ],
        },
    }
    (cache_dir / "buildings.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]})
    )

    result = runner.invoke(app, ["audit", EXAMPLE])

    assert result.exit_code == 0
    assert "Named buildings with a defaulted height (1)" in result.output
    assert "Mystery Hall" in result.output


def test_fr18_build_fails_with_a_hint_when_clearance_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cache_fixture_buildings(tmp_path)
    # No _write_species_config call -- configs/species/maple.yaml doesn't exist
    # at all here, same as a species nobody has ever run the coupon test for.
    (tmp_path / "configs" / "species").mkdir(parents=True)
    (tmp_path / "configs" / "species" / "maple.yaml").write_text(
        yaml.safe_dump({"species": "maple", "clearance_mm": None})
    )
    config = _config_with_outputs(tmp_path, [])

    result = runner.invoke(app, ["build", config])

    assert result.exit_code == 1
    assert "quadwright coupon" in result.output


def test_fr19_build_unions_a_joinery_boss_onto_each_part(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cache_fixture_buildings(tmp_path)
    _write_species_config(tmp_path)
    config = _config_with_outputs(tmp_path, ["part_stl"])

    result = runner.invoke(app, ["build", config])

    assert result.exit_code == 0
    parts_dir = tmp_path / "outputs" / "example-university" / "parts"
    for stl_path in parts_dir.glob("*.stl"):
        part_mesh = trimesh.load(stl_path)
        assert part_mesh.is_watertight
        # A plain box's volume is its footprint area times its height; the
        # integral tenon/dowel boss (FR-19) adds material below that, so
        # the real part is strictly bigger than that plain-box figure.
        min_x, min_y, _ = part_mesh.bounds[0]
        max_x, max_y, max_z = part_mesh.bounds[1]
        box_only_volume = (max_x - min_x) * (max_y - min_y) * max_z
        assert part_mesh.volume > box_only_volume * 0.5  # sanity floor, not a tight bound


def test_fr19_build_cuts_joinery_pockets_into_a_flat_base(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cache_fixture_buildings(tmp_path)
    _write_species_config(tmp_path)
    config = _config_with_outputs(tmp_path, ["base_stl"])

    result = runner.invoke(app, ["build", config])

    assert result.exit_code == 0
    assert "skipping" not in result.output  # example-university has no lidar_project -- flat base
    base_mesh = trimesh.load(tmp_path / "outputs" / "example-university" / "base.stl")
    assert base_mesh.is_watertight
    min_x, min_y, _ = base_mesh.bounds[0]
    max_x, max_y, _ = base_mesh.bounds[1]
    flat_slab_volume = (max_x - min_x) * (max_y - min_y) * BASE_PLATE_THICKNESS_MM
    assert base_mesh.volume < flat_slab_volume


def test_fr16_build_writes_setup_sheets_when_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cache_fixture_buildings(tmp_path)
    _write_species_config(tmp_path)
    config = _config_with_outputs(tmp_path, ["setup_sheets"])

    result = runner.invoke(app, ["build", config])

    assert result.exit_code == 0
    sheets_path = tmp_path / "outputs" / "example-university" / "setup_sheets.txt"
    assert sheets_path.exists()
    assert "Setup sheets:" in sheets_path.read_text(encoding="utf-8")


def test_fr14_build_only_writes_requested_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cache_fixture_buildings(tmp_path)
    _write_species_config(tmp_path)
    config = _config_with_outputs(tmp_path, ["base_stl"])  # no part_stl, no tier_report

    result = runner.invoke(app, ["build", config])

    assert result.exit_code == 0
    out_dir = tmp_path / "outputs" / "example-university"
    assert (out_dir / "base.stl").exists()
    assert not (out_dir / "parts").exists()
    assert not (out_dir / "tier_report.txt").exists()


def test_fr14_build_skips_base_stl_when_not_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cache_fixture_buildings(tmp_path)
    _write_species_config(tmp_path)
    config = _config_with_outputs(tmp_path, ["part_stl"])

    result = runner.invoke(app, ["build", config])

    assert result.exit_code == 0
    out_dir = tmp_path / "outputs" / "example-university"
    assert not (out_dir / "base.stl").exists()
    assert any((out_dir / "parts").glob("*.stl"))


def test_fr14_build_always_writes_kit_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cache_fixture_buildings(tmp_path)
    _write_species_config(tmp_path)
    config = _config_with_outputs(tmp_path, [])  # nothing requested at all

    result = runner.invoke(app, ["build", config])

    assert result.exit_code == 0
    assert (tmp_path / "data" / "interim" / "example-university" / "kit.json").exists()
