"""Confirms the geometry stack installed correctly (catches broken installs early)."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module", ["shapely", "pyproj", "osmnx", "trimesh", "manifold3d", "matplotlib"]
)
def test_geometry_stack_imports(module):
    importlib.import_module(module)


def test_manifold_union_is_watertight():
    import trimesh

    a = trimesh.creation.box((10, 10, 10))
    b = trimesh.creation.box((10, 10, 10))
    b.apply_translation((5, 0, 0))
    merged = trimesh.boolean.union([a, b], engine="manifold")
    assert merged.is_watertight
    assert merged.volume == pytest.approx(1500)
