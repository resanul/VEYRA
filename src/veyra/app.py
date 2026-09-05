from __future__ import annotations

import sys
from pathlib import Path

from .history import PlaybackHistory
from .models import MediaItem
from .providers.stream_request import PlayRequest


VEYRA_VERSION = "0.3.2"


def _fmt_ms(value: int) -> str:
    seconds = max(0, value // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def main() -> int:
    try:
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        from .extensions.host import load_enabled_providers
        from .providers.catalog_view import CatalogView
        from .providers.details_view import DetailsView
        from .providers.media_proxy import MediaStreamProxy
    except ImportError as exc:
        print("VEYRA requires PySide6. Install with: pip install -e '.[test]'", file=sys.stderr)
        print(f"Import error: {exc}", file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("VEYRA")
    app.setApplicationVersion(VEYRA_VERSION)
    window = QMainWindow()
    window.setWindowTitle(f"VEYRA {VEYRA_VERSION} — Universal Media Player")
    window.resize(1280, 800)
    window.setStyleSheet("QMainWindow,QWidget{background:#0b0b0b;color:#f5f5f5;} QPushButton{padding:8px 14px;} QListWidget{background:#151515;border:0;}")

    player = QMediaPlayer(window)
    audio = QAudioOutput(window)
    video = QVideoWidget()
    player.setAudioOutput(audio)
    player.setVideoOutput(video)
    audio.setVolume(1.0)
    media_proxy = MediaStreamProxy()
    history = PlaybackHistory()
    current: MediaItem | None = None
    current_request: PlayRequest | None = None
    registry = load_enabled_providers()

    catalog = CatalogView()
    details = DetailsView()
    player_page = QWidget()
    player_layout = QVBoxLayout(player_page)
    player_layout.addWidget(video, 1)
    player_status = QLabel("Select a title from an extension catalog to play it.")
    player_layout.addWidget(player_status)

    pages = QStackedWidget()
    pages.addWidget(catalog)
    pages.addWidget(details)
    pages.addWidget(player_page)

    header = QHBoxLayout()
    title = QLabel(f"VEYRA {VEYRA_VERSION}")
    title.setStyleSheet("font-size:24px;font-weight:800;")
    home_btn = QPushButton("Home")
    open_btn = QPushButton("Open file")
    extensions_btn = QPushButton("Extensions")
    header.addWidget(title)
    header.addStretch(1)
    header.addWidget(home_btn)
    header.addWidget(open_btn)
    header.addWidget(extensions_btn)

    status = QLabel("No extension loaded. Open Extensions and choose Load selected.")
    time_label = QLabel("00:00 / 00:00")
    seek = QSlider(Qt.Orientation.Horizontal)
    seek.setRange(0, 0)
    volume = QSlider(Qt.Orientation.Horizontal)
    volume.setRange(0, 100)
    volume.setValue(100)
    speed = QSpinBox()
    speed.setRange(25, 400)
    speed.setValue(100)
    speed.setSuffix("%")
    play_btn = QPushButton("Play / Pause")
    back_btn = QPushButton("-10s")
    forward_btn = QPushButton("+10s")
    stop_btn = QPushButton("Stop")
    fullscreen_btn = QPushButton("Fullscreen")

    controls = QHBoxLayout()
    for button in (play_btn, back_btn, forward_btn, stop_btn, fullscreen_btn):
        controls.addWidget(button)
    controls.addWidget(QLabel("Volume"))
    controls.addWidget(volume)
    controls.addWidget(QLabel("Speed"))
    controls.addWidget(speed)

    transport = QHBoxLayout()
    transport.addWidget(time_label)
    transport.addWidget(seek, 1)

    root_layout = QVBoxLayout()
    root_layout.addLayout(header)
    root_layout.addWidget(pages, 1)
    root_layout.addWidget(status)
    root_layout.addLayout(transport)
    root_layout.addLayout(controls)
    root = QWidget()
    root.setLayout(root_layout)
    window.setCentralWidget(root)

    def load_source(request: PlayRequest | object) -> None:
        nonlocal current, current_request
        if isinstance(request, PlayRequest):
            play_request = request
        else:
            from .providers.models import StreamSource
            if not isinstance(request, StreamSource):
                status.setText("Invalid playback request.")
                return
            play_request = PlayRequest.from_source(request)
        current_request = play_request
        source = play_request.source
        source_url = source.url
        play_url = media_proxy.prepare(source)
        title_text = (play_request.title or play_request.item.title) if play_request.item else play_request.title
        current = MediaItem(id=source_url, title=title_text or Path(source_url).name or source_url, source=source_url, media_type=MediaItem.from_source(source_url).media_type)
        player.setSource(QUrl.fromUserInput(play_url) if play_url.startswith(("http://", "https://")) else QUrl.fromLocalFile(play_url))
        record = history.get(source_url)
        player.play()
        if record and record.position_ms > 5000:
            player.setPosition(record.position_ms)
        details_text = [f"Playing: {current.title}"]
        if source.quality:
            details_text.append(source.quality)
        if source.format:
            details_text.append(source.format.upper())
        if source.headers:
            details_text.append(f"{len(source.headers)} request headers")
            details_text.append("network proxy")
        if source.subtitles:
            details_text.append(f"{len(source.subtitles)} subtitle(s)")
        player_status.setText(" · ".join(details_text))
        pages.setCurrentWidget(player_page)

    def open_media() -> None:
        path, _ = QFileDialog.getOpenFileName(window, "Open media", str(Path.home()), "Media (*.mp4 *.mkv *.webm *.avi *.mov *.m4v *.ts *.m2ts *.mp3 *.flac *.aac *.wav *.ogg *.opus *.m4a);;All files (*.*)")
        if path:
            load_source(path)

    def toggle_playback() -> None:
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        else:
            player.play()

    def jump(delta_ms: int) -> None:
        player.setPosition(max(0, player.position() + delta_ms))

    def toggle_fullscreen() -> None:
        video.setFullScreen(not video.isFullScreen())

    def on_position(value: int) -> None:
        if not seek.isSliderDown():
            seek.setValue(value)
        time_label.setText(f"{_fmt_ms(value)} / {_fmt_ms(player.duration())}")

    def on_duration(value: int) -> None:
        seek.setRange(0, max(0, value))
        on_position(player.position())

    def persist_position() -> None:
        if current is not None:
            history.save_position(current.source, current.title, player.position(), player.duration())

    def show_details(item) -> None:
        if catalog.provider is None:
            return
        details.show_item(catalog.provider, item)
        pages.setCurrentWidget(details)
        status.setText(f"Details: {item.title}")

    def load_extension(_plugin=None) -> None:
        nonlocal registry
        registry = load_enabled_providers()
        if _plugin is not None:
            provider = registry.get(_plugin.id)
            if provider is None:
                status.setText(f"{_plugin.name} could not be loaded by the active provider runtime.")
                return
            catalog.set_provider(provider)
            details.provider = provider
            status.setText(f"Loaded extension: {provider.name}")
            pages.setCurrentWidget(catalog)
        elif registry.all():
            provider = registry.all()[0]
            catalog.set_provider(provider)
            details.provider = provider
            status.setText(f"Loaded extension: {provider.name}")
            pages.setCurrentWidget(catalog)

    catalog.details_requested.connect(show_details)
    catalog.play_requested.connect(load_source)
    details.play_requested.connect(load_source)
    details.back_requested.connect(lambda: pages.setCurrentWidget(catalog))

    def show_extensions() -> None:
        from .extensions.ui import RepositoryDialog
        RepositoryDialog(window, on_loaded=load_extension).exec()

    home_btn.clicked.connect(lambda: pages.setCurrentWidget(catalog))
    open_btn.clicked.connect(open_media)
    extensions_btn.clicked.connect(show_extensions)
    play_btn.clicked.connect(toggle_playback)
    back_btn.clicked.connect(lambda: jump(-10_000))
    forward_btn.clicked.connect(lambda: jump(10_000))
    stop_btn.clicked.connect(player.stop)
    fullscreen_btn.clicked.connect(toggle_fullscreen)
    seek.sliderMoved.connect(player.setPosition)
    volume.valueChanged.connect(lambda value: audio.setVolume(value / 100.0))
    speed.valueChanged.connect(lambda value: player.setPlaybackRate(value / 100.0))
    player.positionChanged.connect(on_position)
    player.durationChanged.connect(on_duration)
    player.mediaStatusChanged.connect(lambda _: persist_position())
    player.errorOccurred.connect(lambda _error, message: status.setText(f"Playback error: {message}"))
    app.aboutToQuit.connect(media_proxy.close)

    if registry.all():
        load_extension()

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
