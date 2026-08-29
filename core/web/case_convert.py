"""Shared snake_case (Python) <-> camelCase (wire/JSON) conversion layer.

Any Pydantic model that should expose a camelCase JSON shape to frontend
clients while keeping snake_case attribute names on the Python side should
subclass :class:`ProtocolModel` and be serialized with :func:`wire`.

Originally introduced for the Agent Gateway protocol
(``core/services/agent_protocol.py``); generalized here so other FastAPI
routers can adopt the same convention. Every router that returns JSON with
multi-word field names now goes through it.

Three things deliberately stay snake_case, and none of them are JSON field
names:

``/api/config`` and ``/api/groups``
    Their payload *is* ``config.json``. The keys are the file format, and a
    UI editing a shape that does not match what is on disk is a worse
    problem than the inconsistency.
Query and path parameters
    ``?ca_token=``, ``?cron_expr=``, ``?session_id=`` are URL contracts bound
    to Python parameter names, not body fields.
Engine-native payloads
    Tool-call arguments (``file_path``, ``old_string``), session files, and
    the analytics history file are the providers' formats passing through.
    Renaming their keys would be inventing data.

Internal dicts (``pty._ACTIVE_SESSIONS``, the domain's
``to_summary_dict()``) also stay snake_case; they are Python-side
structures, and the model at the route is where the two vocabularies meet.
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


def wire(model: BaseModel, *, drop_none: bool = False) -> dict[str, Any]:
    """Return the stable camelCase JSON representation used on the wire.

    ``drop_none`` omits unset fields entirely rather than sending them as
    ``null``. Use it for heterogeneous rows -- an audit timeline where a
    message event has no tool fields -- so a large response does not carry a
    null for every field the other variant happens to have.
    """

    return model.model_dump(mode="json", by_alias=True, exclude_none=drop_none)
