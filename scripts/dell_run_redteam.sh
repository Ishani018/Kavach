#!/usr/bin/env bash
# =============================================================================
# dell_run_redteam.sh — red-team LLM evasion run on the Dell (TERTIARY)
# =============================================================================
# Produces the evasion report that section 4 (corpus_agent) consumes.
# Pass --resume to this script to resume from the newest checkpoint if it died.
#   usage:  bash scripts/dell_run_redteam.sh [--resume]
# =============================================================================
set -euo pipefail

KAVACH_URL="http://127.0.0.1:8088"
MODEL="gemma4:26b"
OUTDIR="kavach_eval/evasion_results/redteam_gemma_dell_n250"

# Forward --resume if the caller passed it.
RESUME_FLAG=""
if [ "${1:-}" = "--resume" ]; then
  RESUME_FLAG="--resume"
fi

echo "────────────────────────────────────────────────────────────"
echo "  Dell red-team LLM run — ${MODEL} — 250 seeds — threat-intel RAG"
echo "────────────────────────────────────────────────────────────"

# ── Preflight: ollama has gemma4:26b ─────────────────────────────────────────
echo "[preflight] checking ollama for ${MODEL} ..."
if ! ollama list 2>/dev/null | grep -q "${MODEL}"; then
  echo "[FATAL] ${MODEL} not found in ollama. Pull it:  ollama pull ${MODEL}"
  exit 1
fi
echo "[preflight] ${MODEL} present ✅"

# ── Preflight: parliament up (the scorer uses it) ────────────────────────────
echo "[preflight] checking parliament health ..."
if [ -z "$(curl -s "${KAVACH_URL}/health" || true)" ]; then
  echo "[FATAL] parliament not reachable at ${KAVACH_URL}."
  echo "        Start it:  python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088"
  exit 1
fi
echo "[preflight] parliament OK ✅"

# ── Checkpoint location (so Parv knows where to resume from) ─────────────────
echo "[info] checkpoints + reports land in: ${OUTDIR}/"
echo "[info] if this dies mid-run, relaunch with:  bash scripts/dell_run_redteam.sh --resume"
if [ -n "${RESUME_FLAG}" ]; then
  echo "[info] RESUMING from the newest checkpoint in ${OUTDIR}/"
fi

# ── The run ──────────────────────────────────────────────────────────────────
echo "[run] starting red-team evasion (250 seeds, LLM + threat-intel) ..."
python kavach_eval/redteam_evasion_v0.py \
  --use-llm --model "${MODEL}" \
  --max-seeds 250 \
  --use-threat-intel \
  --out-dir "${OUTDIR}" \
  ${RESUME_FLAG}

# ── Summary — print the evasion report filename (section 4 needs it) ─────────
REPORT="$(ls -t "${OUTDIR}"/evasion_report_*.json 2>/dev/null | head -1 || true)"
echo "────────────────────────────────────────────────────────────"
echo "  DONE."
if [ -n "${REPORT}" ]; then
  echo "  Evasion report:  ${REPORT}"
  echo "  → Section 4 (corpus_agent) command:"
  echo "      python kavach_eval/corpus_agent/agent.py \\"
  echo "        --evasion-report ${REPORT} \\"
  echo "        --minister CHANNEL --model ${MODEL} --measure-closure"
else
  echo "  [warn] no evasion_report_*.json found in ${OUTDIR} — check the run output."
fi
echo ""
echo "  Commit results to parv-results (NOT main/parv):"
echo "    git checkout parv-results"
echo "    git add kavach_eval/evasion_results/"
echo "    git commit -m 'data: Dell gemma4:26b red-team evasion results'"
echo "    git push origin parv-results"
echo "────────────────────────────────────────────────────────────"
