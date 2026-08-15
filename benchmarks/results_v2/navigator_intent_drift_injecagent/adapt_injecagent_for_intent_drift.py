import json

SRC = "/private/tmp/claude-501/-Users-ishani-Desktop-kavach/c3981ef1-cb11-4907-98d7-76d22c4cd689/scratchpad/injecagent_100case_forced.jsonl"
OUT = "/private/tmp/claude-501/-Users-ishani-Desktop-kavach/c3981ef1-cb11-4907-98d7-76d22c4cd689/scratchpad/injecagent_intent_dataset_verify.jsonl"

rows = [json.loads(l) for l in open(SRC)]
out = []
n_attack = 0
n_benign = 0
for r in rows:
    goal = r.get("user_instruction", "")
    turns = []
    for t in r.get("turns", []):
        for tc in t.get("raw_tool_calls", []):
            fn = tc.get("function", {})
            tool = fn.get("name", "")
            args = fn.get("arguments", {})
            text = f"tool:{tool} args:{json.dumps(args, default=str, sort_keys=True)}"
            turns.append({"tool": tool, "args": args, "text": text})
    is_attack = r.get("kind") in ("ds", "dh")
    if is_attack:
        n_attack += 1
    else:
        n_benign += 1
    out.append({
        "case_id": r["case_id"],
        "goal": goal,
        "turns": turns,
        "labels": {"is_attack_case": is_attack},
    })

with open(OUT, "w") as f:
    for o in out:
        f.write(json.dumps(o) + "\n")

print(f"Wrote {len(out)} cases ({n_attack} attack, {n_benign} benign) to {OUT}")
