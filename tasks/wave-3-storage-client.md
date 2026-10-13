# Wave 3 — MinIO/S3 storage client

Read `tasks/README.md` first. Independent of other waves; depends on `server/shared/config.py`.
`boto3` is already a dependency. `server/scripts/bootstrap_storage.py` already shows the boto3 client
construction + bucket creation pattern — reuse it.

## Goal

`server/shared/clients/storage/client.py` — object storage for raw uploaded files and page thumbnails.

## Spec

- Build a boto3 S3 client from `settings.s3_endpoint`, `settings.s3_access_key`,
  `settings.s3_secret_key` (MinIO), default bucket `settings.s3_bucket`.
- Methods: `put_object(key, data, content_type)`, `get_object(key) -> bytes`,
  `presign_get(key, expires) -> str` (and `presign_put` if useful for direct uploads).
- **Object-key helpers** as module-level constants/functions, consistent with the `Thumbnail`
  `object_key` / `bucket` fields (e.g. a raw-file key and a per-page thumbnail key derived from
  `document_uuid` + `page_number`). These keys are a contract — define them once here.
- Re-export the client in `server/shared/clients/storage/__init__.py`.

## Conventions

`from __future__ import annotations`; full type hints; one boundary log on failure. boto3 is sync — keep
the client sync (callers can offload to a thread if needed); do not add `aioboto3` (not a dependency).

## Verification

`tests/integration/storage/test_client.py` against compose MinIO, **skipped if `settings.s3_endpoint`
is unreachable**: round-trip `put_object`/`get_object`; `presign_get` returns a URL. Bring up infra:
`docker compose up -d minio && (cd server && python -m scripts.bootstrap_storage)`.

## Done when

Put/get/presign work against compose MinIO and the gated integration test passes (skips when MinIO is
down).
