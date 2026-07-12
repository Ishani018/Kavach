"""
parliament/prefilters.py
=========================

Stage 1 of the Kavach re-architecture (REARCHITECTURE_PLAN.md): additive,
deterministic pre-filters that run on EVERY call alongside the existing
cosine-similarity ministers, without changing router/minister-internals/
speaker/trajectory/provenance/ledger. A rule hit short-circuits to BLOCK;
no hit leaves the existing pipeline entirely unchanged.

Two rule sets, per the locked Stage 1 scope:
    VAULT-style  — credential-path / secret-format regex (gitleaks/
                   truffleHog-style patterns), flags READS of credential
                   material.
    EXECUTOR-style — LOLBIN / dangerous-call deny-list, flags EXECUTION
                   of known-dangerous commands or code constructs.

Confidence convention (locked): a rule hit reports confidence=1.0, no
hit reports confidence=0.0 — keeps the existing threshold/speaker/
trajectory-accumulation math unchanged, since those already expect a
[0,1] cosine-shaped value. retrieval_mode="deterministic" (a new third
value alongside the existing "dense"/"hybrid") so logs are honest about
the mechanism. matched_text/reason wording avoids "at sim X" phrasing
for rule hits (fixed here at the source; speaker.py's reason-string
still says "at sim X" for cosine-based ministers, which remains
accurate for those — only the prefilter's own MinisterScan avoids the
now-inaccurate wording).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .ministers import MinisterScan


# ──────────────────────────────────────────────────────────────────────────────
# Call-text parsing — same wire format ministers.py/server.py already use
# ──────────────────────────────────────────────────────────────────────────────

_CALL_RE = re.compile(r"^tool:(?P<tool>\S+)\s+args:(?P<args>\{.*\})\s*$", re.DOTALL)


@dataclass
class ParsedCall:
    tool: str
    args: dict
    raw_text: str


def parse_call(text: str) -> ParsedCall | None:
    """Parse the 'tool:{name} args:{json}' wire format used throughout
    Kavach (confirmed against benchmarks/kavach_agentdojo_defense.py's
    _format_tool_call and parliament/ministers.py's _tokenize). Returns
    None if the text doesn't match (e.g. free-text queries with no tool
    call) — pre-filters simply don't apply to those, same as the
    ministers' existing behavior on non-tool-call text."""
    m = _CALL_RE.match(text.strip())
    if not m:
        return None
    tool = m.group("tool")
    try:
        args = json.loads(m.group("args"))
    except json.JSONDecodeError:
        args = {}
    return ParsedCall(tool=tool, args=args, raw_text=text)


def _flatten_arg_values(args: dict) -> list[str]:
    """String-render every leaf value in the args dict (recursing into
    nested dicts/lists) so regex rules can scan file paths, commands, or
    secret-shaped strings wherever they appear in the call, not just at
    the top level."""
    out: list[str] = []

    def _walk(v):
        if isinstance(v, dict):
            for vv in v.values():
                _walk(vv)
        elif isinstance(v, (list, tuple)):
            for vv in v:
                _walk(vv)
        elif v is not None:
            out.append(str(v))

    _walk(args)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# VAULT-style: credential-path / secret-format regex
# ──────────────────────────────────────────────────────────────────────────────
# Patterns modeled on gitleaks/truffleHog's maintained secret-format and
# credential-path rule sets (borrowed pattern shapes, not novel — per
# REARCHITECTURE_PLAN.md §2.1). Each entry: (name, compiled regex,
# ATT&CK/CWE source tag for provenance.py).

VAULT_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("dotenv-file",
     re.compile(r"(^|[/\\])\.env(\.[a-zA-Z0-9_]+)?$"),
     "MITRE ATT&CK T1552.001"),
    ("aws-credentials-file",
     re.compile(r"\.aws[/\\]credentials"),
     "MITRE ATT&CK T1552.001"),
    ("ssh-private-key-path",
     re.compile(r"(^|[/\\])(\.ssh[/\\])?id_(rsa|dsa|ecdsa|ed25519)(\.[a-zA-Z0-9]+)?$"),
     "MITRE ATT&CK T1552.004"),
    ("ssh-dir",
     re.compile(r"(^|[/\\])\.ssh[/\\]"),
     "MITRE ATT&CK T1552.004"),
    ("pem-key-file",
     re.compile(r"\.pem$"),
     "MITRE ATT&CK T1552.004"),
    ("aws-access-key-id",
     re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     "MITRE ATT&CK T1552.001"),
    # NOTE: an earlier "aws-secret-key-shape" rule (generic 40-char
    # mixed-case/digit blob, no anchor) was deliberately dropped before
    # commit. Adversarial testing showed it both false-positives on
    # ordinary 40-char tokens (session IDs, hashes, JWT-fragment-shaped
    # strings) whenever they happen to land a regex \b boundary at
    # exactly position 40, AND misses real AWS secret keys that are off
    # by even one character or lack a clean boundary at that offset --
    # a rule that is simultaneously too loose and too brittle, built on
    # a coincidence of length rather than a real signal. gitleaks' own
    # real AWS-secret rule pairs the shape with nearby context (a
    # preceding aws_secret_access_key key name or an adjacent AKIA...
    # access-key-id), not shape alone -- the AKIA rule above already
    # covers the more reliable, structurally-anchored half of a real
    # AWS credential leak. Left as a documented gap, not silently
    # dropped, for whoever revisits VAULT's rule set in Stage 2.
    ("gcp-service-account-json-shape",
     re.compile(r'"type"\s*:\s*"service_account"'),
     "MITRE ATT&CK T1552.001"),
    ("private-key-block",
     re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
     "MITRE ATT&CK T1552.004"),
    ("generic-secret-keyword-path",
     re.compile(r"(^|[/\\])(secrets?|credentials?)\.(json|ya?ml|txt)$", re.IGNORECASE),
     "MITRE ATT&CK T1552.001"),
]


def check_vault(call: ParsedCall) -> MinisterScan | None:
    values = _flatten_arg_values(call.args)
    haystacks = [call.tool] + values
    for text in haystacks:
        for name, pattern, source in VAULT_PATTERNS:
            m = pattern.search(text)
            if m:
                return MinisterScan(
                    minister="VAULT",
                    verdict="BLOCK",
                    confidence=1.0,
                    matched_id=f"VAULT-PREFILTER:{name}",
                    matched_text=f"rule '{name}' matched {m.group(0)!r} in call to {call.tool}",
                    matched_level="deterministic",
                    source=source,
                    retrieval_mode="deterministic",
                )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# EXECUTOR-style: LOLBIN / dangerous-call deny-list
# ──────────────────────────────────────────────────────────────────────────────

EXECUTOR_DENYLIST: list[tuple[str, re.Pattern, str]] = [
    ("curl-pipe-shell",
     re.compile(r"\bcurl\b[^|;\n]{0,200}\|\s*(sh|bash|zsh)\b", re.IGNORECASE),
     "CWE-78"),
    ("wget-pipe-shell",
     re.compile(r"\bwget\b[^|;\n]{0,200}\|\s*(sh|bash|zsh)\b", re.IGNORECASE),
     "CWE-78"),
    ("certutil-download",
     re.compile(r"\bcertutil\b.{0,80}-urlcache", re.IGNORECASE),
     "T1105"),
    ("mshta-remote",
     re.compile(r"\bmshta\b\s+https?://", re.IGNORECASE),
     "T1218.005"),
    ("rundll32-script",
     re.compile(r"\brundll32\b.{0,80}(javascript:|GetObject)", re.IGNORECASE),
     "T1218.011"),
    ("regsvr32-remote",
     re.compile(r"\bregsvr32\b.{0,80}(/i:https?://|scrobj\.dll)", re.IGNORECASE),
     "T1218.010"),
    ("cmstp-inf",
     re.compile(r"\bcmstp\b.{0,40}\.inf\b", re.IGNORECASE),
     "T1218.003"),
    ("powershell-encoded",
     re.compile(r"powershell(\.exe)?\b.{0,40}-(enc|e|EncodedCommand)\b", re.IGNORECASE),
     "T1059.001"),
    ("powershell-download-invoke",
     re.compile(r"(Invoke-Expression|IEX)\b.{0,80}(DownloadString|DownloadFile)", re.IGNORECASE),
     "T1059.001"),
    ("dotnet-webclient-download",
     re.compile(r"Net\.WebClient\b.{0,120}\.(DownloadString|DownloadFile)\s*\(", re.IGNORECASE | re.DOTALL),
     "T1105"),
    ("bitsadmin-transfer",
     re.compile(r"\bbitsadmin\b.{0,40}/transfer", re.IGNORECASE),
     "T1197"),
    ("ruby-inline-shell-exec",
     re.compile(r"\bruby\b.{0,20}-e\b.{0,120}(open3|`.*`|system\s*\()", re.IGNORECASE | re.DOTALL),
     "T1059.004"),
    ("php-inline-system-exec",
     re.compile(r"\bphp\b.{0,20}-r\b.{0,120}\b(system|exec|shell_exec|passthru)\s*\(", re.IGNORECASE | re.DOTALL),
     "T1059.004"),
    ("python-eval-exec",
     re.compile(r"\b(eval|exec)\s*\(", re.IGNORECASE),
     "CWE-95"),
    ("os-system-call",
     re.compile(r"\bos\.system\s*\(", re.IGNORECASE),
     "CWE-78"),
    ("subprocess-shell-true",
     re.compile(r"subprocess\.(run|Popen|call|check_output)\s*\([^)]*shell\s*=\s*True", re.IGNORECASE | re.DOTALL),
     "CWE-78"),
    ("base64-decode-then-exec",
     re.compile(r"(base64\.b64decode|atob)\s*\([^)]*\)[^;\n]{0,60}(exec|eval)\s*\(", re.IGNORECASE),
     "T1027"),
    ("gdb-lldb-inject",
     re.compile(r"\b(gdb\b.{0,40}--pid|lldb\b.{0,40}-p\b)", re.IGNORECASE),
     "T1055"),
    ("nc-reverse-shell",
     re.compile(r"\bnc\b.{0,40}-e\s+/bin/(sh|bash)", re.IGNORECASE),
     "T1059.004"),
]


def check_executor(call: ParsedCall) -> MinisterScan | None:
    values = _flatten_arg_values(call.args)
    haystacks = [call.tool] + values
    for text in haystacks:
        for name, pattern, source in EXECUTOR_DENYLIST:
            m = pattern.search(text)
            if m:
                return MinisterScan(
                    minister="EXECUTOR",
                    verdict="BLOCK",
                    confidence=1.0,
                    matched_id=f"EXECUTOR-PREFILTER:{name}",
                    matched_text=f"rule '{name}' matched {m.group(0)!r} in call to {call.tool}",
                    matched_level="deterministic",
                    source=source,
                    retrieval_mode="deterministic",
                )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Combined entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_prefilters(text: str) -> list[MinisterScan]:
    """Run all Stage 1 pre-filters against the raw call text. Returns a
    list of MinisterScan hits (empty if nothing fired) — additive,
    designed to be unioned with the existing ministers' results before
    combine_verdicts(), never replacing them. Never raises on
    unparseable text (returns [] instead), matching the existing
    ministers' fail-open-on-empty-result behavior."""
    call = parse_call(text)
    if call is None:
        return []
    hits = []
    v = check_vault(call)
    if v:
        hits.append(v)
    e = check_executor(call)
    if e:
        hits.append(e)
    return hits
