# ADR-0002: OpenStreetMap as the primary data source

Status: accepted
Date: 2026-10-02

## Context
Building footprints and heights must be free, openly licensed, and available for most campuses.

## Decision
Use OpenStreetMap via Overpass as the primary source, with USGS 3DEP LiDAR as a backup for heights.

## Consequences
Broad coverage under the ODbL with attribution. Rejected: Google photorealistic 3D tiles, whose terms forbid extracting geometry.
