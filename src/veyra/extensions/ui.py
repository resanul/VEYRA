from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QInputDialog, QLabel, QListWidget, QMessageBox, QPushButton, QVBoxLayout

from .repository import RepositoryManager


class RepositoryDialog(QDialog):
    """Simple functional repository manager; UI is intentionally independent of CloudStream."""

    def __init__(self, parent=None, manager: RepositoryManager | None = None) -> None:
        super().__init__(parent)
        self.manager = manager or RepositoryManager()
        self.setWindowTitle("VEYRA Extensions")
        self.resize(760, 500)

        self.status = QLabel("Add a repository URL to discover extensions.")
        self.repositories = QListWidget()
        self.plugins = QListWidget()
        add = QPushButton("Add repository")
        refresh = QPushButton("Refresh selected")
        remove = QPushButton("Remove selected")
        add.clicked.connect(self.add_repository)
        refresh.clicked.connect(self.refresh_plugins)
        remove.clicked.connect(self.remove_repository)
        self.repositories.currentRowChanged.connect(lambda _: self.refresh_plugins())

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("Repositories"))
        layout.addWidget(self.repositories)
        buttons = QDialogButtonBox()
        buttons.addButton(add, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(refresh, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(remove, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)
        layout.addWidget(QLabel("Available extensions"))
        layout.addWidget(self.plugins)
        self.reload_repositories()

    def reload_repositories(self) -> None:
        self.repositories.clear()
        for repo in self.manager.repositories.values():
            item = f"{repo.name} — {repo.url}"
            self.repositories.addItem(item)

    def add_repository(self) -> None:
        url, ok = QInputDialog.getText(self, "Add repository", "Repository URL or shortcode:")
        if not ok or not url.strip():
            return
        try:
            repo = self.manager.add(url)
        except ValueError as exc:
            QMessageBox.warning(self, "Repository error", str(exc))
            return
        self.status.setText(f"Added: {repo.name}")
        self.reload_repositories()
        self.repositories.setCurrentRow(self.repositories.count() - 1)

    def refresh_plugins(self) -> None:
        self.plugins.clear()
        row = self.repositories.currentRow()
        repos = list(self.manager.repositories.values())
        if row < 0 or row >= len(repos):
            return
        repo = repos[row]
        try:
            extensions = self.manager.plugins(repo)
        except (OSError, ValueError) as exc:
            self.status.setText(f"Repository error: {exc}")
            return
        for plugin in extensions:
            author = f" — {plugin.author}" if plugin.author else ""
            self.plugins.addItem(f"{plugin.name} v{plugin.version}{author}\n{plugin.description}")
        self.status.setText(f"{len(extensions)} extension(s) available from {repo.name}")

    def remove_repository(self) -> None:
        row = self.repositories.currentRow()
        repos = list(self.manager.repositories.values())
        if row < 0 or row >= len(repos):
            return
        self.manager.remove(repos[row].url)
        self.reload_repositories()
        self.plugins.clear()
        self.status.setText("Repository removed.")
