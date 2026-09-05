from veyra.extensions.cs3_runtime.cloudstream_lifecycle import CloudStreamLifecycleAdapter


def test_main_page_and_search_translate_cloudstream_payloads() -> None:
    calls = []

    def request(method, payload):
        calls.append((method, payload))
        if method == "home":
            return {"pages": [{"name": "Trending", "items": [{"id": "m1", "title": "Movie", "url": "https://example.test/m1"}], "hasNext": True}]}
        return {"items": [{"id": "m2", "title": "Search Movie", "url": "https://example.test/m2", "year": 2026}]}

    adapter = CloudStreamLifecycleAdapter(request)
    home = adapter.get_main_page(2)
    search = adapter.search("Movie", 3)

    assert home.home_pages[0].name == "Trending"
    assert home.home_pages[0].items[0].id == "m1"
    assert home.home_pages[0].has_next is True
    assert search.results[0].year == 2026
    assert calls == [("home", {"page": 2}), ("search", {"query": "Movie", "page": 3})]


def test_load_and_load_links_preserve_episodes_streams_and_metadata() -> None:
    def request(method, payload):
        if method == "load":
            return {
                "item": {"id": "series", "title": "Series", "url": payload["url"], "kind": "tvseries"},
                "episodes": [{"id": "ep1", "title": "Episode 1", "url": "https://example.test/ep1"}],
                "metadata": {"season": "1"},
            }
        return {
            "streams": [{
                "url": "https://cdn.example.test/video.m3u8",
                "quality": "1080p",
                "type": "m3u8",
                "headers": {"Referer": "https://example.test"},
            }]
        }

    adapter = CloudStreamLifecycleAdapter(request)
    loaded = adapter.load("https://example.test/series")
    links = adapter.load_links("https://example.test/ep1", referer="https://example.test", data="episode-data")

    assert loaded.load is not None
    assert loaded.load.item.title == "Series"
    assert loaded.load.episodes[0].title == "Episode 1"
    assert loaded.load.metadata["season"] == "1"
    assert links.streams[0].format == "m3u8"
    assert links.streams[0].headers["Referer"] == "https://example.test"
