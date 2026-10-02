# ADR-0001: Python with shapely, trimesh, and manifold3d

Status: accepted
Date: 2026-10-02

## Context
The pipeline needs 2D polygon operations, 3D meshes, and reliable boolean unions, and must be easy to test.

## Decision
Use Python with shapely (2D), trimesh (meshes and export), and manifold3d (booleans).

## Consequences
Mature, well-documented libraries and plain pytest testing. Rejected: Blender scripting, which is harder to test and run in CI.
