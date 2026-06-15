# R2 Coverage & Pipeline Findings

## R2a — Coverage Census (25 LOLBINs)
HIGH = 12 · MEDIUM = 2 · LOW = 11
Blind spot confirmed: Windows signed-binary LOLBINs absent from corpus by name
but recognized semantically by dense retrieval above threshold.

## R2b — Full Hybrid Pipeline (13 tools, real run_minister_hybrid)
EVADED: 11 — certutil, mshta, regsvr32, cmstp, IEX, Invoke-Expression,
  WebClient, DownloadString, DownloadFile, ruby -e, bitsadmin
BLOCKED_DENSE: 2 — rundll32, php -r
BLOCKED_BM25: 0 (gate is multiplicative, not a floor-block)

Excluded from evasion claims: php -r (corpus already names "php", gate=1.000)

## Mechanism
hybrid_conf = dense_sim × lexical_gate, GATE_FLOOR = 0.65
EVADED when dense_sim >= threshold but lexical_gate floors at ~0.65,
dragging hybrid_conf below threshold.
Anchor example — certutil: dense=0.586 > threshold=0.55, gate=0.878,
hybrid=0.515 < 0.55 → EVADED.

## Raw Results
Tool | minister | bm25_top | dense_sim | lexical_gate | hybrid_conf | threshold | nearest_id | result
certutil | EXECUTOR | 5.806 | 0.586 | 0.878 | 0.515 | 0.55 | EXEC-042 | EVADED
mshta | EXECUTOR | 4.432 | 0.550 | 0.633 | 0.348 | 0.55 | EXEC-008 | EVADED
rundll32 | EXECUTOR | 4.870 | 0.629 | 1.000 | 0.629 | 0.55 | EXEC-037 | BLOCKED_DENSE
regsvr32 | EXECUTOR | 4.432 | 0.618 | 0.599 | 0.370 | 0.55 | EXEC-035 | EVADED
cmstp | EXECUTOR | 4.962 | 0.617 | 0.628 | 0.388 | 0.55 | EXEC-037 | EVADED
IEX | EXECUTOR | 4.432 | 0.578 | 0.648 | 0.374 | 0.55 | EXEC-046 | EVADED
Invoke-Expression | EXECUTOR | 4.432 | 0.631 | 0.650 | 0.410 | 0.55 | EXEC-037 | EVADED
WebClient | CHANNEL | 3.134 | 0.583 | 0.645 | 0.376 | 0.60 | CHAN-039 | EVADED
DownloadString | CHANNEL | 3.134 | 0.595 | 0.636 | 0.379 | 0.60 | CHAN-002 | EVADED
DownloadFile | CHANNEL | 3.134 | 0.599 | 0.650 | 0.389 | 0.60 | CHAN-016 | EVADED
ruby -e | EXECUTOR | 9.137 | 0.586 | 0.840 | 0.492 | 0.55 | EXEC-038 | EVADED
php -r | EXECUTOR | 10.786 | 0.640 | 1.000 | 0.640 | 0.55 | EXEC-038 | BLOCKED_DENSE
bitsadmin | CHANNEL | 4.570 | 0.618 | 0.644 | 0.398 | 0.60 | CHAN-032 | EVADED

## Mitigation Experiment — naive lexical patching (Variant A)
Controlled experiment on throwaway branch `redteam-r2-mitigation-exp` (corpus
reverted byte-identical to baseline afterward; no permanent corpus change).
For each of the 11 EVADED tools, the tool name was APPENDED (append-only) to the
L3_surface field of its R2b nearest_id pattern, the corpus was re-embedded into a
temp ChromaDB, and R2b was re-run. Several attributions are deliberately
semantically mismatched (e.g. cmstp/Invoke-Expression appended to EXEC-037, a
Node.js vm-escape pattern) — this is a MECHANISM DEMO, not honest corpus coverage.

Result: EVADED 11 → 5. Naive lexical patching fixed 6 of 11.

Tool | before_hybrid | after_hybrid | before | after
certutil | 0.515 | 0.626 | EVADED | BLOCKED  ✅ fixed
mshta | 0.348 | 0.562 | EVADED | BLOCKED  ✅ fixed
IEX | 0.374 | 0.629 | EVADED | BLOCKED  ✅ fixed
Invoke-Expression | 0.410 | 0.670 | EVADED | BLOCKED  ✅ fixed
ruby -e | 0.492 | 0.604 | EVADED | BLOCKED  ✅ fixed
bitsadmin | 0.398 | 0.707 | EVADED | BLOCKED  ✅ fixed
regsvr32 | 0.370 | 0.370 | EVADED | EVADED  ❌ still evades
cmstp | 0.388 | 0.424 | EVADED | EVADED  ❌ still evades
WebClient | 0.376 | 0.418 | EVADED | EVADED  ❌ still evades
DownloadString | 0.379 | 0.426 | EVADED | EVADED  ❌ still evades
DownloadFile | 0.389 | 0.388 | EVADED | EVADED  ❌ still evades

## Why 5 still evade
Appending a tool name only raises lexical_gate toward 1.0 IF the patched pattern
is the one dense retrieval actually SELECTS for that tool. For the 5 remaining
evaders, the appended token landed on a pattern that is not the dense winner:
the embedding still ranks a different doc highest, so bm25_sel/bm25_qmax stays
low and the gate remains floored at ~0.60–0.65, holding hybrid_conf below
threshold (e.g. regsvr32 gate 0.605, cmstp 0.650, the CHANNEL download trio
~0.60–0.65). DownloadFile even re-routed from CHAN-016 to CHAN-002 — the new
token shifted the embedding but the gate still floored it.

Conclusion: naive lexical patching is pattern-placement-dependent and therefore
NOT a reliable fix. The real fix is authoring semantically-correct patterns that
dense retrieval will select — which is precisely what the corpus-improvement
agent (kavach_eval/corpus_agent/) does: it proposes new patterns and validates
them through a 3-part anti-poisoning gate. This experiment is the empirical
motivation for that agent.
