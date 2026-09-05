from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QMessageBox, QPushButton, QVBoxLayout, QHBoxLayout, QInputDialog

from .installer import ExtensionInstaller
from .repository import RepositoryManager, RemoteExtension, ExtensionRepository


class RepositoryDialog(QDialog):
    """Repository catalog with install, enable/disable and uninstall actions."""

    def __init__(self, parent=None, manager: RepositoryManager | None = None) -> None:
        super().__init__(parent)
        self.manager = manager or RepositoryManager()
        self.installer = ExtensionInstaller()
        self.plugins_data: list[RemoteExtension] = []
        self.setWindowTitle("VEYRA Extensions")
        self.resize(820, 560)
        self.status = QLabel("Add a repository to load its extensions.")
        self.repositories = QListWidget()
        self.plugins = QListWidget()
        self.repositories.currentRowChanged.connect(lambda _: self.refresh_plugins())
        add = QPushButton("Add repository")
        refresh = QPushButton("Refresh")
        remove_repo = QPushButton("Remove repository")
        install = QPushButton("Install / Update")
        toggle = QPushButton("Enable / Disable")
        uninstall = QPushButton("Uninstall")
        add.clicked.connect(self.add_repository)
        refresh.clicked.connect(self.refresh_plugins)
        remove_repo.clicked.connect(self.remove_repository)
        install.clicked.connect(self.install_selected)
        toggle.clicked.connect(self.toggle_selected)
        uninstall.clicked.connect(self.uninstall_selected)
        root = QVBoxLayout(self)
        root.addWidget(self.status)
        root.addWidget(QLabel("Repositories"))
        root.addWidget(self.repositories)
        top = QHBoxLayout()
        for button in (add, refresh, remove_repo):
            top.addWidget(button)
        root.addLayout(top)
        root.addWidget(QLabel("Extensions"))
        root.addWidget(self.plugins)
        bottom = QHBoxLayout()
        for button in (install, toggle, uninstall):
            bottom.addWidget(button)
        root.addLayout(bottom)
        self.reload_repositories()

    def reload_repositories(self) -> None:
        self.repositories.clear()
        for repo in self.manager.repositories.values():
            self.repositories.addItem(f"{repo.name} - {repo.url}")

    def _repo(self) -> ExtensionRepository | None:
        repos = list(self.manager.repositories.values())
        row = self.repositories.currentRow()
        return repos[row] if 0 <= row < len(repos) else None

    def add_repository(self) -> None:
        url, ok = QInputDialog.getText(self, "Add repository", "Repository URL:")
        if not ok or not url.strip():
            return
        try:
            repo = self.manager.add(url)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Repository error", str(exc))
            return
        self.reload_repositories()
        self.repositories.setCurrentRow(max(0, self.repositories.count() - 1))
        self.status.setText(f"Repository loaded: {repo.name}")

    def refresh_plugins(self) -> None:
        self.plugins.clear()
        self.plugins_data = []
        repo = self._repo()
        if repo is None:
            return
        try:
            self.plugins_data = self.manager.plugins(repo)
        except (OSError, ValueError, TypeError) as exc:
            self.status.setText(f"Load failed: {exc}")
            return
        enabled = set(self.installer.enabled())
        for plugin in self.plugins_data:
            installed = self.installer.is_installed(plugin)
            state = "Installed/Enabled" if installed and plugin.id in enabled else "Installed/Disabled" if installed else "Available"
            self.plugins.addItem(f"{plugin.name} v{plugin.version} [{state}] - {plugin.author}")
        self.status.setText(f"Loaded {len(self.plugins_data)} extension(s)")

    def _plugin(self) -> RemoteExtension | None:
        row = self.plugins.currentRow()
        return self.plugins_data[row] if 0 <= row < len(self.plugins_data) else None

    def install_selected(self) -> None:
        plugin = self._plugin()
        if plugin is None:
            return
        try:
            path = self.installer.install(plugin)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Install failed", str(exc))
            return
        self.status.setText(f"Installed: {path}")
        self.refresh_plugins()

    def toggle_selected(self) -> None:
        plugin = self._plugin()
        if plugin is None or not self.installer.is_installed(plugin):
            return
        try:
            enabled = plugin.id not in set(self.installer.enabled())
            self.installer.set_enabled(plugin.id, enabled)
        except (KeyError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "State change failed", str(exc))
            return
        self.refresh_plugins()

    def uninstall_selected(self) -> None:
        plugin = self._plugin()
        if plugin is None or not self.installer.is_installed(plugin):
            return
        try:
            self.installer.uninstall(plugin.id)
        except OSError as exc:
            QMessageBox.warning(self, "Uninstall failed", str(exc))
            return
        self.refresh_plugins()

    def remove_repository(self) -> None:
        repo = self._repo()
        if repo is None:
            return
        self.manager.remove(repo.url)
        self.reload_repositories()
        self.plugins.clear()
        self.plugins_data = []
