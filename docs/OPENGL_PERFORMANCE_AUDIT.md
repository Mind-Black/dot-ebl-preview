# OpenGL GUI performance audit

Audited 2026-09-20 against the current working tree, including its uncommitted GUI implementation. Application sources were not changed.

The highest-priority improvement is frame delivery: the GUI can discard almost every completed frame during continuous input. On this machine, spectral shading is substantially cheaper than the readback and Tk image pipeline. Optimize scheduling and presentation before changing the optical model.

## Measured baseline

Hardware/runtime: NVIDIA GeForce RTX 3060 Ti, OpenGL 3.3.0 NVIDIA 616.64, Python 3.14.7, PyOpenGL 3.1.10, GLFW 2.10.2.

The real input was `_INPUT/sekmes_pinigelis_01.png`, decoded as Holtida legacy HLS at 20 micrometres pitch: 1075 × 1075 cells, 60.78% active. Synthetic cases used 1000 nm period, zero cell angle, 20 micrometres pitch, and all cells active. Scenes used the GUI's default source and camera with orientation swept from 1 through 9 degrees.

| Design / render target | GPU draw median | Blocking readback call median |
| --- | ---: | ---: |
| Sample / 384 × 384 | 0.137 ms | 0.389 ms |
| Sample / 1075 × 1075 | 0.750 ms | 2.374 ms |
| Synthetic 1024² / 384² | 0.157 ms | 0.628 ms |
| Synthetic 1024² / 1024² | 0.938 ms | 2.507 ms |
| Synthetic 2048² / 384² | 0.163 ms | 0.705 ms |
| Synthetic 2048² / 2048² | 3.807 ms | 8.762 ms |

Nine measurements per target, after initial fast and settled frames. GPU time uses `GL_TIME_ELAPSED` around the existing draw. Readback uses CPU wall time around the existing `glReadPixels`; it includes waiting for outstanding GPU work. **These columns overlap and must not be added or interpreted as isolated transfer time.** Timer results are fetched after readback. No application shader was modified.

An isolated run of the actual `_draw_panel` method, with a withdrawn Tk root and a simulated 600 × 400 canvas, produced these medians (22 samples after three warmups). All outputs were 384 × 384:

| Source image | Resize + PhotoImage + canvas update |
| --- | ---: |
| 384² | 3.19 ms |
| 1075² | 7.88 ms |
| 2048² | 14.61 ms |
| 4096² | 40.14 ms |

These timings include Python/Tk image preparation and canvas commands, not final visible-window painting. The 4096² case measures presentation only, not spectral rendering. There is additional NumPy/Pillow conversion work between readback and the GUI. End-to-end interactive frame rate cannot be calculated by summing these separate experiments.

## Findings, in recommended order

### 1. High priority: completed frames are rejected during continuous interaction

Locations: `src/dot_ebl_preview/gui.py:381-384`; producer checks at `src/dot_ebl_preview/preview/realtime.py:273-285`.

The GUI only accepts a frame if its serial equals the *currently requested* scene. A correct completed frame becomes ineligible as soon as another mouse/slider update arrives before the next 16 ms GUI poll. The producer also requires a current serial before reading back a fast frame. This can leave an old image visible despite many newly completed frames.

A controlled harness used the real hidden-context viewer and the real `_poll_viewer_events` acceptance logic, with scene updates at 60/120 Hz, event polls every 16 ms, and an initial 4 ms polling offset. Each run lasted 1.2 seconds. Presentation was replaced with a timestamp sink to isolate acceptance:

| Input | Acceptance rule | Published / displayed | Largest display gap* |
| --- | --- | ---: | ---: |
| 60 Hz | Current implementation | 70 / 25 | 244 ms |
| 60 Hz | Latest completed frame experiment | 67 / 67 | 36 ms |
| 120 Hz | Current implementation | 69 / 11 | 527 ms |
| 120 Hz | Latest completed frame experiment | 52 / 52 | 48 ms |

*Includes gaps at the start and end of the measurement window. These are controlled scheduling experiments, not measured physical mouse gestures or full-window FPS. Counts vary with scheduling; an earlier run with different phases also reproduced long gaps.

**Recommendation:** display the newest completed frame for the current viewer/design generation, even if newer input is pending. Keep serials monotonic relative to the last *displayed* frame, and allow a full-quality upgrade at the same serial. Continue coalescing pending scene requests to the newest scene. Avoid rejecting every completed fast frame when rendering takes longer than the input interval. Keep capture completion and errors reliable and separate from replaceable live frames.

Use a one-frame mailbox for live images instead of an unbounded queue, so a blocked UI cannot accumulate stale image allocations. The existing consumer already coalesces frames, but only after allocations and queueing have occurred. Validate continuous input, design replacement, same-serial quality upgrades, and explicit captures when implementing this change.

### 2. High impact for larger designs: separate pane presentation from full-resolution capture

Locations: `preview/realtime.py:152-154,179-185,278-297`; `gui.py:669-677`.

After 300 ms without a scene change, the viewer always shades and reads back the entire design. Tk then reduces that image to the panel size. Every such transfer and CPU resize scales with design area, even when the pane is only a few hundred pixels across. The 1075² sample evaluates 7.84 times as many output pixels as a 384² target; 4096² would evaluate about 114 times as many.

**Recommendation:** distinguish interaction resolution, settled pane resolution, and full-resolution export. Pass actual pane dimensions to the renderer and use GPU timing to choose an interaction size that meets a frame budget. Allocate the full-resolution target lazily when needed.

If the existing full-resolution settled-image quality must be preserved, keep the full render but downsample its *rendered color image* on the GPU before readback, with suitable minification filtering. This avoids large CPU transfers/resizes while retaining a separate full-resolution capture. Directly shading only pane pixels is faster but changes sampling of fine design detail; treat that as a quality policy, not an exact substitute. Do not average period/angle parameter textures as if they were colors.

Recheck the latest scene before starting expensive settled work. A monolithic full render/readback already in progress prevents the same worker from producing the next fast frame; progressive tiles with revision checks are a later option for very large designs.

### 3. Medium priority: synchronous GPU-to-CPU presentation

Locations: `preview/realtime.py:222-226`; `gui.py:519,658-678`.

The default GUI creates `RealtimeViewer(..., visible=False)`. Its visible GLFW display pass is therefore not the GUI's presentation path. Every live image crosses GPU → client RGBA → contiguous RGB array → PIL image → resized image → Tk PhotoImage. A fullscreen triangle or faster draw submission does not remove these costs.

**Recommendation:** first reduce readback dimensions. Then evaluate a two- or three-slot pixel-pack-buffer ring and fence-based completion. Enqueue readback, poll completion without blocking, and consume an older completed buffer. Do not immediately map the buffer just written; that would recreate the synchronization stall. Associate each buffer with scene serial, design generation, size, and quality. Flush submitted work appropriately in this hidden context, which does not swap buffers. Bound outstanding work and prioritize freshness over building a frame backlog.

PBOs can overlap transfer/waiting; they do not make the shader cheaper, eliminate Tk copies, or guarantee lower latency. On this GPU, the fast readback is already below 1 ms, so benchmark the benefit before adding complexity. See the Khronos [pixel buffer object documentation](https://wikis.khronos.org/opengl/Pixel_Buffer_Object) and [synchronization documentation](https://wikis.khronos.org/opengl/Synchronization).

Longer term, a native OpenGL-backed preview pane can present the color texture directly and restrict CPU readback to PNG export. This is a larger GUI integration change.

### 4. Medium priority: reduce Tk allocation and polling overhead

Locations: `gui.py:368,653-678`; `preview/realtime.py:310-312`.

Every accepted frame deletes the canvas items, allocates a resized image and PhotoImage, and creates a new canvas image item. The GUI schedules its next poll 16 ms *after* processing, while the renderer has an independent 60 Hz loop. The 3.19 ms measured fast presentation alone makes a nominal 16 ms poll cycle approximately 19 ms, before other UI work.

**Recommendation:** retain the canvas image item and update its image reference. Cache unchanged captions and dimensions, skip resizing when sizes match, and benchmark reusing PhotoImage storage rather than assuming it is faster. Prefer bounded notification/deadline scheduling on the Tk thread, allowing input processing between updates. Do not invoke Tk widgets from the GL worker.

The hidden worker continues waking at about 60 Hz when idle, although spectral rendering is already dirty-driven. A condition/event with a settle deadline can reduce idle CPU usage. This is primarily an efficiency improvement, not a shader speedup.

### 5. Lower priority for live interaction: reuse resources in manual rendering

Locations: `preview/gl_renderer.py:185-240,269-281`; `gui.py:559-598`.

The live path already reuses its context, compiled programs, static textures, and FBOs. The non-live `render_opengl_preview` path initializes GLFW, creates a context, compiles shaders, uploads the design, allocates targets, and tears everything down for each call. Three sample manual renders took 61.14, 43.42, and 47.94 ms, versus a 0.75 ms live full-resolution GPU draw.

**Recommendation:** share a reusable renderer implementation owned by a dedicated GL thread for manual refreshes and batch captures. Retain shader/uniform locations and upload design data only when it changes. This benefits live-disabled refresh and repeated standalone renders; it will not fix the default live GUI's frame rejection.

### 6. Profile before changing the spectral shader

Location: `preview/gl_renderer.py:137-160`.

Each active output pixel evaluates 77 wavelengths and up to two propagating orders per wavelength, including square roots, `acos`, and exponentials. This is the principal shader workload, but measured GPU time is currently small on the RTX 3060 Ti.

Potential experiments for slower GPUs or larger outputs:

- Precompute wavelength/pitch constants, reciprocal periods, and static grating directions; apply global orientation with one uniform rotation. Evaluate added texture bandwidth against saved arithmetic. The driver may already hoist some invariants.
- Bound evanescent or negligible contributions before expensive angular functions, with an explicit error bound against the full result.
- Explore a small-angle Gaussian approximation using dot products only, or a reduced spectral quadrature during interaction. These change numerical behavior and require comparisons over camera/source positions, apertures, periods, orientations, and weak/narrow peaks. Restore the reference-quality path for captures.
- Cache uniform locations and omit display-program compilation in hidden mode as small housekeeping improvements. They are not the first performance targets here.

Do not start with a compute-shader rewrite, extra geometry batching, or reduced parameter-texture precision. The live implementation already uses one fullscreen triangle and static GPU data; no repeated per-cell Python draw/upload loop was found. Reduced precision can change diffraction colors.

## Validation and reproducibility

Existing GUI/OpenGL tests: `9 passed` via `.venv\Scripts\python.exe -m pytest tests\test_gl_preview.py tests\test_gui_logic.py -q`. This includes the existing CPU/GPU comparison, but does not establish correctness of any proposed shader approximation or new scheduling implementation.

Local scripts and raw results are in the ignored `_OUTPUT/opengl_audit/` directory:

- `benchmark.py` / `baseline.json`: instrumented existing renderer; run from repository root.
- `presentation.py` / `presentation.json`: actual Tk preparation method and controlled frame-acceptance comparison.

These scripts are audit experiments, not production changes. Measurements reflect one GPU, sample interpretation, and short run; repeat on an integrated GPU and representative large designs before assigning portable FPS targets. For ongoing profiling, add separate GPU timer queries and CPU timestamps for draw, readback, conversion, queue age, resize, and presentation; retrieve GPU query results asynchronously, as described in the Khronos [query object documentation](https://wikis.khronos.org/opengl/Query_Object).

Recommended implementation sequence: fix completed-frame acceptance → bound/coalesce live frame delivery → reduce pane transfer/resize work → benchmark asynchronous readback → optimize the shader only if GPU timings justify it.
