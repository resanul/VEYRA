from __future__ import annotations

from pathlib import Path

import pytest

from veyra.subtitles import SubtitleEngine, SubtitleStyle, parse_ass, parse_srt, parse_vtt


SRT = """1
00:00:01,000 --> 00:00:02,500
Hello <i>world</i>!

2
00:00:03,000 --> 00:00:04,000
Second line
"""

VTT = """WEBVTT

00:00:00.500 --> 00:00:01.500 align:start
First cue

00:00:02.000 --> 00:00:03.000
Second cue
"""

ASS = """[Script Info]
Title: Demo

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,Hello {\i1}world{\i0}\Nsecond line
"""


def test_parse_srt_strips_markup_and_preserves_timing() -> None:
    cues = parse_srt(SRT)
    assert len(cues) == 2
    assert cues[0].start_ms == 1000
    assert cues[0].end_ms == 2500
    assert cues[0].text == "Hello world!"


def test_parse_vtt_accepts_cue_settings() -> None:
    cues = parse_vtt(VTT)
    assert [cue.text for cue in cues] == ["First cue", "Second cue"]
    assert cues[0].start_ms == 500


def test_parse_ass_supports_dialogue_and_line_breaks() -> None:
    cues = parse_ass(ASS)
    assert len(cues) == 1
    assert cues[0].start_ms == 1000
    assert cues[0].text == "Hello world\nsecond line"


def test_engine_applies_offset_and_uses_cursor() -> None:
    engine = SubtitleEngine()
    assert engine.load_text(SRT, format_hint="srt") == 2
    assert engine.text_at(1000) == "Hello world!"
    assert engine.text_at(2600) == ""
    engine.adjust_offset(200)
    assert engine.text_at(800) == "Hello world!"


def test_engine_load_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.srt"
    path.write_text(SRT, encoding="utf-8")
    engine = SubtitleEngine()
    assert engine.load_file(path) == 2
    assert engine.source == str(path)


def test_engine_clear() -> None:
    engine = SubtitleEngine()
    engine.load_text(SRT)
    engine.clear()
    assert engine.cues == ()
    assert engine.text_at(1000) == ""


def test_subtitle_style_validates_and_copies_changes() -> None:
    style = SubtitleStyle()
    updated = style.with_changes(font_size=32, background_opacity=64, bold=False)
    assert style.font_size == 20
    assert updated.font_size == 32
    assert updated.background_opacity == 64
    assert updated.bold is False


@pytest.mark.parametrize(
    "changes",
    [
        {"font_size": 9},
        {"font_size": 65},
        {"bottom_margin": -1},
        {"bottom_margin": 241},
        {"background_opacity": -1},
        {"background_opacity": 256},
    ],
)
def test_subtitle_style_rejects_invalid_values(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        SubtitleStyle(**changes)
