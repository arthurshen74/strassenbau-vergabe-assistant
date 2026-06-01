from __future__ import annotations

import shared.db.tables  # noqa: F401  -- registers tables on the shared metadata
from shared.db.metadata import metadata

EXPECTED_TABLES = {
    "projects",
    "documents",
    "source_lines",
    "thumbnails",
    "ingest_jobs",
    "ingest_job_events",
    "lv_items",
    "prompt_versions",
    "openrouter_usage",
}


def test_all_tables_registered() -> None:
    assert set(metadata.tables) == EXPECTED_TABLES


def test_one_lv_document_partial_index_present() -> None:
    documents = metadata.tables["documents"]
    index_names = {ix.name for ix in documents.indexes}
    assert "uq_one_lv_document_per_project" in index_names


def test_lv_items_oz_unique_per_document() -> None:
    lv_items = metadata.tables["lv_items"]
    unique_cols = {
        tuple(sorted(c.name for c in con.columns))
        for con in lv_items.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("document_uuid", "oz") in unique_cols
