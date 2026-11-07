# Tasks: Manual translation mode

## Feature

Add an On-demand mode that opens the screen selector from a configurable global shortcut and translates the selected region once. Keep Continuous mode as the default and preserve the existing temporary-region shortcut.

## Phase 1: Setup

No project setup tasks are needed; the repository and runtime dependencies are already in place.

## Phase 2: Foundational

- [X] T001 Add `capture_mode` (`continuous` or `on_demand`, default `continuous`) and `translation_hotkey` (default `<shift>+<alt>+t`) to `AppSettings`, including fallback to the default for unsupported mode values, in `src/usta/application/settings.py`.

## Phase 3: User Story 1 — Choose on-demand mode (P1)

**Goal:** The user can choose Continuous or On-demand and keep the choice after restarting USTA.

**Independent acceptance:** Select On-demand, restart the app, and confirm it remains selected. Select Continuous and confirm the current continuous capture mode starts as before.

- [X] T002 [US1] Load and save `capture_mode` and `translation_hotkey` through the existing settings presentation flow in `src/usta/ui/settings_presenter.py`.
- [X] T003 [US1] Add a Continuous/On-demand selector to the settings UI and connect changes to the settings presenter in `src/usta/ui/tabs/ocr_tab.py` and `src/usta/ui/main_window.py`.

## Phase 4: User Story 2 — Translate a manually selected region on demand (P1)

**Goal:** Each configured shortcut press opens region selection; a valid selection is captured, OCR'd, and translated exactly once.

**Independent acceptance:** In On-demand mode, press the shortcut, select a non-empty rectangle, and confirm a single result appears. Cancel selection and confirm no capture or translation starts. Trigger while busy and confirm no overlapping capture/OCR occurs and busy state is shown.

- [X] T004 [US2] Add a one-shot pipeline request path that captures the supplied rectangle once, runs the configured OCR once, and submits translation through the existing executor; keep `Pipeline.run` in its existing loop only for Continuous mode in `src/usta/application/pipeline.py` and `src/usta/application/results.py`.
- [X] T005 [US2] Expose the one-shot request and busy/result signals through the worker and application controller without calling engines from the UI in `src/usta/application/worker.py` and `src/usta/application/controller.py`.
- [X] T006 [US2] Register and persist a dedicated translation shortcut, open the existing selector on activation, submit confirmed rectangles, and guard cancellation, busy state, and shutdown in `src/usta/ui/main_window.py` and `src/usta/application/hotkey_controller.py`.
- [X] T007 [US2] Add translated labels, shortcut capture/reset behavior, and help text that explains the one-shot selection flow in `src/usta/ui/tabs/hotkey_tab.py` and `src/usta/resources/translations/*/LC_MESSAGES/messages.po`.

## Phase 5: User Story 3 — Keep existing continuous and temporary-region behavior (P1)

**Goal:** Existing users retain continuous mode, their current shortcuts, and the temporary ten-second region behavior.

**Independent acceptance:** Load settings without the new keys and confirm Continuous mode and default hotkey values apply. Use the existing temporary-region shortcut while Continuous mode runs and confirm the selected region is restored after ten seconds.

- [X] T008 [US3] Keep temporary-region shortcut registration, selection, and ten-second restoration independent of the new translation mode in `src/usta/ui/main_window.py`, `src/usta/ui/tabs/hotkey_tab.py`, and `src/usta/application/region_controller.py`.
- [X] T009 [US3] Document both modes, the default behavior, and the separate temporary-region shortcut in `README.md` and `docs/architecture.md`.

## Phase 6: Polish and cross-cutting concerns

- [X] T010 Update the manual-mode scenario and platform permission notes to match the implemented controls in `docs/superpowers/specs/2026-11-07-manual-translation-mode/quickstart.md`.

## Dependencies

```text
T001 → T002 → T003
T001 → T004 → T005 → T006 → T007
T006 → T008
T003, T007, T008 → T009 → T010
```

User Story 1 precedes User Story 2 because mode selection and persisted settings are prerequisites to routing hotkey actions. User Story 3 compatibility and temporary-region behavior should be completed before the cross-cutting documentation task.

## Parallel execution opportunities

- After T001, T002 and T004 can proceed in parallel because they change settings presentation and pipeline internals respectively.
- After T004 and T005, T003 can proceed in parallel with T006 if separate implementers own the tab UI and main-window shortcut integration; integrate both before T007.
- T008 can proceed alongside T004/T005 after T001, provided changes to shortcut wiring do not conflict; integrate before T009.

## Implementation strategy

1. Deliver the On-demand path end-to-end: settings, one-shot pipeline request, worker boundary, selector shortcut, and visible result/busy feedback.
2. Confirm Continuous remains the default and preserve existing settings and temporary-region semantics.
3. Finish localization and documentation, then run the automated and native validation scenarios in `quickstart.md`.

**Suggested MVP:** User Stories 1 and 2 together. Story 1 adds the selectable mode; Story 2 makes the on-demand flow usable end-to-end. Story 3 is required before declaring the full feature complete because it protects existing behavior.

## Test-generation note

The feature spec defines acceptance scenarios but does not explicitly request adding test code or TDD. Therefore, this task list does not add test-authoring tasks. Validate the listed acceptance criteria using the existing test suite and native desktop checks during implementation.
