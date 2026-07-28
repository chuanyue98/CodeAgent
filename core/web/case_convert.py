"""Shared snake_case (Python) <-> camelCase (wire/JSON) conversion layer.

Any Pydantic model that should expose a camelCase JSON shape to frontend
clients while keeping snake_case attribute names on the Python side should
subclass :class:`ProtocolModel` and be serialized with :func:`wire`.

Originally introduced for the Agent Gateway protocol
(``core/services/agent_protocol.py``); generalized here so other FastAPI
routers can adopt the same convention.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ProtocolModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        use_enum_values=True,
    )


def wire(model: BaseModel) -> dict[str, Any]:
    """Return the stable camelCase JSON representation used on the wire."""

    return model.model_dump(mode="json", by_alias=True)
