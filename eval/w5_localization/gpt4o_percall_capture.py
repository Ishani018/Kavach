"""W5 re-run: extends gpt4o_real_trajectory_full.py to capture PER-CALL
detail (call index, per-call verdict, per-call decided_by, per-minister
fire) instead of only per-trajectory aggregates. No detection logic
touched -- this is a superset of what the original script already
computed, adding a `steps` list to each trajectory record.

PARITY GATE: must reproduce the committed aggregates exactly:
  467/629 fired total; banking 119/144, slack 105/105, travel 63/140,
  workspace 180/240.
"""
import json
import time
import urllib.request
from pathlib import Path

KAVACH_URL = "http://127.0.0.1:8088"
_RUN_TAG = str(int(time.time()))

RUNS_ROOT = Path(
    "/private/tmp/claude-501/-Users-ishani-Desktop-kavach/"
    "c3981ef1-cb11-4907-98d7-76d22c4cd689/scratchpad/agentdojo_repo/runs/gpt-4o-2024-05-13"
)
SUITES = ["banking", "slack", "travel", "workspace"]
MINISTERS = ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"]


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
            ii_dir = ut_dir / "important_instructions"
            if not ii_dir.is_dir():
                continue
            for f in sorted(ii_dir.glob("injection_task_*.json")):
                files.append((suite, ut_dir.name, f))
    return files


def main():
    files = find_trajectory_files()
    print(f"Found {len(files)} trajectory files.")

    results = []
    n_kavach_fired = 0
    by_suite = {}

    for i, (suite, ut_id, path) in enumerate(files):
        d = json.loads(path.read_text(encoding="utf-8"))
        it_id = d.get("injection_task_id") or path.stem
        agentdojo_security = d.get("security")
        user_instruction = extract_user_instruction(d.get("messages", []))
        steps_raw = extract_steps(d.get("messages", []))

        session_id = f"gpt4o-percall-{_RUN_TAG}-{suite}-{ut_id}-{it_id}"
        kavach_ever_fired = False
        kavach_fired_verdict = None
        kavach_fired_decided_by = None
        kavach_fired_step_index = None
        step_records = []

        for si, (fn, args, tool_output) in enumerate(steps_raw):
            print(f"[{i+1}/{len(files)}] {suite}/{ut_id}/{it_id} step {si}/{len(steps_raw)}", flush=True)
            text = fmt(fn, args)
            context = {
                "source": "gpt4o-percall-capture", "call_n": si,
                "user_instruction": user_instruction, "tool_output": tool_output,
            }
            try:
                resp = post(text, session_id, context)
            except Exception as e:
                step_records.append({"step": si, "tool": fn, "error": str(e)})
                continue

            verdict = resp.get("verdict")
            decided_by = resp.get("speaker", {}).get("decided_by")
            ministers = resp.get("ministers", {}) or {}
            fired_ministers = [m for m in MINISTERS if ministers.get(m, {}).get("verdict") in ("BLOCK", "ESCALATE")]

            step_records.append({
                "step": si, "tool": fn, "args_repr": json.dumps(args, default=str)[:200],
                "verdict": verdict, "decided_by": decided_by,
                "fired_ministers": fired_ministers,
                "short_circuited": resp.get("short_circuited"),
            })

            if verdict in ("BLOCK", "ESCALATE") and not kavach_ever_fired:
                kavach_ever_fired = True
                kavach_fired_verdict = verdict
                kavach_fired_decided_by = decided_by
                kavach_fired_step_index = si
            if verdict == "BLOCK":
                break

        if kavach_ever_fired:
            n_kavach_fired += 1
        by_suite.setdefault(suite, {"n": 0, "fired": 0})
        by_suite[suite]["n"] += 1
        if kavach_ever_fired:
            by_suite[suite]["fired"] += 1

        results.append({
            "suite": suite, "user_task": ut_id, "injection_task": it_id,
            "n_steps": len(steps_raw),
            "agentdojo_security": agentdojo_security,
            "kavach_fired": kavach_ever_fired,
            "kavach_fired_verdict": kavach_fired_verdict,
            "kavach_fired_decided_by": kavach_fired_decided_by,
            "kavach_fired_step_index": kavach_fired_step_index,
            "steps": step_records,
        })
        if (i + 1) % 100 == 0:
            print(f"  ...{i+1}/{len(files)}  fired so far: {n_kavach_fired}")

    print(f"\n=== PARITY CHECK ===")
    print(f"Total fired: {n_kavach_fired}/{len(files)}  (committed: 467/629)")
    for s in SUITES:
        c = by_suite.get(s, {"n": 0, "fired": 0})
        print(f"  {s}: {c['fired']}/{c['n']}")
    print("  (committed: banking 119/144, slack 105/105, travel 63/140, workspace 180/240)")

    out = Path("/private/tmp/claude-501/-Users-ishani-Desktop-kavach/c3981ef1-cb11-4907-98d7-76d22c4cd689/scratchpad/gpt4o_percall_capture.json")
    out.write_text(json.dumps({"n_trajectories": len(files), "n_fired": n_kavach_fired,
                                "by_suite": by_suite, "results": results}, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
