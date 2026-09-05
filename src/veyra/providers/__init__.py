"""Provider contracts and registry for VEYRA catalogs and streams."""

from .models import SearchResult, StreamSource
from .network import NetworkClient, NetworkRequestError, NetworkResponse, RequestOptions
from .registry import ProviderRegistry
from .catalog import CatalogProvider, CatalogSection
from .stream_resolver import ManifestInfo, StreamResolver

__all__ = [
    "ProviderRegistry",
    "SearchResult",
    "StreamSource",
    "CatalogProvider",
    "CatalogSection",
    "ManifestInfo",
    "StreamResolver",
    "NetworkClient",
    "NetworkRequestError",
    "NetworkResponse",
    "RequestOptions",
]
