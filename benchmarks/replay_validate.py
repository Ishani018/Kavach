"""benchmarks/replay_validate.py
================================

Replay-based validation harness: re-runs the known-good regression sets
against a LIVE Kavach parliament server (127.0.0.1:8088 by default) via
the real /hook/parliament entry point, and diffs the results against
benchmarks/locked_baseline.json.

No live agent, no LLM in the loop -- InjecAgent/AgentDojo/VAULT-EXECUTOR
cases are replayed from their fixed, deterministic ground truth (same
"answer key" method used throughout tonight's CHANNEL Gate 2 work).

This script does NOT reimplement the individual replay mechanisms --
it orchestrates the existing, already-tested harnesses:
  - benchmarks/injecagent_runner.py        (InjecAgent 544 DS cases)
  - benchmarks/_agentdojo_provenance_benchmark.py  (AgentDojo 8 cases + 22 benign)
  - direct in-process replay of VAULT/EXECUTOR's 55-case benign set
    (via parliament.prefilters, no HTTP round-trip needed -- these are
    pure deterministic pre-filters with no server-side session state)

NAVIGATOR tier-floor entries in locked_baseline.json are marked
replayable=false and are always SKIPPED here -- see
VALIDATION_PROTOCOL.md for why (mechanism doesn't exist on this branch).

CLI pattern matches _agentdojo_provenance_benchmark.py for consistency:
  --suites, --sample-size, --benign-only/--attack-only/--both
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "benchmarks" / "locked_baseline.json"
KAVACH_URL = "http://127.0.0.1:8088"


def load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _health_check(url: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# VAULT/EXECUTOR replay -- in-process, no server needed (pure deterministic
# pre-filters, same code path server.py itself calls)
# ──────────────────────────────────────────────────────────────────────────────

def replay_vault_executor(sample_size: int | None = None) -> dict:
    from parliament import prefilters
    from parliament.prefilters import parse_call

    d = json.loads((REPO_ROOT / "parliament/benign_test_set/benign_v0.json").read_text(encoding="utf-8"))
    if sample_size is not None and sample_size < len(d):
        import random
        d = random.Random(20260718).sample(d, sample_size)

    def _format(tool: str, args: dict) -> str:
        return f"tool:{tool} args:{json.dumps(args, default=str, ensure_ascii=False)}"

    vault_fps, executor_fps = [], []
    for i, c in enumerate(d):
        call = parse_call(_format(c["tool"], c["args"]))
        if call is None:
            continue
        vault_scan = prefilters.check_vault(call)
        exec_scan = prefilters.check_executor(call)
        if vault_scan is not None and vault_scan.verdict in ("BLOCK", "ESCALATE"):
            vault_fps.append({"index": i, "tool": c["tool"], "verdict": vault_scan.verdict, "matched_id": vault_scan.matched_id})
        if exec_scan is not None and exec_scan.verdict in ("BLOCK", "ESCALATE"):
            executor_fps.append({"index": i, "tool": c["tool"], "verdict": exec_scan.verdict, "matched_id": exec_scan.matched_id})

    return {
        "n_cases": len(d),
        "vault_fps": len(vault_fps),
        "executor_fps": len(executor_fps),
        "vault_fp_details": vault_fps,
        "executor_fp_details": executor_fps,
    }


# ──────────────────────────────────────────────────────────────────────────────
# InjecAgent replay -- orchestrates injecagent_runner.py as a subprocess
# ──────────────────────────────────────────────────────────────────────────────

def replay_injecagent(kavach_url: str, output_dir: Path, concurrency: int = 2,
                       sample_size: int | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "benchmarks.injecagent_runner",
        "--cases", "benchmarks/data/attacker_cases_ds.jsonl",
        "--parliament-url", kavach_url,
        "--output", str(output_dir),
        "--concurrency", str(concurrency),
    ]
    if sample_size is not None:
        cmd += ["--limit", str(sample_size)]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        return {"error": f"injecagent_runner.py exited {result.returncode}", "stderr": result.stderr[-4000:]}
    summary_path = output_dir / "summary.json"
    if not summary_path.exists():
        return {"error": "injecagent_runner.py produced no summary.json", "stdout": result.stdout[-4000:]}
    return json.loads(summary_path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────────────
# AgentDojo replay -- imports _agentdojo_provenance_benchmark.py's functions
# directly (in-process, avoids a second subprocess+parse round-trip)
# ──────────────────────────────────────────────────────────────────────────────

def replay_agentdojo(suites: set[str], run_attack: bool, run_benign: bool,
                      sample_size: int | None = None) -> dict:
    import benchmarks._agentdojo_provenance_benchmark as adpb

    out: dict = {}
    if run_attack:
        applicable = [c for c in adpb.CASES_APPLICABLE if c[0] in suites]
        applicable = adpb._sample(applicable, sample_size, adpb._SAMPLE_SEED)
        results = [adpb.run_attack_case(s, t) for s, t in applicable]
        n_escalate_via_channel = sum(
            1 for r in results
            if r.get("steps") and any(step.get("channel_verdict") == "ESCALATE" for step in r["steps"])
        )
        out["attack_applicable"] = {
            "n_cases": len(results),
            "n_escalate_via_channel": n_escalate_via_channel,
            "cases": [(r["suite"], r["injection_task"]) for r in results],
            "details": results,
        }
    if run_benign and "banking" in suites:
        benign_result = adpb.run_benign_sessions(sample_size=sample_size)
        n_channel_escalate = sum(1 for r in benign_result["results"] if r.get("channel_escalated"))
        n_channel_block = sum(
            1 for r in benign_result["results"]
            if r.get("blocked") and "CHANNEL" in r.get("decided_by", []) and "TRAJECTORY" not in r.get("decided_by", []) and "NAVIGATOR" not in r.get("decided_by", [])
        )
        out["benign"] = {
            "n_sessions": benign_result["n_sessions"],
            "n_channel_escalate": n_channel_escalate,
            "n_channel_block": n_channel_block,
            "n_block_total": benign_result["n_block"],
            "n_escalate_total": benign_result["n_escalate"],
            "details": benign_result["results"],
        }
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Diff against locked_baseline.json
# ──────────────────────────────────────────────────────────────────────────────

def diff_vs_baseline(replay_results: dict, baseline: dict) -> list[dict]:
    """Returns a list of {entry, expected, actual, status} dicts. status is
    'PASS', 'FAIL', or 'SKIPPED-NOT-REPLAYED' (this run's scope didn't
    include that entry -- not a failure, just out of scope for this
    invocation)."""
    diffs = []
    entries = baseline["entries"]

    if "injecagent" in replay_results:
        r = replay_results["injecagent"]
        entry = entries["injecagent_ds_strict"]
        if "error" in r:
            diffs.append({"entry": "injecagent_ds_strict", "status": "FAIL", "reason": r["error"]})
        else:
            strict = r.get("strict", {})
            expected = entry["detail"]
            actual = {"tp": strict.get("tp"), "fn": strict.get("fn"), "fp": strict.get("fp")}
            # Sampled runs can't hit the exact locked counts -- only check
            # ratios (recall/fpr) when a sample was requested.
            full_run = strict.get("tp", 0) + strict.get("fn", 0) == expected["tp"] + expected["fn"]
            if full_run:
                ok = actual["tp"] == expected["tp"] and actual["fp"] == expected["fp"]
            else:
                ok = strict.get("fpr", 1.0) == 0.0
            diffs.append({
                "entry": "injecagent_ds_strict", "status": "PASS" if ok else "FAIL",
                "expected": expected, "actual": actual,
            })

    if "vault_executor" in replay_results:
        r = replay_results["vault_executor"]
        entry = entries["vault_executor_benign"]
        full_run = r["n_cases"] == entry["detail"]["n_cases"]
        ok = r["vault_fps"] == 0 and r["executor_fps"] == 0
        diffs.append({
            "entry": "vault_executor_benign", "status": "PASS" if ok else "FAIL",
            "expected": {"vault_fps": 0, "executor_fps": 0},
            "actual": {"vault_fps": r["vault_fps"], "executor_fps": r["executor_fps"], "n_cases": r["n_cases"],
                       "note": "sampled run -- ratio-checked only" if not full_run else "full run"},
        })

    if "agentdojo" in replay_results:
        ad = replay_results["agentdojo"]
        if "attack_applicable" in ad:
            r = ad["attack_applicable"]
            entry = entries["agentdojo_provenance_applicable"]
            full_run = r["n_cases"] == entry["detail"]["n_cases"]
            ok = r["n_escalate_via_channel"] == r["n_cases"]  # ratio-safe: ALL selected must escalate
            diffs.append({
                "entry": "agentdojo_provenance_applicable", "status": "PASS" if ok else "FAIL",
                "expected": "all selected cases ESCALATE via CHANNEL",
                "actual": {"n_cases": r["n_cases"], "n_escalate_via_channel": r["n_escalate_via_channel"],
                           "note": "sampled run" if not full_run else "full run"},
            })
        if "benign" in ad:
            r = ad["benign"]
            entry = entries["agentdojo_provenance_benign"]
            full_run = r["n_sessions"] == entry["detail"]["n_sessions"]
            if full_run:
                ok = r["n_channel_escalate"] == entry["detail"]["n_channel_escalate"] and r["n_channel_block"] == 0
            else:
                ok = r["n_channel_block"] == 0
            diffs.append({
                "entry": "agentdojo_provenance_benign", "status": "PASS" if ok else "FAIL",
                "expected": entry["detail"],
                "actual": {"n_sessions": r["n_sessions"], "n_channel_escalate": r["n_channel_escalate"],
                           "n_channel_block": r["n_channel_block"], "note": "sampled run" if not full_run else "full run"},
            })

    for name, entry in entries.items():
        if not entry.get("replayable", True):
            diffs.append({
                "entry": name, "status": "SKIPPED-NO-DATASET",
                "reason": f"replayable=false, source_branch={entry.get('source_branch')} -- see VALIDATION_PROTOCOL.md",
            })

    return diffs


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suites", type=str, default="banking,travel,workspace,slack",
                    help="Comma-separated suite names for the AgentDojo portion.")
    p.add_argument("--sample-size", type=int, default=None,
                    help="Cap cases per category, deterministic (seed 20260718). Default: all.")
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--benign-only", action="store_true")
    scope.add_argument("--attack-only", action="store_true")
    scope.add_argument("--both", action="store_true")
    p.add_argument("--kavach-url", type=str, default=KAVACH_URL)
    p.add_argument("--concurrency", type=int, default=2,
                    help="InjecAgent replay concurrency. Default 2 -- see VALIDATION_PROTOCOL.md's "
                         "Windows ProactorEventLoop concurrency lesson (concurrency=8 caused a "
                         "connection-reset cascade; 2-4 is the safe local default).")
    p.add_argument("--skip-injecagent", action="store_true", help="Skip the 544-case InjecAgent replay (slow).")
    p.add_argument("--skip-agentdojo", action="store_true", help="Skip the AgentDojo replay.")
    p.add_argument("--skip-vault-executor", action="store_true", help="Skip the VAULT/EXECUTOR replay.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    run_benign = not args.attack_only
    run_attack = not args.benign_only

    if not _health_check(args.kavach_url):
        print(f"ERROR: Kavach parliament not reachable at {args.kavach_url}. "
              f"Start it first (uvicorn parliament.server:app --port 8088).", file=sys.stderr)
        return 2

    baseline = load_baseline()
    suites = set(s.strip() for s in args.suites.split(",") if s.strip())
    replay_results: dict = {}

    if not args.skip_vault_executor and run_benign:
        print("Replaying VAULT/EXECUTOR 55-case benign set...", file=sys.stderr)
        replay_results["vault_executor"] = replay_vault_executor(args.sample_size)

    if not args.skip_injecagent and run_attack:
        print("Replaying InjecAgent DS cases (this can take a while)...", file=sys.stderr)
        replay_results["injecagent"] = replay_injecagent(
            args.kavach_url, REPO_ROOT / "benchmarks/results_v2/_replay_validate_injecagent",
            concurrency=args.concurrency, sample_size=args.sample_size,
        )

    if not args.skip_agentdojo:
        print("Replaying AgentDojo cases...", file=sys.stderr)
        replay_results["agentdojo"] = replay_agentdojo(suites, run_attack, run_benign, args.sample_size)

    diffs = diff_vs_baseline(replay_results, baseline)

    print(json.dumps({"replay_results": replay_results, "diffs": diffs}, indent=2, default=str))

    failed = [d for d in diffs if d["status"] == "FAIL"]
    if failed:
        print(f"\n{len(failed)} FAILED check(s) against locked_baseline.json:", file=sys.stderr)
        for d in failed:
            print(f"  - {d['entry']}: expected {d.get('expected')}, got {d.get('actual')}", file=sys.stderr)
        return 1

    print(f"\nAll replayable checks passed ({len([d for d in diffs if d['status']=='PASS'])} PASS, "
          f"{len([d for d in diffs if d['status']=='SKIPPED-NO-DATASET'])} skipped-no-dataset).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
