# Generate ONLY multi-turn dataset using OpenAI mode (PowerShell)
# Prerequisites: $env:OPENAI_API_KEY set; will run Stage 1/2 if needed.

$ErrorActionPreference = "Stop"

if (!(Test-Path -Path "run_id")) {
  Write-Host "run_id not found, running Stage 1 (OpenAI)..."
  python run_s1_openai.py
}

$run_id = (Get-Content -Path "run_id").Trim()
$functionsPath = Join-Path -Path "pipeline/data/$run_id" -ChildPath "functions.json"
if (!(Test-Path -Path $functionsPath)) {
  Write-Host "functions.json not found for run_id=$run_id, running Stage 2 (OpenAI)..."
  python run_s2_openai.py
}

$env:ONLY_MULTI_TURN = "1"
python run_s3_openai.py
