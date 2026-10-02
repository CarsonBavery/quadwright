from pathlib import Path

from typer.testing import CliRunner

from quadwright.cli import app

runner = CliRunner()
EXAMPLE = str(Path(__file__).parents[1] / "configs" / "campuses" / "example-university.yaml")


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
    result = runner.invoke(app, ["build", EXAMPLE])
    assert result.exit_code == 2
