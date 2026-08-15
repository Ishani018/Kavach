# Kavach Validation Protocol

Replay-based, CI/CD-style regression validation for the parliament's
deterministic and near-deterministic detection paths. This protocol
governs `validate.py`, `benchmarks/replay_validate.py`, and
`benchmarks/locked_baseline.json`.

## Scope: what this protocol validates, and what it does NOT

**This protocol validates detection regression on known trajectories.**
It replays fixed, pre-recorded call sequences (InjecAgent's 544 DS
cases, AgentDojo's 8 ground-truth attack cases + 22 real benign
sessions, VAULT/EXECUTOR's 55-case benign set) through the live
parliament and checks the verdicts against locked, reviewed numbers in
`locked_baseline.json`. A green run means: **nothing that used to be
caught stopped being caught, and nothing that used to be clean started
false-positiving, on these specific known cases.**

**It does NOT discover new agent behaviors.** The original 39/81
NAVIGATOR miss set (the empirical basis for the tier-floor mechanism)
was found by running a live 100-case forced-format InjecAgent batch
against a real local model and manually triaging misses — replay CI
cannot find gaps like that, because it only re-checks cases someone
already looked at once. New attack surface, new tool-naming
conventions, new environments (AgentDojo's other suites, a live agent
loop) require a fresh live/manual pass, not a passing CI badge.

**It does NOT measure utility.** Whether Kavach's interventions break
a legitimate agent's ability to complete its task (AgentDojo's
`utility_under_attack` metric, benign-utility regression) is a
separate, live-agent concern this protocol doesn't touch.

**A passing Tier A/B/C run on kavach-rearch does NOT mean NAVIGATOR's
three baseline numbers were re-verified.** `navigator_tier_floor_malicious`
(43/43), `navigator_tier_floor_benign` (32/32), and
`navigator_channel_regression` (0/29) in `locked_baseline.json` are all
marked `"replayable": false, "source_branch": "navigator-rearch"`.
`benchmarks/replay_validate.py` always SKIPs these three checks — they
show up in its output as `SKIPPED-NO-DATASET`, never as `PASS`. **A
green CI check or a clean `validate.py --tier C` exit code on
kavach-rearch says nothing about whether NAVIGATOR's tier-floor
mechanism still works** — that mechanism (`parliament/navigator_tiers.py`)
does not exist on this branch at all. Re-verifying those three numbers
requires checking out `navigator-rearch` specifically and running its
own equivalent harness there. Do not read a passing badge here as
"everything including NAVIGATOR was just checked" — it wasn't.

## Known limitations (open, not blockers)

- **Benign coverage is banking-suite only.** All 22 real AgentDojo
  benign sessions (`parliament/benign_test_set/real_benign_trajectories.json`)
  come from the `banking` suite. Zero false-positive coverage exists
  yet for `travel`/`workspace`/`slack` benign agent behavior — a clean
  Tier B/C run says nothing about FP rate on those three suites. Not a
  blocker for tonight's build; tracked here as an explicit gap for
  whoever builds out benign fixtures for the other suites next.
- **NAVIGATOR's three baseline numbers are reference-only** (see above)
  — not a limitation to fix so much as a structural fact of the
  current two-branch split. Resolving it requires either merging
  NAVIGATOR-domain code back onto a shared branch, or building a
  parallel replay harness on `navigator-rearch` itself.
- **Tier B fails on `navigator-rearch` by design, not by bug.**
  `benchmarks/replay_validate.py`'s AgentDojo replay path imports
  `benchmarks/_agentdojo_provenance_benchmark.py`, which was introduced
  on `kavach-rearch` in commit `6982522` (tonight's CHANNEL Gate 2
  work) and was never part of the CI/CD infra cherry-pick — it does not
  exist on `navigator-rearch` at all. Confirmed via a real GitHub
  Actions run on `navigator-rearch`
  ([29638959686](https://github.com/Ishani018/Kavach/actions/runs/29638959686)):
  Tier A passes cleanly (correctly auto-discovers and runs only
  `test_speaker.py`, the module that actually exists there), Tier B
  fails with `ModuleNotFoundError: No module named
  'benchmarks._agentdojo_provenance_benchmark'`. **A PR opened against
  `navigator-rearch` today will show a genuine, permanent Tier B
  failure until this is resolved** — either by backporting the
  AgentDojo harness (crosses the same branch-domain boundary the
  NAVIGATOR-code cherry-pick was rejected for), or by making
  `replay_validate.py` degrade this specific check to
  `SKIPPED-NO-DATASET` on branches where the module is absent (the same
  pattern already used for NAVIGATOR's three entries). Left
  unresolved and explicitly documented here rather than silently
  patched, since choosing between those two fixes is a real decision,
  not a mechanical one.

## The Windows ProactorEventLoop concurrency lesson

The 544-case InjecAgent replay was first attempted at `--concurrency
8` and suffered a sustained `ConnectionResetError: [WinError 10054]`
cascade in asyncio's Windows ProactorEventLoop
(`_ProactorBasePipeTransport._call_connection_lost`) roughly 5 minutes
into a ~38-minute run — only 60 of 1054+ expected requests actually
completed before the cascade began. The Kavach server process itself
survived (confirmed via `netstat` still showing it `LISTENING`, and a
later successful `/health` call), but client-side, the run was
unusable. A re-run at `--concurrency 2` completed cleanly with **zero**
connection resets across all 1054 cases.

**Rule: default to concurrency 2–4 for any local run on Windows.** This
is a client-side workaround, not a server fix — `parliament/server.py`'s
event loop policy was deliberately left untouched (out of scope,
per explicit instruction, the first time this was hit). `validate.py`
and `benchmarks/replay_validate.py` both default `--concurrency` to 2
for this reason. Raise it only on Linux/macOS CI runners or after
confirming the Windows-specific instability doesn't apply to your
environment.

## Locked baseline numbers

See `benchmarks/locked_baseline.json` for the full, structured list.
Changing any locked number is a **reviewed act** (Ishani + Parv),
never automatic — `validate.py`/`replay_validate.py` exit nonzero on
any deviation and print a diff; they never auto-retune the baseline
file.

Summary (full detail, dataset paths, and replayability flags live in
the JSON file itself):

| Entry | Value | Replayable from kavach-rearch? |
|---|---|---|
| `injecagent_ds_strict` | 544/544 strict recall, 0% FPR | Yes |
| `agentdojo_provenance_applicable` | 5/5 ESCALATE via CHANNEL | Yes |
| `agentdojo_provenance_benign` | 5/22 ESCALATE, 0/22 BLOCK (CHANNEL only) | Yes |
| `vault_executor_benign` | 0/55 (corrected from originally-reported 0/77 — see JSON note) | Yes |
| `navigator_tier_floor_malicious` | 43/43 ESCALATE | **No — navigator-rearch reference only** |
| `navigator_tier_floor_benign` | 32/32 ESCALATE, 0 BLOCK | **No — navigator-rearch reference only** |
| `navigator_channel_regression` | 0/29 regressed | **No — navigator-rearch reference only** |

## The tiers

### Tier A — unit suites (seconds)
`python -m parliament.test_channel_taint` (13 tests, includes the
tokenizer regression tests) and `python -m parliament.test_speaker`
(12 tests). **pytest is not installed in this venv** — both are run
via direct module invocation, not `pytest`. Always run before every
push (local hook, see below).

### Tier B — sampled replay census (minutes)
Runs Tier A first, then `benchmarks/replay_validate.py` with
`--sample-size 50 --skip-injecagent` (the full 544-case InjecAgent
replay is Tier C's job — too slow for a pre-push hook). Covers both
benign and attack sides for VAULT/EXECUTOR and AgentDojo. Sampled runs
check ratios (e.g. "0 FPs in the sampled subset", "all selected cases
escalate") rather than the exact locked counts, since a sample can't
hit an exact count by construction.

### Tier C — full replay (longer, CI-scale)
Runs Tier B first, then the full, unsampled replay: all 544 InjecAgent
DS cases, all 8 AgentDojo attack cases, all 22 benign sessions, all 55
VAULT/EXECUTOR cases. Includes a relative latency check — compared
against a **local reference measurement**, not the locked absolute
latency baseline (`~78ms` clean, `~0.035ms/call` provenance overhead)
directly, since CI hardware is not the Dell the original numbers were
measured on. The locked absolute latency numbers exist for
documentation/comparison, not as a hard CI gate.

## CI/CD wiring

- **Local pre-push hook** (`.git/hooks/pre-push`, not tracked — see
  `scripts/install-hooks.sh` or the setup note in the repo root):
  Tier A always; Tier B additionally when the push touches
  `parliament/`, `corpus_v2/`, or vocabulary/pattern files.
- **GitHub Actions** (`.github/workflows/validate.yml`): Tier A + Tier
  B on push/PR to both `kavach-rearch` and `navigator-rearch`. Latency
  checks are skipped in cloud CI (shared, variable-performance
  runners — no meaningful "local reference" to compare against).
  Cross-branch PRs (a PR that touches both CHANNEL/NAVIGATOR-relevant
  paths) additionally run the CHANNEL↔NAVIGATOR interface contract
  test (`test_provenance_record_schema_frozen` in
  `test_channel_taint.py`), since that frozen 5-field schema is the
  one contract both branches must honor even while their
  implementations diverge.
