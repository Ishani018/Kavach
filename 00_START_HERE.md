# START HERE — Get the Repo Up to Date

This folder has every file we created or changed. Below is exactly what each
file is, where it goes in the repo, and the commands to push it all.

Your repo is at: C:\Users\ishan\Downloads\kavach_push
Your GitHub is:  github.com/Ishani018/Kavach

---

## The files and where each one goes

| File in this folder | Goes to (repo path) | What it is |
|---|---|---|
| `README.md` | `README.md` (root) | Full detailed team README with diagrams |
| `kavach_boot.sh` | `kavach_boot.sh` (root) | One-shot setup script (corpus-merge fixed) |
| `TEAM.md` | `TEAM.md` (root) | Ownership table |
| `gitignore.txt` | `.gitignore` (root) | **rename to `.gitignore`** |
| `predownload_model.py` | `predownload_model.py` (root) | BGE model pre-download helper |
| `compass_calibrator.py` | `compass_calibrator.py` (root) | Calibrator (hijacked-label fixed) |
| `injecagent_runner.py` | `benchmarks/injecagent_runner.py` | Runner with --full 1054-case synthesis |
| `new_patterns_channel_b.json` | `corpus_v2/new_patterns_channel_b.json` | CHANNEL batch 2 |
| `new_patterns_navigator_b.json` | `corpus_v2/new_patterns_navigator_b.json` | NAVIGATOR batch 2 (NAV-096 fixed) |
| `new_patterns_vault_b.json` | `corpus_v2/new_patterns_vault_b.json` | VAULT batch 2 |
| `OPENCLAW_INTEGRATION.md` | `docs/OPENCLAW_INTEGRATION.md` | How to hook up OpenClaw + live test |
| `MONDAY_RUNBOOK.md` | `MONDAY_RUNBOOK.md` (root) | Step-by-step for Monday at the Dell |

Not in this folder (already in your repo from the zip, leave as-is):
- All of `parliament/`, `plugin/`, `paper/`, `openclaw_pr/`
- `corpus_loader.py`, `merge_corpus.py`, `kavach_corpus_v1.json`
- `benchmarks/data/*.jsonl` (InjecAgent building blocks)
- `benchmarks/benign_traces.py`, `threshold_sweep.py`

---

## STEP 1 — Download all files from this chat

Download every file to your Downloads folder. They'll land in
`C:\Users\ishan\Downloads\`.

---

## STEP 2 — Copy them into the repo (Command Prompt)

```
cd C:\Users\ishan\Downloads\kavach_push

copy /Y C:\Users\ishan\Downloads\README.md README.md
copy /Y C:\Users\ishan\Downloads\kavach_boot.sh kavach_boot.sh
copy /Y C:\Users\ishan\Downloads\TEAM.md TEAM.md
copy /Y C:\Users\ishan\Downloads\predownload_model.py predownload_model.py
copy /Y C:\Users\ishan\Downloads\compass_calibrator.py compass_calibrator.py
copy /Y C:\Users\ishan\Downloads\injecagent_runner.py benchmarks\injecagent_runner.py
copy /Y C:\Users\ishan\Downloads\new_patterns_channel_b.json corpus_v2\new_patterns_channel_b.json
copy /Y C:\Users\ishan\Downloads\new_patterns_navigator_b.json corpus_v2\new_patterns_navigator_b.json
copy /Y C:\Users\ishan\Downloads\new_patterns_vault_b.json corpus_v2\new_patterns_vault_b.json
copy /Y C:\Users\ishan\Downloads\MONDAY_RUNBOOK.md MONDAY_RUNBOOK.md
```

The `.gitignore` needs renaming (Windows hides the leading dot):
```
copy /Y C:\Users\ishan\Downloads\gitignore.txt .gitignore
```

Make the docs folder and copy the integration guide:
```
if not exist docs mkdir docs
copy /Y C:\Users\ishan\Downloads\OPENCLAW_INTEGRATION.md docs\OPENCLAW_INTEGRATION.md
```

---

## STEP 3 — Commit and push everything at once

```
cd C:\Users\ishan\Downloads\kavach_push
git add .
git commit -m "full repo update: detailed README, fixed calibrator+corpus, --full benchmark, OpenClaw guide, Monday runbook"
git pull --rebase origin main
git push
```

If `git pull --rebase` reports a conflict (because you edited files directly on
GitHub earlier), resolve by taking your local versions:
```
git checkout --theirs .
git add .
git rebase --continue
git push
```

If that gets messy, simpler fallback — force your local state as truth (ONLY safe
because you're the only one pushing right now):
```
git push --force-with-lease
```

---

## STEP 4 — Verify on GitHub

Open github.com/Ishani018/Kavach and confirm:
- README shows the detailed version (Table of Contents at top)
- `docs/OPENCLAW_INTEGRATION.md` exists
- `MONDAY_RUNBOOK.md` exists
- `predownload_model.py` exists
- `compass_calibrator.py` shows the `hijacked` line (search the file for "hijacked")

Done. Repo is current. Take MONDAY_RUNBOOK.md to the lab.
