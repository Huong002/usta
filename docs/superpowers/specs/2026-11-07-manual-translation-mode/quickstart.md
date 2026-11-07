# Quickstart validation: Manual translation mode

## Prerequisites

- Install USTA and its dependencies following [Development](../../../development.md).
- Configure an OCR engine and translation provider as for normal continuous use.
- On macOS, grant the relevant screen recording and accessibility permissions; on Linux, verify the selected desktop capture portal/tool is available.

## Scenarios

1. Start USTA with an existing settings file that has no `capture_mode` or `translation_hotkey`. Expected: Continuous mode remains selected and current continuous translation works.
2. Select On-demand mode and configure a shortcut. Press it, select a screen rectangle, and confirm. Expected: one OCR/translation result appears in the overlay; no continuous polling starts. The first shortcut request starts the worker if needed.
3. Press the shortcut and cancel region selection. Expected: no capture/OCR/translation work; another shortcut can start a request.
4. Trigger another request while one is active. Expected: no overlapping capture/OCR work and a busy indication.
5. Switch back to Continuous mode. Use the temporary-region shortcut. Expected: its selected region is temporary and the previous region restores after ten seconds.
6. Quit during selection or translation. Expected: listeners close, stale results are ignored, and the GUI remains responsive.

## Automated validation

Run `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v` as documented in [Testing](../../../testing.md). Run opt-in native tests from `tests/native` in a real desktop session to validate platform shortcut and selection behavior.
