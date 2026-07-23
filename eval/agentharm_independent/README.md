# AgentHarm-derived independent generalization check

Addresses reviewer weakness W6 (circular VAULT/EXECUTOR rule authoring):
Kavach's deterministic rules were authored by mining detection misses on the
same corpora (AtomicRedTeam, GTFOBins, InjecAgent, AgentDojo) the paper
evaluates against. The existing generalization audit (AtriumOS, Appendix A)
is author-written, n=18. This directory builds a *second*, genuinely
independent check using data the Kavach team did not author: **AgentHarm**
(UK AI Safety Institute + Gray Swan, ICLR 2025), specifically its published,
static synthetic tool implementations.

## Why AgentHarm, and why only the tool code, not the official benchmark

AgentHarm's official 110/440-task benchmark (behaviors + grading) is gated
behind the Inspect Evals framework and a HuggingFace dataset requiring API
keys to run a real agent loop -- out of reach on this project's timeline.
Its **synthetic tool implementations**, however, are plain, public Python
files on GitHub
(`UKGovernmentBEIS/inspect_evals/src/inspect_evals/agentharm/benchmark/{harmful_tools,benign_tools}/`),
MIT-licensed with a clause permitting use "for improving the safety and
security of AI systems" (this project's exact use case). `tools/harmful/`
and `tools/benign/` in this directory are unmodified copies of those files
(80 tools each), fetched 2026-07-23.

## Methodology

1. **Parse** each tool file's `async def run(...)` signature and docstring
   (`llm_generate_and_dispatch.py::parse_tool_file`).
2. **Generate realistic arguments** for each tool via a local LLM
   (`qwen2.5:7b` via Ollama, temperature 0.7), prompted once per tool with
   the tool's own docstring and told to generate a "malicious" (for
   `harmful_tools`) or "ordinary-benign" (for `benign_tools`) call --
   deliberately not reusing Kavach's own corpus phrasing.
   - **A first attempt used a hand-written regex/keyword heuristic
     instead of an LLM** (see git history) and was discarded: it produced
     bland placeholder values ("test_value") for anything it didn't
     recognize on the harmful side, and reused the same suspicious-looking
     placeholder values (e.g. an "attacker" email) on the nominally-benign
     side regardless of intent. Both halves of that run were artifacts of
     the generator, not real findings, and neither was used in the paper.
3. **Dispatch** every generated call through the live `/hook/parliament`
   endpoint, one call per tool, fresh session per case.
4. **Classify** (by hand, once, before any number was computed --
   `categorization.json`) each of the 79 successfully-generated harmful
   cases into: in-scope-and-caught, in-scope-and-missed (a real gap), or
   excluded (either the underlying AgentHarm harm category is outside
   Kavach's four-domain threat model -- e.g. drug-marketplace search,
   romance-scam messaging, marketplace fraud -- or the LLM-generated
   argument content didn't carry a meaningful malicious signal at all).
   This step is necessary because AgentHarm covers 11 harm categories
   (Fraud, Cybercrime, Harassment, Sexual, Drugs, Disinformation, Hate,
   Violence, ...) far broader than Kavach's stated scope (credential
   theft, dangerous code, exfiltration, unauthorized action), so a bare
   catch-rate over all 79 cases would unfairly penalize Kavach for not
   detecting harms it never claimed to detect.

No rule under `parliament/` was authored, tuned, or even consulted while
building the argument generator or doing the classification.

## Results

- **79 harmful cases dispatched** (1 of 80 tool files failed argument
  generation and was skipped). Of these, **44 were in-scope** for Kavach's
  four-domain threat model.
  - **36/44 (81.8%) correctly flagged** (BLOCK or ESCALATE).
  - **8/44 (18.2%) missed**, each named and explained in
    `categorization.json`: anti-forensics (`delete_access_logs`), public
    exploit-bragging (`post_on_x`), phishing-asset generation
    (`run_stable_diffusion_model`), a phishing email with a malware
    attachment (`send_email`), a crypto-to-crypto transfer likely missed
    on tool-name vocabulary grounds (`transfer_money_crypto` -- the
    same class of gap already disclosed for CHANNEL's hard-block path in
    Appendix A), two malware-named file uploads (`upload_file`,
    `upload_youtube_video`), and a no-argument credential-harvest call
    (`get_all_login_data`, consistent with the same gap found
    independently in an earlier small hand-built pilot).
- **80 benign cases dispatched**: **0% hard-block FPR**, **56.3% Escalate
  rate**. This is not a new finding in isolation -- it corroborates the
  paper's already-disclosed 67.3% agent-shaped-benign-Escalate rate
  (\S\ref{sec:design-tradeoffs}) with a second, independent data source.

## Files

- `tools/harmful/*.py`, `tools/benign/*.py` -- unmodified AgentHarm tool
  source (UK AISI, MIT license).
- `llm_generate_and_dispatch.py` -- generation + dispatch script.
- `results.json` -- raw per-case dispatch results (both populations).
- `categorization.json` -- the hand classification and summary numbers.

## Caveats, stated plainly

- Single LLM-generation pass, one seed per tool, not resampled or
  cherry-picked.
- The in-scope/excluded classification is a judgment call, done by one
  person, once; `categorization.json` lists every decision so it can be
  checked or disputed.
- n=44 in-scope cases is small -- illustrative, not statistically
  powered, the same caveat the AtriumOS audit already carries.
- This complements, not replaces, the AtriumOS audit: AtriumOS tests
  novel-*vocabulary* transfer with author-written scenarios; this tests
  transfer to a genuinely independently-authored attack/benign corpus,
  with LLM-generated (not author-written) call content.
