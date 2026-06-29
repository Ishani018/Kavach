#!/usr/bin/env bash
# =============================================================================
# dell_run_injecagent.sh — InjecAgent re-run on the Dell (SECONDARY)
# =============================================================================
# Uses the CANONICAL root-level injecagent_runner.py (696 lines), not the
# benchmarks/ copy. Threshold lives in parliament/config.yaml — not a CLI flag.
# =============================================================================
set -euo pipefail

KAVACH_URL="http://127.0.0.1:8088"
OUT="benchmarks/results_v2/injecagent_gemma_dell/"

echo "────────────────────────────────────────────────────────────"
echo "  Dell InjecAgent run (full benchmark, --include-benign)"
echo "────────────────────────────────────────────────────────────"

# ── Preflight: parliament up ─────────────────────────────────────────────────
echo "[preflight] checking parliament health ..."
HEALTH="$(curl -s "${KAVACH_URL}/health" || true)"
if [ -z "${HEALTH}" ]; then
  echo "[FATAL] parliament not reachable at ${KAVACH_URL}."
  echo "        Start it:  python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088"
  exit 1
fi
echo "[preflight] parliament OK ✅"

# ── The run ──────────────────────────────────────────────────────────────────
# Canonical runner is at the repo ROOT (not benchmarks/). Threshold + hybrid
# retrieval come from parliament/config.yaml — do NOT pass them as flags.
echo "[run] starting InjecAgent (full, with benign FPR pairs) ..."
python injecagent_runner.py \
  --full \
  --parliament-url "${KAVACH_URL}" \
  --output "${OUT}" \
  --include-benign

# ── Summary ──────────────────────────────────────────────────────────────────
N="$(find "${OUT}" -type f 2>/dev/null | wc -l | tr -d ' ')"
echo "────────────────────────────────────────────────────────────"
echo "  DONE. ${N} files in ${OUT}"
echo "  Sanity-check vs committed Dell figures: loose ~0.88, strict ~0.53,"
echo "  DH hard-block FPR ~19%. If wildly off, note it — do NOT re-run."
echo ""
echo "  Commit results to parv-results (NOT main/parv):"
echo "    git checkout parv-results"
echo "    git add benchmarks/results_v2/"
echo "    git commit -m 'data: Dell gemma4:26b InjecAgent results'"
echo "    git push origin parv-results"
echo "────────────────────────────────────────────────────────────"
