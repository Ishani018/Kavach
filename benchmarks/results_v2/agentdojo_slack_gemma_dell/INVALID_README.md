# INVALID — do not cite

`agentdojo_summary.json` in this directory (`with_kavach`: 108 calls, 40 blocks,
0.0% ASR, 0.0% utility) is **not a valid result.**

**Root cause:** 93/105 baseline trajectories (90/105 with-Kavach) died at message
5 — the assistant's turn immediately after the *first* tool-call result —
emitting the literal garbage token `<|tool_response>` instead of continuing.
`GemmaTolerantLLM` (`benchmarks/run_agentdojo_kavach.py`) was sending tool
results to Ollama as `role="tool"`, a role Gemma's chat template does not
support, producing a degenerate echo. Since both baseline and with-Kavach die
at the same point, neither `attack_success_rate` nor `utility_under_attack`
here measures anything real, and the 40 "blocks" are not evidence of Kavach
blocking benign task-completion calls — they're artifacts of mostly-dead,
single-tool-call trajectories.

**Fix:** `GemmaTolerantLLM(..., tool_delimiter="user")` — folds tool results
into a `user` turn instead of the unsupported `tool` role. Verified on a
25-pair pilot: 0/15 degenerate `<|tool_response>` outputs (was 88-93%).

**Status:** fix applied and pilot-verified; full corrected run
(`agentdojo_slack_gemma_dell_fix2/` or successor) has not yet completed. Do not
report any number from this directory in the paper. See
`HANDOFF_2026-07-06_agentdojo_gemma4_fix.md` in this same directory for the full
investigation.
