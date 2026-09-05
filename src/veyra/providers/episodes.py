from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .models import SearchResult


@dataclass(frozen=True, slots=True)
class EpisodeGroup:
    season: int
    episodes: tuple[SearchResult, ...]


def _number(item: SearchResult, *keys: str, default: int = 0) -> int:
    for key in keys:
        value = item.metadata.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


def group_episodes(items: Iterable[SearchResult]) -> tuple[EpisodeGroup, ...]:
    """Group CloudStream episode results by season and episode number."""
    groups: dict[int, list[SearchResult]] = defaultdict(list)
    for item in items:
        season = _number(item, "season", "seasonNumber", "season_number", default=1)
        groups[season].append(item)

    ordered: list[EpisodeGroup] = []
    for season in sorted(groups):
        episodes = sorted(
            groups[season],
            key=lambda item: (
                _number(item, "episode", "episodeNumber", "episode_number", default=0),
                item.title.casefold(),
            ),
        )
        ordered.append(EpisodeGroup(season=season, episodes=tuple(episodes)))
    return tuple(ordered)
