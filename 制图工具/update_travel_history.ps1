param(
    [string]$QgisPython = 'E:\QGIS 3.44.8\bin\python-qgis-ltr.bat',
    [switch]$TimetableOnly
)

$ErrorActionPreference = 'Stop'
$mapRoot = Split-Path -Parent $PSScriptRoot
$scriptsRoot = Join-Path $PSScriptRoot 'scripts'
$blogRoot = Split-Path -Parent $mapRoot
$env:OPENBLAS_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'

if (-not (Test-Path -LiteralPath $QgisPython)) {
    throw "QGIS Python not found: $QgisPython"
}

function Invoke-MapStep([string]$RelativeScript) {
    Write-Host "Running $RelativeScript"
    & $QgisPython (Join-Path $scriptsRoot $RelativeScript)
    if ($LASTEXITCODE -ne 0) {
        throw "Map build failed: $RelativeScript"
    }
}

Invoke-MapStep 'travel_history\parse_source.py'
if ($TimetableOnly) {
    Invoke-MapStep 'travel_history\sync_rail_records.py'
} else {
    Invoke-MapStep 'travel_history\inspect_sources.py'
    Invoke-MapStep 'travel_history\build_routes.py'
    Invoke-MapStep 'travel_history\build_maps.py'
}
Invoke-MapStep 'railway_web\build_web_data.py'
Invoke-MapStep 'travel_history\validate_maps.py'

if (Test-Path -LiteralPath (Join-Path $blogRoot 'package.json')) {
    Push-Location $blogRoot
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Blog build failed' }
    } finally {
        Pop-Location
    }
}
Write-Host 'Updated map data, startup bundle and journey calendar.'
