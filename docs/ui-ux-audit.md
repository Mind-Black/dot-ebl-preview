# Web UI/UX audit

Date: 2 November 2026. Target: current working-tree `web/` implementation, including pre-existing uncommitted work. Expert review for mixed-experience technical users; desktop first. No application fixes were made.

## Executive summary

Core desktop tasks are usable: all four presets load, supplied image formats can be interpreted, NPZ imports work, inspector views switch, and PNG/CSV/JSON/GDS/ZIP downloads are reachable through the UI. The dark visual hierarchy groups the scientific controls clearly at 1440×900. Fabrication review exposes useful physical units and restores focus after closing.

Four high-priority barriers remain: smaller-screen clipping, inaccessible welcome presets, unnamed scientific inputs, and an unexplained blank application when WebGL initialization fails. Address those before cosmetic refinement. Medium findings concern stale-design ambiguity after failed import, interpretation guidance, keyboard probing, contrast, and tab semantics. The fabrication dialog has additional presentation and naming defects.

No critical finding was established. Severity here describes user impact, not engine correctness. Critical means a blocked core task or misleading consequential output; high means a major barrier affecting a user group or environment; medium means recoverable friction; low means minor clarity/polish. Conditional failures are classified high when a workaround outside the app exists. Heuristic concerns are explicitly identified below.

## Environment and baseline

- Production build served locally through Vite preview on port 4174. Chromium 156.0.8078.4; ANGLE Vulkan SwiftShader software renderer. The visible flat canvas uses 2D composition; `observations.json` reports its WebGL query as unavailable. A separate WebGL canvas query in `additional-observations.json` identifies the rendering backend.
- Firefox 157.0: preset, Analytics, and JSON-download smoke checks passed. WebKit launch exceeded a five-second bound; no WebKit compatibility claim.
- `npm run check`: passed. `npm test`: 44/44 passed. `npm run build`: passed, with a warning for a JavaScript chunk over 500 kB (552.13 kB uncompressed). Bundle size alone is not evidence of a UX defect.
- Development Playwright suite: 13/13 passed. Production suite: 9/13 passed. Four failures import source `.ts` modules not available in the build: fabrication snapshot export, million-cell benchmark, texture refresh, and rapid-edit snapshot review. These are test portability defects, not confirmed product failures. Production UI import/export checks independently passed.
- Initial sandbox attempts could not access localhost or the browser cache; successful runs used the installed browser cache and a preview/browser pair outside network isolation. These setup failures are excluded from product findings.

## Prioritized findings

### UX-01 — High: workbench clips controls on tablet and mobile

**Status:** Reproduced. **Workflow:** inspection, editing, navigation. **Environment:** Chromium, 768×1024 and 390×844; also a 720×450 reduced-viewport reflow probe.

**Reproduce:** Load Concentric Test Pattern on desktop, resize to the listed sizes, then attempt to inspect Analytics and edit illumination. Both main panes retain half the viewport; the sidebar retains two internal columns. On mobile its outer width is only 195 px. Tabs, scene controls, toolbar text, and map content extend beyond the visible area. Vertical scrolling does not resolve the horizontal clipping.

**Evidence:** [Mobile](ui-ux-audit-assets/layout-390x844.png), [tablet](ui-ux-audit-assets/layout-768x1024.png), and panel dimensions in [observations](ui-ux-audit-assets/observations.json). **Location:** `web/style.css`, `.workbench-sidebar`, `.sidebar-content`, `.workbench-container`, and viewport toolbar rules. Only the welcome action grid has a narrow-screen breakpoint.

**Recommendation / acceptance:** Introduce a narrow-screen workbench layout and one-column controls; allow toolbar/tab wrapping or deliberate accessible scrolling. At all audited sizes, every enabled control and inspector view must be reachable and readable without clipped labels or hidden columns. Recheck on physical touch hardware and actual browser zoom.

### UX-02 — High: welcome presets cannot be activated with a keyboard

**Status:** Reproduced. **Workflow:** onboarding. **Environment:** Chromium, 1440×900.

**Reproduce:** Reload and repeatedly press Tab. Focus cycles through Preset Gallery and Browse Local Files, skipping all four cards. Cards are `DIV` elements with `tabIndex=-1`, no role, and click handlers only.

**Evidence:** `presets` in [observations](ui-ux-audit-assets/observations.json) and keyboard sequence in [additional observations](ui-ux-audit-assets/additional-observations.json). **Location:** `web/components/welcome/WelcomeView.ts`, `renderPresets`.

**Recommendation / acceptance:** Use native buttons for preset actions with visible focus. All four must be reachable in logical order and load via Enter and Space. Verify focus moves sensibly into the workbench after activation. WCAG reference: 2.1.1.

### UX-03 — High: scientific controls lack accessible names

**Status:** Reproduced DOM defect. **Workflow:** design and scene editing. **Environment:** Chromium, desktop.

**Reproduce:** Inspect a visible range/number pair for pitch, orientation, light position, or observer position. The visible label sits outside both controls with no `for`, wrapping relationship, or ARIA naming. The interpretation select also has no associated label. A user navigating inputs with assistive technology cannot reliably identify their meaning.

**Evidence:** Empty `labels` and `aria` fields in [observations](ui-ux-audit-assets/observations.json). **Location:** `web/components/controls/sliderControl.ts` and `DesignControls.ts`.

**Recommendation / acceptance:** Give each slider and numeric input a unique, meaningful accessible name including the parameter and unit; associate shared help text programmatically. Verify the accessibility tree and a screen-reader walkthrough. Visible badges must not be the only source of units. WCAG reference: 1.3.1, 3.3.2, 4.1.2.

### UX-04 — High: WebGL startup failure leaves a blank application

**Status:** Reproduced with explicit fault injection. **Workflow:** first use and recovery. **Environment:** Chromium, desktop.

**Reproduce:** Before loading the app, override canvas WebGL context creation to return null. Initialization throws `Error creating WebGL context`; only the header remains. No message explains the requirement or offers recovery.

**Evidence:** [Failed-render screenshot](ui-ux-audit-assets/07-no-webgl.png), `failureErrors` and `failureBody` in additional observations. This simulates unavailable WebGL; it is not an observed hardware failure. **Location:** `web/main.ts` eagerly constructs `DualViewport`; viewer constructors initialize renderers before mounting the welcome screen.

**Recommendation / acceptance:** Catch renderer initialization failure and present an accessible explanation with retry/troubleshooting guidance. Keep non-rendering inspection/import functionality available where feasible. A denied context must never produce an unexplained empty page; successful retry should restore the intended interface.

### UX-05 — Medium: failed import leaves the prior design visible without identifying it as retained

**Status:** Reproduced. **Workflow:** replacement and error recovery. **Environment:** Chromium, 1440×900.

**Reproduce:** Import `design.npz`, return to the gallery, upload a corrupt PNG. The workbench opens immediately, the previous preview remains visible, the profile reads RGBA continuous, and the error is `InvalidStateError: The source image could not be decoded.` An unsupported text upload produces the same message. Users must infer which data is still being shown.

**Evidence:** [Failed import](ui-ux-audit-assets/06-corrupt-import.png), error strings in observations. **Location:** `WelcomeView.handleFile`, `designStore.loadFile`, and the error banner in `DesignControls`.

**Recommendation / acceptance:** Identify the failed filename, offer a useful recovery action, and explicitly identify any retained design. While replacement is processing or failed, all artifact actions must clearly reflect the retained design or be unavailable. Announce errors programmatically. A subsequent valid upload must clear the message and replace the design.

### UX-06 — Medium: import interpretation needs an explicit decision

**Status:** Default behavior reproduced; risk to comprehension is heuristic. **Workflow:** image import. **Environment:** Chromium desktop.

**Reproduce:** Upload each supplied HLS, Unity, RGB8, and RGB16 PNG fixture. Every image initially uses RGBA continuous. Selecting its matching profile subsequently succeeds without an error. The welcome screen lists supported image types but does not explain that the encoding must be known and selected.

**Evidence:** Initial profile values in observations; successful profile changes in additional observations. **Location:** `WelcomeView`, `DesignControls`, and the default/reset profile in `designStore`.

**Recommendation / acceptance:** Explain parameter-image encoding at ingestion and make the current interpretation prominent before users trust results or export. Do not imply automatic encoding detection. Provide concise guidance for the available profiles and ordinary photographs/lossy images. Validate the wording with first-time technical users; this audit does not establish numerical misinterpretation of outputs.

### UX-07 — Medium: cell probing relies on pointer hover

**Status:** Pointer behavior reproduced; keyboard gap confirmed by interaction/source inspection. **Workflow:** precise parameter inspection. **Environment:** Chromium desktop.

**Reproduce:** Hover the flat canvas to show row, column, period, stored angle, and effective angle. Click and press an arrow key: there is no implemented keyboard cell-navigation workflow. The prompt explicitly asks users to hover.

**Evidence:** `probe` in observations, canvas interaction code in `web/components/viewer/FlatView.ts`, and [workbench screenshot](ui-ux-audit-assets/02-workbench-desktop.png). **Recommendation / acceptance:** Add a focusable probe with keyboard cell movement or row/column input, and a tap-based persistent selection. Users must obtain the same values without hover or color discrimination. Announce the selected-cell result without flooding announcements during pointer movement.

### UX-08 — Medium: muted explanatory text has insufficient contrast

**Status:** CSS contrast defect verified; not a complete contrast audit. **Workflow:** reading instructions and scientific labels. **Environment:** desktop stylesheet.

**Reproduce / evidence:** `--text-muted: #64748b` against raised surface `#182030` has approximately 3.43:1 contrast, below 4.5:1 for normal text. Small labels using this pairing are visible in [the corrupt-import screenshot](ui-ux-audit-assets/06-corrupt-import.png). **Location:** `web/style.css` color tokens and `.text-muted` usages.

**Recommendation / acceptance:** Adjust foreground/background tokens so normal informational text reaches 4.5:1. Measure rendered combinations, including alpha backgrounds; separately check active/focus states. Disabled controls are excluded from this specific contrast claim. WCAG reference: 1.4.3.

### UX-09 — Medium: inspector selection is communicated visually but lacks tab semantics

**Status:** Source/DOM-confirmed. **Workflow:** inspector navigation. **Environment:** Chromium desktop.

**Reproduce:** Switch Period Map, Angle Map, Source Image, and Analytics. Buttons update an `active` class and hide/show containers, but do not expose tablist/tab/tabpanel relationships or selected state.

**Evidence:** `web/main.ts`, inspector construction and `updateActiveTab`; selected appearance in the desktop screenshot. **Recommendation / acceptance:** Implement semantic tabs with selected state, associated panels, and standard arrow-key navigation, or expose an equivalent accessible navigation pattern. Assistive technology must identify the active view and its content; keyboard users must see focus independently of selection.

### UX-10 — Low: fabrication dialog has broken unit text and inconsistent presentation

**Status:** Reproduced. **Workflow:** fabrication review. **Environment:** Chromium desktop.

**Reproduce:** Open EBL Lithography Fabrication and Export EBL Layout. Orientation displays `0�` (and `30�` after editing). The dialog opens at the upper-left with tightly packed action buttons; it has a visible heading but no accessible name association. Progress starts indeterminate even after validation. Closing restores focus to the export button.

**Evidence:** [Fabrication dialog](ui-ux-audit-assets/04-fabrication.png), dialog text and null `aria-labelledby` in observations. **Location:** `web/components/export/FabricationModal.ts` and `.fabrication-dialog` in `web/style.css`.

**Recommendation / acceptance:** Correct the degree glyph, associate the heading and progress label, space actions consistently, and distinguish validated/generating/completed states. Verify degree text at nonzero orientation, modal naming, Escape/Close focus restoration, repeated GDS/ZIP generation, and narrow-screen containment. Treat the naming problem as an accessibility regression even though the grouped visual issue is low priority.

## Workflow coverage

| Area | Result and evidence | Limits / follow-up |
|---|---|---|
| Purpose and presets | Purpose and qualitative preview are stated; all four presets open the workbench | Comprehension needs user research; keyboard defect UX-02 |
| Image import / interpretation | HLS, Unity, RGB8, RGB16 fixtures upload; matching profiles selected successfully | BMP/JPEG/WebP and Learning Shaders HLS not exercised end to end |
| NPZ / missing source | NPZ imports; Source Image explains no raw RGB image was imported | See `05-npz-source.png`; empty canvas occupies substantial space |
| Replacement / gallery | Gallery return works; replacing a design works; orientation 30° persists across replacement | Persistence is observed behavior, not classified as a bug; clarify its scope to users |
| Corrupt / unsupported input | Both produce a visible error; prior preview retained | UX-05; text upload bypassed picker extension filtering via browser test upload |
| Maps / analytics | All four inspector controls exercised; hover returns units and stored/effective angles | Numeric optics/map correctness outside scope |
| Design / scene edits | Orientation edited via numeric input; final rapid edit reads 35°; scene layout/source reviewed | Full scene-control combination matrix and invalid numeric boundaries not dynamically covered |
| Processing / large design | Synthetic 1075×1075 uniform PNG uploaded through file input; no error after 3-second observation; subsequent orientation edits work | Not a measured processing-time bound. `08-large-design.png`; no hardware performance claim |
| Worker responsiveness | Existing dev test: 1,155,625 cells, edit 2154.5 ms, export 1110.4 ms, 290 timer ticks, 69,338,616-byte GDS | Internal worker test, not visible-UI usability evidence; software rendering environment |
| PNG / CSV / JSON | Four data/capture actions download; sample files retained with byte counts | Filenames match grid dimensions; screenshot PNG content inspected, numerical data correctness not audited |
| GDS / ZIP review | Both downloads through visible controls; updated orientation appears in review; Close restores focus | Mid-generation cancellation, worker ERROR recovery, and latest-edit artifact-content parity need further coverage |
| Desktop layout | 1440×900 and 1280×720 screenshots reviewed; sidebar scrolls | Hidden scrollbars reduce discovery; assess with users |
| Tablet / mobile | 768×1024 and 390×844 captured and inspected | Reproduced UX-01. Physical touch gestures not tested |
| Zoom / reflow | 720×450 CSS viewport used as a half-size proxy for 1440×900 at 200% | Native browser 200% zoom not verified; proxy does not test all zoom behavior |
| Keyboard / semantics | Preset traversal, input labels, tab markup, probe behavior, dialog close/focus checked | No full screen-reader session or exhaustive focus-order audit |
| Failed rendering | Null WebGL context fault injected before startup; blank application reproduced | Context-loss-after-start and device-specific GPU errors not tested |
| Second browser | Firefox preset → Analytics → JSON export passes | Full cross-browser suite and WebKit unavailable |

## Existing-test gaps and next verification

1. Mobile tests only assert that containers are visible; they pass while controls are clipped. Assert control bounds and task completion at each target size, including actual browser zoom.
2. Four browser tests import development source modules and cannot validate the production bundle. Prepare fixtures through file uploads or production-safe test setup, then assert visible results and downloaded contents.
3. Add focused regression coverage for keyboard preset activation, input accessible names, selected-tab semantics, unsupported WebGL, and retained-design identification after failed replacement.
4. Extend export coverage beyond suggested filenames: latest edit reflected in CSV/JSON and fabrication snapshot, cancel while generating, retry after worker failure, repeated downloads, and meaningful completion feedback.
5. Complete manual screen-reader, physical touch, native 200% zoom, numeric-boundary, and scene-edit checks before declaring accessibility or device coverage complete.

## Evidence and reproducibility

Screenshots, sample non-fabrication downloads, and raw observations are in [ui-ux-audit-assets](ui-ux-audit-assets/). The audit harnesses are retained there; they use the repository's existing Playwright dependency and require no package changes. From `web/`, build and serve with `npm run build` and `npm run preview -- --host 127.0.0.1 --port 4174`, then run `node ../docs/ui-ux-audit-assets/audit-ui.cjs` and `node ../docs/ui-ux-audit-assets/audit-extra.cjs`. Set `PLAYWRIGHT_BROWSERS_PATH` to the installed cache if required. The scripts overwrite their own evidence files and use browser automation only for the audited local app. The large PNG is generated as synthetic test input; WebGL failure is explicitly injected. No app-internal API is used by these harnesses.

Observation caveats: the first harness samples tab visibility at the workbench level rather than asserting every panel. Source and screenshots support the manual review. `dialogClosed: false` was sampled immediately after Escape before asynchronous close cleanup; the subsequent explicit-close check confirms focus restoration. It is not reported as a modal-close failure.

This is an expert review without recruited users, full assistive-technology testing, or WCAG certification. Numerical optics, fabrication engine validation, hardware qualification, and redesign implementation remain outside scope. Unverified items above are coverage limitations, not passing results.


## Implementation follow-up - 2 November 2026

UX-01-10 have implementation changes in `web/`. The original findings and evidence above describe the pre-remediation baseline and are preserved.

| Finding | Change | Regression evidence |
|---|---|---|
| UX-01 | Stacked layout below 1100 px; single control column below 1400 px; wrapping toolbars/tabs/actions; visible scrollbars | `audit_regressions.spec.ts`: bounds and editing/navigation/download tasks at all five audited sizes |
| UX-02 | Native preset buttons, visible focus, heading focus on navigation | Enter and Space activation, all four presets |
| UX-03 | Unique range/number IDs, parameter/unit names, optional shared help associations, labeled profile select, redundant hidden inputs detached | Named-control browser assertions and keyboard editing |
| UX-04 | Renderer failures isolated; persistent inspection and exports; retry for flat preview; unavailable capture explanation | Injected denied contexts, JSON download while denied, successful preview retry |
| UX-05 | Candidate import worker with atomic commit; preserved prior worker/metadata; named errors and recovery actions; export gating until acknowledgement | Failed first/replacement imports, repeated filename, valid recovery, unit tests for stale responses and retained-worker editing |
| UX-06 | Shared ingestion dialog requires a profile before image decoding; provenance and photograph/lossy-image guidance | Initially disabled Import, explicit selection, Cancel, NPZ bypass |
| UX-07 | Shared selection path for row/column inputs, arrows, and click/tap; marker; persistent textual values and polite announcements | Keyboard selection with row/column updates; existing hover behavior retained |
| UX-08 | Muted token raised from #64748b to #a0aec0; visible focus treatment | Token contrast exceeds 4.5:1 against raised surface; comprehensive rendered-state contrast review remains outstanding |
| UX-09 | Linked tablist/tab/tabpanel semantics and roving keyboard focus | Selected-state assertions, End and navigation across all views |
| UX-10 | Correct degree text, named dialog/progress, centered contained dialog, explicit generation/completion/failure feedback and worker retry | Nonzero orientation, failure injection/retry, repeated GDS/ZIP, Escape/focus restoration, immediate generation cancellation |

Verification: TypeScript/build checks and 45 unit tests pass. Development and production Chromium browser suites pass with 24 tests, including the million-cell UI upload/export responsiveness check. No browser-side source-module imports or source worker URLs are required. Renderer pixel-readback uses the existing bundled hook. Fabrication ZIP checks restore NPZ angles after a 30-degree edit and compare the bundled GDS with the standalone download; CSV/JSON checks include file content and edited pitch. Stored-angle CSV/JSON semantics remain unchanged.

Fresh screenshots are in [ui-ux-remediation-assets](ui-ux-remediation-assets/); they show the viewport after the editing/export task, so smaller screens are scrolled to scene/export controls. The mobile capture was visually inspected. Original audit assets were not overwritten. Build retains the existing JavaScript chunk-size warning.

Outstanding manual validation: a full screen-reader walkthrough, physical touch hardware/gestures, native browser 200% zoom, comprehensive rendered contrast/focus combinations, first-time-user comprehension, numeric boundary matrix, and the full scene-control combination matrix. The automated cancellation check cancels immediately after requesting generation; extended mid-generation/device-specific stress checks remain useful follow-up. No WCAG certification or new hardware/cross-browser qualification is claimed.
