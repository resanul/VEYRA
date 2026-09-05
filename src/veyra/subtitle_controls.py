from __future__ import annotations

from dataclasses import replace


def install_subtitle_controls(window, video, overlay, subtitle_engine, parent_menu, *, settings=None):
    """Install persistent subtitle sync/styling actions into the player menu.

    ``parent_menu`` must not be rebuilt by track discovery; the caller can
    therefore refresh the embedded-track submenu without deleting these controls.
    """
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QKeySequence, QShortcut

    from .subtitles import SubtitleStyle

    store = settings or QSettings("VEYRA", "VEYRA")
    try:
        style = SubtitleStyle(
            font_size=int(store.value("subtitle/font_size", 20)),
            bottom_margin=int(store.value("subtitle/bottom_margin", 24)),
            background_opacity=int(store.value("subtitle/background_opacity", 150)),
            bold=str(store.value("subtitle/bold", "true")).lower() in {"1", "true", "yes"},
        )
    except (TypeError, ValueError):
        style = SubtitleStyle()

    def save_style() -> None:
        store.setValue("subtitle/font_size", style.font_size)
        store.setValue("subtitle/bottom_margin", style.bottom_margin)
        store.setValue("subtitle/background_opacity", style.background_opacity)
        store.setValue("subtitle/bold", style.bold)
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

    settings_menu = parent_menu.addMenu("Subtitle settings")
    sync_menu = settings_menu.addMenu("Subtitle sync")
    sync_minus_1 = sync_menu.addAction("Delay −1.0 s")
    sync_minus = sync_menu.addAction("Delay −0.1 s")
    sync_reset = sync_menu.addAction("Reset delay")
    sync_plus = sync_menu.addAction("Delay +0.1 s")
    sync_plus_1 = sync_menu.addAction("Delay +1.0 s")
    sync_menu.addSeparator()
    sync_status = sync_menu.addAction("Current: +0.0 s")
    sync_status.setEnabled(False)

    def adjust_sync(delta: int) -> None:
        subtitle_engine.adjust_offset(delta)
        sync_status.setText(f"Current: {subtitle_engine.offset_ms / 1000:+.1f} s")

    sync_minus_1.triggered.connect(lambda: adjust_sync(-1000))
    sync_minus.triggered.connect(lambda: adjust_sync(-100))
    sync_plus.triggered.connect(lambda: adjust_sync(100))
    sync_plus_1.triggered.connect(lambda: adjust_sync(1000))
    sync_reset.triggered.connect(lambda: (subtitle_engine.set_offset(0), sync_status.setText("Current: +0.0 s")))

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

    apply_style()
    QShortcut(QKeySequence("["), window).activated.connect(lambda: adjust_sync(-500))
    QShortcut(QKeySequence("]"), window).activated.connect(lambda: adjust_sync(500))
    return apply_style


__all__ = ["install_subtitle_controls"]
