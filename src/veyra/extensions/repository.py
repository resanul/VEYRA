from __future__ import annotations

import json
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class RemoteExtension:
    id: str
    name: str
    version: str
    url: str
    description: str = ""
    author: str = ""
    icon_url: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class ExtensionRepository:
    name: str
    url: str
    description: str = ""
    manifest_version: int = 1


class RepositoryManager:
    """Persistent, read-only repository catalog with CloudStream-style repo.json support."""

    def __init__(self, storage: Path | None = None, timeout: float = 15.0) -> None:
        self.storage = storage or (Path.home() / "AppData" / "Local" / "VEYRA" / "repositories.json")
        self.timeout = timeout
        self.repositories: dict[str, ExtensionRepository] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.storage.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        for row in data:
            if not isinstance(row, dict) or not row.get("url") or not row.get("name"):
                continue
            repo = ExtensionRepository(
                name=str(row["name"]), url=str(row["url"]),
                description=str(row.get("description", "")),
                manifest_version=int(row.get("manifest_version", 1)),
            )
            self.repositories[repo.url] = repo

    def save(self) -> None:
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.storage.write_text(
            json.dumps([asdict(repo) for repo in self.repositories.values()], indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def normalize_url(value: str) -> str:
        value = value.strip()
        if value.startswith("cloudstreamrepo://"):
            value = value.removeprefix("cloudstreamrepo://")
        if value.startswith("https://cs.repo/"):
            value = value.removeprefix("https://cs.repo/")
        if value.startswith("github.com/"):
            value = "https://github.com/" + value.removeprefix("github.com/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Repository URL must use http:// or https://")
        return value

    @staticmethod
    def _github_repo_json(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.netloc.lower() != "github.com":
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return None
        owner, repo = parts[:2]
        return f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/main/repo.json"

    def _fetch_json(self, url: str) -> object:
        request = urllib.request.Request(url, headers={"User-Agent": "VEYRA/0.2"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def add(self, url: str, name: str | None = None) -> ExtensionRepository:
        normalized = self.normalize_url(url)
        candidates = [normalized]
        fallback = self._github_repo_json(normalized)
        if fallback and fallback not in candidates:
            candidates.append(fallback)
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                raw = self._fetch_json(candidate)
                if not isinstance(raw, dict):
                    raise ValueError("Repository manifest must be a JSON object")
                repo = ExtensionRepository(
                    name=str(name or raw.get("name") or urlparse(candidate).path.strip("/").split("/")[-1] or "Repository"),
                    url=candidate,
                    description=str(raw.get("description", "")),
                    manifest_version=int(raw.get("manifestVersion", raw.get("manifest_version", 1))),
                )
                self.repositories[candidate] = repo
                self.save()
                return repo
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
        raise ValueError(f"Unable to load repository: {last_error}")

    def remove(self, url: str) -> None:
        self.repositories.pop(url, None)
        self.save()

    def plugins(self, repository: ExtensionRepository) -> list[RemoteExtension]:
        raw = self._fetch_json(repository.url)
        if not isinstance(raw, dict):
            return []
        urls = raw.get("pluginLists", [])
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, list):
            urls = []
        # Also accept a compact VEYRA-style repo.json with an inline extensions list.
        inline = raw.get("extensions", raw.get("plugins", []))
        result: list[RemoteExtension] = []
        if isinstance(inline, list):
            result.extend(self._parse_plugins(inline))
        for list_url in urls:
            if not isinstance(list_url, str):
                continue
            try:
                data = self._fetch_json(list_url)
                if isinstance(data, list):
                    result.extend(self._parse_plugins(data))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return result

    @staticmethod
    def _parse_plugins(rows: list[object]) -> list[RemoteExtension]:
        result: list[RemoteExtension] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("url"):
                continue
            name = str(row.get("name") or row.get("internalName") or "Unnamed extension")
            extension_id = str(row.get("id") or row.get("internalName") or name.lower().replace(" ", "-"))
            result.append(RemoteExtension(
                id=extension_id,
                name=name,
                version=str(row.get("version", "1")),
                url=str(row["url"]),
                description=str(row.get("description") or ""),
                author=", ".join(map(str, row.get("authors", []))) if isinstance(row.get("authors"), list) else str(row.get("author") or ""),
                icon_url=row.get("iconUrl") or row.get("icon_url"),
                sha256=row.get("fileHash") or row.get("sha256"),
            ))
        return result
