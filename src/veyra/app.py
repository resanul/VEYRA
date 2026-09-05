from __future__ import annotations

import sys
from pathlib import Path

from .models import MediaItem


def main() -> int:
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
    except ImportError as exc:
        print("VEYRA requires PySide6. Install with: pip install -e '.[test]'", file=sys.stderr)
        print(f"Import error: {exc}", file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("VEYRA")
    app.setApplicationVersion("0.1.0")

    window = QMainWindow()
    window.setWindowTitle("VEYRA — Universal Media Player")
    window.resize(1100, 700)

    player = QMediaPlayer(window)
    audio = QAudioOutput(window)
    video = QVideoWidget()
    player.setAudioOutput(audio)
    player.setVideoOutput(video)
    audio.setVolume(1.0)

    title = QLabel("VEYRA\nUniversal Media Player")
    title.setStyleSheet("font-size: 22px; font-weight: 700; padding: 12px;")
    status = QLabel("Open a local media file to begin.")
    open_button = QPushButton("Open Media")
    play_button = QPushButton("Play / Pause")

    def open_media() -> None:
        path, _ = QFileDialog.getOpenFileName(
            window,
            "Open media",
            str(Path.home()),
            "Media (*.mp4 *.mkv *.webm *.avi *.mov *.m4v *.ts *.mp3 *.flac *.aac *.wav *.ogg);;All files (*.*)",
        )
        if not path:
            return
        item = MediaItem.from_source(path)
        player.setSource(QUrl.fromLocalFile(path))
        status.setText(f"Loaded: {item.title}")
        player.play()

    def toggle_playback() -> None:
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        else:
            player.play()

    open_button.clicked.connect(open_media)
    play_button.clicked.connect(toggle_playback)

    layout = QVBoxLayout()
    layout.addWidget(title)
    layout.addWidget(video, stretch=1)
    layout.addWidget(status)
    layout.addWidget(open_button)
    layout.addWidget(play_button)

    root = QWidget()
    root.setLayout(layout)
    window.setCentralWidget(root)
    window.show()
    return app.exec()
