"""FR-01: load and validate a campus config."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from quadwright.config import load_config, load_species_config

EXAMPLE = Path(__file__).parents[1] / "configs" / "campuses" / "example-university.yaml"
SPECIES_DIR = Path(__file__).parents[1] / "configs" / "species"


@pytest.fixture
def example_data() -> dict:
    return yaml.safe_load(EXAMPLE.read_text())


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "campus.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_fr01_example_config_loads():
    cfg = load_config(EXAMPLE)
    assert cfg.campus.name == "example-university"
    assert cfg.tool.radius_mm == pytest.approx(1.5875)


def test_fr01_rejects_both_scale_options(tmp_path, example_data):
    example_data["scale"]["ratio"] = 2500
    with pytest.raises(ValidationError, match="exactly one"):
        load_config(_write(tmp_path, example_data))


def test_fr01_rejects_neither_scale_option(tmp_path, example_data):
    del example_data["scale"]["target_size_mm"]
    with pytest.raises(ValidationError, match="exactly one"):
        load_config(_write(tmp_path, example_data))


def test_fr01_rejects_inverted_bbox(tmp_path, example_data):
    w, s, e, n = example_data["campus"]["bbox"]
    example_data["campus"]["bbox"] = [e, s, w, n]
    with pytest.raises(ValidationError, match="west < east"):
        load_config(_write(tmp_path, example_data))


def test_fr01_rejects_unknown_keys(tmp_path, example_data):
    example_data["tool"]["diamter_mm"] = 3  # typo should fail, not be ignored
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, example_data))


def test_fr01_rejects_bad_tier_override(tmp_path, example_data):
    example_data["tiers"]["overrides"]["Library"] = 7
    with pytest.raises(ValidationError, match="0-3"):
        load_config(_write(tmp_path, example_data))


def test_fr18_example_species_config_loads():
    # Not asserting on clearance_mm's value here -- configs/species/maple.yaml
    # is live project state (a placeholder today, a real measurement later),
    # not a fixture this test should pin down. test_fr18_species_config_rejects_null
    # below covers the still-unmeasured case with its own tmp_path fixture.
    cfg = load_species_config("maple", species_dir=SPECIES_DIR)
    assert cfg.species == "maple"


def test_fr18_species_config_accepts_a_null_clearance(tmp_path):
    path = tmp_path / "maple.yaml"
    path.write_text(yaml.safe_dump({"species": "maple", "clearance_mm": None}))
    cfg = load_species_config("maple", species_dir=tmp_path)
    assert cfg.clearance_mm is None


def test_fr18_species_config_accepts_a_measured_clearance(tmp_path):
    path = tmp_path / "maple.yaml"
    path.write_text(yaml.safe_dump({"species": "maple", "clearance_mm": 0.15}))
    cfg = load_species_config("maple", species_dir=tmp_path)
    assert cfg.clearance_mm == pytest.approx(0.15)


def test_fr18_species_config_rejects_unknown_keys(tmp_path):
    path = tmp_path / "maple.yaml"
    path.write_text(yaml.safe_dump({"species": "maple", "claerance_mm": 0.15}))  # typo
    with pytest.raises(ValidationError):
        load_species_config("maple", species_dir=tmp_path)
