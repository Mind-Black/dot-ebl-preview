# Response to independent Critic

The initial plan was reviewed by a separate Critic subagent after it was written and after the user's single-pixel-line requirement was incorporated. [CRITIC_REVIEW.md](CRITIC_REVIEW.md) preserves the independent review. Its verdict was a feasible architecture with three required amendments and two smaller refinements.

The same independent Critic completed a second pass on 2026-09-20 and confirmed R1–R5 are closed at the planning level, with no remaining contradiction within that review scope. Its dated second-pass verdict is appended to the original review.

All five findings are incorporated into the revised plan:

| Finding | Resolution in DEVELOPMENT_PLAN.md | Implementation acceptance evidence required |
|---|---|---|
| R1 — Unity appearance/HSV compatibility | Section 2 adds `legacy-unity-hsv`, independent persisted appearance/fallback data, strict thresholds/ties and finite zero-diffraction→fallback behavior. Section 5 no longer forces all zero-XYZ output to display black. F12 coverage updated. | Brightness differences at equal physical parameters, HSV boundaries/ties, fallback threshold and save/reload fixtures. Unity runtime color/sampling settings remain an explicit missing baseline. |
| R2 — Axial filtering may shift finite stripe phase | Section 3 retains directed SREF angles, uses nearest-original branch with defined ties, rejects out-of-range branches, and prohibits modulo-180 normalization/deduplication. | Transformed-path tests including the 20,000/900 nm asymmetric lattice and −90/+90° boundaries. |
| R3 — Deterministic RGB8 quantization | Section 2 requires exact representation by default; explicit quantization uses physical distances, directed angles, lowest-index ties, separate clipping policy and error metrics. Emitted images are decoded and verified; the Design is unchanged. | Tie/custom-palette/out-of-range fixtures, error reports and exact activity preservation. |
| R4 — Local half-grid stripe centers | Section 3 adds even-pitch/odd-period fixtures, including the 903 nm calibration period, and separate spacing/phase versus placement error reporting. | Positive/negative half-nm rounding and snapped line-spacing tests. |
| R5 — Multi-file export consistency | Section 4 stages the entire bundle, validates files, writes hashed completion metadata and publishes the directory/marker only at completion. | Cancellation/failure at every inter-file boundary; incomplete outputs never appear completed. |

The performance estimates remain planning targets. Added appearance data is now included in the memory-accounting requirements. The review did not uncover a reason to expand the initial Raith port beyond zero-width two-endpoint PATHs, SREFs, hierarchy, transforms and serialization utilities.

“Addressed” here means the plan now specifies the behavior and its acceptance gate. It does not mean tests have been implemented or passed. GPU/CPU parity, original application baselines, MATLAB-generated writer fixtures, and NanoSuite single-pixel-line/dose qualification remain implementation work. Neither original project was modified.
