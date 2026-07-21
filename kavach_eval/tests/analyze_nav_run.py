#!/usr/bin/env python3
import json
from collections import Counter

lines = [json.loads(l) for l in open('benchmarks/results_v2/nav2/navigator_isolated_workspace_predictions.jsonl').read().splitlines() if l.strip()]

print('Confidence analysis:')
confs = sorted([r['pred_confidence'] for r in lines], reverse=True)
print('  max confidence:', round(max(confs), 4))
print('  min confidence:', round(min(confs), 4))
print('  median:', round(confs[len(confs)//2], 4))
print('  top 5:', [round(c,4) for c in confs[:5]])
print('  bottom 5:', [round(c,4) for c in confs[-5:]])

# Tool frequency
tool_counts = Counter(r['pred_tool'] for r in lines)
print('\nTools scored (top 15):')
for t, c in tool_counts.most_common(15):
    print(f'  {t}: {c}')

# Benign vs attack confidence
benign = [r for r in lines if r['truth']=='BENIGN']
attack = [r for r in lines if r['truth']=='ATTACK']
print(f'\nBenign: {len(benign)} cases')
print(f'  conf range: {min(r["pred_confidence"] for r in benign):.4f} - {max(r["pred_confidence"] for r in benign):.4f}')
b_confs = sorted([r['pred_confidence'] for r in benign])
print(f'  benign confs: {[round(c,4) for c in b_confs]}')

print(f'\nAttack: {len(attack)} cases')
print(f'  conf range: {min(r["pred_confidence"] for r in attack):.4f} - {max(r["pred_confidence"] for r in attack):.4f}')

# n_tool_calls distribution
n_calls = Counter(r['n_tool_calls'] for r in lines)
print(f'\nTool calls per case:')
for n, c in sorted(n_calls.items()):
    print(f'  {n} calls: {c} cases')

# Show a few benign predictions in detail
print('\n--- Benign case predictions ---')
for r in benign:
    print(f'  {r["case_id"]:40s} pred={r["pred"]:20s} tool={str(r["pred_tool"]):20s} conf={r["pred_confidence"]:.4f}')
