# Manual translation mode

## Summary

Add an on-demand translation mode alongside USTA's existing continuous capture mode. In on-demand mode, the user presses a configurable global shortcut, selects a screen rectangle, and USTA captures it once, runs OCR once, translates the recognized text once, and displays the result in the existing overlay. The current continuous mode remains the default and keeps its current behavior.

## User stories

- As a user who does not want continuous screen monitoring, I can choose on-demand mode and request a translation only when I need one.
- As a user, I can trigger a screen-region selector with a configurable shortcut, select a rectangle, and receive one translation for that selection.
- As an existing user, I can keep continuous mode and retain my current settings and shortcuts.

## Functional requirements

1. The UI exposes Continuous and On-demand translation modes.
2. Continuous remains the default for existing and newly created settings.
3. On-demand mode registers a configurable global translation shortcut. Pressing it opens the existing region selector; confirming a valid rectangle starts one capture/OCR/translation request.
4. Canceling region selection produces no capture, OCR, or translation request.
5. Repeated requests do not overlap capture/OCR work. While a request is active, additional trigger attempts are ignored or clearly queued; the initial implementation should ignore them and indicate that work is in progress.
6. Results and errors use existing overlay/status surfaces and respect the existing session invalidation rules.
7. Temporary-region selection continues to mean a temporary override for continuous monitoring and does not silently change its existing ten-second restoration behavior.
8. The mode and shortcut persist through the existing settings store. Existing JSON and legacy settings without these fields load as Continuous with the default shortcut.
9. Shutdown unregisters the new shortcut and cancels or invalidates any pending request without blocking the GUI on translation network I/O.

## Acceptance scenarios

- Given existing settings without a mode field, when USTA loads, then Continuous mode is selected and the current continuous loop operates unchanged.
- Given On-demand mode, when the user presses the configured shortcut and selects a non-empty area, then exactly one capture/OCR/translation request runs and its result appears in the overlay.
- Given On-demand mode, when the user cancels region selection, then no request runs and the application remains ready for the next shortcut.
- Given an active request, when another shortcut is pressed, then a second capture/OCR request does not overlap it and the user receives a busy indication.
- Given either mode, when the user changes OCR, translator, language, or capture settings, then subsequent requests use the latest settings and stale results are discarded.
- Given a temporary-region shortcut in Continuous mode, then the existing temporary-region behavior and restoration timer remain intact.

## Assumption to confirm during implementation

“Nhấn một phím thì mới chọn dịch” is interpreted as: each shortcut press opens the selector, then the chosen rectangle is translated once. If the intended interaction is instead to choose a persistent rectangle once and have each shortcut press translate that same rectangle, the UI flow and acceptance scenarios should be adjusted before implementation.
