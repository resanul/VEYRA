from __future__ import annotations

from pathlib import Path

from veyra.subtitles import SubtitleEngine, parse_ass, parse_srt, parse_vtt


SRT = """1\n00:00:01,000 --> 00:00:02,500\nHello <i>world</i>!\n\n2\n00:00:03,000 --> 00:00:04,000\nSecond line\n"""

VTT = """WEBVTT\n\n00:00:00.500 --> 00:00:01.500 align:start\nFirst cue\n\n00:00:02.000 --> 00:00:03.000\nSecond cue\n"""

ASS = """[Script Info]\nTitle: Demo\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,Hello {\\i1}world{\\i0}\\Nsecond line\n"""


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
