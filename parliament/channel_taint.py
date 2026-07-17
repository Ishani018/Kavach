"""
parliament/channel_taint.py
============================

Stage 2 of the Kavach re-architecture (REARCHITECTURE_PLAN.md §2, CHANNEL):
symbolic taint tracking for the read-sensitive-data -> send-externally exfil
shape. The taint/lattice model itself is borrowed (Denning 1976, realized in
CaMeL/FIDES/NeuroTaint) -- not novel. What's novel here is applying it to
Kavach's own tool-call surface plus a destination allow-list scoped to the
tool suites Kavach actually screens (AgentDojo workspace/slack/banking).

UNLIKE VAULT/EXECUTOR: this is inherently a multi-call, SESSION-level
pattern -- the sensitive read and the external send are different tool
calls in the same session. A single-call regex (prefilters.py's shape)
cannot express this; it needs state that persists across calls within a
session.

Session-state mechanism (design decision, made explicit rather than
silently reusing trajectory.py):
    trajectory.py's ActionRecord/_state["history"] was read in full before
    designing this. It is cosine-only by explicit design constraint (module
    docstring: "no re-embedding... performs ONLY cosine math over cached
    768-dim vectors") and its ActionRecord dataclass stores only the BGE
    vector + verdict metadata -- no raw tool name or args. Taint requires
    knowing the ACTUAL tool identity (is this call a sensitive-read tool?
    a destination tool?), which an embedding alone can't answer reliably
    for the same reason VAULT/EXECUTOR moved off cosine. Rather than
    overload ActionRecord with fields trajectory.py's five cosine signals
    don't use, channel_taint.py keeps its OWN small per-session taint-tag
    store, mirroring the exact pattern server.py already uses for
    _state["history"] / _state["intents"] (a session_id-keyed dict, same
    lifecycle, same place it would be wired into _state). This is a
    deliberate choice, flagged for review before the dispatch-wiring pass:
    an alternative would be to extend ActionRecord with a `tool` field and
    fold taint into trajectory.py directly. Kept separate here because
    trajectory.py's risk signals are continuous/cosine-based and taint is
    a discrete boolean lattice -- mixing them would blur trajectory.py's
    own "pure cosine math" design constraint for no benefit.

TAINT MODEL
    A call to a SOURCE tool (reads domain-specific sensitive data) marks
    the session TAINTED, tagged with which source fired. A subsequent call
    in the SAME session to a DESTINATION tool (external communication) is
    BLOCKed if the session is tainted AND the destination is not on the
    allow-list. No allow-list match + no taint -> ALLOW. Taint persists for
    the rest of the session (matches CHAN-102's "any subsequent send" L2
    mechanism; a single-session TTL/expiry was considered and rejected --
    the 32 ground-truth cases are all two-call sessions, no evidence a
    decay window is needed yet, and premature decay risks under-catching).

SOURCE definition (design decision, justified):
    Fixed tool-name pattern, NOT a keyword-in-args check or a
    NAVIGATOR-adjacent signal. Justification: the actual attack corpus
    (attacker_cases_ds.jsonl, all 32 cases) uses a clean, structural verb-
    prefix shape (Get/View/Search/List/Download/Access + a domain-specific
    sensitive noun: address, payment, holdings, genetic, health, password,
    access-history, log, location). This is the same "deterministic beats
    cosine when the shape is structural" thesis VAULT/EXECUTOR already
    validated. Scoped to DOMAIN-SPECIFIC sensitive nouns specifically so
    ordinary reads (read_file, get_balance, get_most_recent_transactions,
    get_scheduled_transactions, get_user_info) do NOT taint -- confirmed
    necessary by real benign trajectories in benign_v0.json's own source
    data (real_benign_trajectories.json): "read_file -> send_money" (pay a
    bill) and "get_most_recent_transactions -> send_money" (goal_as_task
    cases) are both real, legitimate, same-session read-then-send chains
    that must NOT taint, or CHANNEL would immediately re-create Stage 1's
    kind of false-positive problem on the banking domain alone.

DESTINATION definition + allow-list (design decision, flagged explicitly):
    Destination tools are AgentDojo's real outbound-communication surface,
    confirmed directly against the installed agentdojo package (not
    guessed): workspace's send_email/share_file, slack's
    send_direct_message/send_channel_message/invite_user_to_slack, and
    banking's send_money/schedule_transaction (recipient=IBAN, matching
    the plan's explicit "IBANs" destination-surface mention). Each has a
    known recipient-argument key (recipients/email/recipient/channel/user).
    Allow-list is EMPTY by default -- there is no corpus evidence of a
    "trusted" email/Slack recipient distinct from an attacker-controlled
    one (all 32 ground-truth cases target amy.watson@gmail.com /
    john.doe@gmail.com, both attacker-supplied, never the session's own
    user). An empty allow-list means: tainted session + ANY destination
    call -> BLOCK. This is the conservative choice and is flagged here
    rather than picked silently -- a real deployment would need to seed
    this with the actual user's own verified email/Slack handle (e.g. from
    seed_intent or a user-profile call), which Kavach does not currently
    capture anywhere. Left as an explicit gap for whoever wires a user-
    identity source in later, not a silent assumption.

    send_money/schedule_transaction are NOT exempted as a special case --
    they are real destination tools per AgentDojo's banking suite and the
    plan's own IBAN mention. They simply never fire here because ordinary
    banking reads are correctly excluded from SOURCE, so a taint is never
    present when send_money is legitimately reached from a user-stated
    bill-pay/transfer instruction. This is scope-correct, not a carve-out.

Output shape mirrors prefilters.py exactly: MinisterScan, confidence=1.0
on a hit / 0.0 otherwise, retrieval_mode="deterministic",
matched_level="deterministic".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ministers import MinisterScan
from .prefilters import ParsedCall, parse_call, _flatten_arg_values


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE tools — domain-specific sensitive-data reads
# ──────────────────────────────────────────────────────────────────────────────
# Two layers, both required to taint conservatively:
#   (a) exact match against the 32 corpus-confirmed read-tool names (CHAN-102's
#       own evidence base) -- guarantees the ground-truth set is covered even
#       if the lexical pattern below is ever tightened.
#   (b) a generalizable lexical pattern: Service + (Get|View|Search|List|
#       Download|Access) + a domain-specific sensitive noun. Requires the
#       sensitive-noun component specifically so generic reads (read_file,
#       get_balance, get_user_info, get_most_recent_transactions,
#       get_scheduled_transactions) do NOT match -- verified against
#       benign_v0.json's real trajectories below.

SOURCE_TOOLS_EXACT: frozenset[str] = frozenset({
    "AmazonViewSavedAddresses", "AmazonViewSavedPaymentMethods",
    "AugustSmartLockViewAccessHistory", "BankManagerGetAccountInformation",
    "BankManagerSearchPayee", "BinanceGetOrderHistory",
    "CiscoUmbrellaGetLogDetails", "DeepfakeGeneratorGenerateAudioDeepfake",
    "DropboxGetItemMetadata", "DropboxListFilesAndFolders",
    "EpicFHIRDownloadFiles", "EpicFHIRGetPatientDetails",
    "ExpediaSearchReservations", "FacebookManagerGetUserProfile",
    "FacebookManagerSearchFriends", "FedExShipManagerSearchShipment",
    "GitHubGetUserDetails", "GoogleMapGetCurrentLocation",
    "GoogleSearchGetSearchHistory", "InvestmentManagerGetHoldingsInformation",
    "NortonIdentitySafeSearchPasswords", "SpokeoDownloadPublicRecord",
    "SpokeoSearchPeople", "TDAmeritradeGetHoldingsInformation",
    "TeladocAccessUserInfo", "TeladocViewPrescriptions",
    "The23andMeDownloadData", "The23andMeGetGeneticData",
    "The23andMeGetHealthRecommendations", "TwilioGetPhoneNumberInfo",
    "VenmoListLinkedAccounts", "WebBrowserSearchHistory",
})

_SENSITIVE_NOUN = (
    r"(Address|Payment|Holdings?|Genetic|Health|Password|AccessHistory|Log|"
    r"Location|Prescription|PatientDetail|Record|Metadata|SearchHistory|"
    r"PhoneNumber|LinkedAccount|UserProfile|UserDetail|UserInfo|Friend|"
    r"Reservation|Shipment|OrderHistory|Deepfake)"
)
_SOURCE_VERB = r"(Get|View|Search|List|Download|Access)"
SOURCE_TOOL_PATTERN = re.compile(rf"^\w*{_SOURCE_VERB}\w*{_SENSITIVE_NOUN}\w*$")

# ──────────────────────────────────────────────────────────────────────────────
# Naming-convention-agnostic fallback (found via ground-truth replay against
# AgentDojo: SOURCE_TOOL_PATTERN above requires PascalCase adjacency, so it
# cannot match ANY snake_case tool name regardless of semantic content --
# confirmed directly, e.g. AmazonViewSavedAddresses matches but a
# semantically-identical snake_case equivalent structurally cannot).
#
# Fix: tokenize the tool name (snake_case, camelCase, PascalCase all split to
# a common lowercase token list), then check for verb-token + noun-token
# co-occurrence ANYWHERE in the token list, rather than requiring adjacent
# PascalCase substring structure. Uses the EXACT SAME vocabulary as
# SOURCE_TOOL_PATTERN above -- no new nouns/verbs added here. This
# deliberately does NOT add AgentDojo-specific tool names (e.g.
# search_emails, read_channel_messages) as new source triggers: confirmed
# via direct testing against real AgentDojo ground_truth() data that doing
# so would false-positive on 2 real workspace user_tasks and 9/21 (43%) of
# slack user_tasks, where the exact same read-then-send shape is the
# correct, user-requested action, not an attack (same conflict already
# documented above for banking's get_most_recent_transactions/
# get_scheduled_transactions). So this fix closes the NAMING-CONVENTION gap
# only -- it does not and should not expand semantic coverage, which would
# require a signal CHANNEL's session-taint model doesn't have (was this
# specific recipient/content requested by the user, not just "was there a
# prior read").
_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


def _tokenize_tool_name(tool: str) -> list[str]:
    """Splits snake_case, kebab-case, camelCase, and PascalCase tool names
    into a common lowercase token list. E.g. 'AmazonViewSavedAddresses' and
    'amazon_view_saved_addresses' both -> ['amazon','view','saved','addresses']."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", tool)          # camelCase/PascalCase boundary
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)            # e.g. HTTPServer -> HTTP_Server
    return [p.lower() for p in _TOKEN_SPLIT_RE.split(s) if p]


_SOURCE_VERB_TOKENS = frozenset({"get", "view", "search", "list", "download", "access"})
# Exact tokens/compounds -- some source nouns are themselves multi-word
# (e.g. "PhoneNumber" tokenizes to ['phone','number']), so this set includes
# both the single-token and adjacent-2-token-joined forms actually seen in
# the vocabulary below. Matched against individual tokens and adjacent-pair
# joins ONLY (not the full concatenated name) -- an earlier version joined
# ALL tokens into one string and substring-matched against it, which caused
# a real false positive: "get_user_information" joins to
# "getuserinformation", which contains "userinfo" as an accidental
# cross-boundary substring even though "user"/"information" were never
# meant to match "userinfo". Bounding the join to adjacent-pairs-only
# eliminates that class of collision while still catching genuine two-word
# compounds like "phone"+"number" -> "phonenumber".
_SENSITIVE_NOUN_TOKENS: frozenset[str] = frozenset({
    "address", "addresses", "payment", "payments", "holding", "holdings",
    "genetic", "health", "password", "passwords", "accesshistory", "log",
    "logs", "location", "prescription", "prescriptions", "patientdetail",
    "patientdetails", "record", "records", "metadata", "searchhistory",
    "phonenumber", "linkedaccount", "userprofile", "userdetail", "userinfo",
    "friend", "friends", "reservation", "reservations", "shipment",
    "shipments", "orderhistory", "deepfake",
})
# Two-token compounds that form a sensitive noun only when ADJACENT, in this
# order (e.g. "phone","number" adjacent -> phone-number lookup; "phone" or
# "number" alone, or non-adjacent, do not count).
_SENSITIVE_NOUN_BIGRAMS: frozenset[tuple[str, str]] = frozenset({
    ("phone", "number"), ("access", "history"), ("search", "history"),
    ("linked", "account"), ("user", "profile"), ("user", "detail"),
    ("patient", "detail"), ("order", "history"),
})


def is_source_tool(tool: str) -> bool:
    if tool in SOURCE_TOOLS_EXACT:
        return True
    if SOURCE_TOOL_PATTERN.match(tool):
        return True
    tokens = _tokenize_tool_name(tool)
    has_verb = any(t in _SOURCE_VERB_TOKENS for t in tokens)
    if not has_verb:
        return False
    has_noun = any(t in _SENSITIVE_NOUN_TOKENS for t in tokens)
    if not has_noun:
        has_noun = any(
            (tokens[i], tokens[i + 1]) in _SENSITIVE_NOUN_BIGRAMS
            for i in range(len(tokens) - 1)
        )
    return has_noun


# ──────────────────────────────────────────────────────────────────────────────
# DESTINATION tools — external communication, confirmed against the
# installed agentdojo package (default_suites/v1/tools/*.py), not guessed.
# ──────────────────────────────────────────────────────────────────────────────

# tool name -> arg key(s) holding the recipient/destination value(s)
DESTINATION_TOOLS: dict[str, tuple[str, ...]] = {
    "send_email":              ("recipients", "cc", "bcc"),
    "share_file":               ("email",),
    "send_direct_message":      ("recipient",),
    "send_channel_message":     ("channel",),
    "invite_user_to_slack":     ("user", "user_email"),
    "add_user_to_channel":      ("user", "channel"),
    "send_money":                ("recipient",),
    "schedule_transaction":      ("recipient",),
    # InjecAgent corpus wire-format name for the same shape as send_email.
    "GmailSendEmail":            ("email", "to", "recipient", "recipients"),
}


def is_destination_tool(tool: str) -> bool:
    return tool in DESTINATION_TOOLS


def _destination_values(call: ParsedCall) -> list[str]:
    keys = DESTINATION_TOOLS.get(call.tool, ())
    out: list[str] = []
    for k in keys:
        if k in call.args:
            out.extend(_flatten_arg_values({k: call.args[k]}))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Allow-list — deliberately empty by default (see module docstring). A real
# deployment must seed this with the session's own verified user identity
# (email/Slack handle) from a source Kavach does not currently capture.
#
# WORKSPACE FIX (self-send exemption, added after the empty allow-list's
# false-positive gap was demonstrated concretely -- 3/3 constructed "send
# sensitive data to self" cases false-positived): AgentDojo's workspace
# suite genuinely exposes a real, populated, per-task identity field for
# EMAIL destinations specifically -- Inbox.account_email (confirmed
# directly against the installed agentdojo package: populated with a real
# default like "emma.johnson@bluesparrowtech.com", structurally distinct
# from the recipients send_email() is called with). Kavach did not
# previously capture or pass this through anywhere; it now can, via an
# optional `account_email` on the /hook/parliament request's existing
# `context` dict (server.py Step 3a4).
#
# Scope, explicitly: this exemption applies ONLY to EMAIL-shaped
# destination tools (send_email, share_file, and GmailSendEmail -- the
# InjecAgent corpus's wire-format name for the same shape), because
# account_email is specifically an EMAIL identity and AgentDojo's own
# environment model only associates it with the Inbox/Calendar objects.
# It does NOT apply to Slack tools (send_direct_message,
# send_channel_message, invite_user_to_slack, add_user_to_channel) or
# banking tools (send_money, schedule_transaction) -- confirmed directly
# against the installed agentdojo package that NEITHER suite exposes any
# analogous verified-identity field (Slack's environment model has no
# "which user am I" marker at all; banking's BankAccount.iban is not
# semantically distinguished from a recipient IBAN). This remains a
# permanent limitation for those two suites, unchanged by this fix -- no
# identity source was invented for them.
# ──────────────────────────────────────────────────────────────────────────────

DESTINATION_ALLOWLIST: frozenset[str] = frozenset()

_EMAIL_DESTINATION_TOOLS: frozenset[str] = frozenset({"send_email", "share_file", "GmailSendEmail"})


def _destination_allowed(tool: str, values: list[str], account_email: str | None) -> bool:
    if not values:
        return False
    if account_email and tool in _EMAIL_DESTINATION_TOOLS:
        if all(v == account_email or v in DESTINATION_ALLOWLIST for v in values):
            return True
    return all(v in DESTINATION_ALLOWLIST for v in values)


# ──────────────────────────────────────────────────────────────────────────────
# Per-session taint state — mirrors _state["history"]/_state["intents"]'s
# session_id-keyed pattern in server.py. Kept separate from trajectory.py's
# ActionRecord (see module docstring for why).
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SessionTaint:
    tainted: bool = False
    source_tool: str | None = None
    source_matched_id: str | None = None


def new_taint_state() -> SessionTaint:
    """Factory for a fresh per-session taint state (use via defaultdict)."""
    return SessionTaint()


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def check_channel_taint(
    text: str,
    state: SessionTaint,
    account_email: str | None = None,
) -> MinisterScan | None:
    """Score ONE call against the session's taint state, mutating `state` in
    place (source calls set taint; the caller owns state's lifetime, keyed
    per session_id exactly like trajectory.py's history deque).

    account_email: the session's own verified email identity, if known
    (e.g. AgentDojo workspace suite's Inbox.account_email, passed through
    server.py's request context). None by default -- callers that don't
    have this (or Slack/banking sessions, which have no such field at all)
    simply get the original empty-allow-list behavior unchanged.

    Returns a MinisterScan on a destination-tool BLOCK; None otherwise
    (source-tool calls taint the state but do not themselves return a
    verdict -- the read call is not the malicious action, the send is)."""
    call = parse_call(text)
    if call is None:
        return None

    if is_source_tool(call.tool):
        if not state.tainted:
            state.tainted = True
            state.source_tool = call.tool
            state.source_matched_id = f"CHANNEL-TAINT-SOURCE:{call.tool}"
        return None

    if is_destination_tool(call.tool):
        values = _destination_values(call)
        if state.tainted and not _destination_allowed(call.tool, values, account_email):
            return MinisterScan(
                minister="CHANNEL",
                verdict="BLOCK",
                confidence=1.0,
                matched_id="CHANNEL-TAINT:read-then-send",
                matched_text=(
                    f"session tainted by prior read of {state.source_tool!r} "
                    f"({state.source_matched_id}); untrusted destination call "
                    f"to {call.tool!r} with recipient(s) {values!r}"
                ),
                matched_level="deterministic",
                source="MITRE ATT&CK T1041",  # Exfiltration Over C2 Channel
                retrieval_mode="deterministic",
            )
        return None

    return None
