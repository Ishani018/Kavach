import json

SRC = "/Users/ishani/Desktop/kavach/parliament/benign_test_set/real_benign_trajectories.json"
OUT = "/private/tmp/claude-501/-Users-ishani-Desktop-kavach/c3981ef1-cb11-4907-98d7-76d22c4cd689/scratchpad/agentdojo_benign_intent_dataset.jsonl"

sessions = json.load(open(SRC))
out = []
for i, s in enumerate(sessions):
    goal = s.get("user_task_text", "")
    turns = []
    for c in s.get("calls", []):
        tool = c.get("tool", "")
        args = c.get("args", {})
        text = f"tool:{tool} args:{json.dumps(args, default=str, sort_keys=True)}"
        turns.append({"tool": tool, "args": args, "text": text})
    out.append({
        "case_id": f"agentdojo_benign_{i:02d}",
        "goal": goal,
        "turns": turns,
        "labels": {"is_attack_case": False},
    })

with open(OUT, "w") as f:
    for o in out:
        f.write(json.dumps(o) + "\n")

print(f"Wrote {len(out)} AgentDojo benign cases to {OUT}")
