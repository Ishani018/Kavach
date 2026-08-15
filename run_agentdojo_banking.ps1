$env:LOCAL_LLM_PORT = "11434"
$python = "C:\Users\ishan\Desktop\Kavach\.venv\Scripts\python.exe"
$logdir = "C:\Users\ishan\Desktop\Kavach\benchmarks\agentdojo_live\banking_qwen25_7b"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

Write-Output "BASELINE START $(Get-Date -Format 'HH:mm:ss')"
& $python -m agentdojo.scripts.benchmark `
    --model LOCAL `
    --model-id qwen2.5:7b `
    --suite banking `
    --benchmark-version v1.2.2 `
    --logdir $logdir
Write-Output "BASELINE DONE $(Get-Date -Format 'HH:mm:ss')"

Write-Output "ATTACK START $(Get-Date -Format 'HH:mm:ss')"
& $python -m agentdojo.scripts.benchmark `
    --model LOCAL `
    --model-id qwen2.5:7b `
    --suite banking `
    --benchmark-version v1.2.2 `
    --attack important_instructions `
    --logdir $logdir
Write-Output "ATTACK DONE $(Get-Date -Format 'HH:mm:ss')"
