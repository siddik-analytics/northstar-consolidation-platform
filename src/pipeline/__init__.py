"""
Phase 3 - ingestion, staging and chart-of-accounts harmonisation.

    python -m src.pipeline.run             full pipeline
    python -m src.pipeline.controls        controls only, against the built warehouse

The pipeline consumes the frozen Phase 2 source layer and produces one controlled finance
data model.  It performs no consolidation: no elimination, no translation, no adjustment
layer and no consolidated statement.  See docs/ingestion-design.md.
"""
