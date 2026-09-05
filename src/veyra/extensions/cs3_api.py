from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from veyra.providers.models import SearchResult, StreamSource


@dataclass(frozen=True, slots=True)
class CS3ProviderInfo:
    """Portable representation of CloudStream MainAPI registration metadata."""

    id: str
    name: str
    main_api: str | None = None
    supported_types: tuple[str, ...] = ()
    language: str | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CS3ExtractorInfo:
    """Portable representation of an ExtractorApi registration."""

    name: str
    domains: tuple[str, ...] = ()
    kind: str = "video"
    requires_referer: bool = False


@dataclass(frozen=True, slots=True)
class CS3ProviderResponse:
    """Wire response used by the future CS3 sidecar runtime."""

    providers: tuple[CS3ProviderInfo, ...] = ()
    extractors: tuple[CS3ExtractorInfo, ...] = ()
    items: tuple[SearchResult, ...] = ()
    streams: tuple[StreamSource, ...] = ()
    error: str | None = None


def _tuple_strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    return ()


def search_result_from_cloudstream(value: dict[str, Any]) -> SearchResult:
    """Translate common MainAPI search/load metadata into VEYRA's model."""
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    year = value.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    return SearchResult(
        id=str(value.get("id") or value.get("url") or value.get("title") or "item"),
        title=str(value.get("title") or value.get("name") or "Untitled"),
        url=str(value.get("url") or ""),
        kind=str(value.get("kind") or value.get("type") or "unknown"),
        year=year,
        poster=value.get("poster") or value.get("posterUrl") or value.get("image"),
        metadata={str(k): str(v) for k, v in metadata.items()},
    )


def stream_source_from_cloudstream(value: dict[str, Any]) -> StreamSource:
    """Translate common ExtractorLink/stream metadata into VEYRA's model."""
    headers = value.get("headers")
    if not isinstance(headers, dict):
        headers = {}
    subtitles = value.get("subtitles") or value.get("subtitleUrls") or ()
    return StreamSource(
        url=str(value.get("url") or ""),
        quality=str(value.get("quality") or value.get("label") or "auto"),
        format=value.get("format") or value.get("type"),
        headers={str(k): str(v) for k, v in headers.items()},
        subtitles=_tuple_strings(subtitles),
    )


@dataclass(slots=True)
class CloudStreamApiBridge:
    """Clean-room API boundary for MainAPI + ExtractorApi semantics.

    This module defines the portable contract; it does not decompile or
    execute downloaded DEX. A dedicated sidecar can implement this wire
    contract later without changing VEYRA's catalog/player layers.
    """

    providers: list[CS3ProviderInfo] = field(default_factory=list)
    extractors: list[CS3ExtractorInfo] = field(default_factory=list)

    def register_main_api(self, payload: dict[str, Any]) -> CS3ProviderInfo:
        info = CS3ProviderInfo(
            id=str(payload.get("id") or payload.get("internalName") or payload.get("name") or "provider"),
            name=str(payload.get("name") or payload.get("mainUrl") or "CloudStream provider"),
            main_api=payload.get("mainApi") or payload.get("mainUrl"),
            supported_types=_tuple_strings(payload.get("supportedTypes") or payload.get("tvTypes")),
            language=payload.get("language") or payload.get("lang"),
            capabilities=_tuple_strings(payload.get("capabilities")),
        )
        self.providers.append(info)
        return info

    def register_extractor_api(self, payload: dict[str, Any]) -> CS3ExtractorInfo:
        info = CS3ExtractorInfo(
            name=str(payload.get("name") or payload.get("extractor") or "Extractor"),
            domains=_tuple_strings(payload.get("domains") or payload.get("domain")),
            kind=str(payload.get("kind") or "video"),
            requires_referer=bool(payload.get("requiresReferer") or payload.get("requires_referer", False)),
        )
        self.extractors.append(info)
        return info

    def result(self, *, items: list[dict[str, Any]] | None = None, streams: list[dict[str, Any]] | None = None, error: str | None = None) -> CS3ProviderResponse:
        return CS3ProviderResponse(
            providers=tuple(self.providers),
            extractors=tuple(self.extractors),
            items=tuple(search_result_from_cloudstream(item) for item in (items or [])),
            streams=tuple(stream_source_from_cloudstream(stream) for stream in (streams or [])),
            error=error,
        )
