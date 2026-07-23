"""eval/obfuscation_robustness/run_eval_ps_cmd.py
===================================================

Dispatches the PowerShell/cmd.exe obfuscation-transformed cases (built by
transforms_ps_cmd.py) through the live Kavach parliament server, same
mechanism as run_eval.py.

Reports TWO numbers per transform, not conflated:
  - "still_detected" / "missed": the naive overall-verdict check (did the
    Speaker's final verdict flip to ALLOW).
  - "true_evasion": whether the ORIGINALLY TARGETED minister's OWN verdict
    flipped to ALLOW -- i.e. the specific rule the transform targeted was
    actually fooled, not just a case where TRAJECTORY's session-level
    re-confirmation independently relabeled an already-correct verdict.
    This is the same correction applied to the sh/bash study's headline
    numbers (paper/section_7_limitations.tex), applied here from the start
    rather than retrofitted.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent
KAVACH_URL = "http://127.0.0.1:8088"
FIRED_VERDICTS = ("BLOCK", "ESCALATE")
TRANSFORMED_CASES_PATH = HERE / "transformed_cases_ps_cmd.json"
RESULTS_PATH = HERE / "results_ps_cmd.json"


async def _health_ok(session: aiohttp.ClientSession) -> bool:
    try:
        async with session.get(f"{KAVACH_URL}/health", timeout=aiohttp.ClientTimeout(total=10)) as r:
            return r.status == 200
    except Exception:
        return False


async def dispatch_one(sem: asyncio.Semaphore, session: aiohttp.ClientSession,
                        case_id: str, call_text: str, timeout_s: float) -> dict:
    payload = {"text": call_text, "session_id": f"kavach_obfusc_pscmd-{case_id}", "context": {}}
    async with sem:
        t0 = time.perf_counter()
        try:
            async with session.post(
                f"{KAVACH_URL}/hook/parliament", json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as resp:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                if resp.status != 200:
                    text = await resp.text()
                    return {"verdict": "ERROR", "error": f"http {resp.status}: {text[:200]}",
                            "ministers": {}, "latency_ms": latency_ms}
                data = await resp.json()
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return {"verdict": "ERROR", "error": f"{type(e).__name__}: {e}",
                    "ministers": {}, "latency_ms": latency_ms}
    return {
        "verdict": data.get("verdict"),
        "decided_by": data.get("speaker", {}).get("decided_by"),
        "ministers": {k: v.get("verdict") for k, v in data.get("ministers", {}).items()},
        "latency_ms": latency_ms,
    }


async def run_transform(transform_name: str, cases: list[dict], concurrency: int, timeout_s: float) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        if not await _health_ok(session):
            print(f"ERROR: Kavach not reachable at {KAVACH_URL}.", file=sys.stderr)
            sys.exit(2)
        results = []
        batch = 10
        for i in range(0, len(cases), batch):
            chunk = cases[i:i + batch]
            chunk_out = await asyncio.gather(*[
                dispatch_one(sem, session, c["case_id"], c["transformed_call_text"], timeout_s)
                for c in chunk
            ])
            for c, r in zip(chunk, chunk_out):
                results.append({**c, "obfuscated_verdict": r["verdict"],
                                "obfuscated_decided_by": r.get("decided_by"),
                                "obfuscated_ministers": r["ministers"],
                                "obfuscated_error": r.get("error"),
                                "obfuscated_latency_ms": r.get("latency_ms")})
            print(f"  [{transform_name}] {min(i + batch, len(cases))}/{len(cases)} dispatched", file=sys.stderr)
        return results


def summarize(transform_name: str, results: list[dict]) -> dict:
    n = len(results)
    still_detected = sum(1 for r in results if r["obfuscated_verdict"] in FIRED_VERDICTS)
    missed = sum(1 for r in results if r["obfuscated_verdict"] == "ALLOW")
    errored = sum(1 for r in results if r["obfuscated_verdict"] == "ERROR")

    # True evasion: did EVERY originally-targeted minister's OWN verdict
    # flip to ALLOW after transformation? (excludes cases with no
    # target_ministers recorded, and excludes errors from the denominator)
    scoreable = [r for r in results if r["obfuscated_verdict"] != "ERROR" and r.get("target_ministers")]
    true_evaded = 0
    for r in scoreable:
        targets = r["target_ministers"]
        own_verdicts = [r["obfuscated_ministers"].get(t) for t in targets]
        if all(v == "ALLOW" for v in own_verdicts):
            true_evaded += 1

    return {
        "transform": transform_name,
        "n_cases": n,
        "still_detected_after_obfuscation": still_detected,
        "missed_after_obfuscation_naive": missed,
        "errored": errored,
        "n_scoreable_for_true_evasion": len(scoreable),
        "true_evaded_count": true_evaded,
        "true_evasion_rate": (true_evaded / len(scoreable)) if scoreable else None,
        "naive_miss_rate": (missed / n) if n else None,
    }


async def main_async(concurrency: int, timeout_s: float):
    data = json.loads(TRANSFORMED_CASES_PATH.read_text(encoding="utf-8"))
    baseline_n = len(data["baseline_detected_cases"])

    all_results = {}
    summaries = []
    for transform_name in ("encode", "split", "indirect"):
        cases = data[transform_name]
        print(f"=== {transform_name}: {len(cases)} cases ===", file=sys.stderr)
        results = await run_transform(transform_name, cases, concurrency, timeout_s)
        all_results[transform_name] = results
        summaries.append(summarize(transform_name, results))

    out = {
        "baseline_detected_cases": baseline_n,
        "baseline_by_dialect": data["baseline_by_dialect"],
        "skipped": data["skipped"],
        "summaries": summaries,
        "per_case_results": all_results,
    }
    RESULTS_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== SUMMARY (per transform, never averaged together) ===")
    for s in summaries:
        print(f"{s['transform']:>10}: n={s['n_cases']:3d}  "
              f"naive-missed={s['missed_after_obfuscation_naive']:3d}/{s['n_cases']:3d} "
              f"({(s['naive_miss_rate'] or 0)*100:5.1f}%)  "
              f"TRUE-evasion={s['true_evaded_count']:3d}/{s['n_scoreable_for_true_evasion']:3d} "
              f"({(s['true_evasion_rate'] or 0)*100:5.1f}%)  errors={s['errored']}")
    print(f"\nwrote {RESULTS_PATH}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()
    asyncio.run(main_async(args.concurrency, args.timeout))
