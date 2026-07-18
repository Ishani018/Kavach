#!/usr/bin/env python3
"""Gate 1 throwaway census for CHANNEL Stage 2b (argument provenance).

NOT SHIPPED. Measures whether a destination-tool's destination value
(email, IBAN, username, channel, phone number) is USER-SUPPLIED (appears
in the session's original instruction), OUTPUT-DERIVED (first appears in
a prior tool's OUTPUT/result within the same session), or NOVEL (appears
nowhere prior in the visible session). Pure regex/string comparison. No
model, no cosine, no scoring.

DATA SOURCE NOTE (Gate 1 finding, not a design choice): Kavach's own live
pipeline (parliament/channel_taint.py's SessionTaint, trajectory.py's
ActionRecord, server.py's votes ledger) does NOT capture tool call OUTPUTS
anywhere -- confirmed by reading all three. /hook/parliament only ever
receives "tool:X args:Y" (the call being scored), never the result. This
census is therefore built from AgentDojo's own saved trajectory JSON
files (which DO contain full "role": "tool" output messages) and the
InjecAgent/benign corpora already on disk -- an offline measurement, not
something Kavach could compute live today without a new capture point.
That capture-point gap is itself part of the Gate 1 report.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Candidate destination-value patterns (regex only, all listed here) ──────
EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
IBAN_RE = re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}\b")
PHONE_RE = re.compile(r"\b(\+?\d[\d\-\s]{7,14}\d)\b")
# Slack-style channel/username handles seen in AgentDojo's slack suite --
# bare words used as recipient/channel args, not free text. Matched
# separately from regex-extractable identifiers below since they're plain
# alphanumeric tokens with no distinguishing punctuation.
DESTINATION_ARG_KEYS = {
    "send_email":            ("recipients", "cc", "bcc"),
    "share_file":             ("email",),
    "send_direct_message":    ("recipient",),
    "send_channel_message":   ("channel",),
    "invite_user_to_slack":   ("user", "user_email"),
    "add_user_to_channel":    ("user", "channel"),
    "remove_user_from_slack": ("user",),
    "send_money":             ("recipient",),
    "schedule_transaction":   ("recipient",),
    "post_webpage":           ("url",),
    "GmailSendEmail":         ("email", "to", "recipient", "recipients"),
}


def _extract_candidates(text: str) -> set[str]:
    """Every candidate destination-value-shaped string found in free text:
    emails, IBAN-shaped tokens, phone-shaped digit runs. Bare Slack
    usernames/channels are NOT regex-extractable from prose (too ambiguous)
    -- those are read directly from known destination-tool arg keys instead,
    see _destination_values_from_call()."""
    if not isinstance(text, str):
        return set()
    out = set()
    out.update(m.lower() for m in EMAIL_RE.findall(text))
    out.update(IBAN_RE.findall(text))
    out.update(m.strip() for m in PHONE_RE.findall(text) if len(re.sub(r"\D", "", m)) >= 8)
    return out


def _destination_values_from_call(function: str, args: dict) -> list[str]:
    keys = DESTINATION_ARG_KEYS.get(function, ())
    out = []
    for k in keys:
        if k not in args:
            continue
        v = args[k]
        if isinstance(v, list):
            out.extend(str(x) for x in v)
        elif v is not None:
            out.append(str(v))
    return out


def _flatten_text(obj) -> str:
    """Flattens any JSON-ish structure (dict/list/scalar) into one string
    for candidate-extraction, matching prefilters.py's _flatten_arg_values
    spirit but simpler since we're just regex-scanning, not pattern-matching
    per-field."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)) or obj is None:
        return str(obj)
    if isinstance(obj, dict):
        return " ".join(_flatten_text(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten_text(v) for v in obj)
    return str(obj)


def classify_session(messages: list[dict], user_instruction: str) -> list[dict]:
    """Walks a message list (AgentDojo's saved trajectory shape: role
    system/user/assistant/tool, assistant messages carry tool_calls,
    tool messages carry the result in 'content'). For every destination-
    tool call found, classifies its destination value(s) as USER_SUPPLIED,
    OUTPUT_DERIVED, or NOVEL against everything seen so far in the session
    (original instruction + all PRIOR tool outputs, not future ones)."""
    user_candidates = _extract_candidates(user_instruction)
    seen_output_candidates: set[str] = set()
    results = []

    for m in messages:
        role = m.get("role")
        if role == "tool":
            content = m.get("content")
            text = _flatten_text(content)
            seen_output_candidates.update(_extract_candidates(text))
            continue
        if role != "assistant":
            continue
        for tc in (m.get("tool_calls") or []):
            fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
            if fn is None or fn not in DESTINATION_ARG_KEYS:
                continue
            dest_values = _destination_values_from_call(fn, args or {})
            for dv in dest_values:
                dv_norm = dv.strip().lower() if isinstance(dv, str) else str(dv)
                is_user = dv_norm in user_candidates or any(dv_norm in c for c in user_candidates)
                is_output = dv_norm in seen_output_candidates or any(dv_norm in c for c in seen_output_candidates)
                if is_user:
                    classification = "USER_SUPPLIED"
                elif is_output:
                    classification = "OUTPUT_DERIVED"
                else:
                    classification = "NOVEL"
                results.append({
                    "function": fn, "destination_value": dv,
                    "classification": classification,
                })
    return results


if __name__ == "__main__":
    print("_provenance_census.py loaded -- see run scripts for actual census execution.")
