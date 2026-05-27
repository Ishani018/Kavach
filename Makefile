# Kavach — project Makefile
# Usage: make <target>
# All Python commands use the venv at .venv/ if it exists, else system python3.

PYTHON     := $(shell [ -d .venv ] && echo .venv/bin/python3 || echo python3)
PIP        := $(shell [ -d .venv ] && echo .venv/bin/pip || echo pip3)
UVICORN    := $(shell [ -d .venv ] && echo .venv/bin/uvicorn || echo uvicorn)
NODE_DIR   := plugin
PARLIAMENT := parliament

.PHONY: all setup load server test smoke bench plugin paper clean help

## ── Default ──────────────────────────────────────────────────────────────────
all: help

## ── Environment setup ────────────────────────────────────────────────────────
setup:
	@echo "[kavach] Creating virtualenv..."
	python3 -m venv .venv
	@echo "[kavach] Installing Python deps..."
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo "[kavach] Setup complete. Run: make load"

## ── Corpus loading (must run before server) ──────────────────────────────────
load:
	@echo "[kavach] Loading corpus into ChromaDB..."
	$(PYTHON) corpus_loader.py
	@echo "[kavach] Corpus loaded. Run: make server"

## ── Server ───────────────────────────────────────────────────────────────────
server:
	@echo "[kavach] Starting parliament server on :8000 ..."
	$(UVICORN) parliament.server:app --host 0.0.0.0 --port 8088 --reload

server-prod:
	@echo "[kavach] Starting parliament server (production, no reload)..."
	$(UVICORN) parliament.server:app --host 0.0.0.0 --port 8088 --workers 2

## ── Tests ────────────────────────────────────────────────────────────────────
test:
	@echo "[kavach] Running unit tests (parliament/test_speaker.py)..."
	$(PYTHON) -m pytest parliament/test_speaker.py -v

smoke:
	@echo "[kavach] Running smoke test (requires server on :8000)..."
	$(PYTHON) parliament/smoke_test.py

## ── Calibration ──────────────────────────────────────────────────────────────
calibrate:
	@echo "[kavach] Running COMPASS calibration (Youden J threshold sweep)..."
	$(PYTHON) compass_calibrator.py

## ── Benchmarks ───────────────────────────────────────────────────────────────
bench:
	@echo "[kavach] Running InjecAgent benchmark (requires server on :8000)..."
	$(PYTHON) benchmarks/injecagent_runner.py

bench-thresholds:
	@echo "[kavach] Running threshold sweep..."
	$(PYTHON) benchmarks/threshold_sweep.py

bench-benign:
	@echo "[kavach] Running benign trace FPR evaluation..."
	$(PYTHON) -c "from benchmarks.injecagent_runner import run_benign; run_benign()"

## ── Plugin (TypeScript) ──────────────────────────────────────────────────────
plugin:
	@echo "[kavach] Building OpenClaw plugin..."
	cd $(NODE_DIR) && npm install && npm run build
	@echo "[kavach] Plugin built at plugin/dist/index.js"

plugin-install:
	@echo "[kavach] Installing plugin into local OpenClaw project..."
	@if [ -z "$(OPENCLAW_DIR)" ]; then \
		echo "ERROR: set OPENCLAW_DIR=<path to your openclaw project>"; exit 1; \
	fi
	cp -r $(NODE_DIR)/dist $(OPENCLAW_DIR)/node_modules/openclaw-plugin-kavach/
	cp $(NODE_DIR)/openclaw.plugin.json $(OPENCLAW_DIR)/

## ── Paper ────────────────────────────────────────────────────────────────────
paper:
	@echo "[kavach] Building paper PDF..."
	cd paper && pdflatex skeleton.tex && bibtex skeleton && \
	  pdflatex skeleton.tex && pdflatex skeleton.tex
	@echo "[kavach] PDF at paper/skeleton.pdf"

paper-clean:
	cd paper && rm -f *.aux *.bbl *.blg *.log *.out *.toc

## ── Full pipeline (lab day) ──────────────────────────────────────────────────
lab-setup: setup load calibrate
	@echo "[kavach] Lab setup complete. Run 'make server' in one terminal, 'make smoke' in another."

## ── Corpus merge (v1 + v2 new patterns) ─────────────────────────────────────
merge-corpus:
	@echo "[kavach] Merging corpus v1 + v2 patterns..."
	$(PYTHON) corpus_v2/merge_corpus.py

## ── Clean ────────────────────────────────────────────────────────────────────
clean:
	@echo "[kavach] Cleaning ChromaDB data..."
	rm -rf chroma_data/
	@echo "[kavach] Cleaning compiled plugin..."
	rm -rf $(NODE_DIR)/dist $(NODE_DIR)/node_modules
	@echo "[kavach] Cleaning Python cache..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

clean-db:
	@echo "[kavach] Removing parliament ledger DB..."
	rm -f parliament/kavach_parliament.db

## ── Health check ─────────────────────────────────────────────────────────────
health:
	curl -s http://localhost:8088/health | python3 -m json.tool

## ── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Kavach — Makefile targets"
	@echo "  ─────────────────────────────────────────────────────"
	@echo "  make setup           Create venv, install Python deps"
	@echo "  make load            Load corpus into ChromaDB"
	@echo "  make server          Start parliament server (:8000, reload)"
	@echo "  make server-prod     Start server (production, 2 workers)"
	@echo "  make test            Run unit tests"
	@echo "  make smoke           Smoke test (server must be running)"
	@echo "  make calibrate       COMPASS threshold calibration"
	@echo "  make bench           InjecAgent benchmark"
	@echo "  make bench-thresholds Threshold sweep"
	@echo "  make plugin          Build TypeScript plugin"
	@echo "  make lab-setup       Full lab-day bootstrap (setup+load+calibrate)"
	@echo "  make merge-corpus    Merge v2 patterns into corpus"
	@echo "  make paper           Build paper PDF (requires LaTeX)"
	@echo "  make health          Check server health endpoint"
	@echo "  make clean           Remove build artifacts"
	@echo "  make clean-db        Remove ledger DB (resets session state)"
	@echo ""
