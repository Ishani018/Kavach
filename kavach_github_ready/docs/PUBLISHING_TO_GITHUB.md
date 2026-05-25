# Publishing Kavach to GitHub

Three options, ordered from simplest to most complete. Pick one.

---

## Option 1 — Drag-and-drop into a new repo (fastest, no terminal)

The simplest way if you just want the code up on GitHub today.

1. Go to **https://github.com/new**
2. Repository name: `kavach` (or whatever your team prefers)
3. Visibility: **Private** for now. You can flip it to public after the corpus has been cross-reviewed and the FPR gate has passed — releasing patterns that block 30% of legit work would be embarrassing.
4. **Do not** initialize with a README, .gitignore, or license. We already have those.
5. Click "Create repository". GitHub will show you a "Quick setup" page with a URL like `https://github.com/<your-username>/kavach.git`.
6. From that page, click **"uploading an existing file"** in the small text under "Quick setup".
7. Drag the entire contents of the `kavach/` folder (not the folder itself — the contents) into the upload area. GitHub will preserve the directory structure.
8. Scroll down, write a commit message like "Initial commit of Kavach workspace", and click "Commit changes".

Done. The repo is on GitHub. Skip to **After the first push** below.

**Caveat:** This loses the local commit history and the commit message I wrote in the bundle. Option 2 preserves both.

---

## Option 2 — Clone from the bundle, then push (recommended)

This preserves the exact commit I made, with the proper commit message.

```bash
# 1. Clone from the bundle into a local working directory
git clone /path/to/kavach_repo.bundle kavach
cd kavach

# 2. Verify the commit landed
git log --oneline
# You should see: 0e955b9 Initial commit: Kavach semantic firewall workspace

# 3. Create the GitHub repo (you can do this in the browser, OR with gh CLI):

# OPTION A — Via gh CLI (one command):
gh repo create <your-org>/kavach --private --source=. --remote=origin --push

# OPTION B — Via browser:
#   Go to https://github.com/new, name it `kavach`, private, do NOT initialize.
#   Then back in your terminal:
git remote add origin https://github.com/<your-org>/kavach.git
git branch -M main
git push -u origin main
```

That's it. The repo is now on GitHub with the original commit history.

---

## Option 3 — Clone from the tarball (if the bundle file gets corrupted in transit)

```bash
# 1. Extract the tarball
tar xzf kavach_repo.tar.gz
cd kavach

# 2. Verify the .git directory is intact
git log --oneline
# Same commit as above

# 3. Continue from step 3 of Option 2.
```

---

## After the first push

Five small things that pay back later. Do them in order, or open them as issues to do later.

### 1. Verify CI passed

Go to the repo's **Actions** tab. You should see the "CI" workflow running, with five jobs:

- `validate-corpus` — checks all JSON files parse and counts patterns
- `validate-merge-runs` — runs `merge_corpus.py` against synthetic v1, expects zero rejects
- `python-syntax` — `ast.parse` every Python file
- `speaker-tests` — runs the 12 speaker unit tests
- `ts-syntax` — checks the TypeScript files compile
- `yaml-syntax` — validates `parliament/config.yaml`

All five should be green. If any fail on the first push, something got corrupted; the validation in this workspace was clean before bundling.

### 2. Branch protection

`Settings → Branches → Add branch protection rule`:

- Branch name pattern: `main`
- ✅ Require a pull request before merging
- ✅ Require approvals (1 is fine for a 5-person team)
- ✅ Require status checks to pass before merging
  - Add: all five CI jobs above
- ✅ Require conversation resolution before merging

This stops anyone (including you on a tired Friday) from pushing directly to `main` and breaking the corpus.

### 3. Set up project visibility carefully

If you want the repo public eventually:

- **Don't make it public until after** Workstream C's cross-review and Workstream D's benign FPR gate. Public patterns that have a 30% FPR will be cited against the project in reviews.
- When you do make it public, also publish a `SECURITY.md` saying how to report vulnerabilities (the project itself is a security tool; researchers will look).

For now, keep it **private** and add the team as collaborators:

`Settings → Collaborators and teams → Add people`

Add Janya, Pranitha, Parv, Ishani as `Maintainer` so they can review PRs.

### 4. Add the GitHub URL to the citation

Once the repo URL is fixed, update the citation block in `README.md`:

```bibtex
url = {https://github.com/<your-org>/kavach}
```

And the corresponding line in `paper/skeleton.tex`'s reproducibility paragraph (last paragraph of §1).

### 5. Add a README badge for the CI

Once CI runs at least once, GitHub assigns the workflow a permalink. Replace the `Status: Pre-release` badge in the README with a CI badge:

```markdown
[![CI](https://github.com/<your-org>/kavach/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-org>/kavach/actions/workflows/ci.yml)
```

This is cosmetic but signals the project is alive and tested.

---

## What NOT to do

- **Do not commit benchmark results** until the benign FPR gate has passed. Reporting numbers obtained on a corpus that hadn't passed the gate would be misleading. Add a `benchmarks/results_v1/` directory only after Step 5 of `REPRODUCIBILITY.md` passes.
- **Do not push `parliament/.chroma_kavach/`** or the SQLite ledger. The `.gitignore` excludes them; verify with `git status` after first running the parliament that they don't show up as untracked.
- **Do not commit the v1 corpus file** (`kavach_corpus_v1.json`) into this repo if it has any patterns derived from a specific transcript. The expansion protocol's whole point is that the v2 patterns should generalize beyond what's in v1, and committing the contaminated v1 patterns next to the clean v2 patterns muddles the story.

---

## What's in this repo when it's pushed

```
40 files, 8,658 lines
├── 200 v2 corpus patterns (50 per minister)
├── 12 passing speaker unit tests
├── 7-test end-to-end smoke harness
├── ROC + Youden's J calibration tooling
├── InjecAgent + benign-FPR benchmark runners
├── Drafted §1 and §4 of the conference paper
├── PR-1 patch spec for OpenClaw bugs #5513 and #5943
└── CI that catches regressions in any of the above
```

What's not in this repo (intentionally):

- The OpenClaw fork with PR-1 applied — that lives in your fork of OpenClaw
- Benchmark numbers — pending lab access
- The browser embedding lab (`kavach_embedding_lab.html`) — kept in the parent project; not duplicated here
- The original v1 corpus — see "What NOT to do" above

---

## If you get stuck

The bundle is just a single file. If `git clone` from it fails, run:

```bash
git bundle verify /path/to/kavach_repo.bundle
```

It will tell you what's wrong. The bundle was verified before being shipped, so issues are usually transit corruption — re-download or re-extract.

If the GitHub push fails with an authentication error, you probably need to set up an SSH key or a personal access token for HTTPS auth. GitHub's docs cover both: https://docs.github.com/en/authentication
