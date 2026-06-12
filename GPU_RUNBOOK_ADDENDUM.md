# GPU Runbook Addendum — Audit Findings Requiring the Dell (RTX 4090)

These audit findings could **not** be verified on the laptop (CPU-only, no Dell
benchmark artifacts committed). Run each on the Dell Precision 3660 and commit
the raw output to `benchmarks/results_v2/` so the number becomes traceable.

Record for every run: exact command, git commit hash, and the output file path.

---

## ⚠ PRE-FLIGHT — do this BEFORE any run below

**Restart the parliament server after pulling.** The server reads
`parliament/config.yaml` **once, at startup** (`_load_config`), and holds the
values in memory — it does **not** re-read the file or the `*_calibration.json`
files at runtime. If a server is already running from a previous session, it is
using the **old** thresholds and a `git pull` will NOT change its behavior.

This matters specifically for the COMPASS drift threshold, which was just
corrected:

- `config.yaml` `compass_drift` is now **0.585** (Youden's-J optimal:
  TPR 0.86 / FPR 0.14). The old value was **0.40**, at which COMPASS barely
  fires (TPR 0.22). A run against a stale server would report near-dead drift
  detection and be **unreproducible** from the committed config.

**Procedure on the Dell:**
```bash
git pull                                   # get config.yaml with compass_drift=0.585
# Kill any parliament already bound to :8088:
pkill -f "uvicorn parliament.server" || true
# Start fresh so the new config is loaded:
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
# Confirm the live value matches the file before running anything:
curl -s http://127.0.0.1:8088/health | python3 -c \
  "import sys,json; print('compass_drift =', json.load(sys.stdin)['thresholds']['compass_drift'])"
# Expected output: compass_drift = 0.585   (NOT 0.40)
```
If `/health` shows `0.40`, the server is stale — kill and restart it.

> General rule: any time you change `config.yaml` or re-run
> `compass_calibrator.py` / `threshold_sweep.py`, copy the new numbers into
> `config.yaml` AND restart the server. The calibration JSONs are not read live.

---

## F-1 — The `p50=826ms / p95=1649ms` latency figure (CRITICAL, UNVERIFIABLE)

**Status:** No committed log anywhere in the repo produces 826ms (`grep -rn 826
benchmarks/` returns nothing). The figure appears in 6+ docs as a Dell RTX 4090
result but has no reproducible source.

**To verify / regenerate on the Dell:**
```bash
# Parliament must be running with BGE on CUDA.
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
# In another shell, drive a latency benchmark and capture the summary:
python benchmarks/benign_traces.py \
  --parliament-url http://127.0.0.1:8088 \
  --output benchmarks/results_v2/latency/
# The summary.json latency_ms.{p50,p95} are the figures to cite.
```
**Expected:** a committed `benchmarks/results_v2/latency/summary.json` whose
`latency_ms.p50` ≈ the cited value. If it is not ~826ms, update all six docs to
the measured number (or `\TBD` until then).

---

## F-2 / D-1 / E-1 — InjecAgent headline numbers (98.4% recall, 2.1% FPR, 88.2% FPR) (CRITICAL, UNVERIFIABLE)

**Status:** `benchmarks/results_v1/benign/` is `.gitkeep`-only; no `results.csv`
committed. `PARV_RESULTS.md` is an empty template. The headline numbers have no
backing data in the repo.

**To regenerate on the Dell (Gemma4 27B primary config):**
```bash
# Full InjecAgent attack set + benign gate, hybrid retrieval, per-minister thresholds
python benchmarks/injecagent_runner.py \
  --parliament-url http://127.0.0.1:8088 \
  --cases <full InjecAgent test_cases.json> \
  --include-benign \
  --output benchmarks/results_v2/injecagent_dell/
# Commit results.csv + summary.json. Cite strict/loose recall + FPR from summary.json.
```
**Expected:** committed `results_v2/injecagent_dell/summary.json`. Replace the
README §11 table and paper §4/§5 `\TBD` slots with these numbers only.

> NOTE: REPRODUCIBILITY.md §Step 6 points `--cases` at
> `/path/to/InjecAgent/data/test_cases.json` — the **full** 1,054-case InjecAgent
> set is NOT in the repo (D-6). Add a fetch/clone step for it to the runbook.

---

## D-2 — Dell primary results vs laptop secondary (MAJOR, UNVERIFIABLE)

The only committed results are small-N laptop (qwen2.5:3b) runs. The Dell primary
(Gemma4 27B) configuration has no committed results. Run the full benchmark suite
(InjecAgent above, AgentDojo below) on the Dell and commit to
`results_v2/<benchmark>_dell/`.

---

## D-4 — AgentDojo run (MAJOR, UNVERIFIABLE)

`benchmarks/agentdojo_runner.py` exists but has never been run; the related-work
table has `[TBD]` for Kavach's AgentDojo ASR.
```bash
python benchmarks/agentdojo_runner.py \
  --parliament-url http://127.0.0.1:8088 \
  --suite workspace \
  --output benchmarks/results_v2/agentdojo_dell/
```
**Expected:** committed ASR + benign-utility numbers to fill the related-work
table and §5.

---

## Summary

| Finding | Needs | Output to commit |
|---|---|---|
| F-1 | Dell latency run | `results_v2/latency/summary.json` |
| F-2 / D-1 / E-1 | Dell InjecAgent run (full set) | `results_v2/injecagent_dell/` |
| D-2 | Dell primary config runs | `results_v2/*_dell/` |
| D-4 | AgentDojo run | `results_v2/agentdojo_dell/` |
| D-6 | InjecAgent full dataset fetch | add fetch step to REPRODUCIBILITY.md |
