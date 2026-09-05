from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from .providers.network import NetworkClient, NetworkRequestError


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise ValueError("invalid subtitle cue timing")


_TAG_RE = re.compile(r"<[^>]+>")
_ASS_TAG_RE = re.compile(r"\{[^}]*\}")


def parse_timestamp(value: str) -> int:
    """Parse SRT/WebVTT timestamps into milliseconds."""
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"invalid subtitle timestamp: {value!r}")
    whole, dot, fraction = seconds.partition(".")
    if not dot or not fraction.isdigit() or len(fraction) not in (1, 2, 3):
        raise ValueError(f"invalid subtitle timestamp: {value!r}")
    milliseconds = int(fraction.ljust(3, "0"))
    result = ((int(hours) * 60 + int(minutes)) * 60 + int(whole)) * 1000 + milliseconds
    if result < 0:
        raise ValueError(f"invalid subtitle timestamp: {value!r}")
    return result


def _clean_text(lines: list[str], *, ass: bool = False) -> str:
    text = "\n".join(lines).strip()
    if ass:
        text = _ASS_TAG_RE.sub("", text).replace(r"\N", "\n").replace(r"\n", "\n")
    text = html.unescape(_TAG_RE.sub("", text))
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def parse_srt(text: str) -> tuple[SubtitleCue, ...]:
    cues: list[SubtitleCue] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.replace("\ufeff", "").strip())
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if not lines:
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        timing = lines[timing_index].split("-->", 1)
        try:
            start = parse_timestamp(timing[0].strip())
            end = parse_timestamp(timing[1].split()[0])
        except (ValueError, IndexError):
            continue
        cue_text = _clean_text(lines[timing_index + 1 :])
        if cue_text and end >= start:
            cues.append(SubtitleCue(start, end, cue_text))
    return tuple(sorted(cues, key=lambda cue: (cue.start_ms, cue.end_ms)))


def parse_vtt(text: str) -> tuple[SubtitleCue, ...]:
    text = text.replace("\ufeff", "")
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        left, right = lines[timing_index].split("-->", 1)
        try:
            start = parse_timestamp(left.strip())
            end = parse_timestamp(right.strip().split()[0])
        except (ValueError, IndexError):
            continue
        cue_text = _clean_text(lines[timing_index + 1 :])
        if cue_text and end >= start:
            cues.append(SubtitleCue(start, end, cue_text))
    return tuple(sorted(cues, key=lambda cue: (cue.start_ms, cue.end_ms)))


def parse_ass(text: str) -> tuple[SubtitleCue, ...]:
    cues: list[SubtitleCue] = []
    events = False
    text_fields = 10
    for raw_line in text.replace("\ufeff", "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.lower() == "[events]":
            events = True
            continue
        if line.startswith("["):
            events = False
            continue
        if not events or not line.lower().startswith("dialogue:"):
            continue
        values = line.split(":", 1)[1].lstrip().split(",", text_fields - 1)
        if len(values) < 10:
            continue
        try:
            start = parse_ass_timestamp(values[1])
            end = parse_ass_timestamp(values[2])
        except ValueError:
            continue
        cue_text = _clean_text([values[9]], ass=True)
        if cue_text and end >= start:
            cues.append(SubtitleCue(start, end, cue_text))
    return tuple(sorted(cues, key=lambda cue: (cue.start_ms, cue.end_ms)))


def parse_ass_timestamp(value: str) -> int:
    value = value.strip().replace(",", ".")
    match = re.fullmatch(r"(\d+):(\d{1,2}):([0-5]\d)\.(\d{1,2})", value)
    if not match:
        raise ValueError(f"invalid ASS timestamp: {value!r}")
    hours, minutes, seconds, fraction = match.groups()
    milliseconds = int(fraction.ljust(3, "0")[:3])
    return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000 + milliseconds


def parse_subtitles(text: str, *, format_hint: str | None = None) -> tuple[SubtitleCue, ...]:
    hint = (format_hint or "").lower().lstrip(".")
    if hint in {"ass", "ssa"}:
        return parse_ass(text)
    if hint == "vtt" or text.lstrip().startswith("WEBVTT"):
        return parse_vtt(text)
    return parse_srt(text)


class SubtitleEngine:
    """Load and time external subtitles independently from the media backend."""

    def __init__(self, *, network: NetworkClient | None = None) -> None:
        self.network = network or NetworkClient()
        self.cues: tuple[SubtitleCue, ...] = ()
        self.source: str | None = None
        self.offset_ms = 0
        self._cursor = 0

    def clear(self) -> None:
        self.cues = ()
        self.source = None
        self.offset_ms = 0
        self._cursor = 0

    def load_text(self, text: str, *, source: str | None = None, format_hint: str | None = None) -> int:
        cues = parse_subtitles(text, format_hint=format_hint)
        self.cues = cues
        self.source = source
        self._cursor = 0
        return len(cues)

    def load_file(self, path: str | Path) -> int:
        file_path = Path(path)
        data = file_path.read_bytes()
        text = data.decode("utf-8-sig", errors="replace")
        return self.load_text(text, source=str(file_path), format_hint=file_path.suffix)

    def load_url(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        referer: str | None = None,
        timeout: float | None = None,
    ) -> int:
        response = self.network.get(url, headers=headers, referer=referer, timeout=timeout)
        parsed = urlparse(response.url or url)
        suffix = Path(parsed.path).suffix
        content_type = response.headers.get("Content-Type", "")
        hint = suffix or (".vtt" if "webvtt" in content_type.lower() else None)
        return self.load_text(response.text, source=url, format_hint=hint)

    def load(self, source: str | Path, *, headers: Mapping[str, str] | None = None, referer: str | None = None) -> int:
        value = str(source)
        if urlparse(value).scheme in {"http", "https"}:
            return self.load_url(value, headers=headers, referer=referer)
        return self.load_file(value)

    def set_offset(self, offset_ms: int) -> None:
        self.offset_ms = int(offset_ms)

    def adjust_offset(self, delta_ms: int) -> None:
        self.offset_ms += int(delta_ms)

    def text_at(self, position_ms: int) -> str:
        if not self.cues:
            return ""
        target = int(position_ms) + self.offset_ms
        if target < 0:
            self._cursor = 0
            return ""
        index = min(self._cursor, len(self.cues) - 1)
        if self.cues[index].start_ms <= target <= self.cues[index].end_ms:
            return self.cues[index].text
        if target < self.cues[index].start_ms:
            index = self._find_before(target)
        else:
            while index + 1 < len(self.cues) and self.cues[index + 1].start_ms <= target:
                index += 1
        self._cursor = max(0, index)
        cue = self.cues[self._cursor]
        return cue.text if cue.start_ms <= target <= cue.end_ms else ""

    def _find_before(self, target: int) -> int:
        lo, hi = 0, len(self.cues) - 1
        answer = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.cues[mid].start_ms <= target:
                answer = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return answer


__all__ = [
    "NetworkRequestError",
    "SubtitleCue",
    "SubtitleEngine",
    "parse_ass",
    "parse_ass_timestamp",
    "parse_subtitles",
    "parse_srt",
    "parse_timestamp",
    "parse_vtt",
]
