from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from .models import SearchResult


class CatalogProvider(Protocol):
    id: str
    name: str

    def home(self) -> Iterable[SearchResult]: ...
    def search(self, query: str) -> Iterable[SearchResult]: ...


@dataclass(frozen=True, slots=True)
class CatalogSection:
    title: str
    items: tuple[SearchResult, ...]
