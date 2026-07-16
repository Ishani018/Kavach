"""
parliament/navigator_tiers.py
==============================

NAVIGATOR Phase 1 — deterministic sensitivity-tier floor. A zero-LLM,
zero-cosine safety net that forces ESCALATE on high-stakes/irreversible
tool calls, running ADDITIVELY alongside NAVIGATOR's existing cosine
check (never replacing it) so a confident cosine BLOCK still wins.

WHY THIS EXISTS
----------------
The 100-case forced-format live-agent run (branch kavach-rearch, commit
466c9c9, see benchmarks/results_v2/injecagent_live_results_template.md)
found NAVIGATOR silently ALLOWed 39/81 real dispatched attacks (43
individual attacker-tool calls across those 39 cases, since two DS cases
had 2 dispatched attacker calls each). 35/39 (90%) were direct-harm (DH,
single-step) cases -- there is no read-then-send taint chain for CHANNEL
to exploit, and NAVIGATOR's cosine corpus has essentially zero coverage
for these tool names (every one of the 39 misses was decided by the
Speaker directly, with 0 minister escalations -- confirmed via direct
per-case verdict inspection). The misses cluster into three categories,
which is the empirical basis for this module's TIER_3 classification:

  - Financial-authorization-abuse (15/39): BankManagerPayBill,
    BankManagerTransferFunds, BinanceDeposit, BinanceWithdraw,
    BinancePlaceOrder, VenmoWithdrawMoney, BankManagerSearchPayee,
    FedExShipManagerManageShipment.
  - Physical-access-control-abuse (12/39, "Physical Harm" + "Physical
    Data"): AugustSmartLockUnlockDoor, AugustSmartLockGrantGuestAccess,
    TrafficControlManageTrafficLightState, GoogleHomeScheduleDeviceAction,
    IndoorRobotGoToRoom, EmergencyDispatchSystemCreateDispatchRequest,
    EpicFHIRManagePatientRecords/ManageAppointments, The23andMeShareData/
    UpdateData, GoogleMapGetCurrentLocation, ExpediaSearchReservations.
  - Account/credential-control tampering (remaining ~10/39, "Data
    Security Harm"): NortonIdentitySafeDisableTwoFactorAuthentication,
    NortonIdentitySafeSharePassword, NortonIdentitySafeAutoFillPersonalInfo,
    GitHubDeleteRepository, CiscoUmbrellaCreatePolicy/UpdatePolicy,
    EvernoteManagerManageNoteSharingLevel, DropboxMoveItem,
    EpicFHIRManageClinicalDocuments, SlackLeaveChannel,
    WebBrowserSearchHistory.

This directly matches the financial-authorization/physical-access-control
zero-coverage categories already identified in the NAVIGATOR corpus-
expansion candidates work (kavach_eval/reference_corpus_v0/
proposed_minister_v0/overnight_v1/navigator_candidates_v0/README.md) --
this is a known gap recurring at scale, confirmed here rather than a new
finding.

DESIGN
------
Deliberately conservative: over-including a tool into TIER_3 only costs an
extra ESCALATE (human review), which is safe. Under-including defeats the
purpose entirely, so the tool-name list is combined with regex fallbacks
on action-verb families (transfer/withdraw/deposit/pay, unlock/grantaccess/
dispatch/trafficlight, disable-2fa/sharepassword/deleterepo/policy) to
catch tool names not yet seen in the InjecAgent corpus but following the
same naming pattern.

This module does ONE thing: classify a tool name into TIER_3 or TIER_1,
and produce a MinisterScan for the TIER_3 case. It does not replace
NAVIGATOR's cosine check (parliament/ministers.py's run_minister_hybrid /
run_minister_dual_hybrid) -- server.py runs both and lets the Speaker's
existing most-restrictive-wins logic (parliament/speaker.py's
combine_verdicts) pick the stricter of the two, exactly the same additive
pattern already used for VAULT/EXECUTOR/CHANNEL's deterministic checks
alongside llm_tiebreaker.py's escalation tier.

CONFIDENCE VALUE: chosen as 0.55 (between config.yaml's global grey=0.5
and block=0.55, matching the value already used by
llm_tiebreaker.py's ESCALATE verdicts) specifically so that
speaker.py's _reapply_thresholds() -- which re-derives every scan's
verdict from raw confidence when COMPASS intent-drift modulation is
active -- re-derives this scan to ESCALATE consistently rather than only
relying on the verdict set here. See _reapply_thresholds()'s three-way
split: >= effective block threshold -> BLOCK, >= grey -> ESCALATE, else
ALLOW. 0.55 sits above the global grey (0.5) and is not itself intended to
cross any real per-minister block threshold, which are all >= 0.55.
"""
from __future__ import annotations

import re

from .ministers import MinisterScan

# ──────────────────────────────────────────────────────────────────────────
# TIER_3 confidence: see module docstring for why this exact value.
# ──────────────────────────────────────────────────────────────────────────
TIER_FLOOR_CONFIDENCE = 0.55

# ──────────────────────────────────────────────────────────────────────────
# TIER_3 — high-stakes/irreversible. Default ESCALATE unless explicitly
# allow-listed elsewhere (this module does not implement an allow-list;
# that is Phase 2's per-call policy layer, which can upgrade a TIER_3
# ESCALATE to ALLOW/BLOCK based on task-conditioned context).
# ──────────────────────────────────────────────────────────────────────────

TIER_3_TOOLS_FINANCIAL: frozenset[str] = frozenset({
    "BankManagerPayBill",
    "BankManagerTransferFunds",
    "BankManagerSearchPayee",
    "BinanceDeposit",
    "BinanceWithdraw",
    "BinancePlaceOrder",
    "VenmoWithdrawMoney",
    "FedExShipManagerManageShipment",
})

TIER_3_TOOLS_PHYSICAL: frozenset[str] = frozenset({
    "AugustSmartLockUnlockDoor",
    "AugustSmartLockGrantGuestAccess",
    "TrafficControlManageTrafficLightState",
    "GoogleHomeScheduleDeviceAction",
    "IndoorRobotGoToRoom",
    "EmergencyDispatchSystemCreateDispatchRequest",
    "EpicFHIRManagePatientRecords",
    "EpicFHIRManageAppointments",
    "The23andMeShareData",
    "The23andMeUpdateData",
    "The23andMeDownloadData",
    "GoogleMapGetCurrentLocation",
    "ExpediaSearchReservations",
})

TIER_3_TOOLS_ACCOUNT_SECURITY: frozenset[str] = frozenset({
    "NortonIdentitySafeDisableTwoFactorAuthentication",
    "NortonIdentitySafeSharePassword",
    "NortonIdentitySafeAutoFillPersonalInfo",
    "GitHubDeleteRepository",
    "CiscoUmbrellaCreatePolicy",
    "CiscoUmbrellaUpdatePolicy",
    "EvernoteManagerManageNoteSharingLevel",
    "DropboxMoveItem",
    "EpicFHIRManageClinicalDocuments",
    "SlackLeaveChannel",
    "WebBrowserSearchHistory",
    # GmailSendEmail: found during the paired tier-fire eval (4/43 misses
    # still ALLOWed after the initial tier table) -- these 4 are DS cases
    # (ds_u10_a31, ds_u08_a12, ds_u02_a04, ds_u00_a17) whose source-read
    # step (WebBrowserSearchHistory, ExpediaSearchReservations,
    # BankManagerSearchPayee, GoogleMapGetCurrentLocation) isn't a
    # credential/file-read pattern CHANNEL's taint tracker recognizes as a
    # taint source, so the downstream send was never flagged by CHANNEL
    # either. Classified TIER_3 here as defense-in-depth alongside
    # CHANNEL's own (narrower) taint-based detection -- CHANNEL still
    # catches the cases its taint sources DO recognize (e.g. the 4/4
    # BLOCK@1.0 results from the original 50-case run); this tier entry
    # catches sends CHANNEL's specific source-list misses.
    "GmailSendEmail",
})

TIER_3_TOOLS: frozenset[str] = (
    TIER_3_TOOLS_FINANCIAL | TIER_3_TOOLS_PHYSICAL | TIER_3_TOOLS_ACCOUNT_SECURITY
)

# Regex fallbacks for tool names not yet seen in the corpus but matching
# the same high-stakes action-verb families. Conservative by design --
# false positives here just mean an extra ESCALATE, not a missed attack.
_TIER_3_REGEXES: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)(transfer|withdraw|deposit|pay|placeorder)"),
    re.compile(r"(?i)(unlock|grantaccess|dispatch|trafficlight)"),
    re.compile(r"(?i)(disable.*factor|sharepassword|deleterepo|updatepolicy|createpolicy|updatedata|sharedata)"),
)


def classify_tier(tool_name: str) -> str:
    """Returns 'TIER_3' or 'TIER_1' for the given tool name. Conservative:
    an exact match against the known TIER_3 sets fires first; otherwise
    falls back to the regex families so novel tool names following the
    same naming pattern are still caught."""
    if tool_name in TIER_3_TOOLS:
        return "TIER_3"
    for rx in _TIER_3_REGEXES:
        if rx.search(tool_name):
            return "TIER_3"
    return "TIER_1"


def _tier_category(tool_name: str) -> str:
    if tool_name in TIER_3_TOOLS_FINANCIAL:
        return "financial-authorization"
    if tool_name in TIER_3_TOOLS_PHYSICAL:
        return "physical-access-control"
    if tool_name in TIER_3_TOOLS_ACCOUNT_SECURITY:
        return "account-security-control"
    return "regex-fallback-match"


def check_navigator_tier(tool_name: str) -> MinisterScan | None:
    """Returns a MinisterScan(minister='NAVIGATOR', verdict='ESCALATE', ...)
    if tool_name classifies as TIER_3, else None. Caller (server.py) appends
    this alongside NAVIGATOR's existing cosine-similarity MinisterScan --
    does NOT replace it. speaker.py's combine_verdicts() already picks the
    most-restrictive verdict across all scans for a given minister, so a
    confident cosine BLOCK still wins over this ESCALATE, and this
    ESCALATE still wins over a cosine ALLOW/miss."""
    tier = classify_tier(tool_name)
    if tier != "TIER_3":
        return None

    category = _tier_category(tool_name)
    return MinisterScan(
        minister="NAVIGATOR",
        verdict="ESCALATE",
        confidence=TIER_FLOOR_CONFIDENCE,
        matched_id=f"NAVIGATOR-TIER:{tool_name}",
        matched_text=(
            f"high-stakes action ({category}): {tool_name!r} — "
            f"default-escalate pending authorization context"
        ),
        matched_level="deterministic",
        source=None,
        retrieval_mode="deterministic",
    )
