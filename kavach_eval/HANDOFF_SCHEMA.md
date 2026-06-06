# Kavach Eval — Handoff Schema (Parv → Ishani contract)

This is the **single file format** Parv dumps from the Dell after running the
Ministers. Everything in the analysis pipeline reads this. If Parv produces
this file correctly, all the heavy analysis (metrics, calibration, ablations)
runs without the GPU.

## File: `minister_runs.jsonl`

One JSON object per line. One line = one agent action that the Parliament judged.

```json
{
  "action_id": "agentdojo_banking_07_inj3",
  "benchmark": "agentdojo",
  "suite": "banking",
  "task_id": "user_task_7",
  "injection_id": "injection_task_3",
  "is_attack": true,
  "ground_truth": "BLOCK",
  "action": {
    "tool": "send_money",
    "args": {"recipient": "attacker_iban", "amount": 1000},
    "raw": "send_money(recipient='attacker_iban', amount=1000)"
  },
  "minister_votes": [
    {"minister": "EXECUTOR",  "vote": "BLOCK",   "confidence": 0.91, "reason": "...", "latency_ms": 210},
    {"minister": "VAULT",     "vote": "BLOCK",   "confidence": 0.88, "reason": "...", "latency_ms": 195},
    {"minister": "CHANNEL",   "vote": "ABSTAIN", "confidence": 0.50, "reason": "...", "latency_ms": 180},
    {"minister": "NAVIGATOR", "vote": "BLOCK",   "confidence": 0.79, "reason": "...", "latency_ms": 230}
  ],
  "model": "gemma-4-27b",
  "timestamp": "2026-06-09T11:00:00Z"
}
```

## Field rules

| Field | Required | Notes |
|---|---|---|
| `action_id` | yes | Unique per action. |
| `benchmark` | yes | `agentdojo` / `asb` / `injecagent` / `skill_inject` / `synthetic`. |
| `is_attack` | yes | `true` if this action is an injected/malicious action. |
| `ground_truth` | yes | `"BLOCK"` (attack should be stopped) or `"ALLOW"` (benign). This is the label everything is scored against. |
| `action` | yes | The agent action being judged. `raw` string is enough if structured args are hard. |
| `minister_votes` | yes | Array, one per Minister. `vote` ∈ {ALLOW, BLOCK, ABSTAIN}. `confidence` ∈ [0,1]. `latency_ms` optional but enables the latency analysis. |
| `model` | recommended | Lets us separate runs if Ministers use different models (important for correlation). |
| `suite`/`task_id`/`injection_id` | optional | AgentDojo provenance — useful for per-suite breakdowns. |

## What Parv does NOT need to do
- He does **not** run the Speaker. We run every Speaker variant offline from his votes.
- He does **not** compute any metrics. We do all of that.
- He does **not** tune parameters. We sweep them on his dumped votes.

His only job: run the Ministers over the benchmark, capture the four raw votes
+ confidences + ground truth, write one line per action.

## What we produce from this file
1. ASR / utility / FPR / FNR under every Speaker variant (max-score vs Bayesian)
2. Calibration report (reliability diagram, ECE) per Minister
3. Correlation matrix between Ministers (the rho we need)
4. Full ablation table (1..N Ministers, with/without COMPASS, with/without ABSTAIN)
5. Latency breakdown (p50/p95/p99) if latency_ms present
6. Parameter sweep recommendations (rho, BLOCK_THRESHOLD) to hand back to Parv

## Minimal viable dump
If Parv is time-pressed, the absolute minimum per line is:
`action_id`, `is_attack`, `ground_truth`, `minister_votes` (with vote+confidence).
Everything else degrades gracefully.
