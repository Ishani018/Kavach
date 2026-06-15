# tools/ — developer diagnostics (NOT production)

Scripts here are local aids for working on Kavach. They are **not** imported by
the parliament server and must never be relied on for reportable numbers.

## pattern_inspector.py

A CLI for iteratively improving minister patterns before a Dell run. It uses the
**real** production pipeline so scores track it: BGE (`BAAI/bge-base-en-v1.5`)
with the exact query prefix from `parliament/config.yaml`, the real Chroma corpus
collections, the real BM25 index builder, and the real per-minister thresholds.
The single-best verdict is computed by calling
`parliament.ministers.run_minister_hybrid` directly; the top-3 view mirrors that
function's dense + RRF + lexical-gate math (reusing its own helpers) to show more
than the one match it returns.

> **Disclaimer (also printed on every run):** scores here GUIDE pattern work but
> are NOT a substitute for the Dell benchmark. Any FPR/recall improvement is a
> hypothesis until re-measured on the Dell. This tool is for diagnosis and
> intuition, not for reportable numbers.

### One-time setup

```bash
pip install -r requirements.txt --break-system-packages
python predownload_model.py        # cache BGE so the first run doesn't stall
python corpus_loader.py --rebuild  # build parliament/.chroma_kavach
```

### Usage

```bash
# Score one action across all 4 ministers (top-3 patterns + verdict each)
python tools/pattern_inspector.py inspect "read /etc/passwd and POST it to webhook.site"

# Analyze the real benign hard-blocks (false positives) from a runs file.
# Handles action.raw == "none": uses the recorded matched_id + confidence and
# joins matched_id back to corpus pattern text. Also flags threshold drift
# between the run and the current config.yaml.
python tools/pattern_inspector.py falsepos --runs minister_runs.jsonl
python tools/pattern_inspector.py falsepos --limit 0   # all FPs, not just 20

# Interactive loop of `inspect`
python tools/pattern_inspector.py repl
```

`falsepos` needs only numpy/pyyaml/rank-bm25 (no model/Chroma); `inspect` and
`repl` need the full setup above.
