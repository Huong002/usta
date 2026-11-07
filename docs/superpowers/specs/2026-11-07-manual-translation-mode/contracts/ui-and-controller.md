# UI and controller contract: Manual translation mode

## User-facing contract

- A mode control offers **Continuous** and **On-demand**.
- In On-demand mode, a configurable global shortcut opens the region selector. A valid selection requests exactly one translation. Escape/cancel returns to idle without work.
- While a request is being processed, the UI exposes a busy state and ignores another trigger.
- The existing temporary-region shortcut remains separate and retains its current duration and behavior.

## Application boundary

- UI/controller submits a rectangle and DPI value to the worker; it does not call capture, OCR, or translator engines.
- Worker/pipeline snapshots current settings and associates the operation with a session identifier.
- Results/errors are delivered via existing Qt signals and overlay/status paths.
- Shutdown closes shortcut listeners and invalidates in-flight results without waiting for provider network completion on the GUI thread.

There is no public network API or CLI contract to add.
