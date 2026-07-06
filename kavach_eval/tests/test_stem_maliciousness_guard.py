#!/usr/bin/env python3
"""
kavach_eval/tests/test_stem_maliciousness_guard.py

Verifies the _stem() fix for the 93%-false-AMBIGUOUS bug found on the Dell
250-seed red-team run (evasion_report_20260706T102139Z.json): obviously
malicious paraphrases (mimikatz credential dumping, LSA-protection-disable,
shellcode download+exec, PowerShell "-ExecutionPolicy Bypass") were wrongly
excluded because their words did not stem to the literal forms stored in
_ATTACK_TOKENS.

Run: python kavach_eval/tests/test_stem_maliciousness_guard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kavach_eval.redteam_evasion_v0 import _stem, _ATTACK_TOKENS, MaliciousnessGuard

# (word, must_be_in_attack_tokens_after_stemming)
# The six originally-reported bugs, plus regression coverage for cases that
# already worked before the fix.
CASES = [
    # --- originally-reported bugs (all must now hit _ATTACK_TOKENS) ---
    ("bypass",      True),   # was "bypas" (double-s root over-stripped)
    ("access",      True),   # was "acces" (same double-s bug)
    ("malicious",   True),   # was "maliciou" (no -ous rule)
    ("execution",   True),   # was "execu" (-tion stripped one char too many)
    ("persistence", True),   # was unstemmed "persistence" (no -ence rule)
    ("privileges",  True),   # was "privileg" (-es fired before checking for
                             # an already-e-ending root); "privilege" IS in
                             # _ATTACK_TOKENS, so the old bug was a genuine
                             # missed-detection, not just a cosmetic mismatch.
    # --- must keep working (regression guard) ---
    ("executing",     True),
    ("downloading",   True),
    ("installer",     True),
    ("credentials",   True),
    ("tokens",        True),
    ("attacker",      True),
    ("payloads",      True),
    ("weaponized",    True),
    ("exploited",     True),
    ("deserializ",    True),
    ("injection",     True),
    ("processes",     True),
]

# Exact stem-shape checks (for words whose root isn't in _ATTACK_TOKENS
# either way, so the set-membership check alone can't catch a regression).
SHAPE_CASES = [
    ("privileges", "privilege"),
    ("patches", "patch"),      # true -es plural: sibilant root
    ("mimikatz", "mimikatz"),  # untouched, no matching suffix
    ("shellcode", "shellcode"),
    ("disable", "disable"),
]


def run() -> bool:
    print("=" * 72)
    print("Testing _stem() fix (MaliciousnessGuard false-AMBIGUOUS bug)")
    print("=" * 72)
    ok = True

    for word, expect_hit in CASES:
        stem = _stem(word)
        hit = stem in _ATTACK_TOKENS
        passed = hit == expect_hit
        ok &= passed
        status = "PASS" if passed else "FAIL"
        print(f"  {status} [{word!r:16s}] -> stem={stem!r:16s} "
              f"in_ATTACK_TOKENS={hit} (expected {expect_hit})")

    print()
    for word, expect_stem in SHAPE_CASES:
        stem = _stem(word)
        passed = stem == expect_stem
        ok &= passed
        status = "PASS" if passed else "FAIL"
        print(f"  {status} [{word!r:16s}] -> stem={stem!r:16s} "
              f"(expected {expect_stem!r})")

    # End-to-end: the guard should now KEEP a paraphrase using the exact
    # words that were previously wrongly excluded (bypass + execution +
    # malicious in a single sentence should clear the >=2-stem bar).
    print()
    guard = MaliciousnessGuard()
    seed = "Agent bypassing execution controls to run a malicious payload"
    paraphrase = (
        "Use -ExecutionPolicy Bypass to run the malicious payload and "
        "maintain persistence via a scheduled task"
    )
    verdict = guard.check(seed, paraphrase)
    passed = verdict == "KEEP"
    ok &= passed
    status = "PASS" if passed else "FAIL"
    print(f"  {status} [end-to-end guard.check] verdict={verdict} (expected KEEP)")

    print()
    print("=" * 72)
    print("ALL TESTS PASSED" if ok else "*** SOME TESTS FAILED ***")
    print("=" * 72)
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
