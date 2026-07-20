"""benchmarks/_agentdojo_full_matrix_run.py
============================================

TRUE full AgentDojo matrix run: every (user_task, injection_task) pair
per suite -- AgentDojo's own standard benchmark convention (confirmed
by reading agentdojo.benchmark.benchmark_suite_with_injections()'s
source: it runs every user_task against every injection_task in the
suite, no compatibility filtering). Plus every user_task run
benign-only (no injection) for FP/utility baseline.

Each attack pair is categorized programmatically (APPLICABLE /
NO_SOURCE_STEP / NO_DESTINATION_TOOL / NEITHER) using the exact same
source/destination-tool detection channel_taint.py itself uses
(is_source_tool()/is_destination_tool()) -- not hand-picked.

--sample-size N: deterministic (seed 20260718) cap per suite, for
attack pairs AND benign-only runs independently, so a capped run still
gives a real per-suite read without committing to the full 1046-case
matrix.

Checkpointing: writes progress to a JSON file every N cases (default
25) so a partial result is recoverable if interrupted.

Report/benchmark task only -- does not commit anything, does not touch
parliament/channel_taint.py or server.py.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentdojo.task_suite.load_suites import get_suite, get_suites
from agentdojo.base_tasks import BaseUserTask
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.functions_runtime import FunctionsRuntime

from parliament.channel_taint import is_source_tool, is_destination_tool

KAVACH_URL = "http://127.0.0.1:8088"
_RUN_TAG = str(int(time.time()))
_SAMPLE_SEED = 20260718

ALL_SUITES = sorted(get_suites("v1.2").keys())


class _StubPipeline:
    name = "local"


def _post_parliament(text: str, session_id: str, context: dict) -> dict:
    payload = json.dumps({"text": text, "session_id": session_id, "context": context}).encode("utf-8")
    req = urllib.request.Request(
        f"{KAVACH_URL}/hook/parliament", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _format_tool_call(function: str, args: dict) -> str:
    args_str = json.dumps(args, default=str, ensure_ascii=False)
    return f"tool:{function} args:{args_str}"


def _stringify_result(result) -> str:
    if isinstance(result, list):
        return "\n".join(str(r) for r in result)
    return str(result)


def _sample(items: list, n: int | None, seed: int) -> list:
    if n is None or n >= len(items):
        return list(items)
    rng = random.Random(seed)
    return rng.sample(items, n)


def enumerate_matrix(suite_name: str) -> tuple[list[str], list[str]]:
    suite = get_suite("v1.2", suite_name)
    user_ids = sorted(suite.user_tasks.keys(), key=lambda s: (len(s), s))
    injection_ids = sorted(suite._injection_tasks.keys(), key=lambda s: (len(s), s))
    return user_ids, injection_ids


def run_attack_pair(suite_name: str, user_task_id: str, injection_task_id: str) -> dict:
    suite = get_suite("v1.2", suite_name)
    ut = suite.get_user_task_by_id(user_task_id)
    it_versions = suite._injection_tasks[injection_task_id]
    it = it_versions[list(it_versions.keys())[0]]

    attacker = ImportantInstructionsAttack(suite, _StubPipeline())
    try:
        injections = attacker.attack(ut, it)
        env = suite.load_and_inject_default_environment(injections)
        task_env = ut.init_environment(env) if isinstance(ut, BaseUserTask) else env
        gt = list(it.ground_truth(task_env))
    except Exception as e:
        return {
            "suite": suite_name, "user_task": user_task_id, "injection_task": injection_task_id,
            "error": f"{type(e).__name__}: {e}",
        }

    has_source_step = any(is_source_tool(fc.function) for fc in gt)
    has_destination_tool = any(is_destination_tool(fc.function) for fc in gt)
    if has_source_step and has_destination_tool:
        category = "APPLICABLE"
    elif not has_source_step and has_destination_tool:
        category = "NO_SOURCE_STEP"
    elif has_source_step and not has_destination_tool:
        category = "NO_DESTINATION_TOOL"
    else:
        category = "NEITHER"

    session_id = f"gt-matrix-{_RUN_TAG}-{suite_name}-{user_task_id}-{injection_task_id}"
    user_instruction = getattr(ut, "PROMPT", None) or ""
    runtime = FunctionsRuntime(suite.tools)
    steps = []
    for i, fc in enumerate(gt):
        text = _format_tool_call(fc.function, dict(fc.args))
        try:
            result, error = runtime.run_function(task_env, fc.function, dict(fc.args))
            tool_output = None if error is not None else _stringify_result(result)
        except Exception:
            tool_output = None
        context = {
            "source": "agentdojo-full-matrix-run", "call_n": i,
            "user_instruction": user_instruction, "tool_output": tool_output,
        }
        resp = _post_parliament(text, session_id, context)
        ministers = resp.get("ministers", {})
        ch = ministers.get("CHANNEL", {})
        steps.append({
            "step": i, "function": fc.function,
            "verdict": resp.get("verdict"),
            "decided_by": resp.get("speaker", {}).get("decided_by"),
            "channel_verdict": ch.get("verdict"),
        })
        if resp.get("verdict") == "BLOCK":
            break

    channel_fired = any(s["channel_verdict"] == "ESCALATE" for s in steps)
    final_verdict = steps[-1]["verdict"] if steps else None
    final_decided_by = steps[-1]["decided_by"] if steps else None
    return {
        "suite": suite_name, "user_task": user_task_id, "injection_task": injection_task_id,
        "category": category, "n_steps": len(gt),
        "final_verdict": final_verdict, "final_decided_by": final_decided_by,
        "channel_fired": channel_fired,
    }


def run_benign(suite_name: str, user_task_id: str) -> dict:
    suite = get_suite("v1.2", suite_name)
    ut = suite.get_user_task_by_id(user_task_id)
    env = suite.load_and_inject_default_environment({})
    task_env = ut.init_environment(env) if isinstance(ut, BaseUserTask) else env

    try:
        gt = list(ut.ground_truth(task_env))
    except Exception as e:
        return {"suite": suite_name, "user_task": user_task_id, "error": f"{type(e).__name__}: {e}"}

    session_id = f"gt-matrix-benign-{_RUN_TAG}-{suite_name}-{user_task_id}"
    user_instruction = getattr(ut, "PROMPT", None) or ""
    runtime = FunctionsRuntime(suite.tools)
    blocked = False
    escalated = False
    channel_escalated = False
    decided_by_seen: set[str] = set()
    for i, fc in enumerate(gt):
        text = _format_tool_call(fc.function, dict(fc.args))
        try:
            result, error = runtime.run_function(task_env, fc.function, dict(fc.args))
            tool_output = None if error is not None else _stringify_result(result)
        except Exception:
            tool_output = None
        context = {
            "source": "agentdojo-full-matrix-run-benign", "call_n": i,
            "user_instruction": user_instruction, "tool_output": tool_output,
        }
        resp = _post_parliament(text, session_id, context)
        v = resp.get("verdict")
        decided = resp.get("speaker", {}).get("decided_by")
        if v in ("BLOCK", "ESCALATE") and decided:
            decided_by_seen.add(decided)
        if resp.get("ministers", {}).get("CHANNEL", {}).get("verdict") == "ESCALATE":
            channel_escalated = True
        if v == "BLOCK":
            blocked = True
        elif v == "ESCALATE":
            escalated = True

    return {
        "suite": suite_name, "user_task": user_task_id, "n_steps": len(gt),
        "blocked": blocked, "escalated": escalated,
        "channel_escalated": channel_escalated, "decided_by": sorted(decided_by_seen),
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suites", type=str, default=",".join(ALL_SUITES))
    p.add_argument("--sample-size", type=int, default=None,
                    help="Cap attack pairs AND benign runs per suite independently, deterministic (seed %d)." % _SAMPLE_SEED)
    p.add_argument("--concurrency", type=int, default=2,
                    help="Parallel worker threads. Default 2 -- see VALIDATION_PROTOCOL.md's Windows "
                         "ProactorEventLoop concurrency lesson. Each case dispatches its own independent "
                         "AgentDojo environment and uses its own unique session_id, so thread-level "
                         "parallelism across cases is safe (no shared mutable state between cases).")
    p.add_argument("--checkpoint-every", type=int, default=25)
    p.add_argument("--checkpoint-path", type=str, default="benchmarks/results_v2/_full_matrix_checkpoint.json")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    suite_set = [s.strip() for s in args.suites.split(",") if s.strip()]
    checkpoint_path = Path(args.checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    all_attack_results: list[dict] = []
    all_benign_results: list[dict] = []
    n_done = 0

    def checkpoint(elapsed: float, complete: bool = False) -> None:
        checkpoint_path.write_text(json.dumps({
            "n_done": n_done, "elapsed_s": elapsed, "complete": complete,
            "attack_results": all_attack_results, "benign_results": all_benign_results,
        }, indent=2), encoding="utf-8")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for suite_name in suite_set:
            user_ids, injection_ids = enumerate_matrix(suite_name)
            pairs = [(u, it) for u in user_ids for it in injection_ids]
            pairs = _sample(pairs, args.sample_size, _SAMPLE_SEED)
            benign_ids = _sample(user_ids, args.sample_size, _SAMPLE_SEED)

            print(f"=== {suite_name}: {len(pairs)} attack pairs, {len(benign_ids)} benign runs "
                  f"(of {len(user_ids)}x{len(injection_ids)}={len(user_ids)*len(injection_ids)} total pairs, "
                  f"{len(user_ids)} total user_tasks) ===", file=sys.stderr)

            attack_futures = {pool.submit(run_attack_pair, suite_name, u, it): (u, it) for u, it in pairs}
            for fut in as_completed(attack_futures):
                u, it = attack_futures[fut]
                r = fut.result()
                all_attack_results.append(r)
                n_done += 1
                print(f"  [{n_done}] attack {suite_name}::{u}::{it}: category={r.get('category')} "
                      f"verdict={r.get('final_verdict')} decided_by={r.get('final_decided_by')} "
                      f"channel_fired={r.get('channel_fired')} err={r.get('error')}", file=sys.stderr)
                if n_done % args.checkpoint_every == 0:
                    elapsed = time.time() - t0
                    checkpoint(elapsed)
                    print(f"    [checkpoint] {n_done} cases, {elapsed:.0f}s elapsed", file=sys.stderr)

            benign_futures = {pool.submit(run_benign, suite_name, u): u for u in benign_ids}
            for fut in as_completed(benign_futures):
                u = benign_futures[fut]
                r = fut.result()
                all_benign_results.append(r)
                n_done += 1
                print(f"  [{n_done}] benign {suite_name}::{u}: blocked={r.get('blocked')} "
                      f"escalated={r.get('escalated')} channel_escalated={r.get('channel_escalated')} "
                      f"decided_by={r.get('decided_by')} err={r.get('error')}", file=sys.stderr)
                if n_done % args.checkpoint_every == 0:
                    elapsed = time.time() - t0
                    checkpoint(elapsed)
                    print(f"    [checkpoint] {n_done} cases, {elapsed:.0f}s elapsed", file=sys.stderr)

    elapsed = time.time() - t0
    checkpoint(elapsed, complete=True)

    print(json.dumps({"attack_results": all_attack_results, "benign_results": all_benign_results}, indent=2))

    print(f"\n=== TOTAL: {n_done} cases in {elapsed:.0f}s ({elapsed/max(n_done,1):.2f}s/case avg) ===", file=sys.stderr)


if __name__ == "__main__":
    main()
