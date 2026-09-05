# VEYRA

**VEYRA — Universal Media Player**

Python/PySide6 Windows implementation, designed around the feature footprint of the supplied Android reference player.

## Current milestone

- Python 3.12+
- PySide6 desktop shell
- Local video/audio open dialog
- Initial play/pause playback
- Media type detection for common video/audio formats and HTTP/HLS/DASH sources
- Persistent local media library foundation
- Backend abstraction ready for the production libmpv/FFmpeg engine
- Automated Windows CI: syntax check, unit tests, package build

## Roadmap

1. Production libmpv/FFmpeg playback backend
2. Seeking, speed, volume, fullscreen and keyboard/mouse controls
3. Audio/video/subtitle track selection and subtitle styling/delay
4. HLS/DASH/network streaming controls
5. Queue, history, resume position and favorites
6. Download manager
7. Casting and picture-in-picture
8. Series/episode/provider integration
9. Windows installer and signed release artifacts

The Android APK is used as a functional reference. VEYRA is an independent Windows implementation and does not copy proprietary application source code.
