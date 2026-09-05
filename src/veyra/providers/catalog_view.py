from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from .models import SearchResult


class CatalogView(QWidget):
    """Netflix-style catalog surface for an active VEYRA provider."""

    play_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.provider = None
        self._items: list[SearchResult] = []
        self.setObjectName("catalogView")
        self.setStyleSheet("#catalogView { background:#0b0b0b; color:#f5f5f5; } QLabel { color:#f5f5f5; }")
        self.heading = QLabel("Home")
        self.heading.setStyleSheet("font-size:28px;font-weight:700;padding:8px 0;")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search movies and series...")
        self.search.returnPressed.connect(self.search_provider)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_provider)
        self.results = QListWidget()
        self.results.setViewMode(QListWidget.ViewMode.IconMode)
        self.results.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.results.setMovement(QListWidget.Movement.Static)
        self.results.setIconSize(self.results.iconSize())
        self.results.itemDoubleClicked.connect(self.open_item)
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.search_button)
        root = QVBoxLayout(self)
        root.addWidget(self.heading)
        root.addLayout(top)
        root.addWidget(self.results, 1)

    def set_provider(self, provider) -> None:
        self.provider = provider
        self.heading.setText(f"{provider.name} · Home")
        self.load_home()

    def load_home(self) -> None:
        self.results.clear()
        self._items = []
        if self.provider is None:
            return
        try:
            items = list(self.provider.home())
        except (OSError, RuntimeError, ValueError, TypeError):
            items = []
        self._show(items)

    def search_provider(self) -> None:
        if self.provider is None:
            return
        query = self.search.text().strip()
        if not query:
            self.load_home()
            return
        try:
            items = list(self.provider.search(query))
        except (OSError, RuntimeError, ValueError, TypeError):
            items = []
        self.heading.setText(f"Search · {query}")
        self._show(items)

    def _show(self, items: list[SearchResult]) -> None:
        self.results.clear()
        self._items = items
        for result in items:
            card = QListWidgetItem(result.title)
            card.setToolTip(f"{result.title}\n{result.year or ''} · {result.kind}")
            card.setData(Qt.ItemDataRole.UserRole, result)
            if result.poster:
                try:
                    from urllib.request import urlopen
                    data = urlopen(result.poster, timeout=5).read()
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    if not pixmap.isNull():
                        card.setIcon(pixmap.scaled(140, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                except Exception:
                    pass
            self.results.addItem(card)

    def open_item(self, item: QListWidgetItem) -> None:
        result = item.data(Qt.ItemDataRole.UserRole)
        if result is None or self.provider is None:
            return
        try:
            streams = list(self.provider.streams(result))
        except (OSError, RuntimeError, ValueError, TypeError):
            streams = []
        if streams:
            self.play_requested.emit(streams[0].url)
