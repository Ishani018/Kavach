import json
from pathlib import Path

from parliament.channel_taint import check_provenance, new_provenance_state

d = json.loads(Path("parliament/benign_test_set/real_benign_trajectories.json").read_text(encoding="utf-8"))

n_escalated = 0
results = []
for item in d:
    state = new_provenance_state()
    user_instr = item.get("user_task_text", "")
    escalated = False
    all_classifications = []
    for c in item["calls"]:
        text = f'tool:{c["tool"]} args:{json.dumps(c["args"], default=str)}'
        tool_output = c.get("tool_output")
        scan, records = check_provenance(text, state, user_instruction=user_instr, tool_output=tool_output)
        if scan is not None:
            escalated = True
        all_classifications.extend((r.value, r.classification, r.source_tool) for r in records)
    if escalated:
        n_escalated += 1
    results.append({
        "source_file": item["source_file"],
        "escalated": escalated,
        "classifications": all_classifications,
    })

print(f"{n_escalated}/{len(d)} sessions ESCALATE under provenance (post-regeneration)")
print()
for r in results:
    marker = "ESCALATE" if r["escalated"] else "pass    "
    print(f"{marker}  {r['source_file']}")
    for val, cls, tool in r["classifications"]:
        print(f"          {cls:15s} {val!r:35s} source={tool}")
