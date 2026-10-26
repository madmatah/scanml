"""Request bodies (JSON) of the API."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.text import multi_line, single_line
from ..records import UNCHANGED, DocumentChanges, PageChanges
from .deps import UUID_PATTERN


class SessionBody(BaseModel):
    token: str = Field(max_length=512)


class DocumentBody(BaseModel):
    """Body of PUT (title required on creation) and PATCH /api/documents/{id}."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(None, max_length=300)
    author: str | None = Field(None, max_length=300)
    kind: Literal["book", "document"] | None = None
    notes: str | None = Field(None, max_length=20_000)
    unwarp: bool | None = None

    def changes(self) -> DocumentChanges:
        return DocumentChanges(
            title=None if self.title is None else single_line(self.title),
            author=None if self.author is None else single_line(self.author),
            kind=self.kind,
            notes=None if self.notes is None else multi_line(self.notes),
            unwarp=self.unwarp,
        )


class PagePatchBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    manual_number: int | None = Field(None, ge=1, le=9999)
    excluded: bool | None = None
    rotation: Literal[0, 90, 180, 270] | None = None

    def changes(self) -> PageChanges:
        return PageChanges(
            # An explicit null clears the manual number; an absent field keeps it.
            manual_number=self.manual_number if "manual_number" in self.model_fields_set else UNCHANGED,
            excluded=self.excluded,
            rotation=self.rotation,
        )


class PageOrderBody(BaseModel):
    """Body of PUT /api/documents/{id}/order: the pages of the reading order, in the wanted order."""

    model_config = ConfigDict(extra="ignore")

    page_ids: list[Annotated[str, Field(pattern=f"^{UUID_PATTERN}$")]] = Field(max_length=10_000)
