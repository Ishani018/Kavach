# Kavach — Team Ownership

Review this table as a team. If your name is wrong or missing, edit directly and commit.
Last updated: June 1, 2026 (post lab session).

---

## Ownership Table

| Component | Primary Owner | Reviewer |
|---|---|---|
| **PARLIAMENT** | | |
| `parliament/server.py` | Ishani | Parv |
| `parliament/speaker.py` | Ishani | Parv |
| `parliament/ministers.py` | Ishani | Janya |
| `parliament/test_speaker.py` | Ishani | Parv |
| `parliament/config.yaml` | Ishani | All |
| `compass_calibrator.py` | Pranitha | Ishani |
| `corpus_loader.py` | Ishani | Pranitha |
| **PLUGIN** | | |
| `plugin/openclaw-plugin-kavach.ts` | Parv | Ishani |
| `plugin/tsconfig.json` | Parv | Ishani |
| `openclaw_pr/PR1_hooks_fix.md` | Parv | Ishani |
| `openclaw_pr/PR1_test_5513.ts` | Parv | Ishani |
| `openclaw_pr/PR1_test_5943.ts` | Parv | Ishani |
| **CORPUS** | | |
| `corpus_v2/expansion_protocol.md` | Janya | All |
| `corpus_v2/merge_corpus.py` | Janya | Ishani |
| `corpus_v2/new_patterns_executor.json` | Janya | Pranitha |
| `corpus_v2/new_patterns_channel*.json` | Janya | Pranitha |
| `corpus_v2/new_patterns_navigator*.json` | Janya | Pranitha |
| `corpus_v2/new_patterns_vault*.json` | Pranitha | Janya |
| `kavach_corpus_technical.json` | Pranitha | Janya |
| **BENCHMARKS** | | |
| `benchmarks/injecagent_runner.py` | Ishani | Parv |
| `injecagent_runner.py` (root) | Ishani | Parv |
| `benchmarks/benign_traces.py` | Pranitha | Janya |
| `benchmarks/threshold_sweep.py` | Janya | Pranitha |
| `benchmarks/agentdojo_runner.py` | Ishani | Parv |
| `benchmarks/openclaw_native/` | Ishani | Parv |
| `benchmarks/results_v1/` | All | — |
| **SETUP** | | |
| `kavach_boot.sh` | Ishani + Parv | All |
| `predownload_model.py` | Ishani | All |
| **PAPER** | | |
| `paper/section_1_intro.tex` | Ishani | All |
| `paper/section_2_background.tex` | Ishani | All |
| `paper/section_3_design.tex` | Ishani | All |
| `paper/section_4_temporal_spatial.tex` | Ishani | All |
| `paper/section_5_evaluation.tex` | Ishani | All |
| `paper/section_6_related_work.tex` | Parv | Ishani |
| `paper/section_7_limitations.tex` | Ishani | All |
| `paper/section_8_future_work.tex` | All | Ishani |
| `paper/related_work.md` | Parv | Ishani |
| `paper/related_work_table.tex` | Parv | Ishani |
| **DOCS** | | |
| `README.md` | Ishani | All |
| `TEAM.md` | All | — |
| `FINDINGS.md` | Ishani | All |
| `MONDAY_RUNBOOK.md` | Ishani | All |
| `SAFE_TESTING.md` | Ishani | Parv |
| `docs/OPENCLAW_INTEGRATION.md` | Parv | Ishani |
| `MASTER_PLAN.md` | Ishani | All |

---

## Workstream Split (Next Sprint)

### Ishani
- Dynamic COMPASS-modulated thresholds (`parliament/server.py`, `parliament/speaker.py`)
- Per-minister threshold support (`parliament/config.yaml`)
- SUPPLY minister — fifth minister for supply chain attacks
- AgentDojo benchmark runner (`benchmarks/agentdojo_runner.py`)
- OpenClaw-native benchmark scenarios (`benchmarks/openclaw_native/`)
- Paper §3 (architecture), §5 (evaluation), §7 (limitations)

### Parv
- EXECUTOR corpus quality pass — tighten L1/L2 to reduce benign FPR
- VAULT corpus quality pass — most aggressive minister, needs pruning
- NAVIGATOR corpus quality pass — trajectory drift patterns
- LEAKAGE minister — system prompt leakage (OWASP A07)
- SUPPLY minister corpus patterns (Ishani builds the minister code)
- Plugin args serialization fix
- COMPASS session seeding for live OpenClaw sessions
- Gateway hook investigation and spec document
- Paper §6 (related work update with new findings)

### Janya
- CHANNEL corpus quality pass
- New EXECUTOR patterns for supply chain (T1195)
- `benchmarks/threshold_sweep.py` improvements — finer sweep granularity
- AgentDojo integration testing

### Pranitha
- VAULT corpus quality pass (second pass on existing patterns)
- `benchmarks/benign_traces.py` — add 25 more benign sessions
- `compass_calibrator.py` — fix hijacked label (already done, verify)
- COMPASS corpus pairs — add 50 more aligned/hijacked pairs

---

## Current Benchmark Numbers (June 1, 2026)

| Metric | Value | Notes |
|---|---|---|
| InjecAgent strict recall | 98.4% | threshold=0.55 |
| InjecAgent loose recall | 100% | zero attacks allowed through |
| InjecAgent FPR | 88.2% | representation mismatch — see FINDINGS.md |
| InjecAgent F1 | 0.687 | at threshold=0.55 |
| Benign FPR (native format) | 2.1% | threshold=0.725 |
| Parliament p50 latency | 826ms | RTX 4090, BGE bge-base-en-v1.5 |
| Parliament p95 latency | 1649ms | first-call CUDA warm-up dominates |
| Smoke test | PASS (7/7) | threshold=0.71 |

---

## Key Technical Findings (June 1, 2026)

See `FINDINGS.md` for full details. Summary:

1. OpenClaw 2026.4.15 ships with bugs #5513 and #5943 already fixed
2. `before_tool_call` works correctly in embedded mode (`--local`)
3. Gateway mode has NO pre-execution hook — systemic finding, not a Kavach bug
4. Plugin requires three API fixes for OC 2026.4.15 (toolName, toolKind, timeout)
5. Corpus collection name mismatch fixed (kavach_compass → kavach_compass_calibration)
6. Dynamic thresholds are the #1 architectural priority to fix FPR
