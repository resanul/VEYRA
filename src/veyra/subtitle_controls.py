from __future__ import annotations

from dataclasses import replace


def install_subtitle_controls(window, video, overlay, subtitle_engine, parent_menu, *, settings=None):
    """Install persistent subtitle controls and advanced player state."""
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    from .playback_state import PlaybackState, PlaybackStateStore
    from .subtitles import SubtitleStyle

    store = settings or QSettings("VEYRA", "VEYRA")
    state_store = PlaybackStateStore(store)
    player = window.findChild(QMediaPlayer)
    audio_output = window.findChild(QAudioOutput)

    try:
        style = SubtitleStyle(
            font_size=int(store.value("subtitle/font_size", 20)),
            bottom_margin=int(store.value("subtitle/bottom_margin", 24)),
            background_opacity=int(store.value("subtitle/background_opacity", 150)),
            bold=str(store.value("subtitle/bold", "true")).lower() in {"1", "true", "yes"},
        )
    except (TypeError, ValueError):
        style = SubtitleStyle()

    try:
        subtitle_engine.set_offset(int(store.value("subtitle/offset_ms", 0)))
    except (TypeError, ValueError):
        subtitle_engine.set_offset(0)

    def save_style() -> None:
        store.setValue("subtitle/font_size", style.font_size)
        store.setValue("subtitle/bottom_margin", style.bottom_margin)
        store.setValue("subtitle/background_opacity", style.background_opacity)
        store.setValue("subtitle/bold", style.bold)
        store.setValue("subtitle/offset_ms", subtitle_engine.offset_ms)
        store.sync()

    def apply_style() -> None:
        overlay.setStyleSheet(
            "QLabel{color:white;"
            f"background:rgba(0,0,0,{style.background_opacity});"
            "padding:8px 16px;"
            f"font-size:{style.font_size}px;"
            f"font-weight:{700 if style.bold else 400};"
            "border-radius:5px;}"
        )
        width = max(200, video.width() - 80)
        height = min(160, max(50, video.height() // 4))
        y = max(0, video.height() - height - style.bottom_margin)
        overlay.setGeometry((video.width() - width) // 2, y, width, height)
        overlay.raise_()
        save_style()

    def update_style(**changes) -> None:
        nonlocal style
        style = replace(style, **changes)
        apply_style()

    def current_source() -> str:
        if player is None:
            return ""
        try:
            return player.source().toString()
        except (AttributeError, RuntimeError):
            return ""

    def save_player_state() -> None:
        if player is None:
            return
        source = current_source()
        if not source:
            return
        try:
            rate = float(player.playbackRate())
            audio_index = int(player.activeAudioTrack())
            video_index = int(player.activeVideoTrack())
            subtitle_index = int(player.activeSubtitleTrack())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return
        volume = float(audio_output.volume()) if audio_output is not None else 1.0
        muted = bool(audio_output.isMuted()) if audio_output is not None else False
        state_store.save_source(
            source,
            PlaybackState(
                playback_rate=rate,
                volume=volume,
                muted=muted,
                audio_track=audio_index,
                video_track=video_index,
                subtitle_track=subtitle_index,
                external_subtitle=subtitle_engine.source,
            ),
        )

    def restore_player_state() -> None:
        if player is None:
            return
        source = current_source()
        if not source:
            return
        state = state_store.load_source(source)
        try:
            player.setPlaybackRate(state.playback_rate)
        except (AttributeError, RuntimeError):
            pass
        if audio_output is not None:
            try:
                audio_output.setVolume(state.volume)
                audio_output.setMuted(state.muted)
            except (AttributeError, RuntimeError):
                pass
        try:
            if state.audio_track >= 0:
                player.setActiveAudioTrack(state.audio_track)
            if state.video_track >= 0:
                player.setActiveVideoTrack(state.video_track)
            if state.subtitle_track >= 0:
                player.setActiveSubtitleTrack(state.subtitle_track)
        except (AttributeError, RuntimeError):
            pass

    settings_menu = parent_menu.addMenu("Subtitle settings")
    sync_menu = settings_menu.addMenu("Subtitle sync")
    sync_minus_1 = sync_menu.addAction("Delay −1.0 s")
    sync_minus = sync_menu.addAction("Delay −0.1 s")
    sync_reset = sync_menu.addAction("Reset delay")
    sync_plus = sync_menu.addAction("Delay +0.1 s")
    sync_plus_1 = sync_menu.addAction("Delay +1.0 s")
    sync_menu.addSeparator()
    sync_status = sync_menu.addAction(f"Current: {subtitle_engine.offset_ms / 1000:+.1f} s")
    sync_status.setEnabled(False)

    def adjust_sync(delta: int) -> None:
        subtitle_engine.adjust_offset(delta)
        sync_status.setText(f"Current: {subtitle_engine.offset_ms / 1000:+.1f} s")
        save_style()

    def reset_sync() -> None:
        subtitle_engine.set_offset(0)
        sync_status.setText("Current: +0.0 s")
        save_style()

    sync_minus_1.triggered.connect(lambda: adjust_sync(-1000))
    sync_minus.triggered.connect(lambda: adjust_sync(-100))
    sync_plus.triggered.connect(lambda: adjust_sync(100))
    sync_plus_1.triggered.connect(lambda: adjust_sync(1000))
    sync_reset.triggered.connect(reset_sync)

    style_menu = settings_menu.addMenu("Subtitle styling")
    size_menu = style_menu.addMenu("Font size")
    for size in (14, 16, 18, 20, 24, 28, 32):
        action = size_menu.addAction(f"{size}px")
        action.triggered.connect(lambda _checked=False, value=size: update_style(font_size=value))

    position_menu = style_menu.addMenu("Position")
    up = position_menu.addAction("Move up")
    down = position_menu.addAction("Move down")
    center = position_menu.addAction("Bottom center")
    up.triggered.connect(lambda: update_style(bottom_margin=min(240, style.bottom_margin + 12)))
    down.triggered.connect(lambda: update_style(bottom_margin=max(0, style.bottom_margin - 12)))
    center.triggered.connect(lambda: update_style(bottom_margin=24))

    opacity_menu = style_menu.addMenu("Background opacity")
    for opacity, label in ((0, "Transparent"), (64, "25%"), (128, "50%"), (192, "75%"), (230, "90%"), (255, "Solid")):
        action = opacity_menu.addAction(label)
        action.triggered.connect(lambda _checked=False, value=opacity: update_style(background_opacity=value))

    bold = style_menu.addAction("Bold")
    bold.setCheckable(True)
    bold.setChecked(style.bold)
    bold.triggered.connect(lambda checked: update_style(bold=checked))
    style_menu.addSeparator()
    reset = style_menu.addAction("Reset styling")
    reset.triggered.connect(lambda: update_style(font_size=20, bottom_margin=24, background_opacity=150, bold=True))

    if player is not None:
        player.sourceChanged.connect(lambda _source: restore_player_state())
        player.tracksChanged.connect(lambda: restore_player_state())
        player.activeTracksChanged.connect(save_player_state)
        player.playbackRateChanged.connect(lambda _rate: save_player_state())
    if audio_output is not None:
        audio_output.volumeChanged.connect(lambda _value: save_player_state())
        audio_output.mutedChanged.connect(lambda _muted: save_player_state())

    try:
        preferences = state_store.load_preferences()
        if player is not None:
            player.setPlaybackRate(preferences.playback_rate)
        if audio_output is not None:
            audio_output.setVolume(preferences.volume)
            audio_output.setMuted(preferences.muted)
    except (AttributeError, RuntimeError):
        pass

    apply_style()
    QShortcut(QKeySequence("["), window).activated.connect(lambda: adjust_sync(-500))
    QShortcut(QKeySequence("]"), window).activated.connect(lambda: adjust_sync(500))
    window.destroyed.connect(lambda: save_player_state())
    return apply_style


__all__ = ["install_subtitle_controls"]
