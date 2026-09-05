from pathlib import Path

from veyra.extensions.repository import RepositoryManager


def test_normalize_cloudstream_short_url() -> None:
    assert RepositoryManager.normalize_url("cloudstreamrepo://https://example.test/repo.json") == "https://example.test/repo.json"


def test_inline_repository(tmp_path: Path) -> None:
    repo_file = tmp_path / "repo.json"
    repo_file.write_text(
        '{"name":"Demo","description":"Test","extensions":[{"name":"Demo Provider","internalName":"demo","version":2,"url":"https://example.test/demo.py","description":"Provider"}]}',
        encoding="utf-8",
    )
    manager = RepositoryManager(tmp_path / "repositories.json")
    repo = manager.add(repo_file.as_uri())
    plugins = manager.plugins(repo)
    assert repo.name == "Demo"
    assert plugins[0].id == "demo"
    assert plugins[0].version == "2"
    assert plugins[0].url.endswith("demo.py")
