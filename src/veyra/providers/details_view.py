from __future__ import annotations

from urllib.request import urlopen

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .episodes import EpisodeGroup, group_episodes
from .models import SearchResult, StreamSource


class DetailsView(QWidget):
    """Details surface for movies and series, including seasons/episodes."""

    play_requested = Signal(object)
    back_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.provider = None
        self.item: SearchResult | None = None
        self._loaded = None
        self._groups: tuple[EpisodeGroup, ...] = ()

        self.back_button = QPushButton("← Back")
        self.back_button.clicked.connect(self.back_requested)
        self.poster = QLabel()
        self.poster.setFixedSize(180, 260)
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel("Details")
        self.title.setStyleSheet("font-size:30px;font-weight:800;")
        self.meta = QLabel()
        self.meta.setWordWrap(True)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_loaded)
        self.seasons = QComboBox()
        self.seasons.currentIndexChanged.connect(self._show_selected_season)
        self.episodes = QListWidget()
        self.episodes.itemDoubleClicked.connect(self.play_episode)
        self.empty = QLabel()
        self.empty.setWordWrap(True)

        info = QVBoxLayout()
        info.addWidget(self.title)
        info.addWidget(self.meta)
        info.addWidget(self.description)
        info.addWidget(self.play_button)
        info.addStretch(1)
        hero = QHBoxLayout()
        hero.addWidget(self.poster)
        hero.addLayout(info, 1)

        body = QVBoxLayout()
        body.addWidget(self.back_button)
        body.addLayout(hero)
        body.addWidget(self.seasons)
        body.addWidget(self.episodes, 1)
        body.addWidget(self.empty)
        self.setLayout(body)
        self.reset()

    def reset(self) -> None:
        self.seasons.clear()
        self.episodes.clear()
        self.empty.clear()
        self.play_button.setEnabled(False)
        self.play_button.setVisible(False)
        self.poster.clear()
        self._loaded = None
        self._groups = ()

    def show_item(self, provider, item: SearchResult) -> None:
        self.provider = provider
        self.item = item
        self.reset()
        self.title.setText(item.title)
        bits = [item.kind]
        if item.year:
            bits.append(str(item.year))
        self.meta.setText(" · ".join(bit for bit in bits if bit))
        description = item.metadata.get("description") or item.metadata.get("overview") or item.metadata.get("plot") or ""
        self.description.setText(description)
        if item.poster:
            try:
                data = urlopen(item.poster, timeout=5).read()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull():
                    self.poster.setPixmap(pixmap.scaled(180, 260, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except (OSError, ValueError, TypeError):
                pass
        self._load_details()

    def _load_details(self) -> None:
        if self.provider is None or self.item is None:
            return
        try:
            loaded = self.provider.load(self.item.url) if callable(getattr(self.provider, "load", None)) else None
        except (OSError, RuntimeError, ValueError, TypeError):
            loaded = None
        if loaded is None or loaded.load is None:
            self._load_as_movie()
            return
        self._loaded = loaded.load
        detail = loaded.load.item
        self.title.setText(detail.title)
        description = detail.metadata.get("description") or detail.metadata.get("overview") or detail.metadata.get("plot") or self.description.text()
        self.description.setText(description)
        self._groups = group_episodes(loaded.load.episodes)
        if loaded.load.streams:
            self.play_button.setVisible(True)
            self.play_button.setEnabled(True)
        if self._groups:
            self.seasons.addItems([f"Season {group.season}" for group in self._groups])
            self.empty.setText("")
            self._show_selected_season(0)
        elif loaded.load.streams:
            self.episodes.clear()
            self.empty.setText("Movie / direct stream")
        else:
            self._load_as_movie()

    def _load_as_movie(self) -> None:
        if self.provider is None or self.item is None:
            return
        try:
            streams = list(self.provider.streams(self.item))
        except (OSError, RuntimeError, ValueError, TypeError):
            streams = []
        if streams:
            self._loaded = type("Loaded", (), {"streams": tuple(streams)})()
            self.play_button.setVisible(True)
            self.play_button.setEnabled(True)
            self.empty.setText("Direct playback")
        else:
            self.empty.setText("No playable stream or episode was returned.")

    def _show_selected_season(self, index: int) -> None:
        self.episodes.clear()
        if index < 0 or index >= len(self._groups):
            return
        for number, episode in enumerate(self._groups[index].episodes, 1):
            label = episode.title
            episode_no = episode.metadata.get("episode") or episode.metadata.get("episodeNumber") or episode.metadata.get("episode_number")
            if episode_no:
                label = f"Episode {episode_no} · {episode.title}"
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, episode)
            self.episodes.addItem(row)

    def play_loaded(self) -> None:
        if self._loaded is None:
            return
        streams = list(getattr(self._loaded, "streams", ()))
        if streams:
            self._emit_streams(streams)

    def play_episode(self, row: QListWidgetItem) -> None:
        episode = row.data(Qt.ItemDataRole.UserRole)
        if not isinstance(episode, SearchResult) or self.provider is None:
            return
        streams: list[StreamSource] = []
        try:
            streams = list(self.provider.streams(episode))
        except (OSError, RuntimeError, ValueError, TypeError):
            streams = []
        if not streams and callable(getattr(self.provider, "load_links", None)):
            try:
                response = self.provider.load_links(episode.url)
                streams = list(response.streams)
            except (OSError, RuntimeError, ValueError, TypeError):
                streams = []
        self._emit_streams(streams, episode)

    def _emit_streams(self, streams: list[StreamSource], item: SearchResult | None = None) -> None:
        if not streams:
            self.empty.setText("No playable stream was returned for this selection.")
            return
        if len(streams) == 1:
            self.play_requested.emit(streams[0])
            return
        # Reuse a simple quality chooser through the parent catalog when more
        # than one stream is returned; emit the best available source here.
        preferred = sorted(streams, key=lambda stream: stream.quality or "", reverse=True)[0]
        self.play_requested.emit(preferred)
