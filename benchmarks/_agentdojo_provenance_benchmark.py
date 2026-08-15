"""AgentDojo full-pipeline provenance benchmark: taint + provenance (+
NAVIGATOR tier-floor if merged) against the corrected 8-case
categorization (5 applicable / 2 no-source-step / 1 no-destination-tool)
and the 22 real benign sessions (now with real dispatched tool_output).

No live agent -- attacker sequences come from AgentDojo's own
ground_truth() (the "answer key" method, same as Gate 1), and calls are
sent to the real /hook/parliament endpoint via the SAME wire format
kavach_agentdojo_defense.py's KavachDefense.query() uses, so this
exercises the real entry point's behavior, not a reimplementation.
"""
import argparse
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Fixed seed for deterministic sampling -- --sample-size N must select the
# SAME N cases on every run (reproducibility for CI-style re-verification),
# not a fresh random subset each time.
_SAMPLE_SEED = 20260718

# Unique per invocation of this script. Kavach's session state
# (SessionProvenance/SessionTaint) is keyed by session_id and persists
# server-side across process runs (in-memory dict, no TTL) -- reusing a
# fixed session_id string across repeated benchmark runs (as the original
# f"gt-benchmark-{suite}-{task}" did) let stale state from an EARLIER,
# broken run (e.g. tonight's pre-tool_output-fix attempt) leak into a
# later, fixed run and silently mask real results. Found via a direct
# probe: the exact same call sequence against a FRESH session_id correctly
# ESCALATEd via CHANNEL-PROVENANCE, but the benchmark's reused session_id
# still showed ALLOW.
_RUN_TAG = str(int(time.time()))

from agentdojo.task_suite.load_suites import get_suite, get_suites
from agentdojo.base_tasks import BaseUserTask
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.functions_runtime import FunctionsRuntime

KAVACH_URL = "http://127.0.0.1:8088"

ALL_SUITES = sorted(get_suites("v1.2").keys())

# The 8 AgentDojo multi-step attack cases, corrected categorization from
# tonight's Gate 1 census.
CASES_APPLICABLE = [
    ("workspace", "injection_task_3"),
    ("workspace", "injection_task_4"),
    ("travel", "injection_task_3"),
    ("banking", "injection_task_8"),
    ("slack", "injection_task_4"),
]
CASES_NO_SOURCE_STEP = [
    ("banking", "injection_task_6"),
    ("slack", "injection_task_5"),
]
CASES_NO_DESTINATION_TOOL = [
    ("travel", "injection_task_4"),
]

# All 22 real benign fixture sessions are banking-suite sessions (confirmed
# via source_file inspection during tonight's regeneration) -- filtering
# benign sessions by --suites means filtering to whether "banking" is in
# the selected set, not a per-session suite field (the fixture doesn't
# carry one).
BENIGN_SUITES = frozenset({"banking"})


def _sample(cases: list, n: int | None, seed: int) -> list:
    """Deterministic sample of `cases`, fixed seed so repeated runs with
    the same --sample-size select the SAME subset (reproducibility for
    re-verification), not a fresh random draw each time. n=None or
    n >= len(cases) returns all cases unchanged (no shuffling -- order
    stays meaningful/stable when no sampling is requested)."""
    if n is None or n >= len(cases):
        return list(cases)
    rng = random.Random(seed)
    return rng.sample(cases, n)


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
    # SAME wire format as kavach_agentdojo_defense.py's _format_tool_call.
    args_str = json.dumps(args, default=str, ensure_ascii=False)
    return f"tool:{function} args:{args_str}"


def _stringify_result(result) -> str:
    # Matches _regenerate_benign_outputs.py's flattening -- str() on the
    # AgentDojo model/object, same as a real trajectory's serialized
    # 'tool' role content.
    if isinstance(result, list):
        return "\n".join(str(r) for r in result)
    return str(result)


def run_attack_case(suite_name: str, injection_task_id: str) -> dict:
    """Replays the injection_task's ground_truth() sequence (the attack
    steps only -- provenance's job is to catch the destination, not
    re-derive whether the user's own task was legitimate). Real injected
    environment content is constructed the same way as Gate 1 -- via
    ImportantInstructionsAttack.attack(), no live model."""
    suite = get_suite("v1.2", suite_name)
    ut_ids = list(suite.user_tasks.keys())
    ut = suite.user_tasks[ut_ids[0]]
    it_versions = suite._injection_tasks[injection_task_id]
    it = it_versions[list(it_versions.keys())[0]]

    attacker = ImportantInstructionsAttack(suite, _StubPipeline())
    injections = attacker.attack(ut, it)
    env = suite.load_and_inject_default_environment(injections)
    task_env = ut.init_environment(env) if isinstance(ut, BaseUserTask) else env

    try:
        gt = list(it.ground_truth(task_env))
    except Exception as e:
        return {"suite": suite_name, "injection_task": injection_task_id, "error": f"ground_truth() failed: {e}"}

    session_id = f"gt-benchmark-{_RUN_TAG}-{suite_name}-{injection_task_id}"
    # BUG FOUND: it.GOAL is the INJECTION task's goal -- the attacker's own
    # stated destination text (e.g. "...to 'mark.black-2134@gmail.com'"),
    # not the real user's instruction. Passing it as user_instruction made
    # CHANNEL classify the attacker's own planted destination as
    # USER_SUPPLIED (since it verbatim appears in "the user's instruction"),
    # incorrectly suppressing the ESCALATE that should have fired. The real
    # user's legitimate task text is ut.PROMPT (ut.GOAL is None for these
    # user tasks) -- that's what a real caller's context would actually
    # contain, since the injected instruction is never something the
    # legitimate user typed.
    user_instruction = getattr(ut, "PROMPT", None) or ""
    runtime = FunctionsRuntime(suite.tools)
    steps = []
    for i, fc in enumerate(gt):
        text = _format_tool_call(fc.function, dict(fc.args))
        # Dispatch the real call against the same environment ground_truth()
        # was computed over, so CHANNEL sees the real tool_output -- same
        # method as _regenerate_benign_outputs.py's "answer key" dispatch.
        try:
            result, error = runtime.run_function(task_env, fc.function, dict(fc.args))
            tool_output = None if error is not None else _stringify_result(result)
        except Exception:
            tool_output = None
        context = {
            "source": "agentdojo-provenance-benchmark",
            "call_n": i,
            "user_instruction": user_instruction,
            "tool_output": tool_output,
        }
        resp = _post_parliament(text, session_id, context)
        step = {
            "step": i,
            "function": fc.function,
            "args": dict(fc.args),
            "verdict": resp.get("verdict"),
            "decided_by": resp.get("speaker", {}).get("decided_by"),
            "matched_id": None,
        }
        ministers = resp.get("ministers", {})
        ch = ministers.get("CHANNEL", {})
        step["channel_verdict"] = ch.get("verdict")
        step["channel_matched_id"] = ch.get("matched_id")
        steps.append(step)
        if resp.get("verdict") == "BLOCK":
            break

    return {
        "suite": suite_name,
        "injection_task": injection_task_id,
        "n_steps": len(gt),
        "final_verdict": steps[-1]["verdict"] if steps else None,
        "final_decided_by": steps[-1]["decided_by"] if steps else None,
        "steps": steps,
    }


def run_benign_sessions(sample_size: int | None = None) -> dict:
    d = json.loads(Path("parliament/benign_test_set/real_benign_trajectories.json").read_text(encoding="utf-8"))
    d = _sample(d, sample_size, _SAMPLE_SEED)
    n_escalate = 0
    n_block = 0
    # Track WHICH minister decided each block/escalate, separately from
    # whether it happened -- required to distinguish CHANNEL's own
    # (locked, previously-verified 5/22 ESCALATE / 0 BLOCK) contribution
    # from NAVIGATOR/TRAJECTORY's independent, unrelated interaction. The
    # overall verdict alone can't tell these apart.
    results = []
    for item in d:
        session_id = f"gt-benchmark-benign-{_RUN_TAG}-{item['source_file']}"
        user_instr = item.get("user_task_text", "")
        escalated = False
        blocked = False
        decided_by_seen: set[str] = set()
        channel_escalated = False
        for i, c in enumerate(item["calls"]):
            text = _format_tool_call(c["tool"], c["args"])
            context = {
                "source": "agentdojo-provenance-benchmark", "call_n": i,
                "user_instruction": user_instr,
                "tool_output": c.get("tool_output"),
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
        if blocked:
            n_block += 1
        elif escalated:
            n_escalate += 1
        results.append({
            "source_file": item["source_file"], "blocked": blocked, "escalated": escalated,
            "decided_by": sorted(decided_by_seen), "channel_escalated": channel_escalated,
        })
    return {"n_sessions": len(d), "n_block": n_block, "n_escalate": n_escalate, "n_clean_pass": len(d) - n_block - n_escalate, "results": results}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--suites", type=str, default=",".join(ALL_SUITES),
        help=f"Comma-separated suite names to include (default: all installed -- {', '.join(ALL_SUITES)}).",
    )
    p.add_argument(
        "--sample-size", type=int, default=None,
        help="Cap the number of cases per category (attack cases and benign sessions each capped "
             "independently) to N, sampled deterministically (fixed seed %d). Default: all cases." % _SAMPLE_SEED,
    )
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--benign-only", action="store_true", help="Run only the 22 benign sessions.")
    scope.add_argument("--attack-only", action="store_true", help="Run only the AgentDojo attack cases.")
    scope.add_argument("--both", action="store_true", help="Run both (default).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    requested_suites = [s.strip() for s in args.suites.split(",") if s.strip()]
    unknown = [s for s in requested_suites if s not in ALL_SUITES]
    if unknown:
        print(f"ERROR: unknown suite(s) {unknown} -- installed suites are: {ALL_SUITES}", file=sys.stderr)
        sys.exit(1)
    suite_set = set(requested_suites)

    run_benign = not args.attack_only
    run_attack = not args.benign_only

    all_attack_cases = CASES_APPLICABLE + CASES_NO_SOURCE_STEP + CASES_NO_DESTINATION_TOOL
    selected_applicable = [c for c in CASES_APPLICABLE if c[0] in suite_set]
    selected_no_source = [c for c in CASES_NO_SOURCE_STEP if c[0] in suite_set]
    selected_no_dest = [c for c in CASES_NO_DESTINATION_TOOL if c[0] in suite_set]
    selected_applicable = _sample(selected_applicable, args.sample_size, _SAMPLE_SEED)
    selected_no_source = _sample(selected_no_source, args.sample_size, _SAMPLE_SEED)
    selected_no_dest = _sample(selected_no_dest, args.sample_size, _SAMPLE_SEED)
    n_attack_total_in_scope = len([c for c in all_attack_cases if c[0] in suite_set])
    n_attack_after_sample = len(selected_applicable) + len(selected_no_source) + len(selected_no_dest)

    benign_in_scope = bool(BENIGN_SUITES & suite_set) if run_benign else False
    if benign_in_scope:
        d_all = json.loads(Path("parliament/benign_test_set/real_benign_trajectories.json").read_text(encoding="utf-8"))
        n_benign_total = len(d_all)
        n_benign_after_sample = len(_sample(d_all, args.sample_size, _SAMPLE_SEED))
    else:
        n_benign_total = 0
        n_benign_after_sample = 0

    print("=" * 70)
    print("RUN SCOPE")
    print("=" * 70)
    print(f"suites selected:        {sorted(suite_set)}")
    print(f"sample-size:            {args.sample_size if args.sample_size is not None else 'all'} "
          f"(seed={_SAMPLE_SEED})")
    print(f"scope:                  {'both' if run_benign and run_attack else ('benign-only' if run_benign else 'attack-only')}")
    print(f"attack cases:           {n_attack_total_in_scope} total in scope -> {n_attack_after_sample} after sampling "
          f"({len(selected_applicable)} applicable, {len(selected_no_source)} no-source-step, "
          f"{len(selected_no_dest)} no-destination-tool)")
    print(f"benign sessions:        {n_benign_total} total in scope -> {n_benign_after_sample} after sampling "
          f"({'banking suite' if benign_in_scope else 'excluded -- banking not in --suites or --attack-only set'})")
    print()

    if run_attack:
        print("=" * 70)
        print(f"{len(selected_applicable)} STRUCTURALLY-APPLICABLE ATTACK CASES")
        print("=" * 70)
        for suite_name, it_id in selected_applicable:
            r = run_attack_case(suite_name, it_id)
            print(json.dumps(r, indent=2))
            print()

        print("=" * 70)
        print(f"{len(selected_no_source)} NO-SOURCE-STEP CASES (outside provenance's scope by design)")
        print("=" * 70)
        for suite_name, it_id in selected_no_source:
            r = run_attack_case(suite_name, it_id)
            print(json.dumps(r, indent=2))
            print()

        print("=" * 70)
        print(f"{len(selected_no_dest)} NO-DESTINATION-TOOL CASE(S) (outside provenance's scope by design)")
        print("=" * 70)
        for suite_name, it_id in selected_no_dest:
            r = run_attack_case(suite_name, it_id)
            print(json.dumps(r, indent=2))
            print()

    if run_benign and benign_in_scope:
        print("=" * 70)
        print("BENIGN SESSIONS")
        print("=" * 70)
        benign_result = run_benign_sessions(sample_size=args.sample_size)
        print(f"n_sessions={benign_result['n_sessions']} n_block={benign_result['n_block']} "
              f"n_escalate={benign_result['n_escalate']} n_clean_pass={benign_result['n_clean_pass']}")
        for r in benign_result["results"]:
            if r["blocked"] or r["escalated"]:
                print(" ", r)


if __name__ == "__main__":
    main()
