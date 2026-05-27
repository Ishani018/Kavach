#!/usr/bin/env bash
# =============================================================================
# run_all.sh — Kavach full startup sequence
# PES University · Capstone PW26_RB_03
#
# Run this ONCE when you sit down at the lab machine.
# It will:
#   1. Install Python dependencies
#   2. Load v1 corpus + technical corpus into ChromaDB (one-time, then cached)
#   3. Run COMPASS calibration to derive the drift threshold
#   4. Start the Parliament server on port 8088
#   5. Run the smoke test to verify everything works
#
# Usage:
#   chmod +x run_all.sh
#   ./run_all.sh              # full startup
#   ./run_all.sh --no-load    # skip corpus loading (already done)
#   ./run_all.sh --demo-only  # just start server, assume corpus loaded
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

NO_LOAD=false
DEMO_ONLY=false
for arg in "$@"; do
    [[ "$arg" == "--no-load" ]]   && NO_LOAD=true
    [[ "$arg" == "--demo-only" ]] && DEMO_ONLY=true
done

echo -e "\n${CYAN}${BOLD}Kavach · PW26_RB_03 · Startup sequence${NC}"
echo -e "${CYAN}=======================================${NC}\n"

# ── Step 1: Dependencies ──────────────────────────────────────────────────────
echo -e "${BOLD}[1/5] Installing dependencies...${NC}"
pip install -q --break-system-packages -r requirements.txt
echo -e "${GREEN}✓ Dependencies OK${NC}\n"

# ── Step 2: Corpus loading ────────────────────────────────────────────────────
if [ "$DEMO_ONLY" = false ] && [ "$NO_LOAD" = false ]; then
    echo -e "${BOLD}[2/5] Loading corpus into ChromaDB...${NC}"
    echo -e "  ${YELLOW}This takes 3-5 minutes on first run (BGE model download + embedding).${NC}"
    echo -e "  ${YELLOW}Subsequent runs use cached ChromaDB and take ~10 seconds.${NC}\n"

    # Check if .chroma_kavach already exists and has data
    if [ -d "parliament/.chroma_kavach" ] && [ "$(ls -A parliament/.chroma_kavach 2>/dev/null)" ]; then
        echo -e "  ${GREEN}ChromaDB cache found. Rebuilding to ensure consistency...${NC}"
    fi

    python3 corpus_loader.py --rebuild
    echo -e "\n${GREEN}✓ Corpus loaded${NC}\n"
else
    echo -e "${BOLD}[2/5] Skipping corpus load (--no-load or --demo-only)${NC}\n"
fi

# ── Step 3: COMPASS calibration ───────────────────────────────────────────────
if [ "$DEMO_ONLY" = false ] && [ "$NO_LOAD" = false ]; then
    echo -e "${BOLD}[3/5] Running COMPASS calibration...${NC}"
    python3 compass_calibrator.py
    echo -e "${GREEN}✓ COMPASS threshold calibrated${NC}\n"
else
    echo -e "${BOLD}[3/5] Skipping COMPASS calibration${NC}\n"
fi

# ── Step 4: Start Parliament server ──────────────────────────────────────────
echo -e "${BOLD}[4/5] Starting Parliament server on :8088...${NC}"

# Kill any existing instance
pkill -f "kavach_parliament\|parliament.server" 2>/dev/null || true
sleep 1

# Start server in background, log to parliament/server.log
python3 -m uvicorn parliament.server:app \
    --host 127.0.0.1 \
    --port 8088 \
    --log-level info \
    > parliament/server.log 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > parliament/server.pid

echo -e "  Parliament PID: ${SERVER_PID}"
echo -e "  Waiting for server to be ready..."

# Wait up to 30s for server to be healthy
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8088/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Parliament is up${NC}\n"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Server failed to start. Check parliament/server.log${NC}"
        cat parliament/server.log | tail -20
        exit 1
    fi
done

# ── Step 5: Smoke test ────────────────────────────────────────────────────────
echo -e "${BOLD}[5/5] Running smoke tests...${NC}"
python3 -m pytest parliament/smoke_test.py -v --tb=short
echo -e "\n${GREEN}${BOLD}✓ All systems go.${NC}\n"

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}${BOLD}=== Kavach is ready ===${NC}"
echo -e ""
echo -e "  Parliament API  : ${BOLD}http://127.0.0.1:8088${NC}"
echo -e "  Health check    : ${BOLD}http://127.0.0.1:8088/health${NC}"
echo -e "  Vote ledger     : ${BOLD}http://127.0.0.1:8088/ledger/votes${NC}"
echo -e "  Server log      : ${BOLD}parliament/server.log${NC}"
echo -e ""
echo -e "  ${BOLD}Demo:${NC}          python3 kavach_send_attack.py"
echo -e "  ${BOLD}Monitor:${NC}       python3 kavach_monitor.py"
echo -e "  ${BOLD}InjecAgent:${NC}    python3 benchmarks/injecagent_runner.py"
echo -e "  ${BOLD}Sweep:${NC}         python3 benchmarks/threshold_sweep.py"
echo -e "  ${BOLD}Stop server:${NC}   kill \$(cat parliament/server.pid)"
echo -e ""
