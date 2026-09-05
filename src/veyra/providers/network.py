from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .models import StreamSource
from .stream_resolver import ManifestInfo, StreamResolver


DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "VEYRA/0.3.2",
    "Accept": "*/*",
}


class NetworkRequestError(RuntimeError):
    """Raised when a media/network request cannot be completed."""


@dataclass(frozen=True, slots=True)
class NetworkResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes

    @property
    def text(self) -> str:
        content_type = self.headers.get("Content-Type", "")
        charset = "utf-8"
        for part in content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip().strip('"')
                break
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class RequestOptions:
    timeout: float = 20.0
    max_bytes: int = 32 * 1024 * 1024
    headers: Mapping[str, str] | None = None
    referer: str | None = None
    cookies: Mapping[str, str] | None = None


class NetworkClient:
    """Small stdlib HTTP client for provider/extractor requests.

    Headers, Referer and cookies are explicit so provider authentication data
    is preserved when an extractor resolves a manifest. A CookieJar is kept
    per client to retain Set-Cookie state across requests without sharing
    browser cookies with unrelated providers.
    """

    def __init__(self, *, options: RequestOptions | None = None) -> None:
        self.options = options or RequestOptions()
        self.cookie_jar = CookieJar()
        self._opener = build_opener()

    @staticmethod
    def _cookie_header(cookies: Mapping[str, str] | None) -> str | None:
        if not cookies:
            return None
        return "; ".join(f"{key}={value}" for key, value in cookies.items())

    def _headers(
        self,
        headers: Mapping[str, str] | None,
        *,
        referer: str | None,
        cookies: Mapping[str, str] | None,
    ) -> dict[str, str]:
        merged = dict(DEFAULT_HEADERS)
        merged.update(dict(self.options.headers or {}))
        merged.update(dict(headers or {}))
        effective_referer = referer or self.options.referer
        if effective_referer and not any(key.lower() == "referer" for key in merged):
            merged["Referer"] = effective_referer
        cookie_header = self._cookie_header(cookies or self.options.cookies)
        if cookie_header and not any(key.lower() == "cookie" for key in merged):
            merged["Cookie"] = cookie_header
        return merged

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        referer: str | None = None,
        cookies: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> NetworkResponse:
        request = Request(url, headers=self._headers(headers, referer=referer, cookies=cookies), method="GET")
        limit = self.options.max_bytes if max_bytes is None else max_bytes
        if limit <= 0:
            raise ValueError("max_bytes must be positive")
        try:
            with self._opener.open(request, timeout=timeout or self.options.timeout) as response:
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(min(256 * 1024, limit - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise NetworkRequestError(f"response exceeds {limit} byte limit")
                    chunks.append(chunk)
                return NetworkResponse(
                    url=response.geturl(),
                    status=int(response.status),
                    headers={str(k): str(v) for k, v in response.headers.items()},
                    body=b"".join(chunks),
                )
        except HTTPError as exc:
            raise NetworkRequestError(f"HTTP {exc.code} for {url}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise NetworkRequestError(f"request failed for {url}: {exc}") from exc

    def fetch_manifest(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        referer: str | None = None,
        cookies: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> tuple[NetworkResponse, ManifestInfo]:
        response = self.get(
            url,
            headers=headers,
            referer=referer,
            cookies=cookies,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        request_headers = dict(response.headers)
        if headers:
            request_headers.update(dict(headers))
        if referer and "Referer" not in request_headers:
            request_headers["Referer"] = referer
        manifest = StreamResolver.parse_manifest(
            response.url,
            response.text,
            headers=dict(headers or {}),
            referer=referer,
        )
        return response, manifest

    @staticmethod
    def with_request_context(source: StreamSource, *, referer: str | None = None) -> RequestOptions:
        headers = dict(source.headers)
        effective_referer = referer
        for key, value in source.headers.items():
            if key.lower() == "referer":
                effective_referer = value
                break
        return RequestOptions(headers=headers, referer=effective_referer)
