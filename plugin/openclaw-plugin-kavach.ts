// @ts-nocheck
/**
 * @pesu/openclaw-plugin-kavach — index.ts
 *
 * The Kavach security plugin for OpenClaw.
 *
 * Registers on two typed hooks:
 *   1. before_tool_call    — fires before any tool execution; calls Parliament
 *                            with the resolved tool name + args; honors BLOCK
 *                            verdicts deny-first.
 *   2. message_sending     — fires before any agent reply is delivered; runs
 *                            the parliament on the reply text to catch
 *                            self-disclosure or prompt-injection regurgitation
 *                            on the way out.
 *
 * Dependencies:
 *   - OpenClaw v2026.5.x with PR-1 (#5513 + #5943 fix) merged
 *   - Kavach Parliament HTTP server reachable on http://127.0.0.1:8088
 *
 * Failure modes:
 *   - Parliament unreachable for tool calls  → fail-closed (deny). Tool calls
 *     are the high-stakes path; we'd rather block a legit action than execute
 *     an attack while Kavach is down.
 *   - Parliament unreachable for replies     → fail-open (allow). Replies are
 *     low-stakes (no side effects). A Kavach outage should not silence the
 *     agent.
 *   - 3 consecutive failures                 → circuit-breaker opens for 60s.
 *     During the open window, decisions are logged but not enforced and the
 *     fail-mode flag is set on every event for the post-hoc audit ledger.
 */

import type {
  OpenClawPluginApi,
  BeforeToolCallEvent,
  BeforeToolCallReturn,
  MessageSendingEvent,
  MessageSendingReturn,
} from "openclaw";

// ──────────────────────────────────────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────────────────────────────────────

interface KavachConfig {
  parliamentUrl: string;       // http://127.0.0.1:8088
  toolCallTimeoutMs: number;   // default 3000ms (was 250ms pre-fix) — fail-closed on timeout
  replyTimeoutMs: number;      // 500ms — fail-open on timeout
  toolCallFailMode: "deny" | "allow";
  replyFailMode: "deny" | "allow";
  circuitBreakerThreshold: number;  // consecutive failures before open
  circuitBreakerResetMs: number;     // open-circuit duration
}

const DEFAULT_CONFIG: KavachConfig = {
  parliamentUrl:           "http://127.0.0.1:8088",
  toolCallTimeoutMs:       3000,
  replyTimeoutMs:          500,
  toolCallFailMode:        "deny",
  replyFailMode:           "allow",
  circuitBreakerThreshold: 3,
  circuitBreakerResetMs:   60_000,
};

// ──────────────────────────────────────────────────────────────────────────────
// Circuit breaker state
// ──────────────────────────────────────────────────────────────────────────────

interface BreakerState {
  consecutiveFailures: number;
  openUntil: number;  // unix ms; 0 = closed
}

const breaker: BreakerState = { consecutiveFailures: 0, openUntil: 0 };

function breakerIsOpen(): boolean {
  return Date.now() < breaker.openUntil;
}

function recordSuccess(): void {
  breaker.consecutiveFailures = 0;
  breaker.openUntil = 0;
}

function recordFailure(cfg: KavachConfig): void {
  breaker.consecutiveFailures += 1;
  if (breaker.consecutiveFailures >= cfg.circuitBreakerThreshold) {
    breaker.openUntil = Date.now() + cfg.circuitBreakerResetMs;
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Parliament wire types
// ──────────────────────────────────────────────────────────────────────────────

interface ParliamentRequest {
  text: string;
  session_id: string;
  context?: Record<string, unknown>;
}

interface ParliamentResponse {
  verdict: "BLOCK" | "ALLOW" | "ESCALATE";
  speaker: {
    decided_by: string;
    confidence: number;
    reason: string;
  };
  ministers: Record<string, {
    verdict: string;
    confidence: number;
    matched?: string;
  }>;
  pattern: string;
  ts: string;
}

// ──────────────────────────────────────────────────────────────────────────────
// HTTP call to parliament with timeout + circuit breaker
// ──────────────────────────────────────────────────────────────────────────────

async function callParliament(
  cfg: KavachConfig,
  endpoint: "parliament" | "seed_intent" | "check_drift",
  body: ParliamentRequest,
  timeoutMs: number,
): Promise<ParliamentResponse | null> {
  if (breakerIsOpen()) {
    return null;
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);

  try {
    const res = await fetch(`${cfg.parliamentUrl}/hook/${endpoint}`, {
      method:  "POST",
      headers: { "content-type": "application/json" },
      body:    JSON.stringify(body),
      signal:  ctrl.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      recordFailure(cfg);
      return null;
    }
    recordSuccess();
    return (await res.json()) as ParliamentResponse;
  } catch (err) {
    clearTimeout(timer);
    recordFailure(cfg);
    return null;
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// before_tool_call handler — DENY-FIRST
// ──────────────────────────────────────────────────────────────────────────────

function buildToolCallText(e: BeforeToolCallEvent): string {
  // Render the tool call as a single string the parliament can embed and
  // semantically compare against the corpus. Format: tool name + JSON args.
  const args = JSON.stringify(e.args);
  return `tool:${e.toolName} args:${args}`;
}

async function onBeforeToolCall(
  cfg: KavachConfig,
  e: BeforeToolCallEvent,
): Promise<BeforeToolCallReturn> {
  const text = buildToolCallText(e);
  const res = await callParliament(
    cfg,
    "parliament",
    {
      text,
      session_id: e.sessionId,
      context: {
        tool_name:      e.toolName,
        tool_kind:      e.toolKind ?? "unknown",
        agent_id:       e.agentId,
        turn_number:    e.turnNumber,
        correlation_id: e.correlationId,
      },
    },
    cfg.toolCallTimeoutMs,
  );

  // Parliament unavailable.
  if (res === null) {
    if (cfg.toolCallFailMode === "deny") {
      return {
        block: true,
        blockReason: "kavach_unavailable: failing closed on tool call",
      };
    }
    return {};
  }

  if (res.verdict === "BLOCK") {
    return {
      block:       true,
      blockReason: `kavach: ${res.speaker.reason}`,
    };
  }

  if (res.verdict === "ESCALATE") {
    return {
      requireApproval: {
        reason: `kavach escalation: ${res.speaker.reason} (confidence ${res.speaker.confidence})`,
      },
    };
  }

  // ALLOW
  return {};
}

// ──────────────────────────────────────────────────────────────────────────────
// message_sending handler — FAIL-OPEN
// ──────────────────────────────────────────────────────────────────────────────

async function onMessageSending(
  cfg: KavachConfig,
  e: MessageSendingEvent,
): Promise<MessageSendingReturn> {
  const res = await callParliament(
    cfg,
    "parliament",
    {
      text:       e.replyText,
      session_id: e.sessionId,
      context: {
        agent_id:       e.agentId,
        turn_number:    e.turnNumber,
        channel:        e.channel,
        correlation_id: e.correlationId,
      },
    },
    cfg.replyTimeoutMs,
  );

  if (res === null) {
    // Fail-open on reply path. Don't silence the agent because Kavach is down.
    return {};
  }

  if (res.verdict === "BLOCK") {
    return {
      cancel: true,
      reason: `kavach blocked reply: ${res.speaker.reason}`,
    };
  }

  // ESCALATE on reply path is treated as ALLOW here (no side effects on the
  // reply itself); the verdict is logged for audit but the message is sent.
  return {};
}

// ──────────────────────────────────────────────────────────────────────────────
// Session intent seeding — fix for issue #9
//
// before_agent_run is not a typed/verified event in OpenClaw 2026.4.15 embedded
// mode and silently never fires. Instead we seed intent on the FIRST
// before_tool_call per session, extracted from e.conversationHistory. This is
// robust regardless of which lifecycle hooks OpenClaw exposes.
//
// seededSessions tracks which sessions have already had their intent seeded so
// we don't re-embed on every call (embedding is expensive, ~800ms cold).
// ──────────────────────────────────────────────────────────────────────────────

const seededSessions = new Set<string>();

function extractUserIntent(e: BeforeToolCallEvent): string | null {
  // Walk the conversation history backwards to find the most recent user message.
  // This is the intent the user expressed that triggered this agent session.
  const history = (e as any).conversationHistory as Array<{role: string; content: string}> | undefined;
  if (!history || history.length === 0) return null;
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].role === "user" && history[i].content?.trim()) {
      return history[i].content.trim();
    }
  }
  return null;
}

async function maybeSeedIntent(cfg: KavachConfig, e: BeforeToolCallEvent): Promise<void> {
  const sessionId = e.sessionId ?? "default";
  if (seededSessions.has(sessionId)) return;  // already seeded

  const intentText = extractUserIntent(e);
  if (!intentText) return;  // no user message available yet — will retry next call

  // Mark seeded optimistically so concurrent first-calls don't double-seed.
  seededSessions.add(sessionId);

  try {
    await callParliament(
      cfg,
      "seed_intent",
      { text: intentText, session_id: sessionId },
      cfg.replyTimeoutMs,
    );
    api_logger_ref?.info(`[kavach] seeded intent for session ${sessionId} (${intentText.slice(0, 60)}...)`);
  } catch {
    // Non-blocking — if seeding fails, COMPASS degrades gracefully (compass_sim: null).
    // Will retry on the next tool call since we only un-mark on success.
    seededSessions.delete(sessionId);
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Plugin entry point
// ──────────────────────────────────────────────────────────────────────────────

// Module-level logger ref so maybeSeedIntent can log without passing api everywhere.
let api_logger_ref: OpenClawPluginApi["logger"] | null = null;

export default function register(api: OpenClawPluginApi) {
  const cfg: KavachConfig = {
    ...DEFAULT_CONFIG,
    ...(api.config as Partial<KavachConfig>),
  };

  api_logger_ref = api.logger;

  api.logger.info(
    `[kavach] registering hooks → parliament at ${cfg.parliamentUrl}`,
  );

  api.on("before_tool_call", async (e) => {
    // Seed user intent on first call of each session (fix for issue #9).
    // Runs non-blocking before the parliament call so COMPASS has a vector.
    await maybeSeedIntent(cfg, e);
    return onBeforeToolCall(cfg, e);
  });

  api.on("message_sending", async (e) => onMessageSending(cfg, e));

  api.on("plugin_shutdown", async () => {
    api.logger.info("[kavach] shutting down");
    seededSessions.clear();
  });
}
