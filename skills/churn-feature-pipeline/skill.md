---
name: churn-feature-pipeline
description: >
  Builds a versioned, lineage-documented feature pipeline with a local feature store for the
  e-commerce customer churn dataset. Ingests from three heterogeneous sources (CSV, SQLite,
  Parquet), builds a single parity-tested feature module shared by training and scoring paths,
  stands up a local feature store (SQLite metadata/version registry + parquet value snapshots),
  and runs data-quality checks, feature-registration scripts, and a test suite.
---

# Churn Feature Pipeline Skill

<!-- Full SKILL.md content — see .claude/skills/churn-feature-pipeline/SKILL.md -->