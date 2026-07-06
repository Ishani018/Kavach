r"""
test_format_tool_call.py — verify _format_tool_call handles every tool-call shape,
including zero-argument calls like get_channels that triggered the original crash.

Run:  .venv\Scripts\python.exe benchmarks\test_format_tool_call.py
"""
from __future__ import annotations

import sys
import json

# ---------------------------------------------------------------------------
# Minimal FunctionCall mimic (same attrs as agentdojo.functions_runtime.FunctionCall)
# ---------------------------------------------------------------------------
class FakeFunctionCall:
    def __init__(self, function: str, args: dict, id: str | None = None):
        self.function = function
        self.args = args
        self.id = id


def make_assistant_msg(tool_calls):
    """Build a minimal assistant message dict with the given tool_calls."""
    return {"role": "assistant", "tool_calls": tool_calls, "content": ""}


# ---------------------------------------------------------------------------
# Import the defense (agentdojo not required — the class falls through to the
# ImportError stub, so we re-import the module and grab the REAL class from the
# try-block by importing it from within the module's namespace.)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

# We need agentdojo installed for the real KavachDefense; import it directly.
from benchmarks.kavach_agentdojo_defense import KavachDefense

defense = KavachDefense()

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
PASS = 0
FAIL = 0

def check(label: str, tool_calls, expect_contains: str, expect_not_garbage: bool = True):
    global PASS, FAIL
    msgs = [make_assistant_msg(tool_calls)]
    result = defense._format_tool_call("user query", msgs)

    ok = True
    # 1) Must contain expected substring
    if expect_contains not in result:
        print(f"  FAIL [{label}]: expected {expect_contains!r} in {result!r}")
        ok = False

    # 2) Must NOT be detected as garbage when expect_not_garbage is True
    is_garbage = (
        "tool:unknown" in result
        or result.strip() == "args:{}"
        or result.strip().startswith("tool: args:")
    )
    if expect_not_garbage and is_garbage:
        print(f"  FAIL [{label}]: result {result!r} falsely detected as garbage")
        ok = False
    if not expect_not_garbage and not is_garbage:
        print(f"  FAIL [{label}]: result {result!r} should be garbage but wasn't")
        ok = False

    if ok:
        print(f"  PASS [{label}]: {result!r}")
        PASS += 1
    else:
        FAIL += 1


print("=" * 64)
print("Testing _format_tool_call + guard condition")
print("=" * 64)

# --- THE CRITICAL BUG: zero-argument calls must NOT be treated as garbage ---
check(
    "get_channels (zero-arg, Pydantic FunctionCall)",
    [FakeFunctionCall(function="get_channels", args={})],
    expect_contains="tool:get_channels",
    expect_not_garbage=True,
)

check(
    "get_channels (zero-arg, dict shape)",
    [{"function": "get_channels", "args": {}, "id": "call_1"}],
    expect_contains="tool:get_channels",
    expect_not_garbage=True,
)

# --- Normal multi-argument calls ---
check(
    "send_email (multi-arg)",
    [FakeFunctionCall(function="send_email", args={"to": "a@b.com", "body": "hello"})],
    expect_contains="tool:send_email",
)

check(
    "read_file (single-arg, dict)",
    [{"function": "read_file", "args": {"path": "/etc/passwd"}, "id": "call_2"}],
    expect_contains="tool:read_file",
)

# --- Genuinely broken extractions SHOULD be garbage ---
check(
    "unknown tool name (garbage)",
    [FakeFunctionCall(function="unknown", args={})],
    expect_contains="tool:unknown",
    expect_not_garbage=False,   # THIS should be garbage
)

print()
print("=" * 64)
print(f"Results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("❌ SOME TESTS FAILED")
    sys.exit(1)
else:
    print("✅ ALL TESTS PASSED")
print("=" * 64)
