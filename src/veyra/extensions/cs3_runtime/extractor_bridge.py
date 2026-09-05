from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from veyra.extensions.cs3_api import CS3ExtractorInfo, stream_source_from_cloudstream
from veyra.providers.models import StreamSource


@dataclass(frozen=True, slots=True)
class ExtractorRequest:
    """Portable request matching the useful ExtractorApi link semantics."""

    name: str
    url: str
    referer: str | None = None
    quality: str = "auto"
    headers: Mapping[str, str] = field(default_factory=dict)
    subtitle_urls: tuple[str, ...] = ()
    data: str | None = None


class ExtractorRegistry:
    """Registry of clean-room extractor metadata and domain routing."""

    def __init__(self) -> None:
        self._extractors: dict[str, CS3ExtractorInfo] = {}

    def register(self, info: CS3ExtractorInfo) -> CS3ExtractorInfo:
        key = info.name.strip().lower()
        if not key:
            raise ValueError("extractor name cannot be empty")
        self._extractors[key] = info
        return info

    def register_many(self, extractors: Iterable[CS3ExtractorInfo]) -> None:
        for info in extractors:
            self.register(info)

    def all(self) -> tuple[CS3ExtractorInfo, ...]:
        return tuple(self._extractors.values())

    def get(self, name: str) -> CS3ExtractorInfo | None:
        return self._extractors.get(name.strip().lower())

    def for_url(self, url: str) -> tuple[CS3ExtractorInfo, ...]:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        if not host:
            return ()
        matches: list[CS3ExtractorInfo] = []
        for info in self._extractors.values():
            for domain in info.domains:
                candidate = domain.lower().strip().lstrip(".").rstrip(".")
                if candidate and (host == candidate or host.endswith("." + candidate)):
                    matches.append(info)
                    break
        return tuple(matches)


class ExtractorApiBridge:
    """Bridge extractor registrations and link callbacks to VEYRA streams.

    The execution runtime supplies ``request``; this layer remains independent
    from Android/DEX implementation details and only translates JSON-shaped
    extractor responses into ``StreamSource`` objects.
    """

    def __init__(
        self,
        request: Callable[[str, dict[str, Any]], dict[str, Any]],
        registry: ExtractorRegistry | None = None,
    ) -> None:
        self._request = request
        self.registry = registry or ExtractorRegistry()

    def register(self, payload: dict[str, Any]) -> CS3ExtractorInfo:
        info = CS3ExtractorInfo(
            name=str(payload.get("name") or payload.get("extractor") or "Extractor"),
            domains=self._strings(payload.get("domains") or payload.get("domain")),
            kind=str(payload.get("kind") or "video"),
            requires_referer=bool(payload.get("requiresReferer") or payload.get("requires_referer", False)),
        )
        return self.registry.register(info)

    def register_many(self, payloads: Iterable[dict[str, Any]]) -> tuple[CS3ExtractorInfo, ...]:
        return tuple(self.register(payload) for payload in payloads if isinstance(payload, dict))

    def extract(self, url: str, *, extractor: str | None = None, referer: str | None = None,
                data: str | None = None, headers: Mapping[str, str] | None = None) -> tuple[StreamSource, ...]:
        if not url.strip():
            raise ValueError("extractor URL cannot be empty")
        if extractor is None:
            matches = self.registry.for_url(url)
            if not matches:
                raise LookupError(f"No registered extractor matches {url}")
            extractor = matches[0].name
        payload = self._request("extract", {
            "extractor": extractor,
            "url": url,
            "referer": referer,
            "data": data,
            "headers": dict(headers or {}),
        })
        streams = payload.get("streams", ())
        if not isinstance(streams, (list, tuple)):
            return ()
        return tuple(stream_source_from_cloudstream(value) for value in streams if isinstance(value, dict))

    @staticmethod
    def _strings(value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value if str(item).strip())
        return ()
