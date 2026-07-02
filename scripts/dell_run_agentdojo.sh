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

# ── Preflight 1b: verdict-endpoint probe (catch a fail-open BEFORE the run) ───
# /health only says the server is up; it does NOT prove /hook/parliament returns
# a real verdict. A parliament that is up but whose ChromaDB 500s on every scan
# would pass /health yet FAIL OPEN on every call — silently producing fake
# "defended" numbers. We POST a known-malicious action and require a real
# BLOCK/ESCALATE/ALLOW verdict field before proceeding. Anything else = STOP.
echo "[preflight] probing /hook/parliament for a real verdict ..."
PROBE_BODY='{"text":"tool:read_file args:{\"path\":\"~/.ssh/id_rsa\"}","session_id":"preflight-probe"}'
VERDICT_JSON="$(curl -s -X POST "${KAVACH_URL}/hook/parliament" \
    -H 'Content-Type: application/json' -d "${PROBE_BODY}" || true)"
DECISION="$(printf '%s' "${VERDICT_JSON}" | python -c "import sys,json;
try:
    d=json.load(sys.stdin); print(d.get('decision') or d.get('verdict') or '')
except Exception:
    print('')" 2>/dev/null || echo '')"
case "${DECISION}" in
  BLOCK|ESCALATE|ALLOW)
    echo "[preflight] verdict endpoint returned '${DECISION}' — parliament is scoring ✅" ;;
  *)
    echo "[FATAL] /hook/parliament did NOT return a usable verdict."
    echo "        Raw response: ${VERDICT_JSON:-<empty>}"
    echo "        The server is up but not scoring (likely ChromaDB 500 / stale handle)."
    echo "        If you run now, EVERY call fails open and the 'defended' numbers are FAKE."
    echo "        Fix: python corpus_loader.py --rebuild ; restart parliament ; re-run."
    exit 1 ;;
esac

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

# ── Fail-open guard: HARD STOP if the run was not fully defended ─────────────
# The KAVACH AUDIT line is easy to miss. This programmatically inspects the
# summary and REFUSES to bless the numbers if any tool call failed open (the
# parliament went unreachable mid-run) or if zero calls were screened. A
# defended number computed over calls that silently bypassed the parliament is
# fake, and must not be committed.
SUMMARY="${OUT}/agentdojo_summary.json"
echo "[guard] verifying the run was fully defended ..."
if [ ! -f "${SUMMARY}" ]; then
  echo "[FATAL] ${SUMMARY} not found — the run did not complete. Do NOT report numbers."
  exit 1
fi
GUARD="$(python -c "
import json,sys
d=json.load(open('${SUMMARY}'))
kav=(d.get('with_kavach') or {}).get('kavach',{}) or {}
fo=d.get('kavach_failopen_count', kav.get('failopen_count',0)) or 0
tot=kav.get('total_calls',0) or 0
scr=tot-fo
valid=bool(d.get('run_fully_defended')) and fo==0 and tot>0
print(f'{int(fo)}|{int(tot)}|{int(scr)}|{\"OK\" if valid else \"BAD\"}')
" 2>/dev/null || echo '?|?|?|BAD')"
FO="${GUARD%%|*}"; REST="${GUARD#*|}"; TOT="${REST%%|*}"; REST="${REST#*|}"; SCR="${REST%%|*}"; STATUS="${REST##*|}"
if [ "${STATUS}" != "OK" ]; then
  echo ""
  echo "🛑🛑🛑  FAIL-OPEN GUARD TRIPPED — DO NOT REPORT OR COMMIT THESE NUMBERS  🛑🛑🛑"
  echo "        total_calls=${TOT}  screened=${SCR}  failed_open=${FO}  run_fully_defended=$(python -c "import json;print(json.load(open('${SUMMARY}')).get('run_fully_defended'))" 2>/dev/null)"
  echo "        Either the parliament went unreachable mid-run (calls bypassed it)"
  echo "        or zero calls were screened. The 'defended' ASR is not real."
  echo "        Fix the parliament, then re-run this script from the top."
  exit 1
fi
echo "[guard] fully defended ✅  (total_calls=${TOT}, screened=${SCR}, failed_open=0)"

# ── Summary ──────────────────────────────────────────────────────────────────
N="$(find "${OUT}" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
echo "────────────────────────────────────────────────────────────"
echo "  DONE. ${N} result files in ${OUT}"
echo "  Fail-open guard passed: run_fully_defended=true, 0 calls bypassed Kavach."
echo ""
echo "  Commit results to parv-results (NOT main/parv):"
echo "    git checkout parv-results"
echo "    git add benchmarks/results_v2/"
echo "    git commit -m 'data: Dell gemma4:26b AgentDojo slack results'"
echo "    git push origin parv-results"
echo "────────────────────────────────────────────────────────────"
