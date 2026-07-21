# End-to-end live-HTTP latency — Apple M1 Max, CPU-only

Measurement artifacts for the paper's §4.8 latency claim. **Measurement and
reporting only** — no detection logic, rules, thresholds, or corpus content
were changed. Numbers below are raw; no `.tex` was edited.

## Setup

- **Hardware:** Apple M1 Max, 32 GB, macOS. Native arm64 Python 3.9.6 (no Rosetta).
- **Embedding:** `BAAI/bge-base-en-v1.5` on **CPU**. `parliament/server.py`
  loads `SentenceTransformer` with no `device=` argument, which auto-selects
  MPS on Apple Silicon; `serve_cpu.py` disables MPS *before* the server module
  imports so the identical code path runs on CPU (server log confirms
  `device_name: cpu`). This makes the paper's "CPU-only" framing literally true.
- **Path:** live `POST /hook/parliament`, sequential (no concurrency),
  client-side `time.perf_counter` around each HTTP call.
- **Warm-up:** 20 untimed calls (excludes BGE load / lazy init).
- **Single server:** exactly one listener verified via `lsof -i :8088` before
  and during timing (the duplicate-process bug that corrupted an earlier
  measurement, per §4.1, was specifically guarded against).
- **Sample:** all 55 agent-shaped benign calls + every 5th of the 519-case
  reference corpus by sorted case_id (104) = **159 timed calls**. 0 non-200
  responses, 0 timeouts.

## Phase 1 parity (before trusting any timing)

107-case subset (55 benign + every 10th attack) replayed through the
CPU-pinned live path and compared against the committed reference
(`benchmarks/results_v2/_kavach_pb_*checkpoint.json`, captured earlier this
session on the same machine but MPS-backed): **0 mismatches** — verdict and
fired-minister set 100% identical. The CPU pin did not flip any borderline
threshold case.

## Results — the distribution is BIMODAL

Overall (n=159): **p50 725.5 ms, p95 1428.0 ms, mean 739.1, max 1587.6, min 33.7.**

Reporting a single p50 here would be misleading. There are two disjoint
modes with an empty valley (**0 calls** between 89 ms and 684 ms):

| Mode | What runs | n | p50 | p95 | range |
|---|---|---|---|---|---|
| **Low** — deterministic short-circuit | VAULT/EXECUTOR rule matched, pipeline skips embedding+retrieval | 17 | 45.7 | 85.8 | 33.7–88.9 |
| **High** — embedding path | BGE encode + hybrid retrieval runs (cosine triage, CHANNEL, or ALLOW-after-full) | 142 | 733.0 | 1437.2 | 684.5–1587.6 |

By decision path (`classify()` from existing response fields, no server
instrumentation):

| Path | n | p50 | p95 |
|---|---|---|---|
| cosine (embedding + hybrid retrieval) | 86 | 727.1 | 1438.3 |
| channel (session taint/provenance, embeds) | 29 | 741.2 | 1217.8 |
| deterministic (rule hit) | 26 | 60.7 | 775.2 |
| allow-full (full path, nothing fired) | 18 | 729.5 | 792.0 |

Note the `deterministic` path splits: 17 calls short-circuit (~34–89 ms), but
9 deterministic-rule hits did **not** short-circuit (the pipeline still
embedded, ~700 ms) — which is why its p95 (775) sits in the high mode while
its p50 (61) sits in the low mode. The clean bimodal boundary is
`short_circuited == true` (fast) vs `false` (embedding ran).

## Anomalies

- **0** outliers above 3×p95 (4284 ms).
- **0** non-200 responses, **0** timeouts.
- No first-call effect surviving warm-up (first timed call was in-band).

## ⚠️ Discrepancy vs. the paper's cited 78 ms — READ BEFORE DRAFTING §4.8

The paper repeatedly cites a **78 ms** latency budget/measurement. That figure
is the **Dell, GPU-accelerated** embedding number. **CPU-only on this M1 Max,
the embedding path is ~700 ms p50 — roughly 9× the cited figure.** Only the
deterministic short-circuit path (~34–89 ms) is anywhere near 78 ms, and it
only applies to the fraction of calls a VAULT/EXECUTOR rule catches outright.

This is not a regression or a bug — it is the expected cost of running BGE on
CPU instead of GPU. But it means **the 78 ms number cannot be presented as this
machine's measurement**, and a §4.8 that cites 78 ms alongside "CPU-only,
M1 Max" hardware would be internally inconsistent. Decision on how to frame
this (report both hardware points; report the deterministic-path fast number
separately from the embedding-path number; or keep 78 ms explicitly labeled as
the Dell/GPU figure) is left to the authors — no `.tex` was touched.

## Files

- `serve_cpu.py` — CPU-pinned server launcher (measurement-only; does not alter server code).
- `parity_check.py` — Phase 1 verdict-parity harness.
- `measure_latency.py` — Phase 2 timed replay + path classifier.
- `latency_percall.csv` — raw per-call data (case_id, pop, verdict, path, latency_ms, status, short_circuited, server_latency_ms).
- `latency_summary.json` — computed summary (this README's numbers).
