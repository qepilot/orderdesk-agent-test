"""Pagination helper.

``limit`` defaults to 20 and must be 1..100: larger values are *rejected*
with a 422 validation error (not clamped). ``offset`` must be >= 0.
Responses are ``{items, total, limit, offset}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True)
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0


def page_params(
    limit: Annotated[
        int, Query(ge=1, le=MAX_LIMIT, description="Page size, 1-100.")
    ] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, description="Items to skip.")] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


Pagination = Annotated[PageParams, Depends(page_params)]


class Page(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


def make_page(items: list[Any], total: int, params: PageParams) -> dict[str, Any]:
    """Build the response body; `total` is the count before limit/offset."""
    return {"items": items, "total": total, "limit": params.limit, "offset": params.offset}
