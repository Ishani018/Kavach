"""GPT-4o real-trajectory expansion (scoped, bounded task): replay ALL
629 real recorded AgentDojo attack trajectories for gpt-4o-2024-05-13's
"important_instructions" attack family, across all 4 suites, through
Kavach's live server -- not the minimal ground_truth() subsequence, not
a hand-picked/hand-transcribed subset (that was the earlier, explicitly
bounded 5-case priority check: _priority_real_trajectory_check.py).

Source: github.com/ethz-spylab/agentdojo/tree/main/runs/gpt-4o-2024-05-13
(sparse-checked-out via git, not the pip package -- runs/ isn't shipped
in the installed agentdojo package). Real user_task x injection_task
pairs that were actually recorded (not the full cross-product -- only
pairs AgentDojo itself ran get a file).

Scope: "important_instructions" attack type only, matching what
Kavach's whole corpus/design has targeted all session (the other
attack-type directories -- captcha_dos, offensive_email_dos,
tool_knowledge, etc -- are a different threat class, out of scope for
this task per the standing "don't silently expand scope" rule).

Each trajectory's messages are replayed IN ORDER through
POST /hook/parliament, using the same "tool:X args:Y" wire format and
context (user_instruction, tool_output) fields as every other real-data
benchmark run tonight (_agentdojo_provenance_benchmark.py,
_priority_real_trajectory_check.py). One session_id per trajectory
file. Requires the live Kavach server on :8088 (uvicorn).
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

KAVACH_URL = "http://127.0.0.1:8088"
_RUN_TAG = str(int(time.time()))

RUNS_ROOT = Path(
    "C:/Users/ishan/AppData/Local/Temp/claude/c--Users-ishan-Desktop-Kavach/"
    "ef4b1a3b-08ff-424c-87f9-f88516cb207f/scratchpad/agentdojo_repo/runs/gpt-4o-2024-05-13"
)
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
    """Returns [(function, args, tool_output_or_None), ...] in call order,
    pairing each assistant tool_call with its following tool-role message
    (matched by tool_call_id, same convention as AgentDojo's own message
    schema -- falls back to positional pairing if id lookup fails)."""
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
            ii_dir = ut_dir / "important_instructions"
            if not ii_dir.is_dir():
                continue
            for f in sorted(ii_dir.glob("injection_task_*.json")):
                files.append((suite, ut_dir.name, f))
    return files


def main():
    files = find_trajectory_files()
    print(f"Found {len(files)} real important_instructions trajectory files "
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

        it_id = d.get("injection_task_id") or path.stem
        agentdojo_security = d.get("security")  # True = AgentDojo's own agent/defense resisted
        agentdojo_utility = d.get("utility")
        user_instruction = extract_user_instruction(d.get("messages", []))
        steps = extract_steps(d.get("messages", []))

        session_id = f"gpt4o-real-{_RUN_TAG}-{suite}-{ut_id}-{it_id}"
        final_verdict = None
        final_decided_by = None
        channel_ever_escalated = False
        channel_escalate_matched_id = None
        # Track whether Kavach (any minister) EVER fired at any point in the
        # session, not just the last step's verdict -- a harmless trailing
        # call (e.g. reserve_hotel after the malicious send_email) is ALLOW
        # and would otherwise silently overwrite an earlier real BLOCK/
        # ESCALATE. Same bug class _priority_real_trajectory_check.py found
        # and fixed earlier tonight (only tracking the last step's verdict);
        # reintroduced here in the new script and fixed the same way, after
        # a live re-check of travel::user_task_0/injection_task_3 confirmed
        # CHANNEL genuinely ESCALATEs mid-session but the old aggregation
        # reported it as a miss because reserve_hotel (the final call) came
        # back ALLOW.
        kavach_ever_fired = False
        kavach_fired_verdict = None
        kavach_fired_decided_by = None
        step_errors = 0
        for si, (fn, args, tool_output) in enumerate(steps):
            text = fmt(fn, args)
            context = {
                "source": "gpt4o-real-trajectory-expansion", "call_n": si,
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
            "suite": suite, "user_task": ut_id, "injection_task": it_id,
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
        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1}/{len(files)} replayed "
                  f"(kavach fired: {n_kavach_blocked_or_escalated}, channel fired: {n_channel_fired}, errors: {n_errors})")

    print(f"\n=== SUMMARY ({len(files)} real gpt-4o-2024-05-13 important_instructions trajectories) ===")
    print(f"Kavach BLOCK-or-ESCALATE (any minister): {n_kavach_blocked_or_escalated}/{len(files)}")
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

    out_path = Path("benchmarks/results_v2/gpt4o_real_trajectory_expansion.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "n_trajectories": len(files),
        "n_kavach_fired": n_kavach_blocked_or_escalated,
        "n_channel_fired": n_channel_fired,
        "n_errors": n_errors,
        "by_suite": by_suite,
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
