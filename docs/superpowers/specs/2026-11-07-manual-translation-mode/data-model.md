# Data model: Manual translation mode

## AppSettings additions

| Field | Type | Default | Validation | Purpose |
| --- | --- | --- | --- | --- |
| `capture_mode` | string enum: `continuous`, `on_demand` | `continuous` | Unknown values fall back to `continuous` | Select existing loop or explicit one-shot requests |
| `translation_hotkey` | shortcut string | `<shift>+<alt>+t` | Registered through `HotkeyController`; on registration failure keep previous shortcut | Trigger region selection in on-demand mode |

Missing values from old JSON and legacy pickle settings use the defaults. No persisted request queue is needed.

## One-shot translation request

Reuse immutable request/session concepts already carried through `TranslationRequest`. Add a capture request value if the pipeline boundary needs one:

- `capture_rect`: selected rectangle in screen coordinates
- `dpi_scale`: scale associated with the selected display
- `settings snapshot`: OCR engine, translator, languages, API keys, and screenshot engine
- `session_id`: invalidates results after stop or setting/mode changes

Lifecycle: `idle → selecting_region → pending → capturing_ocr → translating → idle`. Cancellation transitions `selecting_region → idle`. Stop/configuration invalidation makes any in-flight result stale. A second request during a non-idle operation is ignored and surfaced as busy.
