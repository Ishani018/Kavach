"""validate.py -- Kavach's tiered validation runner.

    python validate.py --tier A     # unit suites, seconds
    python validate.py --tier B     # + replay census (benign+attack), minutes
    python validate.py --tier C     # + full 544 InjecAgent + AgentDojo cross-minister + latency

Exit nonzero on ANY locked-number deviation. A moved number FAILS --
never auto-retuned. See VALIDATION_PROTOCOL.md for the full tier
definitions, the live-run boundary, and why NAVIGATOR's three baseline
entries are never re-verified by this script (they live on
navigator-rearch).

pytest is NOT installed in this venv -- Tier A invokes test modules via
`python -m <module>` (the same direct-invocation pattern already proven
throughout tonight's work), not pytest.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

TIER_A_MODULES = [
    "parliament.test_channel_taint",   # 13 tests, includes tokenizer tests
    "parliament.test_speaker",         # 12 tests
]


def _run_module(module: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", module],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    ok = result.returncode == 0
    output = result.stdout + result.stderr
    return ok, output


def run_tier_a(verbose: bool = True) -> bool:
    print("=" * 70)
    print("TIER A -- unit suites")
    print("=" * 70)
    all_ok = True
    for module in TIER_A_MODULES:
        ok, output = _run_module(module)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] python -m {module}")
        if verbose or not ok:
            print(output.strip())
        all_ok = all_ok and ok
    return all_ok


def run_tier_b(kavach_url: str, concurrency: int, verbose: bool = True) -> bool:
    """Replay census on both benign+attack sides, sampled for speed
    (--sample-size 50 keeps this in the 'minutes' budget rather than
    the full 544-case InjecAgent run's ~15-20 min). Skips the full
    InjecAgent replay -- that's Tier C's job."""
    print("=" * 70)
    print("TIER B -- replay census (sampled, benign + attack)")
    print("=" * 70)
    ok_a = run_tier_a(verbose=False)
    if not ok_a:
        print("[FAIL] Tier A must pass before Tier B runs.")
        return False

    cmd = [
        sys.executable, "-m", "benchmarks.replay_validate",
        "--kavach-url", kavach_url,
        "--concurrency", str(concurrency),
        "--sample-size", "50",
        "--skip-injecagent",  # full InjecAgent replay is Tier C only
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0


def run_tier_c(kavach_url: str, concurrency: int, verbose: bool = True) -> bool:
    """Full 544-case InjecAgent replay + AgentDojo cross-minister (no
    sampling) + relative latency check (vs local reference, NOT the
    locked absolute baseline -- CI hardware is not the Dell)."""
    print("=" * 70)
    print("TIER C -- full replay (544 InjecAgent + AgentDojo, no sampling)")
    print("=" * 70)
    ok_b = run_tier_b(kavach_url, concurrency, verbose=False)
    if not ok_b:
        print("[FAIL] Tier B must pass before Tier C runs.")
        return False

    cmd = [
        sys.executable, "-m", "benchmarks.replay_validate",
        "--kavach-url", kavach_url,
        "--concurrency", str(concurrency),
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=3600)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", choices=["A", "B", "C"], required=True)
    p.add_argument("--kavach-url", default="http://127.0.0.1:8088")
    p.add_argument("--concurrency", type=int, default=2,
                    help="Default 2 -- see VALIDATION_PROTOCOL.md's Windows ProactorEventLoop lesson.")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress passing-test output.")
    args = p.parse_args()

    verbose = not args.quiet
    if args.tier == "A":
        ok = run_tier_a(verbose)
    elif args.tier == "B":
        ok = run_tier_b(args.kavach_url, args.concurrency, verbose)
    else:
        ok = run_tier_c(args.kavach_url, args.concurrency, verbose)

    print()
    print(f"TIER {args.tier}: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
