#!/usr/bin/env python3
"""
tools/dell_lab.py
=================

Dell Lab UI — the command center for the Kavach Dell benchmark session.

    python tools/dell_lab.py            # serves on http://127.0.0.1:7788 + opens browser
    python tools/dell_lab.py --port 9000

A single-page dark-theme dashboard (FastAPI backend + vanilla-JS frontend, no
build step) from which Parv and Ishani can:

  * see live System Status  (parliament :8088, Ollama models, ChromaDB counts,
    current git branch + commit)
  * launch the four benchmark runs with buttons (AgentDojo / InjecAgent /
    Red-team / Improvement Loop), each disabled while active
  * watch streaming, color-coded log output (SSE)
  * approve the improvement loop's "yes/no" prompt inline (no terminal needed)
  * watch result metrics update live as the result files land

This UI NEVER starts parliament or Ollama — it only checks they are up. Every
subprocess runs from the repo root. Nothing here writes to the corpus or the
production ChromaDB; the launched scripts own that.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from queue import Queue, Empty

try:
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
except ImportError:
    print(
        "[ERROR] FastAPI/uvicorn not installed. Run:\n"
        "    py -3 -m pip install fastapi uvicorn",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import urllib.request
except ImportError:  # pragma: no cover
    urllib = None  # type: ignore

# ── Repo-root resolution (this file lives in tools/) ──────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = REPO_ROOT / "kavachlogo.png"
PARLIAMENT_URL = os.environ.get("KAVACH_URL", "http://127.0.0.1:8088")
OLLAMA_URL = "http://localhost:11434"

# ── Benchmark registry ────────────────────────────────────────────────────────
# Each run: the command (list, run from REPO_ROOT), and where its results land.
BENCHMARKS: dict[str, dict] = {
    "agentdojo": {
        "label": "AgentDojo",
        "color": "#4f8ef7",
        "cmd": ["bash", "scripts/dell_run_agentdojo.sh"],
        "results_dir": "benchmarks/results_v2/agentdojo_slack_gemma_dell",
        "interactive": False,
    },
    "injecagent": {
        "label": "InjecAgent",
        "color": "#36c98a",
        "cmd": ["bash", "scripts/dell_run_injecagent.sh"],
        "results_dir": "benchmarks/results_v2/injecagent_gemma_dell",
        "interactive": False,
    },
    "redteam": {
        "label": "Red-team",
        "color": "#f5a04f",
        "cmd": ["bash", "scripts/dell_run_redteam.sh"],
        "results_dir": "kavach_eval/evasion_results/redteam_gemma_dell_n250",
        "interactive": False,
    },
    "loop": {
        "label": "Improvement Loop",
        "color": "#a96ff7",
        "cmd": [
            sys.executable, "kavach_eval/improvement_loop.py",
            "--minister", "CHANNEL", "--model", "gemma4:26b", "--verbose",
        ],
        "results_dir": "kavach_eval",  # reads improvement_loop_audit.jsonl
        "interactive": True,           # may prompt for yes/no approval
    },
}

# The exact prompt the improvement loop prints when it wants approval.
APPROVAL_MARKER = "Approve integration"


# ══════════════════════════════════════════════════════════════════════════════
# Run state — one RunHandle per benchmark, owning its subprocess + log buffer
# ══════════════════════════════════════════════════════════════════════════════

class RunHandle:
    """Owns a single benchmark subprocess: its stdout pump thread, a ring of log
    lines, a queue of pending SSE events, and a tiny state machine."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.proc: subprocess.Popen | None = None
        self.status = "idle"          # idle | running | done | error
        self.started_at: float | None = None
        self.ended_at: float | None = None
        self.lines: list[str] = []    # full log history (capped)
        self.subscribers: list[Queue] = []
        self.awaiting_approval = False
        self.approval_text = ""       # the summary block shown before the prompt
        self._lock = threading.Lock()

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> bool:
        if self.status == "running":
            return False
        self.lines = []
        self.status = "running"
        self.started_at = time.time()
        self.ended_at = None
        self.awaiting_approval = False
        self.approval_text = ""
        self.proc = subprocess.Popen(
            BENCHMARKS[self.key]["cmd"],
            cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        threading.Thread(target=self._pump, daemon=True).start()
        return True

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        approval_buf: list[str] = []
        for raw in self.proc.stdout:
            line = raw.rstrip("\n")
            self._emit({"type": "log", "line": line})

            # Detect the improvement loop's approval prompt. We keep a small
            # rolling buffer of recent lines as the "summary" to show the user.
            approval_buf.append(line)
            if len(approval_buf) > 25:
                approval_buf.pop(0)
            if BENCHMARKS[self.key]["interactive"] and APPROVAL_MARKER in line:
                self.awaiting_approval = True
                self.approval_text = "\n".join(approval_buf)
                self._emit({"type": "approval_request", "summary": self.approval_text})

        rc = self.proc.wait()
        self.ended_at = time.time()
        self.status = "done" if rc == 0 else "error"
        self.awaiting_approval = False
        self._emit({"type": "status", "status": self.status, "returncode": rc})

    # ── approval ──────────────────────────────────────────────────────────────
    def approve(self, decision: bool) -> bool:
        if not (self.proc and self.awaiting_approval and self.proc.stdin):
            return False
        self.proc.stdin.write("yes\n" if decision else "no\n")
        self.proc.stdin.flush()
        self.awaiting_approval = False
        self._emit({"type": "approval_sent", "decision": "yes" if decision else "no"})
        return True

    # ── SSE plumbing ──────────────────────────────────────────────────────────
    def _emit(self, event: dict) -> None:
        with self._lock:
            if event["type"] == "log":
                self.lines.append(event["line"])
                if len(self.lines) > 5000:
                    self.lines = self.lines[-4000:]
            for q in list(self.subscribers):
                q.put(event)

    def subscribe(self) -> Queue:
        q: Queue = Queue()
        with self._lock:
            # Replay existing history so a late subscriber sees the full log.
            for ln in self.lines:
                q.put({"type": "log", "line": ln})
            if self.awaiting_approval:
                q.put({"type": "approval_request", "summary": self.approval_text})
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: Queue) -> None:
        with self._lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.ended_at if self.ended_at else time.time()
        return round(end - self.started_at, 1)


RUNS: dict[str, RunHandle] = {k: RunHandle(k) for k in BENCHMARKS}


# ══════════════════════════════════════════════════════════════════════════════
# Status / results probes (all best-effort; never raise to the request handler)
# ══════════════════════════════════════════════════════════════════════════════

def _http_json(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def probe_parliament() -> dict:
    h = _http_json(f"{PARLIAMENT_URL}/health")
    if not h:
        return {"up": False}
    return {"up": True, "doc_counts": h.get("doc_counts", {}),
            "retrieval_mode": h.get("retrieval_mode")}


def probe_ollama() -> dict:
    tags = _http_json(f"{OLLAMA_URL}/api/tags")
    if not tags:
        return {"up": False, "models": []}
    models = [m.get("name", "?") for m in tags.get("models", [])]
    return {"up": True, "models": models}


def probe_git() -> dict:
    def _git(*a: str) -> str:
        try:
            return subprocess.check_output(["git", *a], cwd=str(REPO_ROOT),
                                           text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return "?"
    return {"branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "commit": _git("log", "--oneline", "-1")}


def _latest(glob_pat: str) -> Path | None:
    matches = sorted(REPO_ROOT.glob(glob_pat))
    return matches[-1] if matches else None


def parse_results(key: str) -> dict:
    """Best-effort parse of whatever result files exist for a benchmark. Returns
    a flat dict of display metrics; empty dict if nothing landed yet."""
    try:
        if key == "redteam":
            rpt = _latest(f"{BENCHMARKS[key]['results_dir']}/evasion_report_*.json")
            if not rpt:
                return {}
            d = json.loads(rpt.read_text())
            return {"seeds": d.get("n_seeds"), "evaluated": d.get("n_evaluated"),
                    "n_evaded": d.get("n_evaded"),
                    "evasion_rate": d.get("evasion_rate"),
                    "bm25_gate": d.get("bm25_gate_evasions")}

        if key == "injecagent":
            summ = _latest(f"{BENCHMARKS[key]['results_dir']}/**/summary.json") \
                or _latest(f"{BENCHMARKS[key]['results_dir']}/summary.json")
            if not summ:
                return {}
            d = json.loads(summ.read_text())
            strict, loose = d.get("strict", {}), d.get("loose", {})
            return {"n_attacks": d.get("n_attacks"),
                    "strict_recall": strict.get("recall"),
                    "loose_recall": loose.get("recall"),
                    "fpr": strict.get("fpr")}

        if key == "agentdojo":
            logs = list(REPO_ROOT.glob(f"{BENCHMARKS[key]['results_dir']}/**/*.json"))
            done = len(logs)
            succ = 0
            for f in logs:
                try:
                    j = json.loads(f.read_text())
                    if isinstance(j, dict) and (j.get("utility") or j.get("success")):
                        succ += 1
                except Exception:
                    continue
            util = round(succ / done, 3) if done else None
            return {"pairs_done": done, "utility_rate": util}

        if key == "loop":
            audit = REPO_ROOT / "kavach_eval" / "improvement_loop_audit.jsonl"
            if not audit.exists():
                return {}
            last = None
            for line in audit.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    last = json.loads(line)
            if not last:
                return {}
            return {"iteration": last.get("iteration"),
                    "evaded_before": last.get("n_evaded_before"),
                    "evaded_after": last.get("n_evaded_after"),
                    "effective": last.get("candidates_effective"),
                    "integrated": last.get("patterns_integrated")}
    except Exception:
        return {}
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# FastAPI app
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="Kavach Dell Lab")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/logo.png")
async def logo():
    if LOGO_PATH.exists():
        return FileResponse(str(LOGO_PATH))
    return JSONResponse({"error": "no logo"}, status_code=404)


@app.get("/status")
async def status() -> JSONResponse:
    runs = {k: {"status": r.status, "elapsed": r.elapsed(),
                "awaiting_approval": r.awaiting_approval}
            for k, r in RUNS.items()}
    return JSONResponse({
        "parliament": probe_parliament(),
        "ollama": probe_ollama(),
        "git": probe_git(),
        "runs": runs,
        "benchmarks": {k: {"label": v["label"], "color": v["color"],
                           "interactive": v["interactive"]}
                       for k, v in BENCHMARKS.items()},
    })


@app.get("/results/{benchmark}")
async def results(benchmark: str) -> JSONResponse:
    if benchmark not in BENCHMARKS:
        return JSONResponse({"error": "unknown benchmark"}, status_code=404)
    return JSONResponse(parse_results(benchmark))


@app.post("/run/{benchmark}")
async def run(benchmark: str) -> JSONResponse:
    if benchmark not in BENCHMARKS:
        return JSONResponse({"error": "unknown benchmark"}, status_code=404)
    # Preflight: parliament must be up for any run to be meaningful.
    if not probe_parliament()["up"]:
        return JSONResponse({"error": "parliament not reachable at "
                             f"{PARLIAMENT_URL} — start it first"}, status_code=409)
    started = RUNS[benchmark].start()
    if not started:
        return JSONResponse({"error": "already running"}, status_code=409)
    return JSONResponse({"ok": True, "status": "running"})


@app.post("/approve/{benchmark}")
async def approve(benchmark: str, request: Request) -> JSONResponse:
    if benchmark not in BENCHMARKS:
        return JSONResponse({"error": "unknown benchmark"}, status_code=404)
    body = await request.json()
    decision = bool(body.get("approve"))
    ok = RUNS[benchmark].approve(decision)
    if not ok:
        return JSONResponse({"error": "no pending approval"}, status_code=409)
    return JSONResponse({"ok": True, "decision": "yes" if decision else "no"})


@app.get("/logs/{benchmark}")
async def logs(benchmark: str) -> StreamingResponse:
    if benchmark not in BENCHMARKS:
        return JSONResponse({"error": "unknown benchmark"}, status_code=404)
    handle = RUNS[benchmark]

    async def event_stream():
        q = handle.subscribe()
        try:
            while True:
                try:
                    event = q.get(timeout=0.5)
                    yield f"data: {json.dumps(event)}\n\n"
                except Empty:
                    # heartbeat keeps the connection alive through proxies
                    yield ": keepalive\n\n"
                await asyncio.sleep(0)
        finally:
            handle.unsubscribe(q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ══════════════════════════════════════════════════════════════════════════════
# Frontend — single inline HTML page, vanilla JS, inline styles only
# ══════════════════════════════════════════════════════════════════════════════

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Kavach · Dell Lab</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
<style>
  :root{
    --bg:#faf7f2; --bg2:#f3ede2; --paper:#ffffff;
    --ink:#2b2a26; --ink-soft:#5a5852; --ink-mute:#9a9690;
    --line:#e5dfd2; --line-2:#d4ccba;
    --accent:#8b5a3c; --green:#5b8a72; --rose:#c47b6f; --gold:#c79849; --plum:#8a6a8e; --teal:#4d8a8c;
    --serif:'Fraunces',Georgia,serif; --sans:'Inter',system-ui,sans-serif; --mono:'JetBrains Mono',monospace;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--ink);font-family:var(--serif);font-size:16px;line-height:1.55;min-height:100vh}
  .container{max-width:1320px;margin:0 auto;padding:28px 30px 60px}
  ::-webkit-scrollbar{width:8px;height:8px} ::-webkit-scrollbar-thumb{background:var(--line-2);border-radius:999px}

  header{margin-bottom:22px;padding-bottom:20px;border-bottom:1px solid var(--line);
    display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:20px}
  .brand{display:flex;align-items:center;gap:16px}
  .brand img{height:90px;width:auto;display:block}
  .brand-sub{font-family:var(--sans);font-size:12px;color:var(--ink-mute);letter-spacing:.08em;text-transform:uppercase}
  .brand-title{font-family:var(--serif);font-size:30px;font-weight:500;font-style:italic;color:var(--accent);line-height:1}
  .header-meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:flex-end}
  .status-pill{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;background:var(--paper);
    border:1px solid var(--line);border-radius:999px;font-family:var(--sans);font-size:12.5px;color:var(--ink-soft)}
  .status-pill .lab{color:var(--ink-mute)}
  .status-pill .val{color:var(--ink);font-weight:500}
  .status-pill.mono .val{font-family:var(--mono);font-size:11.5px}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--ink-mute);flex-shrink:0}
  .dot.ready{background:var(--green);box-shadow:0 0 0 3px rgba(91,138,114,.18)}
  .dot.error{background:var(--rose)}

  main{display:grid;grid-template-columns:262px 1fr 300px;gap:18px;align-items:start}
  @media(max-width:1100px){main{grid-template-columns:1fr}}
  .col{display:flex;flex-direction:column;gap:18px;min-width:0}
  .section-card{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px}
  .section-card h3{font-family:var(--serif);font-size:20px;font-weight:500;font-style:italic;margin-bottom:4px}
  .section-card .subtitle{font-family:var(--sans);font-size:11px;color:var(--ink-mute);
    text-transform:uppercase;letter-spacing:.06em;margin-bottom:18px}

  .run-btn{display:block;width:100%;text-align:left;border:1px solid var(--line-2);border-left-width:3px;
    border-radius:10px;padding:14px 16px;margin-bottom:12px;cursor:pointer;background:var(--paper);
    font-family:var(--serif);transition:all .15s}
  .run-btn:hover:not(:disabled){background:var(--bg2)}
  .run-btn:disabled{cursor:not-allowed}
  .run-btn .rb-top{display:flex;align-items:center;justify-content:space-between}
  .run-btn .rb-name{font-size:17px;font-style:italic;font-weight:500}
  .run-btn .rb-badge{font-family:var(--mono);font-size:10px;padding:2px 8px;border-radius:999px;
    border:1px solid var(--line-2);color:var(--ink-mute);text-transform:lowercase}
  .run-btn.running .rb-badge{background:rgba(199,152,73,.14);color:var(--gold);border-color:rgba(199,152,73,.4)}
  .run-btn.done .rb-badge{background:rgba(91,138,114,.12);color:var(--green);border-color:rgba(91,138,114,.4)}
  .run-btn.error .rb-badge{background:rgba(196,123,111,.12);color:var(--rose);border-color:rgba(196,123,111,.4)}
  .run-btn .rb-meta{font-family:var(--sans);font-size:11.5px;color:var(--ink-mute);margin-top:6px}
  .run-btn .rb-meta a{color:var(--accent);text-decoration:none;border-bottom:1px solid var(--line-2)}

  #logwrap{display:flex;flex-direction:column;min-height:0}
  .tabs{display:flex;gap:0;margin-bottom:14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
  .tab{padding:9px 16px;cursor:pointer;color:var(--ink-mute);font-family:var(--serif);font-size:15px;
    font-style:italic;border-bottom:2px solid transparent;margin-bottom:-1px;user-select:none;transition:all .2s}
  .tab:hover{color:var(--ink-soft)}
  .tab.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:500}
  #log{height:60vh;overflow:auto;background:#2b2a26;color:#e8e2d6;border-radius:10px;padding:14px 16px;
    white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12.5px;line-height:1.55}
  #log .l-err{color:#e89b8f} #log .l-warn{color:#e3c06a}
  #log .l-block{color:#e89b8f;font-weight:500} #log .l-allow{color:#86c4a3;font-weight:500}
  #log .l-sys{color:#9a9690;font-style:italic}

  #approval{display:none;background:var(--bg2);border:1px solid var(--plum);border-left:3px solid var(--plum);
    border-radius:10px;padding:16px 18px;margin-bottom:14px}
  #approval .ap-title{font-family:var(--serif);font-size:17px;font-style:italic;font-weight:500;
    color:var(--plum);margin-bottom:10px}
  #approval pre{white-space:pre-wrap;font-family:var(--mono);font-size:12px;color:var(--ink-soft);
    background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:12px;
    max-height:200px;overflow:auto;margin-bottom:12px}
  #approval .btn{margin-right:10px}
  .btn{padding:10px 22px;background:var(--accent);border:1px solid var(--accent);color:#fefdf9;
    font-family:var(--serif);font-size:15px;font-style:italic;cursor:pointer;border-radius:8px;transition:all .15s}
  .btn:hover{background:#75492f;border-color:#75492f}
  .btn.no{background:transparent;color:var(--rose);border-color:var(--rose)}
  .btn.no:hover{background:rgba(196,123,111,.10)}

  .res-block{margin-bottom:18px;padding-bottom:16px;border-bottom:1px solid var(--line)}
  .res-block:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
  .res-block h4{font-family:var(--serif);font-size:17px;font-style:italic;font-weight:500;margin-bottom:8px}
  .metric{display:flex;justify-content:space-between;align-items:baseline;padding:5px 0;font-family:var(--sans);font-size:13px}
  .metric .k{color:var(--ink-mute)}
  .metric .v{font-family:var(--serif);font-weight:500;font-variant-numeric:tabular-nums;font-size:16px}
  .res-empty{color:var(--ink-mute);font-style:italic;font-size:13.5px;font-family:var(--serif);padding:4px 0}
  ul.models{list-style:none;display:flex;gap:6px;flex-wrap:wrap}
  ul.models li{font-family:var(--mono);font-size:11px;background:var(--paper);border:1px solid var(--line);
    border-radius:999px;padding:2px 10px;color:var(--ink-soft)}
  .footer-note{margin-top:36px;text-align:center;font-family:var(--serif);font-style:italic;font-size:13px;color:var(--ink-mute)}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <img src="/logo.png" alt="Kavach" onerror="this.style.display='none'"/>
    </div>
    <div class="header-meta">
      <div class="status-pill"><span class="dot" id="d-parl"></span><span class="lab">Parliament</span><span class="val" id="s-parl">…</span></div>
      <div class="status-pill mono"><span class="lab">ChromaDB</span><span class="val" id="s-chroma">…</span></div>
      <div class="status-pill"><span class="dot" id="d-ollama"></span><span class="lab">Ollama</span><span class="val"><ul class="models" id="s-ollama"></ul></span></div>
      <div class="status-pill mono"><span class="lab">Git</span><span class="val" id="s-git">…</span></div>
    </div>
  </header>

  <main>
    <div class="col">
      <div class="section-card">
        <h3>Run Controls</h3>
        <div class="subtitle">launch · in order</div>
        <div id="controls"></div>
      </div>
    </div>

    <div class="col">
      <div class="section-card" id="logwrap">
        <h3>Live Log</h3>
        <div class="subtitle">streaming · color-coded</div>
        <div class="tabs" id="tabs"></div>
        <div id="approval">
          <div class="ap-title">Improvement loop — approval requested</div>
          <pre id="approval-summary"></pre>
          <button class="btn" onclick="sendApproval(true)">✓ Yes — integrate</button>
          <button class="btn no" onclick="sendApproval(false)">✗ No — decline</button>
        </div>
        <div id="log"></div>
      </div>
    </div>

    <div class="col">
      <div class="section-card">
        <h3>Results</h3>
        <div class="subtitle">live · polled every 10s</div>
        <div id="results"></div>
      </div>
    </div>
  </main>

  <div class="footer-note">कवच — protective armour. This lab orchestrates the real benchmark scripts; it never starts parliament or Ollama.</div>
</div>

<script>
const FMT = {
  redteam:   [["seeds","Seeds"],["evaluated","Evaluated"],["n_evaded","Evaded"],
              ["evasion_rate","Evasion rate"],["bm25_gate","BM25-gate"]],
  injecagent:[["n_attacks","Attacks"],["loose_recall","Loose recall"],
              ["strict_recall","Strict recall"],["fpr","FPR"]],
  agentdojo: [["pairs_done","Pairs done"],["utility_rate","Utility rate"]],
  loop:      [["iteration","Iteration"],["evaded_before","Evaded before"],
              ["evaded_after","Evaded after"],["effective","Effective"],
              ["integrated","Integrated"]],
};
const ACCENT = {agentdojo:"var(--teal)",injecagent:"var(--green)",redteam:"var(--gold)",loop:"var(--plum)"};
let BENCH = {};
let activeTab = null;
let evtSource = null;
const PREVIEW = new URLSearchParams(location.search).get('preview') === '1';

function el(id){return document.getElementById(id);}

async function refreshStatus(){
  let s; try{ s = await (await fetch('/status')).json(); }catch(e){ return; }
  BENCH = s.benchmarks;
  const p = s.parliament;
  el('d-parl').className = 'dot '+(p.up?'ready':'error');
  el('s-parl').textContent = p.up?'healthy':'down';
  el('s-chroma').textContent = p.up ? Object.entries(p.doc_counts||{})
        .map(([k,v])=>`${k[0]}${v}`).join(' ') : '—';
  el('d-ollama').className = 'dot '+(s.ollama.up?'ready':'error');
  el('s-ollama').innerHTML = (s.ollama.models||[]).map(m=>`<li>${m}</li>`).join('') || '<li>none</li>';
  el('s-git').textContent = `${s.git.branch} · ${(s.git.commit||'').split(' ')[0]}`;
  renderControls(s.runs);
  if(!activeTab) selectTab(Object.keys(BENCH)[0]);
  renderTabs();
}

function renderControls(runs){
  const c = el('controls'); c.innerHTML='';
  for(const [key,b] of Object.entries(BENCH)){
    const r = runs[key] || {status:'idle',elapsed:0};
    const running = r.status==='running';
    const btn = document.createElement('button');
    btn.className='run-btn '+r.status;
    btn.style.borderLeftColor = ACCENT[key]||'var(--accent)';
    btn.disabled = running;
    let meta;
    if(running) meta = `running · ${r.elapsed}s`;
    else if(r.status==='done') meta = `done · ${r.elapsed}s · <a href="#" onclick="selectTab('${key}');return false">view log</a>`;
    else if(r.status==='error') meta = `error · ${r.elapsed}s · <a href="#" onclick="selectTab('${key}');return false">view log</a>`;
    else meta = 'idle';
    btn.innerHTML = `<div class="rb-top"><span class="rb-name">${b.label}</span>`+
                    `<span class="rb-badge">${r.status}</span></div>`+
                    `<div class="rb-meta">${meta}</div>`;
    btn.onclick = ()=>launch(key);
    c.appendChild(btn);
  }
}

function renderTabs(){
  const t = el('tabs'); t.innerHTML='';
  for(const [key,b] of Object.entries(BENCH)){
    const tab = document.createElement('div');
    tab.className='tab'+(key===activeTab?' active':'');
    tab.textContent=b.label;
    tab.onclick=()=>selectTab(key);
    t.appendChild(tab);
  }
}

async function launch(key){
  const res = await fetch('/run/'+key,{method:'POST'});
  if(!res.ok){ const j=await res.json(); alert(j.error||'failed to start'); return; }
  selectTab(key); refreshStatus();
}
async function sendApproval(decision){
  if(!activeTab) return;
  await fetch('/approve/'+activeTab,{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({approve:decision})});
  el('approval').style.display='none';
}

function selectTab(key){
  activeTab=key;
  el('log').innerHTML='';
  el('approval').style.display='none';
  renderTabs();
  if(PREVIEW) return;
  if(evtSource) evtSource.close();
  evtSource = new EventSource('/logs/'+key);
  evtSource.onmessage = (e)=>{
    const ev = JSON.parse(e.data);
    if(ev.type==='log') appendLog(ev.line);
    else if(ev.type==='approval_request') showApproval(ev.summary);
    else if(ev.type==='approval_sent'){ el('approval').style.display='none'; }
    else if(ev.type==='status'){ appendLog(`── run ${ev.status} (rc=${ev.returncode}) ──`,'l-sys'); refreshStatus(); }
  };
}
function classify(line){
  const l=line.toLowerCase();
  if(l.includes('error')||l.includes('fatal')||l.includes('traceback')) return 'l-err';
  if(l.includes('warn')) return 'l-warn';
  if(line.includes('BLOCK')) return 'l-block';
  if(line.includes('ALLOW')) return 'l-allow';
  return '';
}
function appendLog(line,cls){
  const log=el('log');
  const div=document.createElement('div');
  const c=cls||classify(line); if(c) div.className=c;
  div.textContent=line;
  log.appendChild(div);
  log.scrollTop=log.scrollHeight;
}
function showApproval(summary){
  el('approval-summary').textContent=summary;
  el('approval').style.display='block';
}

async function refreshResults(){
  const out = el('results'); let html='';
  for(const [key,b] of Object.entries(BENCH)){
    let data={}; try{ data = await (await fetch('/results/'+key)).json(); }catch(e){}
    html += `<div class="res-block"><h4 style="color:${ACCENT[key]||'var(--accent)'}">${b.label}</h4>`;
    const rows = FMT[key]||[];
    if(Object.keys(data).length===0){ html+='<div class="res-empty">no results yet</div>'; }
    else {
      for(const [k,label] of rows){
        if(data[k]===undefined||data[k]===null) continue;
        let v=data[k];
        if(k.includes('rate')||k==='fpr'||k.includes('recall')) v=(v*100).toFixed(1)+'%';
        html+=`<div class="metric"><span class="k">${label}</span><span class="v">${v}</span></div>`;
      }
    }
    html+='</div>';
  }
  out.innerHTML=html;
}

refreshStatus(); refreshResults();
if(!PREVIEW){
  setInterval(refreshStatus, 5000);
  setInterval(refreshResults, 10000);
}
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Kavach Dell Lab UI — browser command center for the Dell "
                    "benchmark session (serves on localhost). Does NOT start "
                    "parliament or Ollama; only checks they are up.")
    ap.add_argument("--port", type=int, default=7788,
                    help="Port to serve on (default: 7788).")
    ap.add_argument("--host", default="127.0.0.1",
                    help="Host to bind (default: 127.0.0.1).")
    ap.add_argument("--no-browser", action="store_true",
                    help="Do not auto-open the browser on launch.")
    args = ap.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"[dell_lab] serving on {url}  (repo root: {REPO_ROOT})")
    print(f"[dell_lab] parliament probe target: {PARLIAMENT_URL}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
