"""Split multi-row INSERT payloads into batches that fit asyncpg's bind-parameter cap.

A single multi-row INSERT binds one parameter per column per row, and asyncpg rejects
any statement over 32767 parameters. Repositories that bulk-insert loop over
`insert_batches` and execute one statement per batch on the same connection, so the
batches still commit or roll back together.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from itertools import batched
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Table

ASYNCPG_MAX_BIND_PARAMS = 32767


def insert_batches(
    table: Table, rows: Sequence[BaseModel]
) -> Iterator[list[dict[str, Any]]]:
    """Yield the dumped rows in batches sized by the table's column count."""
    batch_size = ASYNCPG_MAX_BIND_PARAMS // len(table.c)
    for batch in batched(rows, batch_size):
        yield [row.model_dump() for row in batch]
