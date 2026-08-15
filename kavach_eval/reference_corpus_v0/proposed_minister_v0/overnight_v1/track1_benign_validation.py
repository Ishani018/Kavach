"""
Track 1 step 1: re-run the tiebreaker (pre-flag + LLM extraction + rule)
against ALL existing benign sets, zero-tolerance FP check. Does NOT touch
the live server -- this tests parliament.llm_tiebreaker directly, since
the tiebreaker is explicitly not wired into server.py's dispatch.
"""
import sys, json, time
sys.path.insert(0, r"C:\Users\ishan\Desktop\Kavach")
from parliament.llm_tiebreaker import check_vault_tiebreaker, check_executor_tiebreaker

REPO = r"C:\Users\ishan\Desktop\Kavach"


def render(tool, args):
    return f"tool:{tool} args:{json.dumps(args, default=str)}"


def check_both(text):
    """Simulates: VAULT/EXECUTOR's regex already returned None (since this
    tier only fires after the fast path finds nothing), now check whether
    the tiebreaker escalates."""
    v = check_vault_tiebreaker(text)
    e = check_executor_tiebreaker(text)
    return v, e


results = {"benign_v0": [], "real_benign_trajectories": [], "benign_probe": []}
n_triggers = 0
n_fps = 0
fp_details = []
total_calls = 0
total_time = 0.0

print("=== benign_v0.json (55 independent calls) ===")
benign = json.load(open(REPO + r"\parliament\benign_test_set\benign_v0.json", encoding="utf-8"))
for c in benign:
    text = render(c["tool"], c["args"])
    t0 = time.perf_counter()
    v, e = check_both(text)
    elapsed = time.perf_counter() - t0
    total_time += elapsed
    total_calls += 1
    triggered = (v is not None) or (e is not None)
    if triggered:
        n_triggers += 1
    fp = (v is not None and v.verdict == "BLOCK") or (e is not None and e.verdict == "BLOCK")
    if fp:
        n_fps += 1
        fp_details.append(("benign_v0", c["tool"], v.matched_id if v else None, e.matched_id if e else None))
    results["benign_v0"].append({
        "tool": c["tool"], "triggered": triggered,
        "vault_verdict": v.verdict if v else None, "exec_verdict": e.verdict if e else None,
        "elapsed_s": elapsed,
    })
    if (len(results["benign_v0"])) % 15 == 0:
        print(f"  {len(results['benign_v0'])}/55")

print("\n=== real_benign_trajectories.json (22 sessions) ===")
sessions = json.load(open(REPO + r"\parliament\benign_test_set\real_benign_trajectories.json", encoding="utf-8"))
for t in sessions:
    for c in t["calls"]:
        text = render(c["tool"], c["args"])
        t0 = time.perf_counter()
        v, e = check_both(text)
        elapsed = time.perf_counter() - t0
        total_time += elapsed
        total_calls += 1
        triggered = (v is not None) or (e is not None)
        if triggered:
            n_triggers += 1
        fp = (v is not None and v.verdict == "BLOCK") or (e is not None and e.verdict == "BLOCK")
        if fp:
            n_fps += 1
            fp_details.append(("real_benign_trajectories", c["tool"], v.matched_id if v else None, e.matched_id if e else None))
        results["real_benign_trajectories"].append({
            "task": t["user_task_text"][:50], "tool": c["tool"], "triggered": triggered,
            "vault_verdict": v.verdict if v else None, "exec_verdict": e.verdict if e else None,
            "elapsed_s": elapsed,
        })

print("\n=== benign_probe.json (25) ===")
probe = json.load(open(REPO + r"\kavach_eval\corpus_agent\benign_probe.json", encoding="utf-8"))
for a in probe["benign_actions"]:
    text = render("run_code", {"code": a["text"]})
    t0 = time.perf_counter()
    v, e = check_both(text)
    elapsed = time.perf_counter() - t0
    total_time += elapsed
    total_calls += 1
    triggered = (v is not None) or (e is not None)
    if triggered:
        n_triggers += 1
    fp = (v is not None and v.verdict == "BLOCK") or (e is not None and e.verdict == "BLOCK")
    if fp:
        n_fps += 1
        fp_details.append(("benign_probe", a["text"][:60], v.matched_id if v else None, e.matched_id if e else None))
    results["benign_probe"].append({
        "text": a["text"][:60], "lolbin_legit": a.get("lolbin_legit", False), "triggered": triggered,
        "vault_verdict": v.verdict if v else None, "exec_verdict": e.verdict if e else None,
        "elapsed_s": elapsed,
    })

print(f"\n=== SUMMARY ===")
print(f"total calls scored: {total_calls}")
print(f"pre-flag triggers (escalated to LLM): {n_triggers}/{total_calls} ({n_triggers/total_calls*100:.1f}%)")
print(f"NEW false positives (tiebreaker BLOCK on benign input): {n_fps}")
if fp_details:
    print("\n!!! FALSE POSITIVES FOUND (STOP CONDITION) !!!")
    for d in fp_details:
        print(" ", d)
else:
    print("ZERO new false positives across all 3 benign sets")
print(f"total tiebreaker compute time: {total_time:.1f}s")

out_path = r"C:\Users\ishan\Desktop\Kavach\kavach_eval\reference_corpus_v0\proposed_minister_v0\overnight_v1\track1_benign_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "results": results, "n_triggers": n_triggers, "n_fps": n_fps,
        "fp_details": fp_details, "total_calls": total_calls, "total_time_s": total_time,
    }, f, indent=2)
print(f"\nwrote {out_path}")
