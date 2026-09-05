from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from .models import SearchResult, StreamSource


class Provider(Protocol):
    id: str
    name: str

    def search(self, query: str) -> Iterable[SearchResult]: ...
    def streams(self, item: SearchResult) -> Iterable[StreamSource]: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        if not provider.id or provider.id in self._providers:
            raise ValueError("provider id must be unique and non-empty")
        self._providers[provider.id] = provider

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def get(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def all(self) -> tuple[Provider, ...]:
        return tuple(self._providers.values())

    def search_all(self, query: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        for provider in self._providers.values():
            try:
                results.extend(provider.search(query))
            except Exception:
                continue
        return results
