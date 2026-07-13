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

import ast
import json
import logging
import re
from dataclasses import dataclass

from .ministers import MinisterScan

log = logging.getLogger("kavach.prefilters")


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
    ministers' existing behavior on non-tool-call text.

    Malformed args JSON is treated the same way (returns None) rather
    than silently degrading to an empty {} — an empty args dict looks
    identical to a real call with no arguments, so a malformed call would
    otherwise silently pass through every prefilter check as if it had no
    args to scan at all. Logged so a malformed call is visible, not just
    dropped."""
    m = _CALL_RE.match(text.strip())
    if not m:
        return None
    tool = m.group("tool")
    try:
        args = json.loads(m.group("args"))
    except json.JSONDecodeError as e:
        log.warning("parse_call: malformed args JSON for tool %r: %s", tool, e)
        return None
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
     # Boundary-aware, not end-of-string-anchored (was `r"\.pem$"`, found
     # to miss .pem paths embedded in a longer string -- e.g. a narrative
     # sentence like "tar czf ... /workspace/privatekeyfile.pem && curl
     # ..." never matched, since the value doesn't END in .pem, only
     # contains it -- confirmed to affect check_vault()'s real production
     # matching, not just a test artifact). Mirrors ssh-private-key-path's
     # boundary-check style: `.pem` must be followed by end-of-string or a
     # non-word-non-dot character (so a real extension boundary), NOT
     # another dot (rules out `.pem.example`/`.pem.sample`-style false
     # matches on a `.pem`-containing-but-not-`.pem`-extension filename)
     # and NOT a word character (rules out `.pem_backup`).
     re.compile(r"\.pem(?=$|[^\w.])"),
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
    # ---- corpus-driven expansion (Track 2, overnight session) ----
    ("env-secret-harvest",
     # corpus provenance: VAULT-002 (env_secret_harvest)
     re.compile(r"os\.environ\.copy\(\)|dict\(os\.environ\)|/proc/self/environ"),
     "MITRE ATT&CK T1552.001"),
    ("dotenv-read-call",
     # corpus provenance: VAULT-003 (dotenv_file_read)
     re.compile(r"dotenv\.values\(|load_dotenv\("),
     "MITRE ATT&CK T1552.001"),
    ("git-credential-store-path",
     # corpus provenance: VAULT-005 (git_credential_store)
     re.compile(r"\.git-credentials|\.netrc\b"),
     "MITRE ATT&CK T1552.001"),
    ("k8s-serviceaccount-token",
     # corpus provenance: VAULT-006/VAULT-056 (kubernetes_service_account)
     re.compile(r"/var/run/secrets/kubernetes\.io/serviceaccount|/run/secrets/kubernetes\.io/serviceaccount"),
     "MITRE ATT&CK T1552.007"),
    ("docker-registry-config",
     # corpus provenance: VAULT-007/VAULT-066 (docker_registry_config)
     re.compile(r"\.docker[/\\]config\.json"),
     "MITRE ATT&CK T1552.001"),
    ("terraform-state-secrets",
     # corpus provenance: VAULT-008 (terraform_state_secrets)
     re.compile(r"terraform\.tfstate|\.tfstate\b|\.terraform[/\\]backend"),
     "MITRE ATT&CK T1552.001"),
    ("cloud-metadata-imds",
     # corpus provenance: VAULT-009/VAULT-010/VAULT-011/VAULT-055 (cloud_metadata_imds)
     re.compile(r"169\.254\.169\.254|metadata\.google\.internal"),
     "MITRE ATT&CK T1552.005"),
    ("gpg-private-key-material",
     # corpus provenance: VAULT-012/VAULT-077 (gpg_private_key_export)
     re.compile(r"--export-secret-keys|\.gnupg[/\\](private-keys-v1\.d|secring\.gpg)"),
     "MITRE ATT&CK T1552.004"),
    ("password-manager-db",
     # corpus provenance: VAULT-013/VAULT-058 (password_manager_db)
     re.compile(r"\.kdbx\b|\bpass show\b|\bgopass show\b|\bbw get item\b|\bop item get\b|\blpass show\b"),
     "MITRE ATT&CK T1555.005"),
    ("npm-token-rc",
     # corpus provenance: VAULT-014/VAULT-079 (npm_token_from_rc)
     re.compile(r"\.npmrc\b|_authToken\s*="),
     "MITRE ATT&CK T1552.001"),
    ("pypirc-token",
     # corpus provenance: VAULT-015/VAULT-079 (pypi_token_from_pypirc)
     re.compile(r"\.pypirc\b"),
     "MITRE ATT&CK T1552.001"),
    ("browser-localstorage-leveldb",
     # corpus provenance: VAULT-016 (jwt_from_browser_storage)
     re.compile(r"leveldb.{0,40}localStorage|webappsstore\.sqlite|localStorage\.getItem"),
     "MITRE ATT&CK T1539"),
    ("cloud-provider-env-key",
     # corpus provenance: VAULT-018/021/022/023/024/025/045/048/049 (named-service env key read)
     re.compile(r"os\.environ(\.get)?\(['\"](STRIPE_SECRET_KEY|STRIPE_API_KEY|DD_API_KEY|SONAR_TOKEN|HEROKU_API_KEY|TWILIO_AUTH_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|VAULT_TOKEN|CONSUL_HTTP_TOKEN|GITHUB_TOKEN|GH_TOKEN)['\"]\)|os\.getenv\(['\"](STRIPE_SECRET_KEY|STRIPE_API_KEY|DD_API_KEY|SONAR_TOKEN|HEROKU_API_KEY|TWILIO_AUTH_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|VAULT_TOKEN|CONSUL_HTTP_TOKEN|GITHUB_TOKEN|GH_TOKEN)['\"]\)"),
     "MITRE ATT&CK T1552.001"),
    ("database-connection-string",
     # corpus provenance: VAULT-019/VAULT-085 (database_connection_string)
     re.compile(r"\b(postgres|mysql|mongodb(\+srv)?)://[^\s'\"]*:[^\s'\"]*@|DATABASE_URL\b"),
     "MITRE ATT&CK T1552.001"),
    ("gcloud-application-credentials",
     # corpus provenance: VAULT-026/VAULT-065 (gcloud_application_credentials)
     re.compile(r"GOOGLE_APPLICATION_CREDENTIALS|application_default_credentials\.json"),
     "MITRE ATT&CK T1552.001"),
    ("jenkins-secrets-path",
     # corpus provenance: VAULT-027 (jenkins_secret_file)
     re.compile(r"JENKINS_HOME.{0,20}(credentials\.xml|secrets[/\\]master\.key)"),
     "MITRE ATT&CK T1552.001"),
    ("firebase-service-account-json",
     # corpus provenance: VAULT-028 (firebase_service_account)
     re.compile(r"firebase-adminsdk-.*\.json|FIREBASE_CREDENTIALS"),
     "MITRE ATT&CK T1552.001"),
    ("redis-conf-password",
     # corpus provenance: VAULT-029 (redis_password_from_conf)
     re.compile(r"requirepass\b.{0,20}redis\.conf|redis\.conf.{0,20}requirepass"),
     "MITRE ATT&CK T1552.001"),
    ("ansible-vault-password",
     # corpus provenance: VAULT-030 (ansible_vault_password)
     re.compile(r"ANSIBLE_VAULT_PASSWORD_FILE|\.vault_pass\.txt"),
     "MITRE ATT&CK T1552.001"),
    ("maven-settings-credentials",
     # corpus provenance: VAULT-031 (maven_settings_credentials)
     re.compile(r"\.m2[/\\]settings\.xml"),
     "MITRE ATT&CK T1552.001"),
    ("ruby-gem-credentials",
     # corpus provenance: VAULT-032 (ruby_gem_credentials)
     re.compile(r"\.gem[/\\]credentials"),
     "MITRE ATT&CK T1552.001"),
    ("cargo-registry-token",
     # corpus provenance: VAULT-033 (cargo_registry_token)
     re.compile(r"\.cargo[/\\]credentials\.toml|CARGO_REGISTRY_TOKEN"),
     "MITRE ATT&CK T1552.001"),
    ("pulumi-access-token",
     # corpus provenance: VAULT-034 (pulumi_access_token)
     re.compile(r"\.pulumi[/\\]credentials\.json|PULUMI_ACCESS_TOKEN"),
     "MITRE ATT&CK T1552.001"),
    ("pgpass-credentials",
     # corpus provenance: VAULT-036 (pgpass_credentials)
     re.compile(r"\.pgpass\b|PGPASSFILE"),
     "MITRE ATT&CK T1552.001"),
    ("windows-credential-manager-cmd",
     # corpus provenance: VAULT-038/VAULT-082 (windows_credential_manager)
     re.compile(r"\bcmdkey\s+/list\b|\bvaultcmd\s+/listcreds\b|Get-StoredCredential\b"),
     "MITRE ATT&CK T1555.004"),
    ("macos-keychain-dump",
     # corpus provenance: VAULT-039/VAULT-083 (macos_keychain_dump)
     re.compile(r"security\s+dump-keychain|security\s+find-generic-password|security\s+find-internet-password"),
     "MITRE ATT&CK T1555.001"),
    ("okta-token-cache",
     # corpus provenance: VAULT-041 (okta_token_theft)
     re.compile(r"\.okta[/\\]okta\.yaml|\.okta-aws-cli[/\\]cache"),
     "MITRE ATT&CK T1552.001"),
    ("chrome-login-data-sqlite",
     # corpus provenance: VAULT-043/VAULT-051 (chrome_saved_passwords)
     re.compile(r"['\"]Login Data['\"]|logins\.json\b"),
     "MITRE ATT&CK T1555.003"),
    ("terraform-cloud-token",
     # corpus provenance: VAULT-047 (terraform_cloud_token)
     re.compile(r"\.terraform\.d[/\\]credentials\.tfrc\.json|TF_TOKEN_"),
     "MITRE ATT&CK T1552.001"),
    ("artifactory-token",
     # corpus provenance: VAULT-050 (artifactory_token_read)
     re.compile(r"\.jfrog[/\\]jfrog-cli\.conf|JFROG_CLI_ACCESS_TOKEN"),
     "MITRE ATT&CK T1552.001"),
    ("dotenv-outside-workspace",
     # corpus provenance: VAULT-053 (dotenv_in_repo)
     re.compile(r"secrets\.env\b"),
     "MITRE ATT&CK T1552.001"),
    ("gh-glab-cli-creds",
     # corpus provenance: VAULT-054/VAULT-080 (git_credential_files / github_token_disclosure)
     re.compile(r"\.config[/\\]gh[/\\]hosts\.yml|glab-cli[/\\]config\.yml|glab[/\\]config\.yml"),
     "MITRE ATT&CK T1552.001"),
    ("ssh-agent-socket-hijack",
     # corpus provenance: VAULT-057 (ssh_agent_socket)
     re.compile(r"SSH_AUTH_SOCK\b"),
     "MITRE ATT&CK T1563.001"),
    ("shell-history-credential-grep",
     # corpus provenance: VAULT-059 (shell_history_credential_scrape)
     re.compile(r"\.bash_history\b|\.zsh_history\b|\.psql_history\b|\.mysql_history\b"),
     "MITRE ATT&CK T1552.003"),
    ("lsass-memory-dump",
     # corpus provenance: VAULT-060 (process_memory_credential)
     re.compile(r"\blsass\.exe\b|comsvcs\.dll.{0,20}MiniDump|\bprocdump\b", re.IGNORECASE),
     "MITRE ATT&CK T1003.001"),
    ("git-history-secret-scan",
     # corpus provenance: VAULT-062 (secrets_in_git_history)
     re.compile(r"\bgitleaks\b|\btrufflehog\b|\bdetect-secrets\b"),
     "MITRE ATT&CK T1552.001"),
    ("azure-token-cache",
     # corpus provenance: VAULT-064 (azure_credential_cache)
     re.compile(r"\.azure[/\\](msal_token_cache|accessTokens|azureProfile)\.json"),
     "MITRE ATT&CK T1528"),
    ("vscode-jetbrains-secrets-file",
     # corpus provenance: VAULT-067 (vscode_settings_secrets)
     re.compile(r"\.config[/\\]Code[/\\]User[/\\]settings\.json|JetBrains.{0,20}security\.xml"),
     "MITRE ATT&CK T1552.001"),
    ("etc-shadow-sam-ntds",
     # corpus provenance: VAULT-070 (etc_shadow_attempt)
     re.compile(r"/etc/shadow\b|/etc/master\.passwd\b|System32\\\\config\\\\SAM|NTDS\.dit"),
     "MITRE ATT&CK T1003.008"),
    ("kubernetes-secrets-dump-cmd",
     # corpus provenance: VAULT-071 (kubernetes_secrets_dump)
     re.compile(r"kubectl\s+get\s+secrets\b"),
     "MITRE ATT&CK T1552.007"),
    ("secret-manager-bulk-dump-cmd",
     # corpus provenance: VAULT-072 (vault_or_secret_manager_dump)
     re.compile(r"\bvault\s+kv\s+(list|get)\b|secretsmanager\s+(list-secrets|get-secret-value)\b"),
     "MITRE ATT&CK T1552.001"),
    ("dns-exfil-tool-call",
     # corpus provenance: VAULT-073 (credential_exfil_via_dns)
     re.compile(r"\b(dig|nslookup)\b.{0,60}\b(base32|base64)\b", re.IGNORECASE),
     "MITRE ATT&CK T1048.003"),
    ("kerberos-ticket-cache",
     # corpus provenance: VAULT-081 (kerberos_ticket_cache)
     re.compile(r"/tmp/krb5cc_|\bklist\s+-e\b"),
     "MITRE ATT&CK T1558.004"),
    ("openvpn-wireguard-creds",
     # corpus provenance: VAULT-084 (openvpn_credential_files)
     re.compile(r"auth-user-pass\b|anyconnect\.xml\b|PrivateKey\s*=.{0,10}wireguard", re.IGNORECASE),
     "MITRE ATT&CK T1552.001"),
    ("java-keystore-dump",
     # corpus provenance: VAULT-087 (java_keystore)
     re.compile(r"keytool\s+-list\s+-keystore\b"),
     "MITRE ATT&CK T1552.004"),
    ("redis-mongo-unauth-dump",
     # corpus provenance: VAULT-088 (redis_dump_unauthenticated)
     re.compile(r"redis-cli\s+(KEYS\s+\*|SCAN\s+0)\b"),
     "MITRE ATT&CK T1552.001"),
    ("proc-environ-multi-pid",
     # corpus provenance: VAULT-089 (process_environment_via_proc)
     re.compile(r"/proc/\*/environ|/proc/\*/cmdline"),
     "MITRE ATT&CK T1552.003"),
    ("swap-hiberfil-rawmem",
     # corpus provenance: VAULT-090 (memory_swap_credential)
     re.compile(r"hiberfil\.sys\b|/dev/kmem\b|/var/vm/swapfile"),
     "MITRE ATT&CK T1003.001"),
    ("json-token-shape-grep",
     # corpus provenance: VAULT-098 (json_token_pattern_grep). Matches a
     # grep/ripgrep/ag invocation whose OWN regex argument literally
     # contains a credential-shaped search pattern (e.g. someone scanning
     # the filesystem for "AKIA[0-9A-Z]{16}"-style strings), not a text
     # containing an actual credential -- that case is already covered by
     # the existing aws-access-key-id rule above. Fixed a double-escaping
     # artifact in the original draft (`ya29\\\\?\.` matched a literal
     # backslash-question-mark, not the intended "ya29\." grep-pattern
     # substring) before merge.
     re.compile(r"AKIA\[0-9A-Z\]|ghp_\[A-Za-z0-9\]|sk-\[A-Za-z0-9\]|ya29\\\.\["),
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
    # ---- corpus-driven expansion (Track 2, overnight session) ----
    ("pickle-loads-untrusted",
     # corpus provenance: EXEC-006 (deserialization_exec)
     re.compile(r"pickle\.loads\(|marshal\.loads\("),
     "CWE-502"),
    ("yaml-load-unsafe",
     # corpus provenance: EXEC-006/EXEC-067 (deserialization_exec)
     re.compile(r"yaml\.load\((?!.*SafeLoader)"),
     "CWE-502"),
    ("ld-preload-env-assign",
     # corpus provenance: EXEC-008/EXEC-023/EXEC-063 (dynamic_library_load / ld_preload_injection)
     re.compile(r"LD_PRELOAD\s*=|/etc/ld\.so\.preload\b"),
     "MITRE ATT&CK T1574.006"),
    ("pythonpath-hijack",
     # corpus provenance: EXEC-010 (python_import_hijack)
     re.compile(r"sys\.path\.insert\(0,|PYTHONPATH\s*="),
     "MITRE ATT&CK T1574.007"),
    ("xargs-shell-exec",
     # corpus provenance: EXEC-013 (xargs_injection)
     re.compile(r"\bxargs\b.{0,40}(-I\{\}|sh -c)", re.IGNORECASE),
     "CWE-78"),
    ("docker-privileged-run",
     # corpus provenance: EXEC-015 (docker_privileged_escape)
     re.compile(r"docker\s+run\b.{0,80}(--privileged|-v\s+/:/host|--cap-add=SYS_ADMIN)", re.IGNORECASE),
     "MITRE ATT&CK T1611"),
    ("cgroup-release-agent-escape",
     # corpus provenance: EXEC-022 (cgroup_escape)
     re.compile(r"/sys/fs/cgroup/release_agent|notify_on_release"),
     "MITRE ATT&CK T1611"),
    ("kernel-module-load-cmd",
     # corpus provenance: EXEC-024/EXEC-064 (kernel_module_load)
     re.compile(r"\binsmod\b|\bmodprobe\b.{0,60}(/tmp|/var/tmp)|\bkldload\b", re.IGNORECASE),
     "MITRE ATT&CK T1547.006"),
    ("interpreter-repl-sandbox-escape",
     # corpus provenance: EXEC-026 (interpreter_repl_escape)
     re.compile(r"__class__\.__base__\.__subclasses__\(\)|ctypes\.CDLL\(None\)\.system"),
     "CWE-95"),
    ("cron-drop-in-write",
     # corpus provenance: EXEC-028/EXEC-084 (cron_d_drop)
     re.compile(r"/etc/cron\.d/|/etc/cron\.hourly/|/etc/cron\.daily/|/var/spool/cron/"),
     "MITRE ATT&CK T1053.003"),
    ("systemd-unit-install",
     # corpus provenance: EXEC-029/EXEC-085 (systemd_service_install)
     re.compile(r"/etc/systemd/system/.*\.(service|timer|path)\b"),
     "MITRE ATT&CK T1543.002"),
    ("launchd-plist-persistence",
     # corpus provenance: EXEC-030/EXEC-086 (launchd_persistence)
     re.compile(r"LaunchAgents/.*\.plist|LaunchDaemons/.*\.plist"),
     "MITRE ATT&CK T1543.001"),
    ("wmi-event-subscription",
     # corpus provenance: EXEC-031/EXEC-089 (wmi_subscription)
     re.compile(r"New-WMIEventSubscription|__EventFilter|__EventConsumer|__FilterToConsumerBinding"),
     "MITRE ATT&CK T1546.003"),
    ("browser-extension-load-flag",
     # corpus provenance: EXEC-033/EXEC-077 (browser_extension_install)
     re.compile(r"--load-extension="),
     "MITRE ATT&CK T1176"),
    ("jndi-lookup-string",
     # corpus provenance: EXEC-041 (jndi_injection)
     re.compile(r"\$\{jndi:(ldap|rmi|dns)://"),
     "CWE-917"),
    ("fifo-mkfifo-exec",
     # corpus provenance: EXEC-047 (fifo_exec_trigger)
     re.compile(r"\bmkfifo\b\s+\S+.{0,40}(echo|>)"),
     "CWE-78"),
    ("container-runtime-escape-cmd",
     # corpus provenance: EXEC-051 (container_runtime_escape)
     re.compile(r"\bnsenter\b|\bunshare\b.{0,40}--mount"),
     "MITRE ATT&CK T1611"),
    ("git-hook-file-write",
     # corpus provenance: EXEC-054 (git_hook_install)
     re.compile(r"\.git[/\\]hooks[/\\](pre-commit|post-checkout|post-merge)\b"),
     "MITRE ATT&CK T1546.999"),
    ("git-hookspath-config",
     # corpus provenance: EXEC-055 (git_hook_install)
     re.compile(r"core\.hooksPath\b"),
     "MITRE ATT&CK T1546.999"),
    ("ci-workflow-run-block",
     # corpus provenance: EXEC-058 (ci_pipeline_modification)
     re.compile(r"\.github[/\\]workflows[/\\].*\.ya?ml|\.gitlab-ci\.ya?ml\b|\.circleci[/\\]config\.ya?ml"),
     "MITRE ATT&CK T1195.002"),
    ("lockfile-integrity-tamper",
     # corpus provenance: EXEC-060 (supply_chain_dependency_swap)
     re.compile(r"package-lock\.json\b.{0,20}(integrity|resolved)|yarn\.lock\b|Cargo\.lock\b"),
     "MITRE ATT&CK T1195.001"),
    ("dependency-local-path-override",
     # corpus provenance: EXEC-061 (supply_chain_dependency_swap)
     re.compile(r"\[patch\.crates-io\]|path\s*=\s*['\"]\.\.?/"),
     "MITRE ATT&CK T1195.001"),
    ("direnv-envrc-write",
     # corpus provenance: EXEC-062 (auto_loaded_config)
     re.compile(r"\.envrc\b"),
     "MITRE ATT&CK T1546.004"),
    ("ssh-authorized-keys-append",
     # corpus provenance: EXEC-078 (ssh_authorized_keys)
     re.compile(r"\.ssh[/\\]authorized_keys2?\b"),
     "MITRE ATT&CK T1098.004"),
    ("sudoers-write",
     # corpus provenance: EXEC-080 (sudoers_modification)
     re.compile(r"/etc/sudoers(\.d[/\\][^\s]+)?\b|/etc/doas\.conf\b"),
     "MITRE ATT&CK T1548.003"),
    ("polkit-rule-write",
     # corpus provenance: EXEC-081 (polkit_rule_install)
     re.compile(r"/etc/polkit-1/rules\.d/"),
     "MITRE ATT&CK T1548.003"),
    ("path-env-prepend",
     # corpus provenance: EXEC-083 (path_hijack)
     re.compile(r"export\s+PATH=.{0,10}:\$PATH"),
     "MITRE ATT&CK T1574.007"),
    ("windows-run-key-write",
     # corpus provenance: EXEC-087 (windows_registry_run_key). Bug found
     # and fixed during independent-source generalization testing: the
     # original draft used a double-escaped `\\\\Run` (matching two
     # literal backslashes before "Run"), which never occurs in real
     # `reg add`/PowerShell registry-path syntax (single backslash) --
     # so this rule matched NOTHING in either of its own generalization
     # test variants despite looking superficially plausible. Corrected
     # to a single literal backslash; re-validated against both
     # `reg add "HKCU\...\CurrentVersion\Run"` and PowerShell's
     # `-Path 'HKLM:\...\CurrentVersion\RunOnce'` forms.
     re.compile(r"CurrentVersion\\Run(Once)?(Ex)?\b"),
     "MITRE ATT&CK T1547.001"),
    ("windows-service-create",
     # corpus provenance: EXEC-088 (windows_service_install)
     re.compile(r"\bsc\s+create\b|New-Service\b"),
     "MITRE ATT&CK T1543.003"),
    ("powershell-profile-write",
     # corpus provenance: EXEC-090 (powershell_profile_persistence)
     re.compile(r"\$PROFILE\b|Microsoft\.PowerShell_profile\.ps1"),
     "MITRE ATT&CK T1546.013"),
    ("chrome-devtools-protocol-connect",
     # corpus provenance: EXEC-092 (browser_devtools_protocol)
     re.compile(r"localhost:9222\b|Runtime\.evaluate\b"),
     "MITRE ATT&CK T1185"),
    ("docker-socket-abuse",
     # corpus provenance: EXEC-093 (docker_socket_abuse)
     re.compile(r"/var/run/docker\.sock\b|/run/containerd/containerd\.sock\b"),
     "MITRE ATT&CK T1610"),
    ("kubectl-exec-cmd",
     # corpus provenance: EXEC-094 (kubernetes_exec)
     re.compile(r"\bkubectl\s+exec\b|\bkubectl\s+debug\b"),
     "MITRE ATT&CK T1609"),
    ("k8s-privileged-pod-manifest",
     # corpus provenance: EXEC-095 (kubernetes_privileged_pod)
     re.compile(r"privileged:\s*true|hostPID:\s*true|hostNetwork:\s*true"),
     "MITRE ATT&CK T1610"),
    ("sts-assume-role-cmd",
     # corpus provenance: EXEC-097 (cloud_iam_role_assume)
     re.compile(r"sts\s+assume-role(-with-web-identity)?\b"),
     "MITRE ATT&CK T1550.001"),
    ("interpreter-inline-eval-payload",
     # corpus provenance: EXEC-052 (interpreter_arg_injection). Narrowed
     # before merge from a bare `python -c`/`node -e` flag match (which
     # would have fired on completely ordinary developer one-liners like
     # `python -c "print(1)"`) to require BOTH the inline-eval flag AND
     # suspicious payload content (os.system/subprocess/exec/eval/base64/
     # a backtick shell-out/an outbound network call) within the same
     # call, mirroring how a real attacker payload actually looks in
     # practice (confirmed against Type B: still catches 11/12 of the
     # `python -c "os.system(...)"`-shaped obfuscated-exfil cases the
     # original broad draft caught, with the same 0 benign FPs across all
     # 144 benign-set calls + 7 LOLBIN-legit cases). Still broader than
     # most other rules in this file by design (inline code execution is
     # inherently more example-shaped than a fixed credential path), so
     # kept as its own distinctly-named rule for easy review/revert.
     re.compile(
         r"\b(python3?|node|perl|ruby)\b\s+(-c|--eval|-e)\s.{0,300}"
         r"(os\.system|subprocess|exec\s*\(|eval\s*\(|base64|`.*`|requests\.(get|post)|"
         r"urllib|socket\.|\bcurl\b|\bwget\b|Popen)",
         re.IGNORECASE | re.DOTALL,
     ),
     "MITRE ATT&CK T1059.006"),
]


# ──────────────────────────────────────────────────────────────────────────────
# Import-alias resolution (AST) — closes the tractable half of
# REARCHITECTURE_PLAN.md §2.2's "resolved-call-name tracing" novel-work
# item: `import os as o; o.system(...)` and `from os import system as s;
# s(...)` both defeat EXECUTOR_DENYLIST's pure string matching, since
# neither substring `os.system(` nor a bare `system(` (without knowing it
# resolves to os.system) appears literally in the code. The harder
# variable-bound case (`fn = os.system; fn(...)`) needs real local
# dataflow/def-use tracking, not just import resolution -- deliberately
# OUT OF SCOPE for this pass (REARCHITECTURE_PLAN.md's own §2.2 language
# separates "resolved-call-name tracing" from "decode-then-exec dataflow
# tracing" as two distinct novel-work items; only the former is closed
# here). Left as a documented limitation, not attempted.
#
# Only three EXECUTOR_DENYLIST rules are genuinely Python-call-shaped
# (the rest are shell/PowerShell/curl-pipe patterns with no Python AST to
# walk) -- reused here as the ground truth for "dangerous," per instruction
# not to invent a second list:
#   python-eval-exec       -> eval(...) / exec(...)
#   os-system-call         -> os.system(...)
#   subprocess-shell-true  -> subprocess.{run,Popen,call,check_output}(..., shell=True)
_AST_DANGEROUS_CALLS: dict[str, str] = {
    "eval":         "python-eval-exec",
    "exec":         "python-eval-exec",
    "os.system":    "os-system-call",
}
_AST_SUBPROCESS_FUNCS = frozenset({"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_output"})
_AST_DENYLIST_SOURCE: dict[str, str] = {name: source for name, _pattern, source in EXECUTOR_DENYLIST}


def _build_alias_map(tree: ast.AST) -> dict[str, str]:
    """Walk Import/ImportFrom nodes, return {local_name: resolved_dotted_name}.
    `import os as o` -> {"o": "os"}. `from os import system as s` -> {"s": "os.system"}.
    Unaliased imports are included too (`import os` -> {"os": "os"}, `from os
    import system` -> {"system": "os.system"}) so the resolver below has one
    uniform lookup regardless of whether the code happened to alias anything."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = f"{node.module}.{alias.name}"
    return aliases


def _resolve_call_name(func_node: ast.expr, aliases: dict[str, str]) -> str | None:
    """Resolve a Call node's func expression to a dotted name, through the
    alias map. Handles the two shapes _build_alias_map's entries produce:
    a bare Name (`s(...)` where s is an aliased `from` import) or an
    Attribute on a Name (`o.system(...)` where o is an aliased `import`)."""
    if isinstance(func_node, ast.Name):
        return aliases.get(func_node.id, func_node.id)
    if isinstance(func_node, ast.Attribute) and isinstance(func_node.value, ast.Name):
        base = aliases.get(func_node.value.id, func_node.value.id)
        return f"{base}.{func_node.attr}"
    return None


def _check_executor_ast(text: str) -> MinisterScan | None:
    """AST-based call-name resolution over one candidate string. Returns
    None (not a match, not an error) whenever the text isn't valid Python
    or contains no resolvable dangerous call -- must never crash or flag
    plain non-code text, since EXECUTOR scans arbitrary arg strings that
    are usually NOT code at all."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None

    aliases = _build_alias_map(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call_name(node.func, aliases)
        if resolved is None:
            continue

        if resolved in _AST_DANGEROUS_CALLS:
            rule_name = _AST_DANGEROUS_CALLS[resolved]
            return MinisterScan(
                minister="EXECUTOR",
                verdict="BLOCK",
                confidence=1.0,
                matched_id=f"EXECUTOR-PREFILTER-AST:{rule_name}",
                matched_text=f"AST-resolved call {resolved!r} (rule {rule_name!r}) via alias resolution",
                matched_level="deterministic",
                source=_AST_DENYLIST_SOURCE.get(rule_name),
                retrieval_mode="deterministic",
            )

        if resolved in _AST_SUBPROCESS_FUNCS:
            has_shell_true = any(
                kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in node.keywords
            )
            if has_shell_true:
                return MinisterScan(
                    minister="EXECUTOR",
                    verdict="BLOCK",
                    confidence=1.0,
                    matched_id="EXECUTOR-PREFILTER-AST:subprocess-shell-true",
                    matched_text=f"AST-resolved call {resolved!r} with shell=True via alias resolution",
                    matched_level="deterministic",
                    source=_AST_DENYLIST_SOURCE.get("subprocess-shell-true"),
                    retrieval_mode="deterministic",
                )
    return None


def check_executor(call: ParsedCall) -> MinisterScan | None:
    values = _flatten_arg_values(call.args)
    haystacks = [call.tool] + values

    # Cheapest check first: literal regex, exactly as before -- unchanged
    # behavior for every existing case (LOLBIN shell patterns, direct
    # os.system(/eval(/exec( strings, etc).
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

    # AST alias resolution only runs on haystacks the regex pass above
    # didn't already flag -- catches import-aliased/from-import-aliased
    # indirection (import os as o; o.system(...)) that no literal
    # substring match can see.
    for text in haystacks:
        ast_hit = _check_executor_ast(text)
        if ast_hit is not None:
            return ast_hit

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
