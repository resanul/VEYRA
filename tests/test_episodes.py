from veyra.providers.episodes import group_episodes
from veyra.providers.models import SearchResult


def episode(title: str, season: str, number: str) -> SearchResult:
    return SearchResult(
        id=title,
        title=title,
        url=f"https://example.test/{title}",
        kind="episode",
        metadata={"season": season, "episodeNumber": number},
    )


def test_group_episodes_sorts_seasons_and_episode_numbers() -> None:
    result = group_episodes([
        episode("S2E2", "2", "2"),
        episode("S1E2", "1", "2"),
        episode("S1E1", "1", "1"),
        episode("S2E1", "2", "1"),
    ])

    assert [group.season for group in result] == [1, 2]
    assert [item.title for item in result[0].episodes] == ["S1E1", "S1E2"]
    assert [item.title for item in result[1].episodes] == ["S2E1", "S2E2"]


def test_missing_season_defaults_to_one() -> None:
    item = SearchResult(id="ep", title="Episode", url="https://example.test/ep", metadata={"episode": "1"})
    result = group_episodes([item])
    assert result[0].season == 1
    assert result[0].episodes[0].title == "Episode"
