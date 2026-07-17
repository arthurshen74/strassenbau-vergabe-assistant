"""Deterministic LV post-processing: turns the LLM's segmentation plus the SourceLine
rows into LVItem records. Every module here is pure (no I/O), so it is unit-testable in
isolation with synthetic SourceLine fixtures."""
