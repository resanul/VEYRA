from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from veyra.extensions.cs3_api import (
    CloudStreamApiBridge,
    CS3ExtractorInfo,
    CS3ProviderInfo,
    search_result_from_cloudstream,
    stream_source_from_cloudstream,
)
from veyra.providers.models import SearchResult, StreamSource


@dataclass(frozen=True, slots=True)
class CloudStreamHomePage:
    """Portable equivalent of a CloudStream HomePageList response."""

    name: str
    items: tuple[SearchResult, ...] = ()
    has_next: bool = False
    has_prev: bool = False


@dataclass(frozen=True, slots=True)
class CloudStreamLoadResponse:
    """Portable equivalent of a CloudStream LoadResponse."""

    item: SearchResult
    streams: tuple[StreamSource, ...] = ()
    episodes: tuple[SearchResult, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CloudStreamLifecycleResponse:
    providers: tuple[CS3ProviderInfo, ...] = ()
    extractors: tuple[CS3ExtractorInfo, ...] = ()
    home_pages: tuple[CloudStreamHomePage, ...] = ()
    results: tuple[SearchResult, ...] = ()
    load: CloudStreamLoadResponse | None = None
    streams: tuple[StreamSource, ...] = ()
    error: str | None = None


class CloudStreamLifecycleAdapter:
    """Clean-room adapter for the MainAPI/ExtractorApi lifecycle.

    The adapter only consumes/produces JSON-compatible CloudStream-shaped
    payloads. It deliberately does not load Android DEX or copy CloudStream
    implementation code. A CS3 execution runtime can supply ``request``.
    """

    METHODS = ("providers", "home", "search", "load", "loadLinks", "streams")

    def __init__(self, request: Callable[[str, dict[str, Any]], dict[str, Any]]) -> None:
        self._request = request
        self._bridge = CloudStreamApiBridge()

    @staticmethod
    def _items(payload: Mapping[str, Any], key: str = "items") -> tuple[SearchResult, ...]:
        raw = payload.get(key, ())
        if not isinstance(raw, (list, tuple)):
            return ()
        return tuple(search_result_from_cloudstream(item) for item in raw if isinstance(item, dict))

    def providers(self) -> CloudStreamLifecycleResponse:
        payload = self._request("providers", {})
        providers: list[CS3ProviderInfo] = []
        extractors: list[CS3ExtractorInfo] = []
        for value in payload.get("providers", ()):
            if isinstance(value, dict):
                providers.append(self._bridge.register_main_api(value))
        for value in payload.get("extractors", ()):
            if isinstance(value, dict):
                extractors.append(self._bridge.register_extractor_api(value))
        return CloudStreamLifecycleResponse(tuple(providers), tuple(extractors), error=payload.get("error"))

    def get_main_page(self, page: int = 1) -> CloudStreamLifecycleResponse:
        payload = self._request("home", {"page": page})
        pages: list[CloudStreamHomePage] = []
        raw_pages = payload.get("pages")
        if isinstance(raw_pages, list):
            for raw in raw_pages:
                if not isinstance(raw, dict):
                    continue
                pages.append(CloudStreamHomePage(
                    name=str(raw.get("name") or raw.get("title") or "Home"),
                    items=self._items(raw),
                    has_next=bool(raw.get("hasNext") or raw.get("has_next", False)),
                    has_prev=bool(raw.get("hasPrev") or raw.get("has_prev", False)),
                ))
        elif payload.get("items") is not None:
            pages.append(CloudStreamHomePage(
                name=str(payload.get("name") or "Home"),
                items=self._items(payload),
                has_next=bool(payload.get("hasNext") or payload.get("has_next", False)),
            ))
        return CloudStreamLifecycleResponse(home_pages=tuple(pages), error=payload.get("error"))

    def search(self, query: str, page: int = 1) -> CloudStreamLifecycleResponse:
        payload = self._request("search", {"query": query, "page": page})
        return CloudStreamLifecycleResponse(results=self._items(payload), error=payload.get("error"))

    def load(self, url: str) -> CloudStreamLifecycleResponse:
        payload = self._request("load", {"url": url})
        item_payload = payload.get("item")
        if not isinstance(item_payload, dict):
            return CloudStreamLifecycleResponse(error=payload.get("error") or "load response did not contain an item")
        item = search_result_from_cloudstream(item_payload)
        episodes = self._items(payload, "episodes")
        streams = tuple(
            stream_source_from_cloudstream(value)
            for value in payload.get("streams", ())
            if isinstance(value, dict)
        )
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        loaded = CloudStreamLoadResponse(item=item, streams=streams, episodes=episodes, metadata=metadata)
        return CloudStreamLifecycleResponse(load=loaded, streams=streams, error=payload.get("error"))

    def load_links(self, url: str, *, referer: str | None = None, data: str | None = None) -> CloudStreamLifecycleResponse:
        payload = self._request("loadLinks", {"url": url, "referer": referer, "data": data})
        streams = tuple(
            stream_source_from_cloudstream(value)
            for value in payload.get("streams", ())
            if isinstance(value, dict)
        )
        return CloudStreamLifecycleResponse(streams=streams, error=payload.get("error"))

    def streams(self, item: SearchResult) -> CloudStreamLifecycleResponse:
        payload = self._request("streams", {
            "item": {
                "id": item.id,
                "title": item.title,
                "url": item.url,
                "kind": item.kind,
                "year": item.year,
                "poster": item.poster,
                "metadata": dict(item.metadata),
            }
        })
        streams = tuple(
            stream_source_from_cloudstream(value)
            for value in payload.get("streams", ())
            if isinstance(value, dict)
        )
        return CloudStreamLifecycleResponse(streams=streams, error=payload.get("error"))
