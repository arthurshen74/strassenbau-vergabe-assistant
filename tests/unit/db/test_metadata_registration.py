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
    "ingestion_activity_log",
    "ingestion_activity_log_archive",
    "lv_items",
    "lv_texts",
    "prompt_versions",
    "openrouter_usage",
    "prompt_execution_log",
    "conversations",
    "messages",
    "embedding_cache",
    "document_layout_regions",
    "nlp_render_cache",
    "entity_rules",
    "ner_flags",
    "calculation_ground_truth",
    "variable_corrections",
    "rag_ground_truth",
    "eval_runs",
    "eval_run_events",
    "eval_results",
    "project_context_values",
    "katalog_leistungen",
    "katalog_bauverfahren",
    "katalog_vorgaenge",
    "katalog_ausfuehrungsarten",
    "katalog_betriebskategorien",
    "katalog_betriebsarten",
    "katalog_formeln",
    "katalog_variablen",
    "katalog_globale_variablen",
    "katalog_baustoffe",
    "katalog_lieferanten",
    "katalog_maschinen",
    "katalog_stand",
    "katalog_leistung_bauverfahren",
    "katalog_bauverfahren_vorgaenge",
    "katalog_lieferanten_preise",
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
