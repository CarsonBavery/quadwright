import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from quadwright.cli import app

runner = CliRunner()
EXAMPLE = str(Path(__file__).parents[1] / "configs" / "campuses" / "example-university.yaml")
FIXTURE = Path(__file__).parent / "fixtures" / "sample_buildings.geojson"


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
