from veyra.providers.models import SearchResult, StreamSource
from veyra.providers.registry import ProviderRegistry


class DemoProvider:
    id = "demo"
    name = "Demo"

    def home(self):
        return [SearchResult(id="1", title="Demo", url="https://example.test/demo", kind="movie", year=2026)]

    def search(self, query: str):
        return self.home() if query == "demo" else []

    def streams(self, item: SearchResult):
        return [StreamSource(url="https://example.test/video.m3u8", quality="1080p", format="hls")]


def test_catalog_result_contract() -> None:
    result = SearchResult(id="1", title="Demo", url="https://example.test/demo", kind="movie", year=2026)
    source = StreamSource(url="https://example.test/video.m3u8", quality="1080p", format="hls")
    assert result.title == "Demo"
    assert source.quality == "1080p"


def test_provider_registry_supports_home_search_and_streams() -> None:
    registry = ProviderRegistry()
    provider = DemoProvider()
    registry.register(provider)
    assert registry.get("demo") is provider
    assert list(provider.home())[0].title == "Demo"
    assert list(provider.search("demo"))[0].id == "1"
    assert list(provider.streams(provider.home()[0]))[0].format == "hls"
