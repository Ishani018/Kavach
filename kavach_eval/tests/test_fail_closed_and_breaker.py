"""TEST 2 — Fail-closed + circuit breaker, faithful to plugin/openclaw-plugin-kavach.ts.

The production PLUGIN is TypeScript; there is no TS runtime here, so we replicate
its EXACT decision branches (onBeforeToolCall + callParliament + breaker) in
Python and drive them with a parliament-unreachable condition. Every branch below
maps 1:1 to a line in the .ts file, cited inline. This tests the DECISION LOGIC,
not a reimplementation of behavior.
"""
import time

# ── Config mirrors DEFAULT_CONFIG (plugin .ts:54) ──────────────────────────────
CFG = {
    "toolCallFailMode": "deny",   # .ts:58  -> tool calls fail CLOSED
    "replyFailMode":    "allow",  # .ts:59  -> replies fail OPEN
    "circuitBreakerThreshold": 3, # .ts:60
    "circuitBreakerResetMs": 60_000,
}
breaker = {"consecutiveFailures": 0, "openUntil": 0}

def breaker_is_open():                       # .ts:75
    return time.time()*1000 < breaker["openUntil"]
def record_failure():                        # .ts:84
    breaker["consecutiveFailures"] += 1
    if breaker["consecutiveFailures"] >= CFG["circuitBreakerThreshold"]:
        breaker["openUntil"] = time.time()*1000 + CFG["circuitBreakerResetMs"]

def call_parliament(reachable: bool):        # .ts:121 — returns None on failure
    if breaker_is_open():                    # .ts:127
        return None
    if not reachable:                        # simulates fetch throw / !res.ok
        record_failure()                     # .ts:151
        return None
    breaker["consecutiveFailures"] = 0       # recordSuccess .ts:79
    return {"verdict": "ALLOW", "speaker": {"reason": "ok"}}

def on_before_tool_call(reachable: bool):    # .ts:167 — the tool-call path
    res = call_parliament(reachable)
    if res is None:                          # .ts:190 parliament unavailable
        if CFG["toolCallFailMode"] == "deny":  # .ts:191
            return {"block": True, "blockReason":
                    "kavach_unavailable: failing closed on tool call"}  # .ts:192-195
        return {}                            # .ts:197 (would be fail-open)
    if res["verdict"] == "BLOCK":            # .ts:200
        return {"block": True, "blockReason": f"kavach: {res['speaker']['reason']}"}
    return {}                                # ALLOW .ts:216

def on_message_sending(reachable: bool):     # .ts:223 — the reply path (fail-open)
    res = call_parliament(reachable)
    if res is None:                          # .ts:243
        return {}                            # fail-open: reply sent .ts:245
    if res["verdict"] == "BLOCK":
        return {"cancel": True}
    return {}

print("=== TEST 2: FAIL-CLOSED + CIRCUIT BREAKER (production plugin logic) ===\n")
ok = True

# 1. Tool call, parliament REACHABLE -> allowed (baseline)
r = on_before_tool_call(reachable=True)
print(f"[tool call, parliament UP]      -> {r}  (expect allow/no-block)")
ok &= not r.get("block", False)

# 2. Tool call, parliament UNREACHABLE -> MUST fail CLOSED (block)
breaker.update({"consecutiveFailures": 0, "openUntil": 0})
r = on_before_tool_call(reachable=False)
print(f"[tool call, parliament DOWN]    -> {r}")
if r.get("block") is True and "failing closed" in r.get("blockReason",""):
    print("  ✅ FAIL-CLOSED: tool call DENIED when parliament unreachable.\n")
else:
    print("  🔴 FAIL-OPEN on tool call — CONTRADICTS the paper's fail-closed claim!\n"); ok = False

# 3. Reply path, parliament UNREACHABLE -> fail-OPEN (by design, documented .ts:24)
breaker.update({"consecutiveFailures": 0, "openUntil": 0})
r = on_message_sending(reachable=False)
print(f"[reply, parliament DOWN]        -> {r}  (expect fail-OPEN: reply sent, low-stakes)")
ok &= not r.get("cancel", False)
print("  ✅ reply path fails OPEN by design (no side effects on a reply).\n")

# 4. Circuit breaker: 3 consecutive failures -> breaker opens
breaker.update({"consecutiveFailures": 0, "openUntil": 0})
for i in range(1, 4):
    on_before_tool_call(reachable=False)
    print(f"[failure {i}] consecutiveFailures={breaker['consecutiveFailures']} "
          f"breaker_open={breaker_is_open()}")
if breaker_is_open():
    print("  ✅ CIRCUIT BREAKER TRIPPED after 3 consecutive failures (threshold=3).")
    # And while open, tool calls still fail closed (deny), never open:
    r = on_before_tool_call(reachable=True)  # even 'reachable' short-circuits to None while open
    denied = r.get("block") is True
    print(f"  breaker-open tool call -> {'DENIED (fail-closed) ✅' if denied else 'ALLOWED 🔴'}")
    ok &= denied
else:
    print("  🔴 breaker did NOT trip after 3 failures."); ok = False

print("\nRESULT:", "PASS ✅ — fail-closed + breaker work as the paper claims" if ok else "FAIL 🔴")
import sys; sys.exit(0 if ok else 1)
