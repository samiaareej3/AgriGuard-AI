"""Base schema helpers shared by all domain schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.core.timeutil import ensure_utc

UTCDateTime = Annotated[datetime, AfterValidator(ensure_utc)]

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @classmethod
    def from_doc(cls, doc: dict[str, Any]):
        """Build a schema from a MongoDB document (``_id`` → ``id``)."""
        data = dict(doc)
        if "_id" in data:
            data["id"] = data.pop("_id")
        return cls.model_validate(data)


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
