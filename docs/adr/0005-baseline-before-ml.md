# ADR-0005: Rules-based baseline before any ML

Status: accepted
Date: 2026-10-02

## Context
ML components need a working product and a fair benchmark to be judged against.

## Decision
Build rule-based height and roof logic first; ML models ship only behind a config flag and only if they beat the baseline on unseen campuses.

## Consequences
A working product at every stage and honest evaluation. Rejected: starting with deep learning.
