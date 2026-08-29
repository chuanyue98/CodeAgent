"""Shared snake_case (Python) <-> camelCase (wire/JSON) conversion layer.

A route that *builds* its own response shape declares it as a
:class:`ProtocolModel` and serializes it with :func:`wire`. A route that
*forwards* a shape some lower layer already assembled passes it through
:func:`camelize` instead -- restating that shape as a model here would mean
maintaining the same field list in two files.

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

from collections.abc import Mapping, Sequence
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
    """Return the stable camelCase JSON representation used on the wire.

    Use this for shapes the router itself builds. When the shape already
    exists as a dict or dataclass somewhere below the route, use
    :func:`camelize` instead of restating it as a model.
    """

    return model.model_dump(mode="json", by_alias=True)


def camelize(value: Any) -> Any:
    """Rewrite mapping keys to camelCase, recursively, leaving values alone.

    The counterpart to :func:`wire` for payloads a lower layer already
    assembled -- ``to_summary_dict()``, ``vars(record)``, an aggregator's
    summary. Mirroring those shapes as a model here would mean maintaining
    the field list twice, and Pydantic drops unknown keys silently, so a
    field added below would vanish from the API with nothing to catch it.

    Key absence is preserved: heterogeneous rows -- an audit timeline where
    a message event carries no tool fields -- keep their gaps instead of
    shipping the other variant's nulls.
    """

    if isinstance(value, Mapping):
        return {_to_camel(key): camelize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [camelize(item) for item in value]
    return value
