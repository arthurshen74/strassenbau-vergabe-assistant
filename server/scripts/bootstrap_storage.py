from __future__ import annotations

import time

import boto3
from botocore.exceptions import EndpointConnectionError

from shared.config import settings


def main() -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )
    bucket = settings.s3_bucket
    # MinIO may not accept connections the instant the container starts; retry.
    for _ in range(30):
        try:
            existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
            if bucket in existing:
                print(f"  {bucket}: exists")
            else:
                client.create_bucket(Bucket=bucket)
                print(f"  {bucket}: created")
            return
        except EndpointConnectionError:
            time.sleep(2)
    raise RuntimeError(f"MinIO unreachable; could not ensure bucket {bucket!r}")


if __name__ == "__main__":
    main()
