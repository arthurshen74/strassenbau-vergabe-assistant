from __future__ import annotations

from pydantic import BaseModel

OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {}


class UnknownOutputSchemaError(LookupError):
    pass


def register_output_schema(name: str, model: type[BaseModel]) -> None:
    if name in OUTPUT_SCHEMAS and OUTPUT_SCHEMAS[name] is not model:
        raise ValueError(
            f"output schema {name!r} already registered to a different class"
        )
    OUTPUT_SCHEMAS[name] = model


def resolve_output_schema(ref: str | None) -> type[BaseModel] | None:
    if ref is None:
        return None
    try:
        return OUTPUT_SCHEMAS[ref]
    except KeyError as exc:
        raise UnknownOutputSchemaError(
            f"no output schema registered for {ref!r}"
        ) from exc
