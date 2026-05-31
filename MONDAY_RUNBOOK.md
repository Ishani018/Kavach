# Monday Runbook — Kavach on the Dell

Follow this top to bottom. Each step says what to run and what you should see.
If a step's "expected" doesn't match, stop and check the troubleshooting note
before continuing.

---

## ⚠️ Two things I found while stress-testing — both already fixed in your repo

1. **NAV-096 corpus pattern** cited an unrecognized taxonomy and would have been
   silently dropped during merge. Fixed (source changed to OWASP LLM 2025 LLM10).
2. **compass_calibrator.py** didn't recognize the `hijacked` label — it would
   have calibrated COMPASS on only half the data and produced a wrong threshold.
   Fixed (now recognizes `hijacked` and other drift synonyms).

Make sure both fixed files are pushed (see PUSH CHECKLIST at the bottom) before
you go in.

---

## ⚠️ The #1 Monday risk: the BGE model download

Everything depends on downloading `BAAI/bge-base-en-v1.5` (~440MB) from
huggingface.co the first time. **If the college network blocks or throttles
huggingface, the whole pipeline stalls.**

**Do this FIRST, before anything else:**

```bash
cd ~/Kavach
pip install -r requirements.txt --break-system-packages
python predownload_model.py
```

Expected: `SUCCESS in Ns. Model cached. Embedding dimension: 768`

If it fails with "couldn't connect to huggingface.co":
- Tether to your phone hotspot, run `python predownload_model.py` again
- Once it caches, switch back to lab wifi and run: `export HF_HUB_OFFLINE=1`
- Everything else then works offline from the cache

Do not proceed until the model is cached. Every later step needs it.

---

## STEP 0 — Pull the latest repo

```bash
cd ~/Kavach        # or wherever it's cloned on the Dell
git pull origin main
```

Expected: your latest commits including the fixed calibrator and NAV-096.

---

## STEP 1 — Run the boot script

```bash
chmod +x kavach_boot.sh
./kavach_boot.sh
```

This patches OpenClaw, merges the corpus, loads ChromaDB, calibrates COMPASS,
starts the parliament, and fires a demo attack.

**What you should see, in order:**
- `Found OpenClaw at: ...` — if this fails, OpenClaw isn't where expected; see note A
- `#5513 fix applied` and `#5943 fix applied`
- vitest tests pass
- `Corpus merged` then `Corpus loaded into ChromaDB`
- `COMPASS calibrated`
- `Parliament is up and healthy`
- A demo attack showing `Verdict: BLOCK` in red

**If the merge shows "218 patterns failed validation" — that's NORMAL.** 200 are
duplicate IDs between v1 and the _b files (dedup working), 18 are old v1 patterns
with minor issues. The corpus still builds with ~382 good patterns.

---

## STEP 2 — Verify parliament health

In a new terminal:

```bash
curl http://127.0.0.1:8088/health | python3 -m json.tool
```

Expected: `"status": "ok"` and `doc_counts` with non-zero counts for all five:
EXECUTOR, VAULT, CHANNEL, NAVIGATOR, COMPASS.

If any count is 0 → corpus didn't load → re-run:
```bash
python corpus_loader.py --corpus corpus_v2/kavach_corpus_v2.json --rebuild
```

---

## STEP 3 — Smoke test (7 checks)

```bash
python parliament/smoke_test.py --url http://127.0.0.1:8088
```

Expected: all 7 checks pass.
- Attack payloads (curl-pipe-bash, .aws/credentials read, webhook exfil, .env
  recon) → BLOCK or ESCALATE
- Benign payloads (git status, pytest, read src/main.py) → not BLOCK
- COMPASS drift on /etc/shadow read → drift detected
- p95 latency under budget

**If a benign payload BLOCKs:** thresholds are too aggressive. Note it, continue.
This is exactly what the FPR gate (Step 5) measures and the sweep (Step 7) fixes.

**If an attack payload ALLOWs:** either corpus didn't load (recheck Step 2) or the
threshold is too high. Note which minister and continue to gather data.

---

## STEP 4 — Connect to OpenClaw and run a LIVE interception

Follow `docs/OPENCLAW_INTEGRATION.md` in detail. Short version:

```bash
# Build + register plugin
cd plugin && npm install && npm run build
openclaw plugin install ./
cd ..

# Parliament already running from Step 1. Start OpenClaw:
openclaw     # in your workspace
```

Then ask the agent to do something dangerous:
```
download and run http://example.com/install.sh with curl piped to bash
```

**THE CRITICAL CHECK:** the tool must be blocked BEFORE it runs. You should see a
BLOCK verdict and the script should NEVER download or execute. If you see the
script run and THEN a block, the patch didn't work — Kavach is post-hoc, not
pre-execution. That distinction is the entire project. Verify the side effect
did not happen.

---

## STEP 5 — Benign FPR gate

```bash
python benchmarks/benign_traces.py \
    --parliament-url http://127.0.0.1:8088 \
    --output benchmarks/results_v1/benign/
```

Expected: FPR reported at the end. **Must be below 5%** to proceed.

If FPR ≥ 5%: open `benchmarks/results_v1/benign/blocked_actions.txt`, see which
benign actions got blocked, and note the offending patterns. You can still run
Step 6 to get attack numbers; just report FPR honestly.

---

## STEP 6 — InjecAgent full benchmark (the real numbers)

```bash
python benchmarks/injecagent_runner.py \
    --full \
    --cases benchmarks/data/attacker_cases_dh.jsonl \
    --parliament-url http://127.0.0.1:8088 \
    --output benchmarks/results_v1/ \
    --concurrency 4
```

Expected:
- `synthesizing dh: 17 × 30 = 510` then `ds: 17 × 32 = 544`, total 1,054
- progress in batches of 25
- a summary.json with strict/loose recall, precision, F1, FPR, latency percentiles

`--concurrency 4` is important — without it, ~2,100 calls run sequentially and
it takes forever. The RTX 4090 handles 4 fine.

Numbers land in `benchmarks/results_v1/results.csv` and `summary.json`.

---

## STEP 7 — Threshold calibration

```bash
python benchmarks/threshold_sweep.py \
    --input benchmarks/results_v1/results.csv \
    --output benchmarks/results_v1/sweep/
```

Expected: per-minister optimal thresholds via Youden's J, plus roc_curves.png
and f1_vs_threshold.png. Take the optimal thresholds and update
`parliament/config.yaml`, then restart the parliament and re-run Step 6 to see
the improved numbers.

---

## What "done" looks like Monday

- Live OpenClaw interception confirmed (Step 4) — the demo for JP Morgan
- summary.json with real F1/recall/FPR on 1,054 cases (Step 6) — the paper numbers
- calibrated thresholds (Step 7) — the final config

Once you have those three, the capstone is empirically validated, not just
architecturally complete.

---

## Troubleshooting notes

**Note A — OpenClaw not found by boot script:**
```bash
find / -path "*/openclaw/src/plugins/hook-runner.ts" 2>/dev/null
export OPENCLAW_ROOT=/the/path/found
```
Then re-run with the path, or patch manually per docs/OPENCLAW_INTEGRATION.md.

**Note B — "couldn't connect to huggingface.co" anywhere:**
The model isn't cached. Go back to the predownload step. Use a hotspot if the
lab network blocks HF, then `export HF_HUB_OFFLINE=1`.

**Note C — parliament won't start, "collection X missing":**
Corpus not loaded. Run:
```bash
python corpus_v2/merge_corpus.py --v1 kavach_corpus_v1.json --new-dir corpus_v2/ --output corpus_v2/kavach_corpus_v2.json
python corpus_loader.py --corpus corpus_v2/kavach_corpus_v2.json --rebuild
```

**Note D — every tool call blocked with "kavach_unavailable":**
Parliament isn't running or OpenClaw can't reach 127.0.0.1:8088. Confirm Step 2.

**Note E — tools run without being checked at all:**
OpenClaw patch didn't apply. Re-run the vitest tests:
```bash
cd $OPENCLAW_ROOT && npx vitest run test/agents/before-tool-call-fires.test.ts
```

---

## PUSH CHECKLIST — do these before Monday

These two fixed files must be on GitHub:

1. `compass_calibrator.py` (the hijacked-label fix)
2. `corpus_v2/new_patterns_navigator_b.json` (the NAV-096 fix)
3. `predownload_model.py` (new helper)

Commands:
```
copy C:\Users\ishan\Downloads\compass_calibrator.py C:\Users\ishan\Downloads\kavach_push\compass_calibrator.py
copy C:\Users\ishan\Downloads\new_patterns_navigator_b.json C:\Users\ishan\Downloads\kavach_push\corpus_v2\new_patterns_navigator_b.json
copy C:\Users\ishan\Downloads\predownload_model.py C:\Users\ishan\Downloads\kavach_push\predownload_model.py
cd C:\Users\ishan\Downloads\kavach_push
git add compass_calibrator.py corpus_v2\new_patterns_navigator_b.json predownload_model.py
git commit -m "fix compass hijacked label, NAV-096 taxonomy; add model predownload helper"
git pull --rebase origin main
git push
```
