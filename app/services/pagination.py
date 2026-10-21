"""Small pagination helper that works with any SQLAlchemy ``select`` statement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.sql import Select

from app.extensions import db


@dataclass
class Page:
    items: list[Any]
    page: int
    per_page: int
    total: int
    pages: int = field(init=False)

    def __post_init__(self) -> None:
        self.pages = max(1, -(-self.total // self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def first_item(self) -> int:
        return 0 if self.total == 0 else (self.page - 1) * self.per_page + 1

    @property
    def last_item(self) -> int:
        return min(self.total, self.page * self.per_page)


def paginate(statement: Select, page: int, per_page: int) -> Page:
    """Run ``statement`` with LIMIT/OFFSET. Rows are returned as SQLAlchemy ``Row`` objects."""
    total = db.session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    total = int(total or 0)
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    rows = db.session.execute(statement.limit(per_page).offset((page - 1) * per_page)).all()
    return Page(items=list(rows), page=page, per_page=per_page, total=total)
