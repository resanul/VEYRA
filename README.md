# VEYRA

**VEYRA — Universal Media Player**

Python/PySide6 Windows implementation, designed around the feature footprint of the supplied Android reference player.

## Current milestone

- Python 3.12+
- PySide6 Windows desktop shell
- Local video/audio playback controls
- Provider catalog/search pipeline
- Extension repository + installer foundation
- Clean-room CloudStream lifecycle/API bridge
- Windows-first CS3 execution boundary for a trusted external DEX worker
- Movie/series details surface with season + episode grouping
- Automated Windows CI: syntax check, unit tests, package build

## CS3 execution architecture

VEYRA does **not** attempt to execute Android DEX inside CPython. On Windows, a `.cs3` package is inspected and handed to an isolated `veyra-cs3-executor.exe` through a JSON-lines RPC boundary. The worker must explicitly advertise DEX execution, Android API compatibility, and the CloudStream API bridge before VEYRA treats a CS3 provider as runnable.

The Android ART host under `runtime/android-host/` is validation tooling only. It is not a dependency of the Windows application or the Windows package.

## Roadmap

1. Production libmpv/FFmpeg playback backend
2. HLS/DASH/network stream extraction and headers
3. Advanced subtitles and audio/video track selection
4. Downloads + download manager
5. Library, favorites, queue and resume improvements
6. Casting, picture-in-picture and external players
7. Windows installer, updater and signed release artifacts

The Android APK is used as a functional reference. VEYRA is an independent Windows implementation and does not copy proprietary application source code.
