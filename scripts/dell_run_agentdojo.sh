#!/usr/bin/env bash
# =============================================================================
# dell_run_agentdojo.sh — AgentDojo slack benchmark on the Dell (gemma4:26b)
# =============================================================================
# PRIMARY run — this produces the paper's AgentDojo number.
# Run from the repo root on the parv branch, after corpus_loader.py --rebuild.
# =============================================================================
set -euo pipefail

KAVACH_URL="http://127.0.0.1:8088"
OUT="benchmarks/results_v2/agentdojo_slack_gemma_dell"
MODEL="gemma4:26b"

export LOCAL_LLM_PORT=11434
export KAVACH_URL
export OPENAI_API_KEY=ollama
export OPENAI_API_BASE=http://localhost:11434/v1
export PYTHONIOENCODING=utf-8

echo "────────────────────────────────────────────────────────────"
echo "  Dell AgentDojo run — slack suite — ${MODEL}"
echo "────────────────────────────────────────────────────────────"

# ── Preflight 1: parliament healthy AND CHAN-101 present (CHANNEL == 303) ────
echo "[preflight] checking parliament health + CHAN-101 ..."
HEALTH="$(curl -s "${KAVACH_URL}/health" || true)"
if [ -z "${HEALTH}" ]; then
  echo "[FATAL] parliament not reachable at ${KAVACH_URL}."
  echo "        Start it:  python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088"
  exit 1
fi
CHAN_COUNT="$(printf '%s' "${HEALTH}" | python -c "import sys,json; print(json.load(sys.stdin).get('doc_counts',{}).get('CHANNEL','?'))" 2>/dev/null || echo '?')"
if [ "${CHAN_COUNT}" != "303" ]; then
  echo "[FATAL] CHANNEL doc_count = ${CHAN_COUNT}, expected 303 (CHAN-101 missing)."
  echo "        The ChromaDB was not rebuilt. Run:  python corpus_loader.py --rebuild"
  echo "        then restart the parliament and re-run this script."
  exit 1
fi
echo "[preflight] parliament OK, CHANNEL=303 (CHAN-101 present) ✅"

# ── Preflight 2: sanity check (model + tool-call probe) ──────────────────────
echo "[preflight] running --sanity (model + tool-call probe) ..."
if ! python benchmarks/run_agentdojo_kavach.py \
        --suite slack --model-id "${MODEL}" \
        --kavach-url "${KAVACH_URL}" --sanity; then
  echo "[FATAL] sanity check failed. Fix the ❌ above before running. Aborting."
  exit 1
fi
echo "[preflight] sanity OK ✅"

# ── Confirm before clearing a previous output dir ────────────────────────────
if [ -d "${OUT}" ]; then
  echo "[warn] output dir already exists: ${OUT}"
  read -r -p "        Clear it and start fresh? [y/N] " ans
  case "${ans}" in
    y|Y) rm -rf "${OUT}"; echo "[warn] cleared ${OUT}";;
    *)   echo "[abort] not clearing — move/rename the dir and re-run."; exit 1;;
  esac
fi

# ── The run ──────────────────────────────────────────────────────────────────
echo "[run] starting AgentDojo (slack, ${MODEL}) — expect ~45-90 min on RTX 4090 ..."
python benchmarks/run_agentdojo_kavach.py \
  --suite slack --model-id "${MODEL}" \
  --kavach-url "${KAVACH_URL}" \
  --out "${OUT}" \
  --abort-threshold 20

# ── Summary ──────────────────────────────────────────────────────────────────
N="$(find "${OUT}" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
echo "────────────────────────────────────────────────────────────"
echo "  DONE. ${N} result files in ${OUT}"
echo "  Check the KAVACH AUDIT line above: it must show real screening"
echo "  (N calls reached, M screened, K BLOCKED) and run_fully_defended: true."
echo ""
echo "  Commit results to parv-results (NOT main/parv):"
echo "    git checkout parv-results"
echo "    git add benchmarks/results_v2/"
echo "    git commit -m 'data: Dell gemma4:26b AgentDojo slack results'"
echo "    git push origin parv-results"
echo "────────────────────────────────────────────────────────────"
