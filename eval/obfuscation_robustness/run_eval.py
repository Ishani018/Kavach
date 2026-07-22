"""eval/obfuscation_robustness/run_eval.py
============================================

Dispatches the obfuscation-transformed Kavach-PB cases (built by
transforms.py) through the SAME live Kavach parliament server / dispatch
mechanism benchmarks/parliament_benchmark.py uses (`POST /hook/parliament`,
session_id per case, verdict + per-minister verdict map in the response).
No detection code under parliament/ is touched -- this is a black-box
robustness check of the existing, already-deployed pipeline.

For each transform, reports what fraction of the cases Kavach ORIGINALLY
detected (BLOCK/ESCALATE in the 519-case reference run) are now MISSED
(ALLOW, or no fire) after obfuscation, alongside the un-obfuscated
detection rate on the same subset for direct comparison. Numbers are kept
separate per transform -- never averaged into one combined figure that
would hide that the transforms behave differently.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT))

KAVACH_URL = "http://127.0.0.1:8088"
FIRED_VERDICTS = ("BLOCK", "ESCALATE")
TRANSFORMED_CASES_PATH = HERE / "transformed_cases.json"
RESULTS_PATH = HERE / "results.json"


async def _health_ok(session: aiohttp.ClientSession) -> bool:
    try:
        async with session.get(f"{KAVACH_URL}/health", timeout=aiohttp.ClientTimeout(total=10)) as r:
            return r.status == 200
    except Exception:
        return False


async def dispatch_one(sem: asyncio.Semaphore, session: aiohttp.ClientSession,
                        case_id: str, call_text: str, timeout_s: float) -> dict:
    payload = {"text": call_text, "session_id": f"kavach_obfusc-{case_id}", "context": {}}
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
            print(f"ERROR: Kavach not reachable at {KAVACH_URL}. Start it "
                  f"(uvicorn parliament.server:app --port 8088).", file=sys.stderr)
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
    return {
        "transform": transform_name,
        "n_cases": n,
        "originally_detected": n,  # by construction, all inputs were BLOCK/ESCALATE pre-transform
        "still_detected_after_obfuscation": still_detected,
        "missed_after_obfuscation": missed,
        "errored": errored,
        "detection_rate_before": 1.0 if n else None,
        "detection_rate_after": (still_detected / n) if n else None,
        "miss_rate": (missed / n) if n else None,
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
        "baseline_detected_sh_bash_cases": baseline_n,
        "skipped": data["skipped"],
        "summaries": summaries,
        "per_case_results": all_results,
    }
    RESULTS_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== SUMMARY (per transform, never averaged together) ===")
    for s in summaries:
        print(f"{s['transform']:>10}: n={s['n_cases']:3d}  "
              f"detected-before=100%  detected-after={s['detection_rate_after']*100:5.1f}%  "
              f"MISSED={s['missed_after_obfuscation']:3d}/{s['n_cases']:3d} "
              f"({s['miss_rate']*100:5.1f}%)  errors={s['errored']}")
    print(f"\nwrote {RESULTS_PATH}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()
    asyncio.run(main_async(args.concurrency, args.timeout))
