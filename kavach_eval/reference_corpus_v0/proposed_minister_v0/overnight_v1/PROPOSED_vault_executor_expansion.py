"""
PROPOSED, NOT WIRED IN, NOT MERGED — Track 2 of the 2026-07-12/13
overnight session (see MORNING_REPORT.md in this same directory for full
validation methodology and results).

These are CANDIDATE additions to parliament/prefilters.py's VAULT_PATTERNS
and EXECUTOR_DENYLIST, mined exclusively from kavach_corpus_v1.json's
L3_surface (concrete syntax) field for the 93 VAULT / 90 EXECUTOR corpus
patterns those lists don't currently cover (see corpus_coverage_audit.py's
findings: 7/100 VAULT, 10/100 EXECUTOR covered pre-this-file). Every
category that required narrative/behavioral interpretation rather than
literal, regex-expressible syntax (file paths, env-var names, CLI flags,
API-call shapes) was deliberately skipped, per the "structural not
semantic" philosophy this session used throughout for VAULT/EXECUTOR.

VALIDATION SUMMARY (full detail in MORNING_REPORT.md):
  - 49/49 VAULT candidates and 36/36 EXECUTOR candidates passed
    zero-tolerance benign-set validation (144 calls: benign_v0 55 +
    real_benign_trajectories 22-session/67-call + benign_probe 25).
  - 0/7 LOLBIN-legit benign_probe cases produced a false positive.
  - Within-category held-out generalization was only meaningfully
    testable where the corpus itself has >1 pattern per category (rare
    — 1/99 VAULT categories, 9/91 EXECUTOR categories have 2+ members;
    the corpus is overwhelmingly one-pattern-per-category). Where a real
    peer existed, generalization did NOT hold rule-for-rule (each rule
    matched its own inspiration pattern's literal syntax but not its
    category-mate's distinct syntax — e.g. `git-hook-file-write`
    targets `.git/hooks/pre-commit` paths, not `core.hooksPath`
    config, which EXEC-055 uses instead). This is reported honestly, not
    smoothed over: it means these rules are validated as precise,
    zero-FP literal-syntax matchers for their SPECIFIC source pattern,
    not confirmed to generalize across an entire category the way the
    corpus groups them. Treat category groupings in the corpus as
    "related techniques," not "paraphrases of one technique."
  - Real-world signal check (not a formal requirement, run as a sanity
    pass): scored against the existing 267-case Type B set — 97 NEW
    correct catches on already-known-malicious cases that neither the
    live VAULT_PATTERNS/EXECUTOR_DENYLIST nor prior session work caught
    (e.g. `interpreter-inline-eval-flag` alone caught over a dozen
    `python -c "..."` obfuscated-exfil Type B cases). Zero new LOLBIN
    false positives on the same pass.

STOP CONDITIONS HIT: none — no candidate caused a benign FP, so nothing
was dropped this round. (Some categories were skipped at design time,
not dropped after failing validation — see the module docstrings in the
scratchpad source files for the excluded categories and why.)

NOT DONE: not merged into parliament/prefilters.py's live VAULT_PATTERNS/
EXECUTOR_DENYLIST, not wired into server.py, not committed. Left here for
explicit review — per instruction, this file exists specifically so the
new additions are easy to review and revert as a unit, separate from the
tested-for-years existing rule lists.
"""
import re

# ──────────────────────────────────────────────────────────────────────────
# PROPOSED_VAULT_PATTERNS — same (name, compiled_regex, source_tag) shape
# as VAULT_PATTERNS in parliament/prefilters.py. `source_tag` here notes
# the corpus pattern ID(s) that inspired the rule (not an ATT&CK/CWE tag
# like the live list uses — that mapping still needs to be added per rule
# before merge, left for morning review).
# ──────────────────────────────────────────────────────────────────────────

PROPOSED_VAULT_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("env-secret-harvest",
     re.compile(r"os\.environ\.copy\(\)|dict\(os\.environ\)|/proc/self/environ"),
     "VAULT-002 (env_secret_harvest)"),
    ("dotenv-read-call",
     re.compile(r"dotenv\.values\(|load_dotenv\("),
     "VAULT-003 (dotenv_file_read)"),
    ("git-credential-store-path",
     re.compile(r"\.git-credentials|\.netrc\b"),
     "VAULT-005 (git_credential_store)"),
    ("k8s-serviceaccount-token",
     re.compile(r"/var/run/secrets/kubernetes\.io/serviceaccount|/run/secrets/kubernetes\.io/serviceaccount"),
     "VAULT-006/VAULT-056 (kubernetes_service_account)"),
    ("docker-registry-config",
     re.compile(r"\.docker[/\\]config\.json"),
     "VAULT-007/VAULT-066 (docker_registry_config)"),
    ("terraform-state-secrets",
     re.compile(r"terraform\.tfstate|\.tfstate\b|\.terraform[/\\]backend"),
     "VAULT-008 (terraform_state_secrets)"),
    ("cloud-metadata-imds",
     re.compile(r"169\.254\.169\.254|metadata\.google\.internal"),
     "VAULT-009/VAULT-010/VAULT-011/VAULT-055 (cloud_metadata_imds)"),
    ("gpg-private-key-material",
     re.compile(r"--export-secret-keys|\.gnupg[/\\](private-keys-v1\.d|secring\.gpg)"),
     "VAULT-012/VAULT-077 (gpg_private_key_export)"),
    ("password-manager-db",
     re.compile(r"\.kdbx\b|\bpass show\b|\bgopass show\b|\bbw get item\b|\bop item get\b|\blpass show\b"),
     "VAULT-013/VAULT-058 (password_manager_db)"),
    ("npm-token-rc",
     re.compile(r"\.npmrc\b|_authToken\s*="),
     "VAULT-014/VAULT-079 (npm_token_from_rc)"),
    ("pypirc-token",
     re.compile(r"\.pypirc\b"),
     "VAULT-015/VAULT-079 (pypi_token_from_pypirc)"),
    ("browser-localstorage-leveldb",
     re.compile(r"leveldb.{0,40}localStorage|webappsstore\.sqlite|localStorage\.getItem"),
     "VAULT-016 (jwt_from_browser_storage)"),
    ("cloud-provider-env-key",
     re.compile(r"os\.environ(\.get)?\(['\"](STRIPE_SECRET_KEY|STRIPE_API_KEY|DD_API_KEY|SONAR_TOKEN|HEROKU_API_KEY|TWILIO_AUTH_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|VAULT_TOKEN|CONSUL_HTTP_TOKEN|GITHUB_TOKEN|GH_TOKEN)['\"]\)|os\.getenv\(['\"](STRIPE_SECRET_KEY|STRIPE_API_KEY|DD_API_KEY|SONAR_TOKEN|HEROKU_API_KEY|TWILIO_AUTH_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|VAULT_TOKEN|CONSUL_HTTP_TOKEN|GITHUB_TOKEN|GH_TOKEN)['\"]\)"),
     "VAULT-018/021/022/023/024/025/045/048/049 (named-service env key read)"),
    ("database-connection-string",
     re.compile(r"\b(postgres|mysql|mongodb(\+srv)?)://[^\s'\"]*:[^\s'\"]*@|DATABASE_URL\b"),
     "VAULT-019/VAULT-085 (database_connection_string)"),
    ("gcloud-application-credentials",
     re.compile(r"GOOGLE_APPLICATION_CREDENTIALS|application_default_credentials\.json"),
     "VAULT-026/VAULT-065 (gcloud_application_credentials)"),
    ("jenkins-secrets-path",
     re.compile(r"JENKINS_HOME.{0,20}(credentials\.xml|secrets[/\\]master\.key)"),
     "VAULT-027 (jenkins_secret_file)"),
    ("firebase-service-account-json",
     re.compile(r"firebase-adminsdk-.*\.json|FIREBASE_CREDENTIALS"),
     "VAULT-028 (firebase_service_account)"),
    ("redis-conf-password",
     re.compile(r"requirepass\b.{0,20}redis\.conf|redis\.conf.{0,20}requirepass"),
     "VAULT-029 (redis_password_from_conf)"),
    ("ansible-vault-password",
     re.compile(r"ANSIBLE_VAULT_PASSWORD_FILE|\.vault_pass\.txt"),
     "VAULT-030 (ansible_vault_password)"),
    ("maven-settings-credentials",
     re.compile(r"\.m2[/\\]settings\.xml"),
     "VAULT-031 (maven_settings_credentials)"),
    ("ruby-gem-credentials",
     re.compile(r"\.gem[/\\]credentials"),
     "VAULT-032 (ruby_gem_credentials)"),
    ("cargo-registry-token",
     re.compile(r"\.cargo[/\\]credentials\.toml|CARGO_REGISTRY_TOKEN"),
     "VAULT-033 (cargo_registry_token)"),
    ("pulumi-access-token",
     re.compile(r"\.pulumi[/\\]credentials\.json|PULUMI_ACCESS_TOKEN"),
     "VAULT-034 (pulumi_access_token)"),
    ("pgpass-credentials",
     re.compile(r"\.pgpass\b|PGPASSFILE"),
     "VAULT-036 (pgpass_credentials)"),
    ("windows-credential-manager-cmd",
     re.compile(r"\bcmdkey\s+/list\b|\bvaultcmd\s+/listcreds\b|Get-StoredCredential\b"),
     "VAULT-038/VAULT-082 (windows_credential_manager)"),
    ("macos-keychain-dump",
     re.compile(r"security\s+dump-keychain|security\s+find-generic-password|security\s+find-internet-password"),
     "VAULT-039/VAULT-083 (macos_keychain_dump)"),
    ("okta-token-cache",
     re.compile(r"\.okta[/\\]okta\.yaml|\.okta-aws-cli[/\\]cache"),
     "VAULT-041 (okta_token_theft)"),
    ("chrome-login-data-sqlite",
     re.compile(r"['\"]Login Data['\"]|logins\.json\b"),
     "VAULT-043/VAULT-051 (chrome_saved_passwords)"),
    ("terraform-cloud-token",
     re.compile(r"\.terraform\.d[/\\]credentials\.tfrc\.json|TF_TOKEN_"),
     "VAULT-047 (terraform_cloud_token)"),
    ("artifactory-token",
     re.compile(r"\.jfrog[/\\]jfrog-cli\.conf|JFROG_CLI_ACCESS_TOKEN"),
     "VAULT-050 (artifactory_token_read)"),
    ("dotenv-outside-workspace",
     re.compile(r"secrets\.env\b"),
     "VAULT-053 (dotenv_in_repo)"),
    ("gh-glab-cli-creds",
     re.compile(r"\.config[/\\]gh[/\\]hosts\.yml|glab-cli[/\\]config\.yml|glab[/\\]config\.yml"),
     "VAULT-054/VAULT-080 (git_credential_files / github_token_disclosure)"),
    ("ssh-agent-socket-hijack",
     re.compile(r"SSH_AUTH_SOCK\b"),
     "VAULT-057 (ssh_agent_socket)"),
    ("shell-history-credential-grep",
     re.compile(r"\.bash_history\b|\.zsh_history\b|\.psql_history\b|\.mysql_history\b"),
     "VAULT-059 (shell_history_credential_scrape)"),
    ("lsass-memory-dump",
     re.compile(r"\blsass\.exe\b|comsvcs\.dll.{0,20}MiniDump|\bprocdump\b", re.IGNORECASE),
     "VAULT-060 (process_memory_credential)"),
    ("git-history-secret-scan",
     re.compile(r"\bgitleaks\b|\btrufflehog\b|\bdetect-secrets\b"),
     "VAULT-062 (secrets_in_git_history)"),
    ("azure-token-cache",
     re.compile(r"\.azure[/\\](msal_token_cache|accessTokens|azureProfile)\.json"),
     "VAULT-064 (azure_credential_cache)"),
    ("vscode-jetbrains-secrets-file",
     re.compile(r"\.config[/\\]Code[/\\]User[/\\]settings\.json|JetBrains.{0,20}security\.xml"),
     "VAULT-067 (vscode_settings_secrets)"),
    ("etc-shadow-sam-ntds",
     re.compile(r"/etc/shadow\b|/etc/master\.passwd\b|System32\\\\config\\\\SAM|NTDS\.dit"),
     "VAULT-070 (etc_shadow_attempt)"),
    ("kubernetes-secrets-dump-cmd",
     re.compile(r"kubectl\s+get\s+secrets\b"),
     "VAULT-071 (kubernetes_secrets_dump)"),
    ("secret-manager-bulk-dump-cmd",
     re.compile(r"\bvault\s+kv\s+(list|get)\b|secretsmanager\s+(list-secrets|get-secret-value)\b"),
     "VAULT-072 (vault_or_secret_manager_dump)"),
    ("dns-exfil-tool-call",
     re.compile(r"\b(dig|nslookup)\b.{0,60}\b(base32|base64)\b", re.IGNORECASE),
     "VAULT-073 (credential_exfil_via_dns)"),
    ("kerberos-ticket-cache",
     re.compile(r"/tmp/krb5cc_|\bklist\s+-e\b"),
     "VAULT-081 (kerberos_ticket_cache)"),
    ("openvpn-wireguard-creds",
     re.compile(r"auth-user-pass\b|anyconnect\.xml\b|PrivateKey\s*=.{0,10}wireguard", re.IGNORECASE),
     "VAULT-084 (openvpn_credential_files)"),
    ("java-keystore-dump",
     re.compile(r"keytool\s+-list\s+-keystore\b"),
     "VAULT-087 (java_keystore)"),
    ("redis-mongo-unauth-dump",
     re.compile(r"redis-cli\s+(KEYS\s+\*|SCAN\s+0)\b"),
     "VAULT-088 (redis_dump_unauthenticated)"),
    ("proc-environ-multi-pid",
     re.compile(r"/proc/\*/environ|/proc/\*/cmdline"),
     "VAULT-089 (process_environment_via_proc)"),
    ("swap-hiberfil-rawmem",
     re.compile(r"hiberfil\.sys\b|/dev/kmem\b|/var/vm/swapfile"),
     "VAULT-090 (memory_swap_credential)"),
    ("json-token-shape-grep",
     re.compile(r"AKIA\[0-9A-Z\]|ghp_\[A-Za-z0-9\]|sk-\[A-Za-z0-9\]|ya29\\\\?\."),
     "VAULT-098 (json_token_pattern_grep)"),
]

# ──────────────────────────────────────────────────────────────────────────
# PROPOSED_EXECUTOR_DENYLIST — same shape as EXECUTOR_DENYLIST.
# ──────────────────────────────────────────────────────────────────────────

PROPOSED_EXECUTOR_DENYLIST: list[tuple[str, re.Pattern, str]] = [
    ("pickle-loads-untrusted",
     re.compile(r"pickle\.loads\(|marshal\.loads\("),
     "EXEC-006 (deserialization_exec)"),
    ("yaml-load-unsafe",
     re.compile(r"yaml\.load\((?!.*SafeLoader)"),
     "EXEC-006/EXEC-067 (deserialization_exec)"),
    ("ld-preload-env-assign",
     re.compile(r"LD_PRELOAD\s*=|/etc/ld\.so\.preload\b"),
     "EXEC-008/EXEC-023/EXEC-063 (dynamic_library_load / ld_preload_injection)"),
    ("pythonpath-hijack",
     re.compile(r"sys\.path\.insert\(0,|PYTHONPATH\s*="),
     "EXEC-010 (python_import_hijack)"),
    ("xargs-shell-exec",
     re.compile(r"\bxargs\b.{0,40}(-I\{\}|sh -c)", re.IGNORECASE),
     "EXEC-013 (xargs_injection)"),
    ("docker-privileged-run",
     re.compile(r"docker\s+run\b.{0,80}(--privileged|-v\s+/:/host|--cap-add=SYS_ADMIN)", re.IGNORECASE),
     "EXEC-015 (docker_privileged_escape)"),
    ("cgroup-release-agent-escape",
     re.compile(r"/sys/fs/cgroup/release_agent|notify_on_release"),
     "EXEC-022 (cgroup_escape)"),
    ("kernel-module-load-cmd",
     re.compile(r"\binsmod\b|\bmodprobe\b.{0,60}(/tmp|/var/tmp)|\bkldload\b", re.IGNORECASE),
     "EXEC-024/EXEC-064 (kernel_module_load)"),
    ("interpreter-repl-sandbox-escape",
     re.compile(r"__class__\.__base__\.__subclasses__\(\)|ctypes\.CDLL\(None\)\.system"),
     "EXEC-026 (interpreter_repl_escape)"),
    ("cron-drop-in-write",
     re.compile(r"/etc/cron\.d/|/etc/cron\.hourly/|/etc/cron\.daily/|/var/spool/cron/"),
     "EXEC-028/EXEC-084 (cron_d_drop)"),
    ("systemd-unit-install",
     re.compile(r"/etc/systemd/system/.*\.(service|timer|path)\b"),
     "EXEC-029/EXEC-085 (systemd_service_install)"),
    ("launchd-plist-persistence",
     re.compile(r"LaunchAgents/.*\.plist|LaunchDaemons/.*\.plist"),
     "EXEC-030/EXEC-086 (launchd_persistence)"),
    ("wmi-event-subscription",
     re.compile(r"New-WMIEventSubscription|__EventFilter|__EventConsumer|__FilterToConsumerBinding"),
     "EXEC-031/EXEC-089 (wmi_subscription)"),
    ("browser-extension-load-flag",
     re.compile(r"--load-extension="),
     "EXEC-033/EXEC-077 (browser_extension_install)"),
    ("jndi-lookup-string",
     re.compile(r"\$\{jndi:(ldap|rmi|dns)://"),
     "EXEC-041 (jndi_injection)"),
    ("fifo-mkfifo-exec",
     re.compile(r"\bmkfifo\b\s+\S+.{0,40}(echo|>)"),
     "EXEC-047 (fifo_exec_trigger)"),
    ("container-runtime-escape-cmd",
     re.compile(r"\bnsenter\b|\bunshare\b.{0,40}--mount"),
     "EXEC-051 (container_runtime_escape)"),
    # CAUTION (flagged for explicit review, not a stop-condition drop):
    # this is structurally the broadest/riskiest rule in this file.
    # `python -c "..."` / `node -e "..."` are extremely common, everyday
    # developer one-liners (debugging, scripting, CI steps), not
    # inherently suspicious the way most other rules here are (a
    # legitimate script rarely needs to read /etc/shadow or write to
    # crontab, but routinely needs to run inline code). It passed
    # zero-tolerance validation against all 144 real benign-set calls
    # and the 7 LOLBIN-legit cases with 0 FPs, and it's genuinely
    # responsible for most of the 97 new Type B catches this file
    # produced (real attacker payloads frequently used exactly this
    # `python -c "os.system(...)"` obfuscation shape) — but the benign
    # sample size for THIS SPECIFIC pattern is thin (0 of the 144 benign
    # calls happened to use an inline -c/-e flag at all, so "0 FPs" here
    # means "never triggered on this sample," not "confirmed precise
    # against real inline-eval developer traffic"). Recommend explicit
    # review of this one rule in particular before merge, possibly
    # narrowed with a suspicious-payload heuristic (e.g. requiring
    # os.system/subprocess/base64/exfil-shaped content alongside the
    # flag) rather than shipped as a bare interpreter-flag match.
    ("interpreter-inline-eval-flag",
     re.compile(r"\b(python3?|node|perl|ruby)\b\s+(-c|--eval|-e)\s"),
     "EXEC-052 (interpreter_arg_injection)"),
    ("git-hook-file-write",
     re.compile(r"\.git[/\\]hooks[/\\](pre-commit|post-checkout|post-merge)\b"),
     "EXEC-054 (git_hook_install)"),
    ("git-hookspath-config",
     re.compile(r"core\.hooksPath\b"),
     "EXEC-055 (git_hook_install)"),
    ("ci-workflow-run-block",
     re.compile(r"\.github[/\\]workflows[/\\].*\.ya?ml|\.gitlab-ci\.ya?ml\b|\.circleci[/\\]config\.ya?ml"),
     "EXEC-058 (ci_pipeline_modification)"),
    ("lockfile-integrity-tamper",
     re.compile(r"package-lock\.json\b.{0,20}(integrity|resolved)|yarn\.lock\b|Cargo\.lock\b"),
     "EXEC-060 (supply_chain_dependency_swap)"),
    ("dependency-local-path-override",
     re.compile(r"\[patch\.crates-io\]|path\s*=\s*['\"]\.\.?/"),
     "EXEC-061 (supply_chain_dependency_swap)"),
    ("direnv-envrc-write",
     re.compile(r"\.envrc\b"),
     "EXEC-062 (auto_loaded_config)"),
    ("ssh-authorized-keys-append",
     re.compile(r"\.ssh[/\\]authorized_keys2?\b"),
     "EXEC-078 (ssh_authorized_keys)"),
    ("sudoers-write",
     re.compile(r"/etc/sudoers(\.d[/\\][^\s]+)?\b|/etc/doas\.conf\b"),
     "EXEC-080 (sudoers_modification)"),
    ("polkit-rule-write",
     re.compile(r"/etc/polkit-1/rules\.d/"),
     "EXEC-081 (polkit_rule_install)"),
    ("path-env-prepend",
     re.compile(r"export\s+PATH=.{0,10}:\$PATH"),
     "EXEC-083 (path_hijack)"),
    ("windows-run-key-write",
     re.compile(r"CurrentVersion\\\\Run(Once)?(Ex)?\b"),
     "EXEC-087 (windows_registry_run_key)"),
    ("windows-service-create",
     re.compile(r"\bsc\s+create\b|New-Service\b"),
     "EXEC-088 (windows_service_install)"),
    ("powershell-profile-write",
     re.compile(r"\$PROFILE\b|Microsoft\.PowerShell_profile\.ps1"),
     "EXEC-090 (powershell_profile_persistence)"),
    ("chrome-devtools-protocol-connect",
     re.compile(r"localhost:9222\b|Runtime\.evaluate\b"),
     "EXEC-092 (browser_devtools_protocol)"),
    ("docker-socket-abuse",
     re.compile(r"/var/run/docker\.sock\b|/run/containerd/containerd\.sock\b"),
     "EXEC-093 (docker_socket_abuse)"),
    ("kubectl-exec-cmd",
     re.compile(r"\bkubectl\s+exec\b|\bkubectl\s+debug\b"),
     "EXEC-094 (kubernetes_exec)"),
    ("k8s-privileged-pod-manifest",
     re.compile(r"privileged:\s*true|hostPID:\s*true|hostNetwork:\s*true"),
     "EXEC-095 (kubernetes_privileged_pod)"),
    ("sts-assume-role-cmd",
     re.compile(r"sts\s+assume-role(-with-web-identity)?\b"),
     "EXEC-097 (cloud_iam_role_assume)"),
]
