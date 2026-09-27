# One-command reproduction of the full CareOps pipeline, for Windows
# PowerShell. Mirrors run.sh / run.py exactly, stage for stage.
#
#   .\run.ps1
#   .\run.ps1 -NoInstall     # skip the pip install step
#
# Run from anywhere; this script locates the repo relative to its own path.

param(
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ModelDir = Join-Path $RepoRoot "model"

if (-not $NoInstall) {
    Write-Host "== installing dependencies (pandas, numpy, scikit-learn) =="
    pip install -q -r (Join-Path $RepoRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$Stages = @(
    "disruption_model.py",
    "fairness_subgroup_analysis.py",
    "disruption_type_model.py",
    "communication_intelligence.py",
    "llm_direct_eval.py",
    "hybrid_extraction.py",
    "capacity_recovery.py",
    "agent_state_machine.py",
    "economics_simulation.py",
    "intervention_outcome_simulation.py",
    "generate_dashboard_data.py"
)

Push-Location $ModelDir
try {
    foreach ($stage in $Stages) {
        Write-Host ""
        Write-Host "== $stage =="
        python $stage
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "== done =="
Write-Host "dashboard/index.html now reflects this run's output — open it directly in a browser."
