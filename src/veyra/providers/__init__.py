"""Provider contracts and registry for VEYRA catalogs and streams."""

from .models import SearchResult, StreamSource
from .registry import ProviderRegistry
from .catalog import CatalogProvider, CatalogSection

__all__ = ["ProviderRegistry", "SearchResult", "StreamSource", "CatalogProvider", "CatalogSection"]
