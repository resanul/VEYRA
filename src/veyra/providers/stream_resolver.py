from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from .models import StreamSource


@dataclass(frozen=True, slots=True)
class ManifestInfo:
    """Classification and parsed variants for a network media manifest."""

    format: str
    sources: tuple[StreamSource, ...]


class StreamResolver:
    """Parse HLS/DASH manifests into portable VEYRA stream sources.

    Network fetching is deliberately kept outside this parser. Callers can
    fetch a manifest with the appropriate HTTP headers and pass its URL and
    body to ``parse_manifest``. This keeps authentication, cookies and proxy
    policy in the network layer rather than hiding them in the parser.
    """

    @staticmethod
    def detect_format(url: str, body: str | None = None) -> str:
        path = urlparse(url).path.lower()
        if path.endswith(".m3u8"):
            return "hls"
        if path.endswith(".mpd"):
            return "dash"
        text = (body or "").lstrip()
        if text.startswith("#EXTM3U"):
            return "hls"
        if text.startswith("<?xml") or "<MPD" in text[:1000]:
            return "dash"
        return "direct"

    @classmethod
    def parse_manifest(
        cls,
        url: str,
        body: str,
        *,
        headers: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> ManifestInfo:
        fmt = cls.detect_format(url, body)
        request_headers = dict(headers or {})
        if referer and "Referer" not in request_headers and "referer" not in request_headers:
            request_headers["Referer"] = referer
        if fmt == "hls":
            return ManifestInfo("hls", cls._parse_hls(url, body, request_headers))
        if fmt == "dash":
            return ManifestInfo("dash", cls._parse_dash(url, body, request_headers))
        return ManifestInfo("direct", (StreamSource(url=url, format=None, headers=request_headers),))

    @staticmethod
    def _quality(height: int | None, bandwidth: int | None) -> str:
        if height:
            return f"{height}p"
        if bandwidth:
            return f"{bandwidth // 1000}kbps"
        return "auto"

    @classmethod
    def _parse_hls(cls, base_url: str, body: str, headers: dict[str, str]) -> tuple[StreamSource, ...]:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        sources: list[StreamSource] = []
        pending: dict[str, str | int] | None = None
        for line in lines:
            if line.startswith("#EXT-X-STREAM-INF:"):
                pending = cls._parse_hls_attributes(line.split(":", 1)[1])
                continue
            if pending is not None and not line.startswith("#"):
                height = cls._int_value(pending.get("RESOLUTION_HEIGHT"))
                bandwidth = cls._int_value(pending.get("BANDWIDTH"))
                sources.append(
                    StreamSource(
                        url=urljoin(base_url, line),
                        quality=cls._quality(height, bandwidth),
                        format="m3u8",
                        headers=dict(headers),
                    )
                )
                pending = None
        if sources:
            return tuple(sources)
        return (StreamSource(url=base_url, quality="auto", format="m3u8", headers=dict(headers)),)

    @staticmethod
    def _parse_hls_attributes(value: str) -> dict[str, str | int]:
        result: dict[str, str | int] = {}
        for chunk in value.split(","):
            if "=" not in chunk:
                continue
            key, raw = chunk.split("=", 1)
            raw = raw.strip().strip('"')
            if key == "RESOLUTION" and "x" in raw.lower():
                _, height = raw.lower().split("x", 1)
                result["RESOLUTION_HEIGHT"] = height
            elif key == "BANDWIDTH":
                result[key] = raw
            else:
                result[key] = raw
        return result

    @classmethod
    def _parse_dash(cls, base_url: str, body: str, headers: dict[str, str]) -> tuple[StreamSource, ...]:
        root = ElementTree.fromstring(body)
        mpd_base = cls._child_text(root, "BaseURL")
        period = cls._first_child(root, "Period")
        if period is None:
            return (StreamSource(url=base_url, format="mpd", headers=dict(headers)),)
        sources: list[StreamSource] = []
        for adaptation in cls._children(period, "AdaptationSet"):
            adaptation_base = cls._child_text(adaptation, "BaseURL") or mpd_base or ""
            mime = adaptation.attrib.get("mimeType", "")
            for representation in cls._children(adaptation, "Representation"):
                rep_base = cls._child_text(representation, "BaseURL") or adaptation_base
                if not rep_base:
                    # SegmentTemplate-based DASH needs a full segment resolver;
                    # retain the MPD as a playable source for the media engine.
                    continue
                source_url = urljoin(base_url, rep_base)
                height = cls._int_value(representation.attrib.get("height"))
                bandwidth = cls._int_value(representation.attrib.get("bandwidth"))
                content_type = representation.attrib.get("mimeType") or mime or "application/dash+xml"
                sources.append(
                    StreamSource(
                        url=source_url,
                        quality=cls._quality(height, bandwidth),
                        format="mpd" if "dash" in content_type else content_type,
                        headers=dict(headers),
                    )
                )
        if sources:
            return tuple(sources)
        return (StreamSource(url=base_url, quality="auto", format="mpd", headers=dict(headers)),)

    @staticmethod
    def _children(element: ElementTree.Element, name: str) -> tuple[ElementTree.Element, ...]:
        return tuple(child for child in element if child.tag.rsplit("}", 1)[-1] == name)

    @classmethod
    def _first_child(cls, element: ElementTree.Element, name: str) -> ElementTree.Element | None:
        return next(iter(cls._children(element, name)), None)

    @classmethod
    def _child_text(cls, element: ElementTree.Element, name: str) -> str | None:
        child = cls._first_child(element, name)
        return (child.text or "").strip() if child is not None and child.text else None

    @staticmethod
    def _int_value(value: object) -> int | None:
        try:
            return int(str(value)) if value is not None else None
        except (TypeError, ValueError):
            return None
