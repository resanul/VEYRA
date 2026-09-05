from __future__ import annotations

from urllib.request import urlopen

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .models import SearchResult, StreamSource


class CatalogView(QWidget):
    """Netflix-style catalog surface for an active VEYRA provider."""

    # Emits the complete source so headers, subtitles and format are preserved.
    play_requested = Signal(object)

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
        self.search.clear()
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
                    data = urlopen(result.poster, timeout=5).read()
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(140, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        card.setIcon(QIcon(scaled))
                except (OSError, ValueError, TypeError):
                    pass
            self.results.addItem(card)

    def open_item(self, item: QListWidgetItem) -> None:
        result = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, SearchResult) or self.provider is None:
            return
        try:
            streams = list(self.provider.streams(result))
        except (OSError, RuntimeError, ValueError, TypeError):
            streams = []
        if not streams:
            self._show_error("No playable stream was returned for this title.")
            return
        if len(streams) == 1:
            self.play_requested.emit(streams[0])
            return
        self._choose_stream(result, streams)

    def _choose_stream(self, result: SearchResult, streams: list[StreamSource]) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Choose stream · {result.title}")
        dialog.resize(520, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"{result.title}\nSelect a quality/source:"))
        choices = QListWidget()
        for index, stream in enumerate(streams):
            label = stream.quality or "Auto"
            if stream.format:
                label += f" · {stream.format.upper()}"
            if stream.headers:
                label += " · headers"
            if stream.subtitles:
                label += f" · {len(stream.subtitles)} subtitle(s)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            choices.addItem(item)
        choices.setCurrentRow(0)
        layout.addWidget(choices, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted and choices.currentItem() is not None:
            index = choices.currentItem().data(Qt.ItemDataRole.UserRole)
            self.play_requested.emit(streams[int(index)])

    def _show_error(self, message: str) -> None:
        self.heading.setText(message)
