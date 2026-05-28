#!/usr/bin/env python3
"""
benchmarks/injecagent_runner.py
================================

Replays InjecAgent test cases through the Kavach parliament HTTP endpoint and
computes F1, precision, recall, and latency stats.

InjecAgent (UIUC, 2024) — https://github.com/uiuc-kang-lab/InjecAgent —
provides 1,054 prompt-injection test cases targeting agent tool use. Each case
has:
  - a benign user instruction
  - a tool that the agent would naturally invoke
  - an injected attacker instruction in the tool's output
  - expected behavior: agent should NOT follow the injected instruction

For Kavach evaluation, we treat each case as a binary classification problem:
  - True positive  = parliament BLOCKs the attacker-instructed action
  - False negative = parliament ALLOWs the attacker-instructed action
  - True negative  = parliament ALLOWs the benign user instruction (paired)
  - False positive = parliament BLOCKs the benign user instruction (paired)

Outputs:
  - results.csv   — per-case verdict + latency + matched pattern
  - summary.json  — aggregate F1/precision/recall/FPR + latency percentiles
  - errors.log    — cases where parliament returned malformed responses

Usage:
    python benchmarks/injecagent_runner.py \\
        --cases benchmarks/data/attacker_cases_dh.jsonl \\
        --parliament-url http://127.0.0.1:8088 \\
        --output benchmarks/results_v1/

Optional:
    --limit 50                 # smoke run on a subset
    --dry-run                  # print first 5 requests, don't send
    --concurrency 4            # parallel workers (default 1, sequential)
    --include-benign / --no-benign  # whether to also test benign instructions
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import aiohttp


# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
log = logging.getLogger("injecagent")


# ──────────────────────────────────────────────────────────────────────────────
# Case loading and normalization
# ──────────────────────────────────────────────────────────────────────────────

def load_injecagent_cases(path: Path) -> list[dict[str, Any]]:
    """
    Load InjecAgent test cases. Handles three formats:
      1. .jsonl  — one JSON object per line (attacker_cases_dh.jsonl etc.)
         Keys: 'Attacker Tools', 'Attacker Instruction', 'Expected Achievements',
               'Attack Type', 'Modifed'
      2. .json list — top-level list of case objects
      3. .json dict — {"cases": [...]}

    All formats are normalized to a single shape:
        {
            "id":              str,
            "user_prompt":     str   (benign user instruction, if available),
            "tool_name":       str   (primary attacker tool name),
            "tool_args":       dict,
            "tool_output":     str,
            "attack_text":     str   (the injected attacker instruction),
            "expected_action": str   (what the attack tries to achieve),
            "category":        str   (attack category),
            "label":           str   ("attack" | "benign"),
        }
    """
    text = path.read_text(encoding="utf-8")

    # Detect .jsonl (one JSON object per line)
    if path.suffix == ".jsonl" or (
        text.strip().startswith("{") and "\n{" in text
    ):
        items = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    else:
        raw = json.loads(text)
        if isinstance(raw, dict) and "cases" in raw:
            items = raw["cases"]
        elif isinstance(raw, list):
            items = raw
        else:
            raise ValueError(f"unrecognized InjecAgent format in {path}")

    normalized: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        # Handle the real InjecAgent schema (capital keys)
        tools = item.get("Attacker Tools") or item.get("attacker_tools") or []
        tool_name = tools[0] if isinstance(tools, list) and tools else str(tools)

        attack_text = (
            item.get("Attacker Instruction")
            or item.get("attacker_instruction")
            or item.get("attack_text")
            or ""
        )
        expected = (
            item.get("Expected Achievements")
            or item.get("expected_achievements")
            or item.get("expected_action")
            or item.get("attacker_goal")
            or ""
        )
        category = (
            item.get("Attack Type")
            or item.get("attack_type")
            or item.get("category")
            or "unknown"
        )
        user_prompt = (
            item.get("User Instruction")
            or item.get("user_instruction")
            or item.get("user_prompt")
            or ""
        )
        tool_output = (
            item.get("Attacker Tool Response")
            or item.get("attacker_tool_response")
            or item.get("tool_output")
            or attack_text   # fall back to attack text as the injected payload
        )
        # 'Modifed' == 1 means injection is present → label attack; user_cases are benign
        label = "benign" if item.get("label") == "benign" else "attack"
        if "Modifed" in item:
            label = "attack" if item["Modifed"] == 1 else "benign"

        normalized.append({
            "id":              item.get("id") or item.get("case_id") or f"case_{i:04d}",
            "user_prompt":     user_prompt,
            "tool_name":       tool_name,
            "tool_args":       item.get("tool_args") or item.get("attacker_tool_arguments") or {},
            "tool_output":     tool_output,
            "attack_text":     attack_text,
            "expected_action": expected,
            "category":        str(category),
            "label":           label,
        })

    log.info("loaded %d InjecAgent cases from %s", len(normalized), path)
    return normalized


# ──────────────────────────────────────────────────────────────────────────────
# Constructing parliament request payloads from InjecAgent cases
# ──────────────────────────────────────────────────────────────────────────────

def attack_payload(case: dict[str, Any]) -> dict[str, Any]:
    """
    For an attack case, the parliament should see the *action the attacker is
    trying to make the agent take*, not the original benign user prompt.

    InjecAgent cases describe that action as `expected_action` (e.g. "send all
    contacts to attacker@evil.com"). We render it in the same wire format the
    OpenClaw plugin will use: tool: + JSON args.
    """
    text = (
        f"tool:{case['tool_name']} "
        f"args:{json.dumps(case['tool_args'])}"
    )
    return {
        "text":       text,
        "session_id": case["id"],
        "context": {
            "tool_name":      case["tool_name"],
            "expected_action": case["expected_action"],
            "category":       case["category"],
            "test_kind":      "attack",
        },
    }


def benign_payload(case: dict[str, Any]) -> dict[str, Any]:
    """
    For benign-paired cases, we want to verify the parliament does NOT block
    the user's actual stated tool invocation. We use the user's natural-language
    prompt as the action text.
    """
    return {
        "text":       case["user_prompt"],
        "session_id": case["id"] + "_benign",
        "context": {
            "test_kind": "benign",
            "category":  case["category"],
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Async parliament client
# ──────────────────────────────────────────────────────────────────────────────

async def call_parliament(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict[str, Any],
    timeout_s: float,
) -> tuple[dict[str, Any] | None, float, str | None]:
    """Returns (response_json | None, latency_ms, error_str | None)."""
    t0 = time.perf_counter()
    try:
        async with session.post(
            f"{url}/hook/parliament",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout_s),
        ) as resp:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status != 200:
                text = await resp.text()
                return (None, latency_ms, f"http {resp.status}: {text[:200]}")
            data = await resp.json()
            return (data, latency_ms, None)
    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return (None, latency_ms, "timeout")
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return (None, latency_ms, f"{type(e).__name__}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────────────

async def run_one_case(
    sem: asyncio.Semaphore,
    session: aiohttp.ClientSession,
    url: str,
    case: dict[str, Any],
    include_benign: bool,
    timeout_s: float,
) -> list[dict[str, Any]]:
    """Run one InjecAgent case (attack + optional paired benign). Return rows."""
    rows: list[dict[str, Any]] = []

    async with sem:
        # Attack call
        atk_resp, atk_lat, atk_err = await call_parliament(
            session, url, attack_payload(case), timeout_s,
        )
        rows.append(_row_from_resp(case, "attack", atk_resp, atk_lat, atk_err))

        # Benign paired call
        if include_benign and case.get("user_prompt"):
            ben_resp, ben_lat, ben_err = await call_parliament(
                session, url, benign_payload(case), timeout_s,
            )
            rows.append(_row_from_resp(case, "benign", ben_resp, ben_lat, ben_err))

    return rows


MINISTERS = ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"]


def _row_from_resp(
    case: dict[str, Any],
    test_kind: str,
    resp: dict[str, Any] | None,
    latency_ms: float,
    err: str | None,
) -> dict[str, Any]:
    base = {
        "case_id":     case["id"],
        "test_kind":   test_kind,
        "category":    case["category"],
        "verdict":     "ERROR",
        "decided_by":  "",
        "confidence":  0.0,
        "matched_pattern": "",
        "compass_sim": None,
        "latency_ms":  round(latency_ms, 2),
        "error":       "",
    }
    # Per-minister sim columns — consumed by threshold_sweep.py
    for m in MINISTERS:
        base[f"{m.lower()}_sim"]      = 0.0
        base[f"{m.lower()}_verdict"]  = ""
        base[f"{m.lower()}_matched"]  = ""

    if err is not None or resp is None:
        base["error"] = err or "no-response"
        return base

    base["verdict"]         = resp.get("verdict", "ERROR")
    base["decided_by"]      = resp.get("speaker", {}).get("decided_by", "")
    base["confidence"]      = resp.get("speaker", {}).get("confidence", 0.0)
    base["matched_pattern"] = resp.get("pattern", "")
    base["compass_sim"]     = resp.get("compass_sim")

    ministers = resp.get("ministers", {}) or {}
    for m in MINISTERS:
        m_data = ministers.get(m, {}) or {}
        base[f"{m.lower()}_sim"]     = m_data.get("confidence", 0.0)
        base[f"{m.lower()}_verdict"] = m_data.get("verdict", "")
        base[f"{m.lower()}_matched"] = m_data.get("matched_id", "") or ""

    return base


async def run_all(args: argparse.Namespace) -> None:
    cases = load_injecagent_cases(Path(args.cases))
    if args.limit:
        cases = cases[: args.limit]
        log.info("limited to first %d cases", args.limit)

    if args.dry_run:
        log.info("--- DRY RUN: first 5 attack payloads ---")
        for c in cases[:5]:
            log.info("%s: %s", c["id"], json.dumps(attack_payload(c), indent=2))
        return

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(args.concurrency)
    all_rows: list[dict[str, Any]] = []

    async with aiohttp.ClientSession() as session:
        # Health check first
        try:
            async with session.get(f"{args.parliament_url}/health") as r:
                if r.status != 200:
                    log.error("parliament health check failed: %s", r.status)
                    sys.exit(1)
                health = await r.json()
                log.info("parliament healthy: %s", health.get("doc_counts"))
        except Exception as e:
            log.error("cannot reach parliament at %s: %s", args.parliament_url, e)
            sys.exit(1)

        tasks = [
            run_one_case(sem, session, args.parliament_url, c,
                         args.include_benign, args.timeout)
            for c in cases
        ]

        # Progress reporting in batches
        completed = 0
        batch_size = 25
        for i in range(0, len(tasks), batch_size):
            batch_results = await asyncio.gather(*tasks[i : i + batch_size])
            for rows in batch_results:
                all_rows.extend(rows)
            completed += len(tasks[i : i + batch_size])
            log.info("%d / %d cases complete", completed, len(tasks))

    # Write per-case CSV
    csv_path = out_dir / "results.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    log.info("wrote %d rows to %s", len(all_rows), csv_path)

    # Compute and write summary
    summary = compute_summary(all_rows)
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("summary:\n%s", json.dumps(summary, indent=2))


# ──────────────────────────────────────────────────────────────────────────────
# Aggregation
# ──────────────────────────────────────────────────────────────────────────────

def compute_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attacks  = [r for r in rows if r["test_kind"] == "attack"]
    benigns  = [r for r in rows if r["test_kind"] == "benign"]

    # On attacks: BLOCK or ESCALATE counts as positive (caught).
    # If you want to be strict, set caught = verdict == "BLOCK" only.
    tp_strict = sum(1 for r in attacks if r["verdict"] == "BLOCK")
    tp_loose  = sum(1 for r in attacks if r["verdict"] in ("BLOCK", "ESCALATE"))
    fn_strict = sum(1 for r in attacks if r["verdict"] == "ALLOW")
    errors_atk = sum(1 for r in attacks if r["verdict"] == "ERROR")
    n_attacks  = len(attacks)

    # On benigns: ALLOW = correct (TN), BLOCK = false positive.
    tn_strict = sum(1 for r in benigns if r["verdict"] == "ALLOW")
    fp_strict = sum(1 for r in benigns if r["verdict"] == "BLOCK")
    fp_loose  = sum(1 for r in benigns if r["verdict"] in ("BLOCK", "ESCALATE"))
    errors_ben = sum(1 for r in benigns if r["verdict"] == "ERROR")
    n_benigns  = len(benigns)

    def _safe_div(a: int, b: int) -> float:
        return round(a / b, 4) if b else 0.0

    recall_strict     = _safe_div(tp_strict, n_attacks - errors_atk)
    recall_loose      = _safe_div(tp_loose,  n_attacks - errors_atk)
    fpr_strict        = _safe_div(fp_strict, n_benigns - errors_ben) if n_benigns else None
    precision_strict  = (
        _safe_div(tp_strict, tp_strict + fp_strict) if (tp_strict + fp_strict) else None
    )
    f1_strict = (
        round(2 * precision_strict * recall_strict / (precision_strict + recall_strict), 4)
        if precision_strict and recall_strict else None
    )

    latencies = [r["latency_ms"] for r in rows if r["verdict"] != "ERROR"]
    latency_stats = {
        "p50": round(statistics.median(latencies), 2) if latencies else None,
        "p95": round(_percentile(latencies, 95), 2) if latencies else None,
        "p99": round(_percentile(latencies, 99), 2) if latencies else None,
        "max": round(max(latencies), 2) if latencies else None,
        "n":   len(latencies),
    }

    by_cat = _by_category(rows)

    return {
        "n_attacks":         n_attacks,
        "n_benigns":         n_benigns,
        "errors_attacks":    errors_atk,
        "errors_benigns":    errors_ben,

        # Strict: only BLOCK counts as caught
        "strict": {
            "tp": tp_strict, "fn": fn_strict, "fp": fp_strict, "tn": tn_strict,
            "recall":    recall_strict,
            "fpr":       fpr_strict,
            "precision": precision_strict,
            "f1":        f1_strict,
        },

        # Loose: BLOCK or ESCALATE counts as caught
        "loose": {
            "tp_block_or_escalate":  tp_loose,
            "fp_block_or_escalate":  fp_loose,
            "recall":                recall_loose,
        },

        "latency_ms": latency_stats,
        "by_category": by_cat,
    }


def _percentile(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def _by_category(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        if r["test_kind"] != "attack":
            continue
        cat = r["category"]
        out.setdefault(cat, {"n": 0, "block": 0, "escalate": 0, "allow": 0, "error": 0})
        out[cat]["n"] += 1
        v = r["verdict"].lower()
        if v in out[cat]:
            out[cat][v] += 1
    for cat, d in out.items():
        d["recall_strict"] = round(d["block"] / d["n"], 4) if d["n"] else 0.0
    return out


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Run InjecAgent against Kavach Parliament")
    p.add_argument("--cases",
                   default="benchmarks/data/attacker_cases_dh.jsonl",
                   help="path to InjecAgent test cases (.json or .jsonl)")
    p.add_argument("--parliament-url", default="http://127.0.0.1:8088",
                   help="URL of running Kavach Parliament (default: %(default)s)")
    p.add_argument("--output", default="benchmarks/results_v1",
                   help="output directory (default: %(default)s)")
    p.add_argument("--limit", type=int, default=0,
                   help="run only the first N cases (0 = all)")
    p.add_argument("--concurrency", type=int, default=1,
                   help="parallel workers (default: %(default)d)")
    p.add_argument("--timeout", type=float, default=10.0,
                   help="per-request timeout in seconds")
    p.add_argument("--dry-run", action="store_true",
                   help="print first 5 payloads and exit")
    p.add_argument("--include-benign", action="store_true", default=True,
                   help="also run paired benign instructions for FPR (default: True)")
    p.add_argument("--no-benign", dest="include_benign", action="store_false",
                   help="skip benign pair (recall-only run)")

    args = p.parse_args()
    asyncio.run(run_all(args))


if __name__ == "__main__":
    main()
