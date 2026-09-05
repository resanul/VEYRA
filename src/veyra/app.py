from __future__ import annotations

import sys
from pathlib import Path

from .history import PlaybackHistory
from .models import MediaItem
from .playback_tracks import TrackKind, format_track_label, make_track_info
from .providers.stream_request import PlayRequest
from .subtitle_controls import install_subtitle_controls
from .subtitles import SubtitleEngine


VEYRA_VERSION = "0.3.2"


def _fmt_ms(value: int) -> str:
    seconds = max(0, value // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


class SubtitleOverlayLabel:
    """Small adapter keeping subtitle overlay behavior isolated from player logic."""

    def __init__(self, label) -> None:
        self.label = label
        self.label.setAlignment(label.Qt.AlignmentFlag.AlignHCenter | label.Qt.AlignmentFlag.AlignBottom) if hasattr(label, "Qt") else None


def main() -> int:
    try:
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QKeySequence, QShortcut
        from PySide6.QtWidgets import (
            QApplication,
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QMenu,
            QMessageBox,
            QPushButton,
            QSlider,
            QSpinBox,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )
        from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
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
    subtitle_engine = SubtitleEngine()
    history = PlaybackHistory()
    current: MediaItem | None = None
    current_request: PlayRequest | None = None
    current_external_subtitle: str | None = None
    registry = load_enabled_providers()

    catalog = CatalogView()
    details = DetailsView()
    player_page = QWidget()
    player_layout = QVBoxLayout(player_page)
    video.setMinimumHeight(360)
    player_layout.addWidget(video, 1)
    player_status = QLabel("Select a title from an extension catalog to play it.")
    player_layout.addWidget(player_status)

    # External subtitle rendering is intentionally independent from Qt's
    # embedded subtitle tracks. This works for remote sources and local files.
    subtitle_overlay = QLabel(video)
    subtitle_overlay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
    subtitle_overlay.setWordWrap(True)
    subtitle_overlay.setStyleSheet(
        "QLabel{color:white;background:rgba(0,0,0,150);padding:8px 16px;"
        "font-size:20px;font-weight:600;border-radius:5px;}"
    )
    subtitle_overlay.setMargin(4)
    subtitle_overlay.hide()
    subtitle_overlay.raise_()

    def resize_subtitle_overlay() -> None:
        width = max(200, video.width() - 80)
        height = min(160, max(50, video.height() // 4))
        subtitle_overlay.setGeometry((video.width() - width) // 2, video.height() - height - 24, width, height)
        subtitle_overlay.raise_()

    original_video_resize = video.resizeEvent

    def video_resize_event(event) -> None:
        original_video_resize(event)
        resize_subtitle_overlay()

    video.resizeEvent = video_resize_event

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
    tracks_btn = QPushButton("Tracks")
    stream_info_btn = QPushButton("Stream Info")

    controls = QHBoxLayout()
    for button in (play_btn, back_btn, forward_btn, stop_btn, fullscreen_btn, tracks_btn, stream_info_btn):
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

    tracks_menu = QMenu(window)
    audio_menu = tracks_menu.addMenu("Audio")
    video_menu = tracks_menu.addMenu("Video")
    subtitle_menu = tracks_menu.addMenu("Subtitles")
    tracks_btn.setMenu(tracks_menu)
    install_subtitle_controls(window, video, subtitle_overlay, subtitle_engine, subtitle_menu)

    def _meta_text(metadata, key) -> str | None:
        try:
            value = metadata.stringValue(key)
        except (AttributeError, TypeError, RuntimeError):
            try:
                value = metadata.value(key)
            except (AttributeError, TypeError, RuntimeError):
                return None
        text = str(value).strip()
        return text if text and text.lower() not in {"unknown", "unspecified", "none"} else None

    def _track_detail(metadata, kind: TrackKind) -> tuple[str | None, str | None, str | None, str | None]:
        language = _meta_text(metadata, QMediaMetaData.Key.Language)
        title_text = _meta_text(metadata, QMediaMetaData.Key.Title)
        codec_key = QMediaMetaData.Key.AudioCodec if kind is TrackKind.AUDIO else QMediaMetaData.Key.VideoCodec
        codec = _meta_text(metadata, codec_key) if kind is not TrackKind.SUBTITLE else None
        detail = None
        if kind is TrackKind.VIDEO:
            try:
                resolution = metadata.value(QMediaMetaData.Key.Resolution)
                if resolution and hasattr(resolution, "width") and hasattr(resolution, "height"):
                    width = int(resolution.width())
                    height = int(resolution.height())
                    if width and height:
                        detail = f"{width}x{height}"
            except (AttributeError, TypeError, RuntimeError, ValueError):
                pass
        return title_text, language, codec, detail

    def _load_external_subtitle(source: str) -> None:
        nonlocal current_external_subtitle
        try:
            headers = current_request.source.headers if current_request else None
            count = subtitle_engine.load(source, headers=headers)
            if not count:
                raise ValueError("no subtitle cues found")
            current_external_subtitle = source
            try:
                player.setActiveSubtitleTrack(-1)
            except (AttributeError, RuntimeError):
                pass
            subtitle_overlay.show()
            player_status.setText(f"External subtitles: {Path(source).name or source} · {count} cues")
            rebuild_track_menus()
            update_subtitle(player.position())
        except Exception as exc:
            subtitle_engine.clear()
            current_external_subtitle = None
            subtitle_overlay.clear()
            subtitle_overlay.hide()
            player_status.setText(f"Subtitle error: {exc}")

    def _clear_external_subtitle() -> None:
        nonlocal current_external_subtitle
        subtitle_engine.clear()
        current_external_subtitle = None
        subtitle_overlay.clear()
        subtitle_overlay.hide()

    def _load_subtitle_file() -> None:
        path, _ = QFileDialog.getOpenFileName(
            window,
            "Load subtitle",
            str(Path.home()),
            "Subtitles (*.srt *.vtt *.ass *.ssa);;All files (*.*)",
        )
        if path:
            _load_external_subtitle(path)

    def _populate_track_menu(menu: QMenu, tracks, kind: TrackKind, active_index: int, setter) -> None:
        menu.clear()
        menu.setEnabled(bool(tracks) or kind is TrackKind.SUBTITLE)
        off = menu.addAction("Off")
        off.setCheckable(True)
        off.setChecked(active_index < 0 and current_external_subtitle is None)
        off.triggered.connect(lambda _checked, value=-1: (setter(value), _clear_external_subtitle()))
        if tracks:
            menu.addSeparator()
            for index, metadata in enumerate(tracks):
                title_text, language, codec, detail = _track_detail(metadata, kind)
                info = make_track_info(kind, index, title=title_text, language=language, codec=codec, detail=detail)
                action = menu.addAction(format_track_label(info))
                action.setCheckable(True)
                action.setChecked(index == active_index and current_external_subtitle is None)
                action.triggered.connect(lambda _checked, value=index: (_clear_external_subtitle(), setter(value)))
        elif kind is TrackKind.SUBTITLE:
            note = menu.addAction("No embedded subtitles")
            note.setEnabled(False)

        if kind is TrackKind.SUBTITLE:
            if current_request and current_request.source.subtitles:
                menu.addSeparator()
                external_label = menu.addAction("External subtitles")
                external_label.setEnabled(False)
                for index, source in enumerate(current_request.source.subtitles, start=1):
                    name = Path(source.split("?", 1)[0]).name or f"Subtitle {index}"
                    action = menu.addAction(f"{name} (external)")
                    action.setCheckable(True)
                    action.setChecked(source == current_external_subtitle)
                    action.triggered.connect(lambda _checked, value=source: _load_external_subtitle(value))
            menu.addSeparator()
            load_action = menu.addAction("Load subtitle file…")
            load_action.triggered.connect(_load_subtitle_file)

    def rebuild_track_menus() -> None:
        try:
            _populate_track_menu(audio_menu, player.audioTracks(), TrackKind.AUDIO, player.activeAudioTrack(), player.setActiveAudioTrack)
            _populate_track_menu(video_menu, player.videoTracks(), TrackKind.VIDEO, player.activeVideoTrack(), player.setActiveVideoTrack)
            _populate_track_menu(subtitle_menu, player.subtitleTracks(), TrackKind.SUBTITLE, player.activeSubtitleTrack(), player.setActiveSubtitleTrack)
        except (AttributeError, RuntimeError):
            audio_menu.clear()
            video_menu.clear()
            subtitle_menu.clear()
            tracks_btn.setEnabled(False)

    def update_subtitle(position_ms: int) -> None:
        if current_external_subtitle is None:
            return
        text = subtitle_engine.text_at(position_ms)
        subtitle_overlay.setText(text)
        subtitle_overlay.setVisible(bool(text))
        if text:
            subtitle_overlay.raise_()

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
        _clear_external_subtitle()
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
            details_text.append(f"{len(source.subtitles)} subtitle source(s)")
        player_status.setText(" · ".join(details_text))
        tracks_btn.setEnabled(True)
        stream_info_btn.setEnabled(True)
        pages.setCurrentWidget(player_page)
        resize_subtitle_overlay()
        rebuild_track_menus()

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

    def show_stream_info() -> None:
        if current_request is None:
            return
        source = current_request.source
        lines = [
            f"Title: {current.title if current else current_request.title or 'Unknown'}",
            f"URL: {source.url}",
            f"Quality: {source.quality or 'auto'}",
            f"Format: {source.format or 'auto'}",
            f"Subtitle sources: {len(source.subtitles)}",
            f"Active external subtitle: {current_external_subtitle or 'none'}",
            f"Subtitle delay: {subtitle_engine.offset_ms / 1000:+.1f} s",
            "",
            "Request headers:",
        ]
        sensitive = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
        if source.headers:
            for name, value in source.headers.items():
                shown = "<redacted>" if name.lower() in sensitive else value
                lines.append(f"  {name}: {shown}")
        else:
            lines.append("  none")
        QMessageBox.information(window, "Stream Info", "\n".join(lines))

    def on_position(value: int) -> None:
        if not seek.isSliderDown():
            seek.setValue(value)
        time_label.setText(f"{_fmt_ms(value)} / {_fmt_ms(player.duration())}")
        update_subtitle(value)

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
    stream_info_btn.clicked.connect(show_stream_info)
    seek.sliderMoved.connect(player.setPosition)
    volume.valueChanged.connect(lambda value: audio.setVolume(value / 100.0))
    speed.valueChanged.connect(lambda value: player.setPlaybackRate(value / 100.0))
    player.positionChanged.connect(on_position)
    player.durationChanged.connect(on_duration)
    player.tracksChanged.connect(rebuild_track_menus)
    player.activeTracksChanged.connect(rebuild_track_menus)
    player.mediaStatusChanged.connect(lambda _: persist_position())
    player.bufferProgressChanged.connect(lambda value: status.setText(f"Buffering: {value * 100:.0f}%") if 0.0 < value < 1.0 else None)
    player.errorOccurred.connect(lambda _error, message: status.setText(f"Playback error: {message}"))
    app.aboutToQuit.connect(media_proxy.close)

    QShortcut(QKeySequence("Space"), window).activated.connect(toggle_playback)
    QShortcut(QKeySequence("Left"), window).activated.connect(lambda: jump(-5_000))
    QShortcut(QKeySequence("Right"), window).activated.connect(lambda: jump(5_000))
    QShortcut(QKeySequence("Shift+Left"), window).activated.connect(lambda: jump(-30_000))
    QShortcut(QKeySequence("Shift+Right"), window).activated.connect(lambda: jump(30_000))
    QShortcut(QKeySequence("M"), window).activated.connect(lambda: audio.setMuted(not audio.isMuted()))
    QShortcut(QKeySequence("F"), window).activated.connect(toggle_fullscreen)
    QShortcut(QKeySequence("Escape"), window).activated.connect(lambda: video.setFullScreen(False))

    tracks_btn.setEnabled(False)
    stream_info_btn.setEnabled(False)
    rebuild_track_menus()
    resize_subtitle_overlay()

    if registry.all():
        load_extension()

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
