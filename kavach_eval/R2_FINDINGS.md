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
