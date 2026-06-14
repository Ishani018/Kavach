# Kavach Benchmark Runbook

Single source of truth for the benchmark runs behind the paper's §4/§5 numbers.
Covers both the Dell primary config (Gemma 4 26B / RTX 4090) and the laptop
AgentDojo run. Read the "Already completed" section first so nothing gets re-run.

- **Primary config:** Dell Precision 3660 · RTX 4090 · Gemma 4 26B via Ollama ·
  BAAI/bge-base-en-v1.5 (768-d) · hybrid BM25+dense · per-minister thresholds.
- **Server:** `127.0.0.1:8088`, endpoint `POST /hook/parliament`.

---

## ✅ Already completed (committed — DO NOT re-run)

These produced committed artifacts on `main`. They are the headline §4/§5 inputs.
Do not re-run them; cite the artifacts.

| Result | Artifact path | Headline |
|---|---|---|
| InjecAgent (data-harm) | `benchmarks/results_v2/injecagent_dell_dh/` | loose recall 0.90, strict 0.633 |
| InjecAgent (data-stealing) | `benchmarks/results_v2/injecagent_dell_ds/` | loose recall 0.875, strict 0.438, DS hard-block FPR 0% |
| Latency (GPU steady-state) | `benchmarks/results_v2/latency/benign_summary.json` | p50 ~78 ms / p95 ~82 ms |
| §5 vote dump | `minister_runs.jsonl` (2108 actions) | feeds `kavach_eval/make_section5.py` |

Aggregate (per distinct case): loose recall 0.887, strict 0.532, hard-block FPR
19%, block-or-escalate FPR 38%. (See README §11 and `AUDIT_VERIFICATION.md`.)

---

## ⏳ Still pending (actionable)

### PENDING 1 — AgentDojo + KavachDefense  ← main remaining task
Not yet committed (no `benchmarks/results_v2/agentdojo_*`). Run with the
hardened programmatic driver (the AgentDojo CLI's `--defense` enum cannot load
KavachDefense). For the laptop run on Gemma 4 26B, use the standalone laptop
runbook Ishani provides; the core commands:

```bash
# 0. one server + MANDATORY real readiness check (NOT just /health)
pkill -f "uvicorn parliament"
./kavach_boot.sh --skip-patch
curl -s -X POST http://127.0.0.1:8088/hook/parliament \
  -H "Content-Type: application/json" \
  -d '{"text":"tool:read_file args:{\"path\":\"x.txt\"}","session_id":"preflight","context":{}}'
# MUST return a verdict JSON. If "Internal Server Error" → fix before running
# (ensure ONE server; if it still 500s: rm -rf parliament/.chroma_kavach &&
#  python corpus_loader.py --rebuild, then restart).

# 1. run (driver does defended + baseline; writes agentdojo_summary.json)
export LOCAL_LLM_PORT=11434
export KAVACH_URL=http://127.0.0.1:8088
python benchmarks/run_agentdojo_kavach.py \
  --suite workspace --model-id gemma4:26b \
  --attack important_instructions \
  --out benchmarks/results_v2/agentdojo_gemma_laptop \
  2>&1 | tee benchmarks/results_v2/agentdojo_gemma_laptop/workspace.log
```
🔴 Before trusting numbers, check the **FAIL-OPEN AUDIT** banner and
`run_fully_defended: true` in `agentdojo_summary.json`. If `false`, some actions
were unscreened — fix the parliament and re-run. Targets: ASR < 5% (vs ~17.6%
baseline), benign utility > 40%. Label the output honestly (`_gemma_laptop`, not
`_dell`).

### PENDING 2 — OpenClaw-native benchmark
`native_results.json` does not exist; §4's native-format FPR is still `\TBD`.
Run the native benchmark (clean tool-call register) and commit
`benchmarks/results_v2/native_results.json`, then fill the §4 `\TBD`.

### PENDING 3 — Ledger tamper-evidence artifact
The `/ledger/verify` output is referenced in the paper appendix but not captured.
With a populated ledger and one server up:
```bash
curl -s http://127.0.0.1:8088/ledger/verify | python3 -m json.tool
# expect {"intact": true, "entries_checked": N, "head_hash": "..."}
```
Save the JSON/screenshot as the tamper-evidence artifact.

### PENDING 4 — Re-validate the CHANNEL pattern tightening (HYPOTHESIS)
Four over-broad CHANNEL patterns (CHAN-010/011/042/057) were rewritten to key on
*exfil intent* rather than the bare transport (git/gist/SMS/email) — branch
`channel-pattern-tighten`, commit `5050c18`. A local embedding-margin check
supports the direction, but the FPR improvement is **unmeasured**. On the next
Dell InjecAgent run, verify TWO things:
1. **Benign hard-blocks drop.** These 4 patterns caused all 120 of CHANNEL's
   benign hard-blocks pre-change (30 each); expect markedly fewer, and confirm
   the aggregate hard-block FPR moves **below the current 19%**.
2. **CHAN-011 / CHAN-042 still match their real exfil attacks** (34 and 17
   respectively at escalate level pre-change) — i.e. the tightening did not kill
   attack-level detection. CHAN-010/057 caught zero attacks, so no check needed.

Until this re-run confirms both: the paper's reported FPR stays **19% hard-block**
as-is. Do NOT update any reported FPR based on the local embedding check alone.

### ⚠️ Step-3 staged trajectory live test — NEEDS ISHANI'S DECISION (do not blind-run)
The original runbook had a staged 5-step attack to show `traj_risk` climbing to
a hard-block. **The trajectory ceiling was since redesigned** (scale-invariant
baseline-relative accumulation — see `TRAJECTORY_CEILING_ANALYSIS.md`), and the
old fixed-0.50-ceiling demo may no longer demonstrate the intended behavior
(benign Dell sessions scored ~0.62 under the old absolute signal). **Do NOT run
the old staged-attack demo as-is** — its expected outcome is undefined under the
new accumulation, and combined-risk re-validation is still pending. Ishani
decides whether/how to re-stage this before it runs.

---

## After the pending runs — record + commit

1. Set git identity first (a prior run committed under the wrong account):
   ```bash
   git config user.name "Parv Parmar"
   git config user.email "parvparmar23@gmail.com"
   ```
2. Fill `benchmarks/results_v2/PARV_RESULTS.md` (every field; N/A if not run).
3. Commit raw outputs (`agentdojo_*/`, `native_results.json`, ledger artifact)
   and push to a branch (main is PR-protected).

---

## Red Team Evasion v0

- **Paraphraser**: templated (no LLM)
- **Scale**: 1200 seeds × 15 paraphrases
- **Evaluated**: 5925
- **Ambiguous**: 1479
- **Evasion Rate**: 0.0% across all ministers/levels/stages
- **BM25-gate evasions**: 0
- **Note**: Laptop-measured — Dell is canonical, numbers may shift. Qwen upgrade pending.

---

## Reference (all in docs/internal/)
- §4→artifact map: `GPU_RUNBOOK_ADDENDUM.md`
- Audit verdicts: `AUDIT_VERIFICATION.md`
- Trajectory redesign: `TRAJECTORY_CEILING_ANALYSIS.md`
