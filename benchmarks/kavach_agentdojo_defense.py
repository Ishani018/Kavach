"""
benchmarks/kavach_agentdojo_defense.py
=======================================

AgentDojo custom defense adapter for the Kavach parliament.

USAGE
-----
Make sure the Kavach parliament is running first:
    ./kavach_boot.sh --skip-patch

Then run AgentDojo with the Kavach defense:

    # Workspace suite (start here — smallest, ~30 min with a 27B local model)
    python -m agentdojo.scripts.benchmark \\
        -s workspace \\
        --model ollama_chat/gemma4:27b \\
        --defense KavachDefense \\
        --module-to-load benchmarks.kavach_agentdojo_defense \\
        --attack important_instructions \\
        --max-workers 2 \\
        2>&1 | tee benchmarks/results_v2/agentdojo_workspace.log

    # Baseline (no defense) — run this first so you have the comparison point
    python -m agentdojo.scripts.benchmark \\
        -s workspace \\
        --model ollama_chat/gemma4:27b \\
        --attack important_instructions \\
        --max-workers 2 \\
        2>&1 | tee benchmarks/results_v2/agentdojo_baseline.log

    # Full suite (run overnight)
    for suite in workspace-plus banking travel slack; do
        python -m agentdojo.scripts.benchmark \\
            -s $suite \\
            --model ollama_chat/gemma4:27b \\
            --defense KavachDefense \\
            --module-to-load benchmarks.kavach_agentdojo_defense \\
            --attack important_instructions \\
            --max-workers 2 \\
            2>&1 | tee -a benchmarks/results_v2/agentdojo_full.log
    done

ENVIRONMENT
-----------
KAVACH_URL      Parliament base URL (default: http://127.0.0.1:8088)
KAVACH_SESSION  Session ID prefix for AgentDojo runs (default: agentdojo)
KAVACH_TIMEOUT  Per-call timeout in seconds (default: 10)

INSTALL
-------
    pip install agentdojo --break-system-packages
    pip install inspect-ai --break-system-packages
    pip install inspect_evals --break-system-packages

VERIFY GEMMA TOOL-CALLING (required before AgentDojo will work)
-------
    python - << 'EOF'
    import requests, json
    resp = requests.post("http://localhost:11434/v1/chat/completions", json={
        "model": "gemma4:27b",
        "messages": [{"role": "user", "content": "Use the calculator tool to compute 2+2."}],
        "tools": [{"type":"function","function":{"name":"calculator","description":"Calculate","parameters":{"type":"object","properties":{"expr":{"type":"string"}}}}}]
    })
    choice = resp.json()["choices"][0]
    print("finish_reason:", choice["finish_reason"])
    print("tool_calls OK:", bool(choice["message"].get("tool_calls")))
    EOF

If finish_reason is "stop" (not "tool_calls"), switch to:
    --model ollama_chat/qwen2.5:32b
and note which model you used in PARV_RESULTS.md.

METRICS (what to report)
-------
From the AgentDojo summary at the end of each run:
  - Benign utility        (baseline target: ~47.73%)
  - Utility under attack  
  - Attack success rate   (ASR) (baseline: 17.63%, our target: ≤5%)

All four go into benchmarks/results_v2/PARV_RESULTS.md.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any

import requests

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Config from environment
# ──────────────────────────────────────────────────────────────────────────────

KAVACH_URL     = os.environ.get("KAVACH_URL", "http://127.0.0.1:8088")
KAVACH_SESSION = os.environ.get("KAVACH_SESSION", "agentdojo")
KAVACH_TIMEOUT = float(os.environ.get("KAVACH_TIMEOUT", "10"))

# ──────────────────────────────────────────────────────────────────────────────
# Defense class
# ──────────────────────────────────────────────────────────────────────────────

try:
    from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
    from agentdojo.types import ChatToolResultMessage, text_content_block_from_string

    class KavachDefense(BasePipelineElement):
        """Wraps the Kavach parliament as an AgentDojo defense.

        Intercepts each tool call before execution via the parliament endpoint.
        If parliament returns BLOCK or traj_risk >= ceiling, the tool call is
        suppressed and a safe refusal message is returned to the agent instead.

        Fail-open: if the parliament is unreachable, the tool call is allowed
        through (same as the plugin's reply fail-mode). This prevents Kavach
        downtime from breaking AgentDojo benchmark runs entirely.
        """

        name = "KavachDefense"

        def __init__(self) -> None:
            self._call_count  = 0
            self._block_count = 0
            self._traj_blocks = 0
            # Auditability: every call where the parliament did NOT return a
            # usable verdict (timeout, unreachable, HTTP error, bad JSON) is a
            # fail-OPEN — the action passed through UNSCREENED. We record the
            # count and the affected call indices so a run with fail-opens is
            # salvageable (we know which calls were really defended) instead of
            # silently invalid.
            self._failopen_count = 0
            self._failopen_calls: list[int] = []
            self._seeded_sessions: set[str] = set()

        def query(
            self,
            query: str,
            runtime: Any,
            env: Any = None,
            messages: Any = (),
            extra_args: dict | None = None,
            **kwargs: Any,
        ):
            """Screen the latest tool call before it executes.

            AgentDojo (0.1.x) pipeline-element contract: takes and returns the
            5-tuple (query, runtime, env, messages, extra_args). KavachDefense
            sits inside the ToolsExecutionLoop, so it sees each tool call; if
            the parliament returns BLOCK, we return refusal tool result messages
            so the subsequent ToolsExecutor skips execution.
            """
            if extra_args is None:
                extra_args = {}
            messages = list(messages)
            if not messages:
                return query, runtime, env, messages, extra_args

            last_msg = messages[-1]
            if self._attr(last_msg, "role") != "assistant" or not self._attr(last_msg, "tool_calls"):
                # No tool calls to screen
                return query, runtime, env, messages, extra_args

            self._call_count += 1
            tool_text = self._format_tool_call(query, messages)

            # IMPOSSIBLE-TO-MISS GUARD (bug #1 regression detector): if the action
            # we are about to send Kavach is the empty/unknown placeholder, the
            # tool call was not extracted correctly and the parliament is screening
            # NOTHING — every downstream security number would be fake. Abort the
            # whole run loudly rather than silently producing meaningless results.
            if "tool:unknown" in tool_text or tool_text.strip().endswith("args:{}"):
                self._garbage_calls = getattr(self, "_garbage_calls", 0) + 1
                if self._garbage_calls <= 3:
                    log.error("[KavachDefense] EMPTY ACTION sent to parliament: %r", tool_text)
                if self._garbage_calls >= 5:
                    banner = "🛑 " * 20
                    raise RuntimeError(
                        "\n" + banner + "\n"
                        "[KAVACH FATAL] _format_tool_call produced an EMPTY action "
                        f"({tool_text!r}) for {self._garbage_calls} calls.\n"
                        "Kavach is screening NOTHING — bug #1 has regressed (the tool\n"
                        "call is not being extracted from AgentDojo's FunctionCall).\n"
                        "ALL security numbers from this run would be FAKE. Aborting.\n"
                        "Fix _format_tool_call (use tc.function / tc.args) before re-running.\n"
                        + banner
                    )

            session_id = f"{KAVACH_SESSION}-{id(env)}"

            if session_id not in self._seeded_sessions:
                try:
                    seed_resp = requests.post(
                        f"{KAVACH_URL}/hook/seed_intent",
                        json={
                            "text": query,
                            "session_id": session_id,
                        },
                        timeout=KAVACH_TIMEOUT,
                    )
                    seed_resp.raise_for_status()
                    self._seeded_sessions.add(session_id)
                except Exception as exc:
                    log.warning("[KavachDefense] Failed to seed intent for session %s: %s", session_id, exc)

            try:
                resp = requests.post(
                    f"{KAVACH_URL}/hook/parliament",
                    json={
                        "text":       tool_text,
                        "session_id": session_id,
                        "context":    {"source": "agentdojo", "call_n": self._call_count},
                    },
                    timeout=KAVACH_TIMEOUT,
                )
                resp.raise_for_status()
                result    = resp.json()
                verdict   = result.get("verdict", "ALLOW")
                traj_risk = result.get("traj_risk") or 0.0
                decided   = result.get("speaker", {}).get("decided_by", "UNKNOWN")
                reason    = result.get("speaker", {}).get("reason", "")

                if verdict == "BLOCK":
                    self._block_count += 1
                    if decided == "TRAJECTORY":
                        self._traj_blocks += 1
                    log.info(
                        "[KavachDefense] BLOCK call=%d decided_by=%s traj_risk=%.3f reason=%s",
                        self._call_count, decided, traj_risk, reason[:80],
                    )
                    refusal = (
                        f"[KAVACH BLOCK — decided_by={decided}, traj_risk={traj_risk:.3f}] "
                        f"This action was blocked by the Kavach security monitor. "
                        f"Reason: {reason[:120]}"
                    )
                    # Construct ChatToolResultMessage for each pending tool call to abort execution
                    tool_call_results = []
                    tcs = self._attr(last_msg, "tool_calls") or []
                    for tc in tcs:
                        tool_call_results.append(
                            ChatToolResultMessage(
                                role="tool",
                                content=[text_content_block_from_string(refusal)],
                                tool_call_id=self._attr(tc, "id"),
                                tool_call=tc,
                                error=refusal,
                            )
                        )
                    messages = [*messages, *tool_call_results]
                    return query, runtime, env, messages, extra_args

                log.debug(
                    "[KavachDefense] %s call=%d traj_risk=%.3f",
                    verdict, self._call_count, traj_risk,
                )

            except requests.exceptions.Timeout:
                self._failopen_count += 1
                self._failopen_calls.append(self._call_count)
                log.warning("[KavachDefense] call=%d parliament timeout — FAILING OPEN "
                            "(action UNSCREENED)", self._call_count)
            except Exception as exc:
                self._failopen_count += 1
                self._failopen_calls.append(self._call_count)
                log.warning("[KavachDefense] call=%d parliament unreachable: %s — FAILING OPEN "
                            "(action UNSCREENED)", self._call_count, exc)

            # ALLOW or fail-open: pass through unchanged
            return query, runtime, env, messages, extra_args

        @staticmethod
        def _attr(obj, key, default=None):
            """Read `key` whether obj is a dict or a pydantic/attr object."""
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        def _format_tool_call(self, query: str, messages: list) -> str:
            """Format the pending tool call as a parliament-scorable string.

            BUG-#1 FIX: AgentDojo's FunctionCall exposes `.function` (the tool
            NAME, a str) and `.args` (the argument dict) — there is NO `.name`
            or `.arguments`. The previous code read `fn.name`/`fn.arguments`,
            so every call reached the parliament as `tool:unknown args:{}` and
            Kavach screened an empty action. We now read `.function`/`.args`
            directly, with a dict-shaped fallback for other AgentDojo versions.
            """
            import json as _json
            for msg in reversed(messages):
                role = self._attr(msg, "role")
                tcs = self._attr(msg, "tool_calls")
                if role == "assistant" and tcs:
                    tc = tcs[0]
                    # Correct field names for AgentDojo 0.1.x FunctionCall.
                    name = self._attr(tc, "function", None)
                    args = self._attr(tc, "args", None)
                    # Fallbacks for older/dict shapes (function nested under a
                    # 'function' object, or args under 'arguments').
                    if name is None:
                        fn = self._attr(tc, "function_obj", None)
                        name = self._attr(fn, "name", "unknown") if fn else "unknown"
                    if args is None:
                        args = self._attr(tc, "arguments", {}) or {}
                    try:
                        args_str = _json.dumps(args, default=str, ensure_ascii=False)
                    except Exception:
                        args_str = str(args)
                    return f"tool:{name} args:{args_str}"
            return query

        def summary(self) -> dict:
            """Block + fail-open summary for the end-of-run report.

            `failopen_count` / `failopen_calls` make a run auditable: if any
            calls failed open, those actions were NOT screened by Kavach, so the
            'defended' numbers for them are invalid. A nonzero count means the
            run is only partially defended — surface it loudly.
            """
            screened = self._call_count - self._failopen_count
            return {
                "total_calls":     self._call_count,
                "screened_calls":  screened,
                "blocks":          self._block_count,
                "traj_blocks":     self._traj_blocks,
                "allows":          screened - self._block_count,
                "failopen_count":  self._failopen_count,
                "failopen_calls":  list(self._failopen_calls),
                "fully_defended":  self._failopen_count == 0,
            }

except ImportError:
    # AgentDojo not installed — provide a helpful error rather than a silent failure
    class KavachDefense:  # type: ignore[no-redef]
        name = "KavachDefense"

        def __init__(self) -> None:
            raise ImportError(
                "AgentDojo is not installed. Run:\n"
                "  pip install agentdojo --break-system-packages\n"
                "  pip install inspect-ai --break-system-packages"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Smoke test — python benchmarks/kavach_agentdojo_defense.py
# Verifies the parliament is reachable and the defense class instantiates.
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print(f"Kavach parliament URL: {KAVACH_URL}")

    # Health check
    try:
        r = requests.get(f"{KAVACH_URL}/health", timeout=5)
        print(f"Parliament health: {r.json()}")
    except Exception as e:
        print(f"Parliament unreachable: {e}")
        print("Make sure ./kavach_boot.sh --skip-patch has been run first.")
        sys.exit(1)

    # Quick parliament call
    t0 = time.perf_counter()
    r = requests.post(
        f"{KAVACH_URL}/hook/parliament",
        json={"text": 'tool:read args:{"path":"/etc/passwd"}', "session_id": "smoke-test"},
        timeout=10,
    )
    latency = (time.perf_counter() - t0) * 1000
    result  = r.json()
    print(f"Test call verdict:  {result.get('verdict')}")
    print(f"Test call traj_risk:{result.get('traj_risk')}")
    print(f"Test call latency:  {latency:.0f}ms")
    print(f"\nKavachDefense ready. Register with AgentDojo via:")
    print(f"  --defense KavachDefense --module-to-load benchmarks.kavach_agentdojo_defense")
