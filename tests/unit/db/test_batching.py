from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import Column, Integer, MetaData, Table

from shared.db.batching import ASYNCPG_MAX_BIND_PARAMS, insert_batches

_table = Table(
    "batching_probe",
    MetaData(),
    Column("a", Integer),
    Column("b", Integer),
    Column("c", Integer),
)


class _Row(BaseModel):
    a: int
    b: int
    c: int


def test_batches_stay_under_bind_parameter_cap() -> None:
    per_batch = ASYNCPG_MAX_BIND_PARAMS // 3
    rows = [_Row(a=i, b=i, c=i) for i in range(per_batch * 2 + 1)]
    batches = list(insert_batches(_table, rows))
    assert [len(b) for b in batches] == [per_batch, per_batch, 1]
    assert all(len(b) * 3 <= ASYNCPG_MAX_BIND_PARAMS for b in batches)
    assert batches[2] == [{"a": per_batch * 2, "b": per_batch * 2, "c": per_batch * 2}]


def test_empty_rows_yield_no_batches() -> None:
    assert list(insert_batches(_table, [])) == []
