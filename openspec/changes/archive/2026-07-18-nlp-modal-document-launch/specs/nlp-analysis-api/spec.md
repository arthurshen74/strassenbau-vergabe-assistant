# Spec delta: nlp-analysis-api

## REMOVED Requirements

### Requirement: Analyzable documents can be listed

Removed: `GET /nlp/documents` existed solely for the modal's document picker, which no longer exists. The Documents tab launches the modal from data it already has (document uuid, type, ingest state). The endpoint, `NlpDocumentRead`, and the service method are deleted.
