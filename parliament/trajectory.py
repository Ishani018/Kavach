"""
parliament/trajectory.py
========================

Session-level trajectory monitor for Kavach.

The four ministers score each tool call in isolation. This module adds the
missing layer: it watches the *sequence* of calls in a session and detects
multi-step attacks where each individual call looks benign but the chain is
malicious (read credential -> search for tokens -> POST to external URL).

DESIGN CONSTRAINT — NO RE-EMBEDDING.
    Every action is already embedded once in the parliament endpoint (the
    embed-once refactor). We reuse that vector here. This module performs ONLY
    cosine math over cached 768-dim vectors — no SentenceTransformer / BGE
    calls, no ChromaDB queries. Per-call cost is sub-millisecond, so the hook
    latency budget (p95 ~1.6s, timeout 3000ms) is untouched.

THREE LEGS of the risk signal (each in [0, 1]):
    1. accumulation  — decayed sum of recent per-call confidences (PRISM-parity
                       baseline; recent borderline/block calls raise risk).
    2. escalation    — is the session drifting monotonically AWAY from the
                       seeded user intent? Needs an intent vector; degrades
                       gracefully to 0.0 when intent is unseeded (FINDINGS #9).
    3. chain         — the novel semantic leg: do the recently-flagged actions
                       cohere (cluster + march in a consistent direction) and/or
                       match a known attack-chain prototype? This is what
                       distinguishes Kavach from PRISM's scalar counter.

The combined risk feeds the dynamic-threshold formula in server.py:
    effective_threshold = base + (compass_sim - 0.5) * drift_factor - risk * k

Author: Kavach team (Chain of Trust, PES University 2026)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Optional

import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Tunables (mirror these into config.yaml -> trajectory: when wiring server.py)
# ──────────────────────────────────────────────────────────────────────────────

WINDOW_SIZE: int = 12          # max actions retained per session
DECAY_HALFLIFE: float = 4.0    # accumulation: a call's weight halves every 4 calls
GREY_FLOOR: float = 0.50       # a call is "flagged" (chain-relevant) at conf >= this
CHAIN_COHERENCE_MIN: int = 2   # need >= this many flagged actions for a chain signal

# Combined-risk weights — sum need not be 1; risk is clamped to [0,1] at the end.
W_ACCUMULATION: float = 0.40
W_ESCALATION:   float = 0.30
W_CHAIN:        float = 0.30


# ──────────────────────────────────────────────────────────────────────────────
# Records & result types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ActionRecord:
    ts:         str
    action_vec: np.ndarray      # L2-normalized BGE vector reused from the scan
    verdict:    str             # "BLOCK" | "ESCALATE" | "ALLOW"
    confidence: float           # max minister cosine for this call
    decided_by: str


@dataclass
class TrajectoryResult:
    risk:         float                 # combined session risk in [0, 1]
    accumulation: float                 # leg 1 in [0, 1]
    escalation:   float                 # leg 2 in [0, 1] (0.0 if intent unseeded)
    chain:        float                 # leg 3 in [0, 1]
    window_size:  int                   # number of actions considered
    intent_used:  bool                  # was a seeded intent available?
    reason:       str                   # human-readable summary for the ledger


# ──────────────────────────────────────────────────────────────────────────────
# Per-session history store
#
# In server.py this lives at:  _state["history"]: dict[str, Deque[ActionRecord]]
# Kept here behind tiny helpers so the endpoint never touches deque internals.
# ──────────────────────────────────────────────────────────────────────────────

def new_history() -> Deque[ActionRecord]:
    """Factory for a fresh per-session deque (use via defaultdict in _state)."""
    return deque(maxlen=WINDOW_SIZE)


def record_action(
    history: Deque[ActionRecord],
    action_vec: np.ndarray,
    verdict: str,
    confidence: float,
    decided_by: str,
) -> None:
    """Append one scored action. `action_vec` MUST be the already-computed,
    L2-normalized BGE vector from the parliament scan — never re-embedded here."""
    history.append(
        ActionRecord(
            ts=datetime.now(timezone.utc).isoformat(),
            action_vec=np.asarray(action_vec, dtype=np.float32),
            verdict=verdict,
            confidence=float(confidence),
            decided_by=decided_by,
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Math helpers (vectors are L2-normalized upstream, so dot == cosine)
# ──────────────────────────────────────────────────────────────────────────────

def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


def _decay_weights(n: int) -> np.ndarray:
    """Newest action (index n-1) has weight 1.0; older actions decay by the
    half-life. Returns weights aligned oldest..newest."""
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    ages = np.arange(n - 1, -1, -1, dtype=np.float32)   # oldest has largest age
    return np.power(0.5, ages / DECAY_HALFLIFE).astype(np.float32)


# ──────────────────────────────────────────────────────────────────────────────
# Leg 1 — accumulation (PRISM-parity baseline)
# ──────────────────────────────────────────────────────────────────────────────

def _accumulation(history: Deque[ActionRecord]) -> float:
    """Decayed weighted mean of per-call confidences. A burst of recent
    borderline/block calls drives this up; a single old flag decays away."""
    n = len(history)
    if n == 0:
        return 0.0
    confs = np.array([r.confidence for r in history], dtype=np.float32)
    w = _decay_weights(n)
    denom = float(w.sum())
    if denom <= 0.0:
        return 0.0
    return float(np.clip((confs * w).sum() / denom, 0.0, 1.0))


# ──────────────────────────────────────────────────────────────────────────────
# Leg 2 — escalation / intent drift over the window
# ──────────────────────────────────────────────────────────────────────────────

def _escalation(history: Deque[ActionRecord], intent_vec: Optional[np.ndarray]) -> float:
    """Is the session moving monotonically away from the seeded intent?

    For each action compute alignment = cosine(intent, action). If later
    actions are LESS aligned than earlier ones, the session is escalating away
    from what the user asked for. Returns the normalized negative slope of the
    alignment series, in [0, 1]. Degrades to 0.0 if intent is unseeded
    (FINDINGS #9) or fewer than 2 actions exist.
    """
    if intent_vec is None:
        return 0.0
    n = len(history)
    if n < 2:
        return 0.0
    iv = np.asarray(intent_vec, dtype=np.float32)
    align = np.array([_cos(iv, r.action_vec) for r in history], dtype=np.float32)
    # least-squares slope of alignment vs step index
    x = np.arange(n, dtype=np.float32)
    x -= x.mean()
    var = float((x * x).sum())
    if var <= 0.0:
        return 0.0
    slope = float((x * (align - align.mean())).sum() / var)
    # negative slope = drifting away. Map slope in [-1, 0] -> risk [0, 1].
    return float(np.clip(-slope, 0.0, 1.0))


# ──────────────────────────────────────────────────────────────────────────────
# Leg 3 — semantic chain (the novel leg vs PRISM)
# ──────────────────────────────────────────────────────────────────────────────

def _chain(
    history: Deque[ActionRecord],
    prototypes: Optional[np.ndarray] = None,
) -> float:
    """Coordinated multi-step signal.

    Two sub-signals, combined by max:
      (a) coherence — among recently FLAGGED actions (confidence >= GREY_FLOOR),
          how tightly do they cluster? A real attack chain visits related
          actions (cred files, secret search, egress); incidental greys do not.
          Measured as the mean pairwise cosine of flagged action vectors.
      (b) prototype — if a matrix of pre-embedded attack-chain prototype vectors
          is supplied, the max cosine between the flagged-action centroid and
          any prototype. Optional: 0.0 when no prototypes are provided, so the
          leg works today and strengthens once a chain corpus is built.

    All vectors are reused from the scan — no embedding here.
    """
    flagged = [r.action_vec for r in history if r.confidence >= GREY_FLOOR]
    if len(flagged) < CHAIN_COHERENCE_MIN:
        return 0.0

    M = np.vstack(flagged).astype(np.float32)        # (k, dim), rows normalized

    # (a) coherence: mean of upper-triangle pairwise cosines
    sims = M @ M.T
    k = sims.shape[0]
    iu = np.triu_indices(k, k=1)
    coherence = float(np.clip(sims[iu].mean(), 0.0, 1.0)) if iu[0].size else 0.0

    # (b) prototype match against centroid
    proto = 0.0
    if prototypes is not None and len(prototypes) > 0:
        centroid = M.mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        if norm > 0.0:
            centroid = centroid / norm
            proto = float(np.clip((prototypes @ centroid).max(), 0.0, 1.0))

    return max(coherence, proto)


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def trajectory_risk(
    history: Deque[ActionRecord],
    intent_vec: Optional[np.ndarray] = None,
    prototypes: Optional[np.ndarray] = None,
) -> TrajectoryResult:
    """Compute the combined session trajectory risk. Pure cosine math over
    cached vectors; safe to call on the hot path."""
    acc = _accumulation(history)
    esc = _escalation(history, intent_vec)
    chn = _chain(history, prototypes)

    risk = W_ACCUMULATION * acc + W_ESCALATION * esc + W_CHAIN * chn
    risk = float(np.clip(risk, 0.0, 1.0))

    parts = [f"acc={acc:.2f}", f"esc={esc:.2f}", f"chain={chn:.2f}"]
    if intent_vec is None:
        parts.append("intent=unseeded")
    reason = f"trajectory risk {risk:.2f} ({', '.join(parts)}, window={len(history)})"

    return TrajectoryResult(
        risk=risk,
        accumulation=acc,
        escalation=esc,
        chain=chn,
        window_size=len(history),
        intent_used=intent_vec is not None,
        reason=reason,
    )


def modulate_threshold(
    base: float,
    compass_sim: Optional[float],
    traj_risk: float,
    drift_factor: float = 0.10,
    risk_factor: float = 0.15,
    floor: float = 0.30,
    ceil: float = 0.90,
) -> float:
    """Dynamic block threshold (FINDINGS item #1), now trajectory-aware.

        effective = base + (compass_sim - 0.5)*drift_factor - traj_risk*risk_factor

    High trajectory risk lowers the bar to BLOCK on the NEXT call — so a
    suspicious build-up tightens enforcement before the payload step. Clamped
    to [floor, ceil] so it can never disable or fully open the gate.
    """
    eff = base
    if compass_sim is not None:
        eff += (compass_sim - 0.5) * drift_factor
    eff -= traj_risk * risk_factor
    return float(np.clip(eff, floor, ceil))


# ──────────────────────────────────────────────────────────────────────────────
# Smoke demo (matches the repo's smoke_test.py convention)
#   python -m parliament.trajectory
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng = np.random.default_rng(0)

    def _unit(v: np.ndarray) -> np.ndarray:
        return (v / np.linalg.norm(v)).astype(np.float32)

    # Fake the "read-cred -> search-secret -> exfil" chain: three related,
    # individually-borderline vectors that cohere in embedding space.
    base_dir = _unit(rng.standard_normal(768))
    def near(v, jitter=0.15):
        return _unit(v + jitter * rng.standard_normal(768))

    intent = _unit(rng.standard_normal(768))   # user asked for something unrelated

    h = new_history()
    record_action(h, near(base_dir), "ESCALATE", 0.54, "VAULT")      # read config
    print("after step 1:", trajectory_risk(h, intent).reason)
    record_action(h, near(base_dir), "ESCALATE", 0.57, "VAULT")      # grep secrets
    print("after step 2:", trajectory_risk(h, intent).reason)
    record_action(h, near(base_dir), "ESCALATE", 0.59, "EXECUTOR")   # read .env
    res = trajectory_risk(h, intent)
    print("after step 3:", res.reason)

    base = 0.55
    print(f"\nbase block threshold      = {base:.3f}")
    print(f"effective (traj-modulated) = "
          f"{modulate_threshold(base, compass_sim=0.42, traj_risk=res.risk):.3f}")
    print("→ build-up tightens the gate before the exfil call fires.")
