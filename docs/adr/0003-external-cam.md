# ADR-0003: Export STL per setup and use external CAM

Status: accepted
Date: 2026-10-02

## Context
Toolpath generation is safety-critical and CAM software already solves it well.

## Decision
Export one STL per machining setup in block-local coordinates; generate toolpaths in external CAM software.

## Consequences
Less risk and faster progress. Rejected for v1: generating G-code directly.
