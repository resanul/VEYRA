from __future__ import annotations

import sys
from pathlib import Path

from .history import PlaybackHistory
from .models import MediaItem
from .extensions.ui import RepositoryDialog


def _fmt_ms(value: int) -> str:
    seconds = max(0, value // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def main() -> int:
    try:
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtWidgets import (
            QApplication, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
            QMainWindow, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
        )
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
    except ImportError as exc:
        print("VEYRA requires PySide6. Install with: pip install -e '.[test]'", file=sys.stderr)
        print(f"Import error: {exc}", file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("VEYRA")
    app.setApplicationVersion("0.2.0")
    window = QMainWindow()
    window.setWindowTitle("VEYRA — Universal Media Player")
    window.resize(1280, 760)

    player = QMediaPlayer(window)
    audio = QAudioOutput(window)
    video = QVideoWidget()
    player.setAudioOutput(audio)
    player.setVideoOutput(video)
    audio.setVolume(1.0)
    history = PlaybackHistory()
    current: MediaItem | None = None

    title = QLabel("VEYRA · Universal Media Player")
    title.setStyleSheet("font-size: 22px; font-weight: 700; padding: 10px;")
    status = QLabel("Open a media file or stream URL to begin.")
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

    library_list = QListWidget()
    library_list.setMinimumWidth(260)
    for record in history.recent():
        item = QListWidgetItem(record.title)
        item.setToolTip(f"{record.source}\nResume: {_fmt_ms(record.position_ms)}")
        item.setData(Qt.ItemDataRole.UserRole, record.source)
        library_list.addItem(item)

    def load_source(source: str) -> None:
        nonlocal current
        current = MediaItem.from_source(source)
        player.setSource(QUrl.fromUserInput(source) if source.startswith(("http://", "https://")) else QUrl.fromLocalFile(source))
        status.setText(f"Loaded: {current.title}")
        record = history.get(source)
        player.play()
        if record and record.position_ms > 5000:
            player.setPosition(record.position_ms)

    def open_media() -> None:
        path, _ = QFileDialog.getOpenFileName(window, "Open media", str(Path.home()), "Media (*.mp4 *.mkv *.webm *.avi *.mov *.m4v *.ts *.m2ts *.mp3 *.flac *.aac *.wav *.ogg *.opus *.m4a);;All files (*.*)")
        if path:
            load_source(path)

    def toggle_playback() -> None:
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        else:
            player.play()

    def stop_playback() -> None:
        player.stop()

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

    def show_extensions() -> None:
        RepositoryDialog(window).exec()

    open_btn = QPushButton("Open")
    play_btn = QPushButton("Play / Pause")
    back_btn = QPushButton("-10s")
    forward_btn = QPushButton("+10s")
    stop_btn = QPushButton("Stop")
    fullscreen_btn = QPushButton("Fullscreen")
    extensions_btn = QPushButton("Extensions")

    open_btn.clicked.connect(open_media)
    play_btn.clicked.connect(toggle_playback)
    back_btn.clicked.connect(lambda: jump(-10_000))
    forward_btn.clicked.connect(lambda: jump(10_000))
    stop_btn.clicked.connect(stop_playback)
    fullscreen_btn.clicked.connect(toggle_fullscreen)
    extensions_btn.clicked.connect(show_extensions)
    seek.sliderMoved.connect(player.setPosition)
    volume.valueChanged.connect(lambda value: audio.setVolume(value / 100.0))
    speed.valueChanged.connect(lambda value: player.setPlaybackRate(value / 100.0))
    player.positionChanged.connect(on_position)
    player.durationChanged.connect(on_duration)
    player.mediaStatusChanged.connect(lambda _: persist_position())
    library_list.itemDoubleClicked.connect(lambda item: load_source(item.data(Qt.ItemDataRole.UserRole)))

    controls = QHBoxLayout()
    for button in (open_btn, play_btn, back_btn, forward_btn, stop_btn, fullscreen_btn, extensions_btn):
        controls.addWidget(button)
    controls.addWidget(QLabel("Volume"))
    controls.addWidget(volume)
    controls.addWidget(QLabel("Speed"))
    controls.addWidget(speed)
    transport = QHBoxLayout()
    transport.addWidget(time_label)
    transport.addWidget(seek, stretch=1)
    main = QHBoxLayout()
    main.addWidget(video, stretch=1)
    main.addWidget(library_list)
    root_layout = QVBoxLayout()
    root_layout.addWidget(title)
    root_layout.addLayout(main, stretch=1)
    root_layout.addWidget(status)
    root_layout.addLayout(transport)
    root_layout.addLayout(controls)
    root = QWidget()
    root.setLayout(root_layout)
    window.setCentralWidget(root)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
