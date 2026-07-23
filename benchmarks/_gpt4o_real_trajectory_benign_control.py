"""GPT-4o real-trajectory BENIGN control for the 629-attack replay in
_gpt4o_real_trajectory_expansion.py (benchmarks/results_v2/gpt4o_real_trajectory_expansion.json,
467/629 = 74.2% Kavach fired). That script never replayed AgentDojo's own
recorded NO-injection ("none") trajectories under the identical criterion
(Block-or-Escalate, any minister, anywhere in the session) -- so 74.2% had
no benign control at its own granularity. This script closes that gap.

Source: same sparse checkout as the attack-trajectory script, this time
reading each user_task's `none/none.json` (attack_type=None,
injection_task_id=None -- AgentDojo's own recorded utility run, no attacker
instruction ever injected) across all 4 suites. One file per user_task, not
crossed with any injection_task (there is nothing to cross with -- these are
the model's ordinary, unattacked behavior).

Dispatch, wire format, session-level "ever fired" aggregation, and the
BLOCK-or-ESCALATE-any-minister-anywhere criterion are copied verbatim from
_gpt4o_real_trajectory_expansion.py so the two numbers are comparable by
construction, not just by convention.
"""
import json
import time
import urllib.request
from pathlib import Path

KAVACH_URL = "http://127.0.0.1:8088"
_RUN_TAG = str(int(time.time()))

RUNS_ROOT = Path(__file__).resolve().parent.parent / "scratch_agentdojo_repo" / "runs" / "gpt-4o-2024-05-13"
SUITES = ["banking", "slack", "travel", "workspace"]


def post(text, session_id, context):
    payload = json.dumps({"text": text, "session_id": session_id, "context": context}).encode("utf-8")
    req = urllib.request.Request(
        f"{KAVACH_URL}/hook/parliament", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fmt(function, args):
    return f"tool:{function} args:{json.dumps(args, default=str, ensure_ascii=False)}"


def extract_user_instruction(messages):
    for m in messages:
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def extract_steps(messages):
    by_call_id = {}
    for m in messages:
        if m.get("role") == "tool" and m.get("tool_call_id"):
            by_call_id[m["tool_call_id"]] = m.get("content")

    steps = []
    for m in messages:
        if m.get("role") != "assistant" or not m.get("tool_calls"):
            continue
        for tc in m["tool_calls"]:
            fn = tc.get("function")
            args = tc.get("args") or {}
            tool_output = by_call_id.get(tc.get("id"))
            steps.append((fn, args, tool_output))
    return steps


def find_trajectory_files():
    files = []
    for suite in SUITES:
        suite_dir = RUNS_ROOT / suite
        if not suite_dir.is_dir():
            continue
        for ut_dir in sorted(suite_dir.iterdir()):
            # Only real user_task_* directories -- injection_task_*/none/none.json
            # also exists but is a harness bookkeeping artifact, not a distinct
            # user task (its own user_task_id field reads "injection_task_N",
            # not a real task; including it double-counted 27 bogus benign
            # trajectories on top of AgentDojo's real 97 user tasks).
            if not ut_dir.name.startswith("user_task_"):
                continue
            none_file = ut_dir / "none" / "none.json"
            if none_file.is_file():
                files.append((suite, ut_dir.name, none_file))
    return files


def main():
    files = find_trajectory_files()
    print(f"Found {len(files)} real no-injection (benign/utility) trajectory files "
          f"across {len(SUITES)} suites.\n")

    results = []
    n_kavach_blocked_or_escalated = 0
    n_channel_fired = 0
    n_errors = 0
    for i, (suite, ut_id, path) in enumerate(files):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            n_errors += 1
            results.append({"suite": suite, "user_task": ut_id, "file": path.name,
                             "error": f"failed to load: {e}"})
            continue

        agentdojo_security = d.get("security")
        agentdojo_utility = d.get("utility")
        user_instruction = extract_user_instruction(d.get("messages", []))
        steps = extract_steps(d.get("messages", []))

        session_id = f"gpt4o-real-benign-{_RUN_TAG}-{suite}-{ut_id}"
        final_verdict = None
        final_decided_by = None
        channel_ever_escalated = False
        channel_escalate_matched_id = None
        kavach_ever_fired = False
        kavach_fired_verdict = None
        kavach_fired_decided_by = None
        step_errors = 0
        for si, (fn, args, tool_output) in enumerate(steps):
            text = fmt(fn, args)
            context = {
                "source": "gpt4o-real-trajectory-benign-control", "call_n": si,
                "user_instruction": user_instruction, "tool_output": tool_output,
            }
            try:
                resp = post(text, session_id, context)
            except Exception as e:
                step_errors += 1
                continue
            ch = resp.get("ministers", {}).get("CHANNEL", {})
            final_verdict = resp.get("verdict")
            final_decided_by = resp.get("speaker", {}).get("decided_by")
            if final_verdict in ("BLOCK", "ESCALATE") and not kavach_ever_fired:
                kavach_ever_fired = True
                kavach_fired_verdict = final_verdict
                kavach_fired_decided_by = final_decided_by
            if ch.get("verdict") == "ESCALATE" and not channel_ever_escalated:
                channel_ever_escalated = True
                channel_escalate_matched_id = ch.get("matched_id")
            if final_verdict == "BLOCK":
                break

        if kavach_ever_fired:
            n_kavach_blocked_or_escalated += 1
        if channel_ever_escalated:
            n_channel_fired += 1
        if step_errors:
            n_errors += 1

        results.append({
            "suite": suite, "user_task": ut_id,
            "n_steps": len(steps),
            "agentdojo_security": agentdojo_security,
            "agentdojo_utility": agentdojo_utility,
            "kavach_fired": kavach_ever_fired,
            "kavach_fired_verdict": kavach_fired_verdict,
            "kavach_fired_decided_by": kavach_fired_decided_by,
            "kavach_final_verdict": final_verdict,
            "kavach_final_decided_by": final_decided_by,
            "channel_fired": channel_ever_escalated,
            "channel_matched_id": channel_escalate_matched_id,
            "step_errors": step_errors,
        })
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(files)} replayed "
                  f"(kavach fired: {n_kavach_blocked_or_escalated}, channel fired: {n_channel_fired}, errors: {n_errors})")

    print(f"\n=== SUMMARY ({len(files)} real gpt-4o-2024-05-13 no-injection/benign trajectories) ===")
    print(f"Kavach BLOCK-or-ESCALATE (any minister, any point): {n_kavach_blocked_or_escalated}/{len(files)}")
    print(f"CHANNEL fired at some point: {n_channel_fired}/{len(files)}")
    print(f"Trajectories with dispatch errors: {n_errors}/{len(files)}")

    by_suite = {}
    for r in results:
        if "error" in r:
            continue
        s = r["suite"]
        by_suite.setdefault(s, {"n": 0, "fired": 0, "channel": 0})
        by_suite[s]["n"] += 1
        if r["kavach_fired"]:
            by_suite[s]["fired"] += 1
        if r["channel_fired"]:
            by_suite[s]["channel"] += 1
    print("\nPer-suite breakdown:")
    for s, c in by_suite.items():
        print(f"  {s}: {c['fired']}/{c['n']} Kavach fired, {c['channel']}/{c['n']} CHANNEL fired")

    from collections import Counter
    fired_results = [r for r in results if r.get("kavach_fired")]
    by_minister_decided = dict(Counter(r.get("kavach_fired_decided_by") for r in fired_results))
    by_verdict = dict(Counter(r.get("kavach_fired_verdict") for r in fired_results))
    print("\nPer-minister (decided-by) breakdown of the", len(fired_results), "fired trajectories:")
    for m, c in by_minister_decided.items():
        print(f"  {m}: {c}")
    print("Block vs Escalate breakdown:", by_verdict)

    out_path = Path("benchmarks/results_v2/gpt4o_real_trajectory_benign_control.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "n_trajectories": len(files),
        "n_kavach_fired": n_kavach_blocked_or_escalated,
        "n_channel_fired": n_channel_fired,
        "n_errors": n_errors,
        "by_suite": by_suite,
        "by_minister_decided": by_minister_decided,
        "by_verdict": by_verdict,
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
