#!/bin/sh
# Auto-regenerate FULL_PAPER_DRAFT.tex before every commit.
#
# .git/hooks/ is NOT tracked by git, so this canonical copy lives in the repo.
# Install it after cloning/pulling with:
#   cp docs/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
#
# When any paper/ file is staged, the full concatenated draft is rebuilt from
# the section sources and re-staged so the committed draft never goes stale.
if git diff --cached --name-only | grep -q "^paper/"; then
  cat paper/skeleton_aisec.tex \
      paper/section_1_intro_aisec.tex \
      paper/section_2_background.tex \
      paper/section_3_design_aisec.tex \
      paper/section_4_deployment.tex \
      paper/section_5_frontier.tex \
      paper/related_work_table.tex \
      paper/section_7_limitations.tex \
      > paper/FULL_PAPER_DRAFT.tex
  git add paper/FULL_PAPER_DRAFT.tex
  echo "[pre-commit] FULL_PAPER_DRAFT.tex regenerated"
fi
