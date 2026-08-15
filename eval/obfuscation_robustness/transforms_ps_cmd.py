"""eval/obfuscation_robustness/transforms_ps_cmd.py
=====================================================

Second-pass obfuscation-transform study: extends transforms.py's sh/bash
study to PowerShell and cmd.exe, the two dialects paper/section_7_limitations.tex
names explicitly as untested ("PowerShell and cmd remain on a tokenizer"
--- \S\ref{sec:vault-executor} --- and this obfuscation check "first-pass...
PowerShell and cmd remain untested against obfuscation").

Same scope discipline as transforms.py: black-box, does NOT modify
parliament/'s detection code, reuses the REAL VAULT_PATTERNS/EXECUTOR_DENYLIST
regex tables plus struct_parse's extraction to find the literal anchor span
each rule actually keys on, then obfuscates exactly that span (or the whole
command, for the encode transform). Three transforms per dialect, using
each dialect's own well-known real-world evasion techniques rather than
reusing the sh/bash ones verbatim:

PowerShell:
  1. encode    -- `-EncodedCommand <base64 of UTF-16LE command>`, the
                  single most common real-world PowerShell obfuscation
                  technique (native PowerShell.exe flag, not a fabricated
                  transform).
  2. split     -- string-concatenation split of the anchor span:
                  `$a='...'; $b='...'; ... ($a+$b) ...`
  3. indirect  -- reference an already-set variable with NO assignment in
                  this call: `$KAVACH_TARGET`, modeling an attacker who
                  set it in an earlier, unmonitored turn.

cmd.exe:
  1. encode    -- caret-escape every character of the whole command
                  (`c^m^d^ ^/^c^ ...`), a real, well-documented cmd.exe
                  AMSI/logging evasion technique parsed identically by
                  cmd.exe but opaque to substring matching.
  2. split     -- `set` variable concatenation of the anchor span:
                  `set kv_a=...& set kv_b=...& ...%kv_a%%kv_b%...`
  3. indirect  -- reference an unset-here variable: `%KAVACH_TARGET%`.
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from parliament.prefilters import parse_call, VAULT_PATTERNS, EXECUTOR_DENYLIST  # noqa: E402
from parliament import struct_parse  # noqa: E402

CHECKPOINT = REPO_ROOT / "benchmarks" / "results_v2" / "_kavach_pb_attack_checkpoint.json"

PS_DIALECT = "powershell"
CMD_DIALECT = "command_prompt"


def load_checkpoint() -> dict:
    return json.loads(CHECKPOINT.read_text(encoding="utf-8"))


def find_literal_anchor(command: str) -> tuple[str, int, int] | None:
    """Identical logic to transforms.py's find_literal_anchor() -- reused,
    not reimplemented, so both studies key on the same real rule tables."""
    for _name, pattern, _source in VAULT_PATTERNS:
        m = pattern.search(command)
        if m:
            return m.group(0), m.start(), m.end()
    for _name, pattern, _source in EXECUTOR_DENYLIST:
        m = pattern.search(command)
        if m:
            return m.group(0), m.start(), m.end()
    r = struct_parse.extract(command)
    if r.credential_paths:
        p = r.credential_paths[0]
        idx = command.find(p)
        if idx >= 0:
            return p, idx, idx + len(p)
    if r.urls:
        u = r.urls[0]
        idx = command.find(u)
        if idx >= 0:
            return u, idx, idx + len(u)
    return None


# ---------------------------------------------------------------- PowerShell

def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def ps_transform_encode(command: str) -> str:
    b64 = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    return f"-EncodedCommand {b64}"


def ps_transform_split(command: str, anchor: tuple[str, int, int]) -> str:
    matched, start, end = anchor
    mid = max(1, len(matched) // 2)
    half_a, half_b = matched[:mid], matched[mid:]
    prefix = f"$kv_a={_ps_quote(half_a)}; $kv_b={_ps_quote(half_b)}; "
    replacement = "($kv_a+$kv_b)"
    return prefix + command[:start] + replacement + command[end:]


def ps_transform_indirect(command: str, anchor: tuple[str, int, int]) -> str:
    matched, start, end = anchor
    return command[:start] + "$KAVACH_TARGET" + command[end:]


# ------------------------------------------------------------------- cmd.exe

def cmd_transform_encode(command: str) -> str:
    return "".join(f"^{ch}" if ch not in (" ", "^") else ch for ch in command)


def cmd_transform_split(command: str, anchor: tuple[str, int, int]) -> str:
    matched, start, end = anchor
    mid = max(1, len(matched) // 2)
    half_a, half_b = matched[:mid], matched[mid:]
    prefix = f"set kv_a={half_a}& set kv_b={half_b}& "
    replacement = "%kv_a%%kv_b%"
    return prefix + command[:start] + replacement + command[end:]


def cmd_transform_indirect(command: str, anchor: tuple[str, int, int]) -> str:
    matched, start, end = anchor
    return command[:start] + "%KAVACH_TARGET%" + command[end:]


TRANSFORM_FNS = {
    PS_DIALECT: {
        "encode": lambda cmd, anchor: ps_transform_encode(cmd),
        "split": ps_transform_split,
        "indirect": ps_transform_indirect,
    },
    CMD_DIALECT: {
        "encode": lambda cmd, anchor: cmd_transform_encode(cmd),
        "split": cmd_transform_split,
        "indirect": cmd_transform_indirect,
    },
}


def build_transformed_cases() -> dict:
    checkpoint = load_checkpoint()
    baseline = []
    for case_id, case in checkpoint.items():
        call_text = case.get("call_text", "")
        m = re.match(r"^tool:(\S+)\s+args:", call_text)
        tool = m.group(1) if m else None
        if tool not in (PS_DIALECT, CMD_DIALECT):
            continue
        if case.get("verdict") not in ("BLOCK", "ESCALATE"):
            continue
        parsed = parse_call(call_text)
        if parsed is None or "command" not in parsed.args:
            continue
        command = str(parsed.args["command"])
        baseline.append({
            "case_id": case_id,
            "tool": tool,
            "original_verdict": case.get("verdict"),
            "original_decided_by": case.get("decided_by"),
            "original_ministers": case.get("ministers", {}),
            "target_ministers": case.get("target_ministers", []),
            "command": command,
            "call_text": call_text,
        })

    anchors = {b["case_id"]: find_literal_anchor(b["command"]) for b in baseline}

    out = {"encode": [], "split": [], "indirect": [],
           "skipped": {"split": [], "indirect": []},
           "baseline_detected_cases": [b["case_id"] for b in baseline],
           "baseline_by_dialect": {
               PS_DIALECT: sum(1 for b in baseline if b["tool"] == PS_DIALECT),
               CMD_DIALECT: sum(1 for b in baseline if b["tool"] == CMD_DIALECT),
           }}

    for b in baseline:
        case_id = b["case_id"]
        tool = b["tool"]
        parsed = json.loads(re.match(r"^tool:\S+\s+args:(\{.*\})\s*$", b["call_text"], re.DOTALL).group(1))
        fns = TRANSFORM_FNS[tool]

        new_cmd = fns["encode"](b["command"], None)
        new_args = dict(parsed)
        new_args["command"] = new_cmd
        new_call_text = f"tool:{tool} args:{json.dumps(new_args, ensure_ascii=False)}"
        out["encode"].append({**b, "transformed_command": new_cmd, "transformed_call_text": new_call_text})

        anchor = anchors[case_id]
        if anchor is None:
            out["skipped"]["split"].append({"case_id": case_id, "reason": "no literal anchor found"})
            out["skipped"]["indirect"].append({"case_id": case_id, "reason": "no literal anchor found"})
            continue

        new_cmd = fns["split"](b["command"], anchor)
        new_args = dict(parsed)
        new_args["command"] = new_cmd
        new_call_text = f"tool:{tool} args:{json.dumps(new_args, ensure_ascii=False)}"
        out["split"].append({**b, "anchor": anchor[0], "transformed_command": new_cmd, "transformed_call_text": new_call_text})

        new_cmd = fns["indirect"](b["command"], anchor)
        new_args = dict(parsed)
        new_args["command"] = new_cmd
        new_call_text = f"tool:{tool} args:{json.dumps(new_args, ensure_ascii=False)}"
        out["indirect"].append({**b, "anchor": anchor[0], "transformed_command": new_cmd, "transformed_call_text": new_call_text})

    return out


if __name__ == "__main__":
    data = build_transformed_cases()
    out_path = Path(__file__).resolve().parent / "transformed_cases_ps_cmd.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"baseline detected PowerShell/cmd cases: {len(data['baseline_detected_cases'])} "
          f"({data['baseline_by_dialect']})")
    for t in ("encode", "split", "indirect"):
        print(f"  {t}: {len(data[t])} transformed, {len(data['skipped'].get(t, []))} skipped")
    print(f"wrote {out_path}")
