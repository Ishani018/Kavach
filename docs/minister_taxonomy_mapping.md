# Kavach Minister Taxonomy Mapping
# MITRE ATT&CK + MITRE ATLAS + OWASP Agentic 2026

This is the authoritative mapping between Kavach's four ministers and the
two field-standard threat taxonomies. Both the corpus-expansion protocol and
the paper (§3 Architecture) must cite pattern sources using these IDs.

Running reviewers in 2026 will expect this mapping. The two taxonomies are
independently grounded — MITRE ATT&CK is harness-layer infrastructure,
OWASP Agentic 2026 is agent-specific. Where they overlap we cite both.

---

## EXECUTOR — Code Execution and Persistence

**What it detects:** Agent actions that execute code, modify the execution
environment, or install persistent hooks that will execute code in the future.

### MITRE ATT&CK Technique IDs

| ID | Name | Relevance |
|---|---|---|
| T1059 | Command and Scripting Interpreter | Shell dispatch, interpreter invocation |
| T1059.001 | PowerShell | Windows agent environments |
| T1059.006 | Python | AI agent scripts, inline eval |
| T1190 | Exploit Public-Facing Application | Agent web surface exploitation |
| T1195 | Supply Chain Compromise | Dependency/package manipulation |
| T1195.001 | Compromise Software Dependencies | Package lockfile manipulation |
| T1195.002 | Compromise Software Supply Chain | Build-system injection |
| T1546 | Event Triggered Execution | Hook, listener, callback install |
| T1546.004 | Unix Shell Configuration | .bashrc, .zshrc function override |
| T1546.013 | PowerShell Profile | PS profile persistence |
| T1547 | Boot or Logon Autostart Execution | Persistence install |
| T1547.001 | Registry Run Keys | Windows persistence |
| T1547.006 | Kernel Modules and Extensions | LD_PRELOAD, insmod |
| T1547.013 | XDG Autostart Entries | Linux desktop persistence |
| T1543 | Create or Modify System Process | Service/daemon install |
| T1543.002 | Systemd Service | systemctl enable persistence |
| T1543.003 | Windows Service | sc create persistence |
| T1053 | Scheduled Task/Job | crontab, schtasks |
| T1053.003 | Cron | /etc/cron.d/ drop-in |
| T1548 | Abuse Elevation Control Mechanism | sudoers, polkit modification |
| T1548.003 | Sudo and Sudo Caching | /etc/sudoers edit |
| T1574 | Hijack Execution Flow | PATH hijack, LD_AUDIT |
| T1574.001 | DLL Search Order Hijacking | Shared library preload |
| T1574.007 | Path Interception by PATH Environment Variable | PATH prepend |
| T1610 | Deploy Container | kubectl run, docker exec |
| T1611 | Escape to Host | Container breakout |
| T1136 | Create Account | New user/service account |
| T1098 | Account Manipulation | SSH authorized_keys |
| T1648 | Serverless Execution | Lambda/Cloud Function deploy |

### MITRE ATLAS Technique IDs (AI-specific)

| ID | Name | Relevance |
|---|---|---|
| AML.T0040 | ML Supply Chain Compromise | Model/package dependency attacks |
| AML.T0048 | Backdoor ML Model | Lifecycle hook that injects backdoor |
| AML.T0050 | Exploit Public-Facing ML App | Agent API exploit |

### OWASP Agentic 2026 Categories

| ID | Category | Relevance |
|---|---|---|
| ASI10 | Unsafe Code Execution | Direct code-execution attacks |
| ASI09 | Supply Chain Compromise | Package, dependency, build-system attacks |
| ASI05 | Agent Orchestration Manipulation | MCP tool registration abuse |

---

## VAULT — Credential and Secret Theft

**What it detects:** Agent actions that read, enumerate, copy, or transmit
credential material, authentication tokens, private keys, or secrets.

### MITRE ATT&CK Technique IDs

| ID | Name | Relevance |
|---|---|---|
| T1552 | Unsecured Credentials | Credential file access |
| T1552.001 | Credentials in Files | .env, .aws/credentials, etc. |
| T1552.003 | Bash History | Shell history scrape |
| T1552.004 | Private Keys | PEM key files, SSH keys |
| T1552.005 | Cloud Instance Metadata | 169.254.169.254 metadata token |
| T1552.007 | Container API | K8s serviceaccount token, docker secret |
| T1078 | Valid Accounts | Account material theft |
| T1078.004 | Cloud Accounts | Cloud IAM credential abuse |
| T1539 | Steal Web Session Cookie | Browser credential store access |
| T1555 | Credentials from Password Stores | Keychain, credential manager |
| T1555.001 | Keychain | macOS keychain dump |
| T1555.003 | Credentials from Web Browsers | browser credential DB |
| T1555.004 | Windows Credential Manager | vaultcmd/cmdkey enumeration |
| T1555.005 | Password Managers | 1Password CLI, bw CLI |
| T1040 | Network Sniffing | tcpdump to capture credentials |
| T1003 | OS Credential Dumping | /proc/*/mem, lsass |
| T1003.008 | /etc/passwd and /etc/shadow | Shadow file read |
| T1018 | Remote System Discovery | SSH known_hosts, config enumeration |
| T1558 | Steal or Forge Kerberos Tickets | Kerberos ticket cache read |

### MITRE ATLAS Technique IDs

| ID | Name | Relevance |
|---|---|---|
| AML.T0024 | Exfiltration via ML Inference API | Credential leakage through model API |
| AML.T0057 | LLM Data Leakage | Secrets in model output |

### OWASP Agentic 2026 Categories

| ID | Category | Relevance |
|---|---|---|
| ASI02 | Excessive Agency | Agent accessing more credentials than needed |
| ASI06 | Memory Poisoning | Credential injection into agent memory |
| ASI07 | Identity Spoofing | Token theft for identity substitution |

---

## CHANNEL — Data Exfiltration

**What it detects:** Agent actions that transmit data, files, or in-memory
content to external network endpoints outside the user's stated task.

### MITRE ATT&CK Technique IDs

| ID | Name | Relevance |
|---|---|---|
| T1041 | Exfiltration Over C2 Channel | Direct outbound data transmission |
| T1567 | Exfiltration Over Web Service | Paste, webhook, S3, gist |
| T1567.001 | Exfiltration to Code Repository | gist, pastebin, hastebin |
| T1567.002 | Exfiltration to Cloud Storage | S3, GCS, Azure blob upload |
| T1071 | Application Layer Protocol | HTTP/HTTPS C2 |
| T1071.001 | Web Protocols | curl, wget, requests |
| T1071.004 | DNS | DNS tunnel exfiltration |
| T1048 | Exfiltration Over Alternative Protocol | DNS/ICMP/SMB tunneling |
| T1048.003 | Exfiltration Over Unencrypted/Obfuscated Non-C3 Protocol | FTP, SMTP |
| T1572 | Protocol Tunneling | SSH -R/-L/-D tunneling |
| T1095 | Non-Application Layer Protocol | ICMP payload |
| T1560 | Archive Collected Data | tar/zip before transmission |
| T1560.001 | Archive via Utility | Compress then upload |
| T1102 | Web Service | Discord/Slack/Telegram webhook |
| T1102.002 | Bidirectional Communication | Chat-platform exfil |
| T1571 | Non-Standard Port | Reverse shell on uncommon port |
| T1018 | Remote System Discovery | Network recon pre-exfil |
| T1046 | Network Service Discovery | Port scanning |

### MITRE ATLAS Technique IDs

| ID | Name | Relevance |
|---|---|---|
| AML.T0024 | Exfiltration via ML Inference API | Covert data exfiltration through model |
| AML.T0025 | Exfiltration via Cyber Means | Data exfiltration from ML environment |
| AML.T0057 | LLM Data Leakage | Data leakage via agent output |

### OWASP Agentic 2026 Categories

| ID | Category | Relevance |
|---|---|---|
| ASI04 | Tool Misuse | Misuse of network tools for exfil |
| ASI08 | Cascading Failures | Cascading exfil across agent calls |

---

## NAVIGATOR — Trajectory Drift and Intent Breaking

**What it detects:** Agent actions that diverge from the user's stated task,
manipulate the agent's goal, expand its scope without authorization, or
otherwise break the intent → action alignment contract.

### MITRE ATT&CK Technique IDs

| ID | Name | Relevance |
|---|---|---|
| T1083 | File and Directory Discovery | Broad filesystem recon beyond task |
| T1057 | Process Discovery | Process enumeration beyond task |
| T1005 | Data from Local System | Broad file collection beyond task |
| T1135 | Network Share Discovery | Network share enumeration |
| T1119 | Automated Collection | Automated scraping of more than asked |
| T1070 | Indicator Removal | Log clearing, trace removal |
| T1070.004 | File Deletion | Removing files created during session |
| T1027 | Obfuscated Files or Information | Unicode homoglyphs, encoding obfuscation |
| T1027.003 | Steganography | Hiding data in media before exfil |
| T1087 | Account Discovery | User enumeration |
| T1082 | System Information Discovery | Host recon |
| T1217 | Browser Information Discovery | Browser history access |
| T1018 | Remote System Discovery | Network recon |
| T1046 | Network Service Discovery | Port scanning |

### MITRE ATLAS Technique IDs

| ID | Name | Relevance |
|---|---|---|
| AML.T0043 | Craft Adversarial Data | Injection content in tool outputs |
| AML.T0051 | LLM Prompt Injection | Prompt injection in tool output |
| AML.T0054 | LLM Jailbreak | Goal manipulation via jailbreak |
| AML.T0058 | LLM Prompt Injection via Tool Output | The dominant attack vector for NAVIGATOR |

### OWASP Agentic 2026 Categories

| ID | Category | Relevance |
|---|---|---|
| ASI01 | Agent Goal Hijack | Core NAVIGATOR threat — goal manipulation |
| ASI05 | Agent Orchestration Manipulation | Subagent dispatch misdirection |

---

## COMPASS Oracle — Alignment and Drift

COMPASS is not a pattern-matching minister; it is an alignment oracle that
measures cosine distance between the user's seeded intent vector and the
proposed agent action. Its threat model maps to:

| MITRE ATLAS | AML.T0051 (LLM Prompt Injection) — drift is evidence of injection |
| OWASP Agentic | ASI01 (Agent Goal Hijack) — COMPASS detects goal divergence |
| SoK Reference | Trustworthiness-Authorization Mismatch (arXiv:2512.06914) |

The asymmetric seeding model (intent embedded once at session start; every
subsequent action compared to that fixed reference) differentiates COMPASS from:
- **DeepContext** (arXiv:2602.16935) — measures user-turn drift, not action-vs-intent
- **TaskTracker** (arXiv:2406.00799) — measures activation deltas, white-box only
- **Trajectory Guard** (arXiv:2601.00516) — Siamese RAE on trajectory pairs, not cosine vs seeded intent

---

## Combined: How the four ministers map to the CVE motivation in §1

| CVE | Minister(s) | Attack class |
|---|---|---|
| CVE-2025-59536 (Claude Code) | EXECUTOR | Hook/lifecycle code execution |
| CVE-2026-21852 (Claude Code) | VAULT, CHANNEL | Credential exfil via URL override |
| CVE-2025-68664 (LangChain Core) | EXECUTOR, VAULT | Serialization → class instantiation + secret extraction |
| CVE-2025-34291 (LangFlow) | EXECUTOR | CSRF → RCE via code-execution endpoint |
| CVE-2025-68665 (LangChain JS) | VAULT | Same class as CVE-2025-68664 |
| CVE-2026-21858 (n8n) | CHANNEL | Workflow config as exfiltration channel |

The OpenClaw bugs #5513 and #5943 are *latent* vulnerabilities rather than CVEs:
they prevent the security hook from firing, meaning any tool-call-time guardrail
on OpenClaw is silently bypassed. These map to MITRE ATLAS AML.T0050
(Exploit Public-Facing ML Application) and to the SoK Trust-Authorization
Mismatch framework (arXiv:2512.06914).
