# Research: Manual translation mode

## Decision: reuse the existing application boundaries

**Rationale:** `ControlPanel` already owns global hotkeys and region selection; `OCRWorker` is the Qt thread adapter; `Pipeline` owns capture/OCR and a single-thread translation executor. Route a one-shot request through these boundaries instead of creating a second provider stack.

**Alternatives considered:** Capture and translate directly from the hotkey callback (rejected because UI callback would own blocking capture/OCR/network operations); build a parallel pipeline (rejected because it duplicates settings, provider lifecycle, and stale-result handling).

## Decision: keep mode as backward-compatible settings data

**Rationale:** `AppSettings.from_dict` supplies defaults for missing keys and `SettingsStore` stores version-1 JSON. Adding a string enum field with default `continuous` preserves old settings.

**Alternatives considered:** Bump the settings schema (unnecessary for an additive field); infer mode from whether the worker is running (does not represent user preference and cannot persist).

## Decision: keep temporary-region shortcut semantics independent

**Rationale:** Current UI and `RegionController` deliberately implement a temporary ten-second region while Continuous mode runs. Reusing that shortcut as an on-demand trigger would change an established behavior.

**Alternatives considered:** Repurpose the existing shortcut (rejected for compatibility); remove temporary selection (outside requested scope).

## Open implementation check

Exercise the existing selector and `pynput`-based shortcut on supported OS/desktop combinations. The plan does not require a new native API, but platform permission and cancellation behavior can vary.
