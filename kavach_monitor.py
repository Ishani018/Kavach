#!/usr/bin/env python3
"""
kavach_monitor.py
=================
Kavach Parliament Monitor for OpenClaw sessions.

Watches an OpenClaw session JSONL transcript for new assistant turns,
applies regex pre-filter, then calls the Parliament API for semantic
verdict. Prints regex and Parliament verdicts side-by-side.

This is the PRIMARY integration point with OpenClaw until the
before_tool_call plugin hook is merged (OpenClaw issues #5513/#5943).
Until those PRs land, this monitor runs post-hoc (after the fact)
rather than blocking execution. It still demonstrates the detection
pipeline end-to-end.

Usage:
    # Watch a live session:
    python3 kavach_monitor.py --session-file ~/.openclaw/sessions/latest.jsonl

    # Watch a specific session with custom parliament:
    python3 kavach_monitor.py --session-file session.jsonl --port 8088

    # Replay a recorded session (no tail, just process once):
    python3 kavach_monitor.py --session-file recorded.jsonl --no-tail

Architecture:
    OpenClaw JSONL → kavach_monitor.py → regex gatekeeper → POST /hook/parliament
                                                          → side-by-side output
"""
from __future__ import annotations

import sys, os, re, json, time, argparse, urllib.request
from datetime import datetime

# ─── port (8088 is the parliament server default since server.py config.yaml) ─
DEFAULT_PORT = 8088

# ─── Regex rules (same as kavach_architecture.md Layer 0) ─────────────────────
REGEX_RULES = {
    "RULE-01": (re.compile(r"curl|wget",                              re.I), "External fetch"),
    "RULE-02": (re.compile(r"\|\s*(bash|sh|zsh|python|node|perl|ruby)", re.I), "Pipe to shell"),
    "RULE-03": (re.compile(r"gatewayUrl|ws://|wss://"),                       "WebSocket"),
    "RULE-04": (re.compile(r"--no-sandbox|--disable-setuid-sandbox"),         "Sandbox bypass"),
    "RULE-05": (re.compile(r"[a-z0-9\-]+\.[a-z]{2,}\.(app|dev|io|vercel|ngrok)"), "Suspicious domain"),
    "RULE-06": (re.compile(r"rm\s+-rf|dd\s+if=|mkfs\."),                     "Destructive cmd"),
    "RULE-07": (re.compile(r"~/\.ssh/|id_rsa|id_ed25519"),                   "SSH key access"),
    "RULE-08": (re.compile(r"AWS_SECRET|API_KEY|PRIVATE_KEY|DATABASE_URL"),  "Credential pattern"),
    "RULE-09": (re.compile(r"crontab|systemctl enable|launchctl load"),      "Persistence"),
    "RULE-10": (re.compile(r"/dev/tcp/|nc\s+-e|mkfifo"),                     "Reverse shell"),
}

# ─── Colours ──────────────────────────────────────────────────────────────────
R="\033[0m"; RED="\033[91m"; GRN="\033[92m"
YEL="\033[93m"; CYN="\033[96m"; BLD="\033[1m"; DIM="\033[2m"


def regex_check(text: str) -> tuple[bool, list[str]]:
    """Return (matched, [triggered_rule_names])."""
    hits = []
    for rule_id, (pattern, _) in REGEX_RULES.items():
        if pattern.search(text):
            hits.append(rule_id)
    return bool(hits), hits


def parliament_check(text: str, session_id: str, port: int) -> dict | None:
    """Call POST /hook/parliament. Returns response dict or None on error."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/hook/parliament",
            data=json.dumps({"text": text, "session_id": session_id}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def vcolor(v: str) -> str:
    if v == "BLOCK":    return f"{RED}{BLD}{v}{R}"
    if v == "ESCALATE": return f"{YEL}{BLD}{v}{R}"
    return f"{GRN}{v}{R}"


def print_verdict(text: str, regex_hit: bool, regex_rules: list, parl: dict | None) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    snippet = text[:80].replace("\n", " ")
    print(f"\n{DIM}[{ts}]{R}  {snippet}…" if len(text) > 80 else f"\n{DIM}[{ts}]{R}  {text}")
    print(f"  {'─'*60}")

    # Regex column
    rx_label = f"{RED}HIT {regex_rules}{R}" if regex_hit else f"{GRN}PASS{R}"
    print(f"  Regex      : {rx_label}")

    # Parliament column
    if parl is None:
        print(f"  Parliament : {DIM}(not called — no regex hit){R}")
    elif "error" in parl:
        print(f"  Parliament : {RED}ERROR — {parl['error']}{R}")
    else:
        pv = parl.get("verdict", "?")
        conf = parl.get("speaker", {}).get("confidence", "?")
        print(f"  Parliament : {vcolor(pv)}  conf={conf}")
        ministers = parl.get("ministers", {})
        for name, data in ministers.items():
            if not isinstance(data, dict):
                continue
            mv = data.get("verdict", "?")
            mc = data.get("confidence", 0)
            bar_len = int(mc * 16) if isinstance(mc, float) else 0
            bar = f"{'█'*bar_len}{'░'*(16-bar_len)}"
            col = RED if mv == "BLOCK" else (YEL if mv == "ESCALATE" else GRN)
            print(f"    {CYN}{name:<16}{R} {col}{mv:<10}{R} {col}{bar}{R} {mc:.3f}")


def process_line(line: str, session_id: str, port: int) -> None:
    """Parse one JSONL line from an OpenClaw session transcript."""
    line = line.strip()
    if not line:
        return
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return

    # OpenClaw session JSONL format: {role, content, ...}
    role = entry.get("role", "")
    content = entry.get("content", "")

    # Only inspect assistant turns
    if role not in ("assistant", "tool_use", "tool"):
        return

    # Extract text from various content shapes
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", "") or str(block.get("input", "")))
        text = " ".join(p for p in parts if p)
    elif isinstance(content, dict):
        text = content.get("text", "") or str(content.get("input", ""))
    else:
        return

    if not text or len(text) < 10:
        return

    # Layer 0: regex
    regex_hit, regex_rules = regex_check(text)

    # Layer 1+: parliament (only if regex fired — post-hoc monitor mode)
    parl = None
    if regex_hit:
        parl = parliament_check(text, session_id, port)

    print_verdict(text, regex_hit, regex_rules, parl)


def watch_file(path: str, session_id: str, port: int, tail: bool) -> None:
    """Read session file, optionally tailing for new lines."""
    print(f"{CYN}{BLD}Kavach Monitor{R} · session={session_id} · port={port}")
    print(f"{DIM}Watching: {path}{R}")
    print(f"{DIM}Regex gates active: {len(REGEX_RULES)}{R}")
    print(f"{'─'*62}\n")

    try:
        with open(path, "r") as f:
            # Process existing lines
            for line in f:
                process_line(line, session_id, port)

            if not tail:
                return

            # Tail for new lines
            print(f"\n{DIM}Tailing for new turns… (Ctrl+C to stop){R}")
            while True:
                line = f.readline()
                if line:
                    process_line(line, session_id, port)
                else:
                    time.sleep(0.5)
    except FileNotFoundError:
        print(f"{RED}File not found: {path}{R}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{DIM}Monitor stopped.{R}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.strip())
    p.add_argument("--session-file", "-f", required=True, help="Path to OpenClaw session JSONL")
    p.add_argument("--session-id",   "-s", default="monitor-session", help="Session ID for Parliament calls")
    p.add_argument("--port",         "-p", type=int, default=DEFAULT_PORT, help=f"Parliament port (default {DEFAULT_PORT})")
    p.add_argument("--no-tail",      action="store_true", help="Process file once, don't tail")
    args = p.parse_args()

    # Auto-generate session ID from filename if not provided
    sid = args.session_id
    if sid == "monitor-session":
        base = os.path.basename(args.session_file).replace(".jsonl", "")
        sid = f"monitor-{base}"

    watch_file(args.session_file, sid, args.port, not args.no_tail)


if __name__ == "__main__":
    main()
