"""Importing this package registers every table on the shared metadata.

`metadata.create_all` only sees tables whose modules have been imported, so any process
that builds the schema (tests, bootstrap) must import this package first.
"""

from __future__ import annotations

from shared.db.tables.calculation_ground_truth import calculation_ground_truth
from shared.db.tables.conversations import conversations
from shared.db.tables.document_layout_regions import document_layout_regions
from shared.db.tables.documents import documents
from shared.db.tables.embedding_cache import embedding_cache
from shared.db.tables.entity_rules import entity_rules
from shared.db.tables.eval_results import eval_results
from shared.db.tables.eval_run_events import eval_run_events
from shared.db.tables.eval_runs import eval_runs
from shared.db.tables.form_fields import form_fields
from shared.db.tables.ingest_job_events import ingest_job_events
from shared.db.tables.ingest_jobs import ingest_jobs
from shared.db.tables.ingestion_activity_log import ingestion_activity_log
from shared.db.tables.ingestion_activity_log_archive import (
    ingestion_activity_log_archive,
)
from shared.db.tables.katalog_ausfuehrungsarten import katalog_ausfuehrungsarten
from shared.db.tables.katalog_baustoffe import katalog_baustoffe
from shared.db.tables.katalog_bauverfahren import katalog_bauverfahren
from shared.db.tables.katalog_bauverfahren_vorgaenge import (
    katalog_bauverfahren_vorgaenge,
)
from shared.db.tables.katalog_betriebsarten import katalog_betriebsarten
from shared.db.tables.katalog_betriebskategorien import katalog_betriebskategorien
from shared.db.tables.katalog_formeln import katalog_formeln
from shared.db.tables.katalog_globale_variablen import katalog_globale_variablen
from shared.db.tables.katalog_leistung_bauverfahren import katalog_leistung_bauverfahren
from shared.db.tables.katalog_leistungen import katalog_leistungen
from shared.db.tables.katalog_lieferanten import katalog_lieferanten
from shared.db.tables.katalog_lieferanten_preise import katalog_lieferanten_preise
from shared.db.tables.katalog_maschinen import katalog_maschinen
from shared.db.tables.katalog_stand import katalog_stand
from shared.db.tables.katalog_variablen import katalog_variablen
from shared.db.tables.katalog_vorgaenge import katalog_vorgaenge
from shared.db.tables.lv_items import lv_items
from shared.db.tables.lv_texts import lv_texts
from shared.db.tables.messages import messages
from shared.db.tables.ner_flags import ner_flags
from shared.db.tables.nlp_render_cache import nlp_render_cache
from shared.db.tables.openrouter_usage import openrouter_usage
from shared.db.tables.project_context_values import project_context_values
from shared.db.tables.project_info_activity_log import project_info_activity_log
from shared.db.tables.project_info_jobs import project_info_jobs
from shared.db.tables.projects import projects
from shared.db.tables.prompt_execution_log import prompt_execution_log
from shared.db.tables.prompt_versions import prompt_versions
from shared.db.tables.rag_ground_truth import rag_ground_truth
from shared.db.tables.rag_query_versions import rag_query_versions
from shared.db.tables.source_lines import source_lines
from shared.db.tables.thumbnails import thumbnails
from shared.db.tables.variable_corrections import variable_corrections

__all__ = [
    "calculation_ground_truth",
    "conversations",
    "document_layout_regions",
    "documents",
    "embedding_cache",
    "entity_rules",
    "eval_results",
    "eval_run_events",
    "eval_runs",
    "form_fields",
    "ingest_job_events",
    "ingest_jobs",
    "ingestion_activity_log",
    "ingestion_activity_log_archive",
    "katalog_ausfuehrungsarten",
    "katalog_baustoffe",
    "katalog_bauverfahren",
    "katalog_bauverfahren_vorgaenge",
    "katalog_betriebsarten",
    "katalog_betriebskategorien",
    "katalog_formeln",
    "katalog_globale_variablen",
    "katalog_leistung_bauverfahren",
    "katalog_leistungen",
    "katalog_lieferanten",
    "katalog_lieferanten_preise",
    "katalog_maschinen",
    "katalog_stand",
    "katalog_variablen",
    "katalog_vorgaenge",
    "lv_items",
    "lv_texts",
    "messages",
    "ner_flags",
    "nlp_render_cache",
    "openrouter_usage",
    "project_context_values",
    "project_info_activity_log",
    "project_info_jobs",
    "projects",
    "prompt_execution_log",
    "prompt_versions",
    "rag_ground_truth",
    "rag_query_versions",
    "source_lines",
    "thumbnails",
    "variable_corrections",
]
