# Implementation plan: Manual translation mode

**Branch:** `main`  
**Feature directory:** `docs/superpowers/specs/2026-11-07-manual-translation-mode/`

## Goal

Add an on-demand mode that translates one manually selected screen rectangle after a configurable global shortcut, while retaining the current continuous mode as the default.

## Technical context

- Python 3.10+ and PySide6; no new dependency is expected.
- `Pipeline` currently owns a continuous capture/OCR loop and a single translation executor.
- `OCRWorker` wraps the pipeline in a `QThread` and forwards results using Qt signals.
- `ControlPanel` already owns global shortcut registration, region selection, mode controls, and settings interactions.
- `SettingsStore` uses schema version 1 and `AppSettings.from_dict` supplies defaults for omitted fields, so new fields can be backward-compatible without a schema bump.
- Existing temporary-region selection changes the active continuous capture rectangle for ten seconds; it must remain a separate action.
- Unknown: platform-specific region selector cancellation and global shortcut behavior should be checked on Linux, Windows, and macOS while implementing. Existing selector and shortcut abstractions should be reused.

## Constitution / design gates

No `.specify/memory/constitution.md` exists in this repository, so a formal Spec Kit constitution check is unavailable. Apply repository architecture constraints from `docs/architecture.md`: UI does not access worker internals, core engines do not import UI, jobs carry immutable settings/session metadata, worker cleanup remains asynchronous, and no dependency is added.

Gate result: **PASS with platform validation required**. The mode belongs in application settings and pipeline/worker boundaries; UI selects the rectangle and submits a request through the controller. Existing continuous behavior and settings serialization must have regression coverage before completion.

## Phase 0: research findings

See [research.md](../specs/2026-11-07-manual-translation-mode/research.md). Existing project abstractions cover shortcut registration, screen selection, capture, OCR, translation, and stale-session suppression. No external framework/API choice is needed.

## Phase 1: design

- [Data model](../specs/2026-11-07-manual-translation-mode/data-model.md)
- [UI and controller contract](../specs/2026-11-07-manual-translation-mode/contracts/ui-and-controller.md)
- [Quickstart validation](../specs/2026-11-07-manual-translation-mode/quickstart.md)

## Implementation sequence

1. Add `capture_mode` and `translation_hotkey` settings, defaults, validation, persistence compatibility, and settings presenter plumbing.
2. Add a mode selector and shortcut capture row to the existing UI, with translated labels and reset behavior. Keep the temporary-region shortcut independent.
3. Add a one-shot request path through controller, worker, and pipeline. Capture the supplied rectangle once, OCR once, submit translation through the existing single-thread executor, and use session IDs to reject stale results.
4. Wire the global shortcut to the existing region selector only in On-demand mode. Debounce and guard selector state, cancellation, busy state, and shutdown.
5. Keep Continuous mode's capture loop behavior unchanged; verify temporary region selection and restoration remain unchanged.
6. Update documentation and localization catalogs for mode and shortcut labels/help text.

## Validation plan

- Settings unit tests: default mode, valid/invalid mode values, persistence round trip, and old JSON/legacy migration compatibility.
- Pipeline tests: exactly one capture/OCR/translation on a one-shot request; no work on cancellation; no overlapping requests; stale session suppression; error reporting.
- UI/integration tests: mode selection, shortcut registration/replacement, selector cancellation/confirmation, busy feedback, and shutdown cleanup.
- Regression tests: continuous pipeline behavior and the existing ten-second temporary-region restoration.
- Run the portable suite described in `docs/testing.md`; use opt-in native tests on each available desktop platform for hotkey and selector integration.

## Risks and mitigations

- Platform selectors may block synchronously: reuse the current deferred selector invocation and ensure it runs on the GUI thread, while capture/OCR/translation stay in the worker.
- Configuring separate shortcuts can create collisions: reject failed registration and retain the previous shortcut using `HotkeyController`'s candidate-first replacement behavior.
- Settings changes during an in-flight request can show an obsolete result: bind the immutable request to a session ID and discard results after configuration changes or stop.
- Translation providers may take time: keep network work on the existing executor and avoid blocking the GUI.
