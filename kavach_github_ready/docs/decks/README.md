# Decks

Capstone-review presentations for the Kavach project.

| File | Date | Status | Use |
|------|------|--------|-----|
| `Kavach_v2_Progress_Review.pptx` | May 2026 | **Current** | Capstone progress review — what changed between April's blue deck and now |

The April deck (`Kavach_Deck_v5_final.html`) lives in the parent project. We didn't duplicate it here.

---

## What this deck is

A 20-slide progress update for the capstone team and Prof. Banginwar covering everything done since the April demo. The narrative arc:

1. **Recap of April** — what the blue deck showed, which was a post-hoc monitor with 10 regex rules and the ClawHavoc playback
2. **The honest reckoning** — why a regex monitor + ClawHavoc demo isn't enough for the paper
3. **Phase 2 architecture** — the parliament-of-ministers semantic firewall
4. **The corpus discipline** — how the 200 v2 patterns were written without overfitting
5. **Validation gates** — the 10-step sequence that produces trustworthy benchmark numbers
6. **What's left** — the 4-week sprint plan with workstream owners
7. **Asks** — what we need from the advisor and from the team

The visual identity carries forward from the April deck: navy + blue palette, the कवच Sanskrit watermark, slide markers in the bottom-right, thin top accent line.

## Regenerating the deck

If anyone wants to edit slides at the source level:

```bash
cd docs/decks
npm install -g pptxgenjs react-icons react react-dom sharp
node build_deck.js
```

Output is written to `Kavach_v2_Progress_Review.pptx` in the same directory.

You can also edit the .pptx directly in PowerPoint or Keynote — the build script is provided for reproducibility, not because every edit needs to flow through code.

## Suggested presentation flow

For the next review, plan ~30-40 minutes:

- Slides 1-2 (3 min): set the frame — what we promised, where we are
- Slides 3-5 (5 min): recap and the OpenClaw-bug pivot
- Slides 6-9 (8 min): the parliament architecture, in depth
- Slides 10-11 (5 min): the corpus discipline and the by-the-numbers
- Slides 12-14 (5 min): validation methodology
- Slides 15-17 (8 min): paper status, workstream burndown, 4-week plan
- Slides 18-20 (5 min): demo plan, asks, closing

Print slides 17 and 19 as handouts so the asks and the burndown are visible during discussion.

## What the next deck (June, post-lab-access) should add

- Real InjecAgent recall / FPR / latency numbers, replacing the `[TBD]` callouts in the paper
- A live or recorded demo of the OpenClaw plugin blocking ClawHavoc-style attacks
- ROC curves from the threshold sweep (Slides 11 and 14 should grow charts)
- Updated Workstream status (slide 16) — most should be at ON TRACK by then
