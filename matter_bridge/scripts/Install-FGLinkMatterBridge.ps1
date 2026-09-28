param(
    [string]$ApiUrl = "",
    [string]$MatterbridgeVersion = "3.10.11"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

Write-Host "FG Link Matter Bridge - Windows Beta" -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Node.js is not installed and winget is unavailable. Install Node.js 24 LTS, then run this script again."
    }
    Write-Host "Installing Node.js LTS with winget..." -ForegroundColor Yellow
    winget install --id OpenJS.NodeJS.LTS --exact --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

$nodeVersion = (& node --version).Trim().TrimStart("v")
$nodeMajor = [int]($nodeVersion.Split(".")[0])
if ($nodeMajor -notin @(22, 24, 26)) {
    throw "Matterbridge requires a supported Node.js line. Detected $nodeVersion; use Node 22, 24 or 26."
}

if ([string]::IsNullOrWhiteSpace($ApiUrl)) {
    $ApiUrl = Read-Host "FG Link API URL (example http://192.168.1.25:18086)"
}
$secureToken = Read-Host "Paste the FG Link CONTROL/Home Assistant token" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
if ([string]::IsNullOrWhiteSpace($token)) { throw "A FG Link CONTROL token is required." }

Write-Host "Installing Matterbridge $MatterbridgeVersion..." -ForegroundColor Yellow
npm install -g "matterbridge@$MatterbridgeVersion" --omit=dev --no-fund --no-audit
if ($LASTEXITCODE -ne 0) { throw "Matterbridge installation failed." }

Push-Location $Root
try {
    npm link matterbridge --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { throw "Could not link the Matterbridge runtime to the FG Link plugin." }
    matterbridge --add $Root
    if ($LASTEXITCODE -ne 0) { throw "Could not register matterbridge-fg-link." }
} finally {
    Pop-Location
}

$profileDir = Join-Path $HOME ".matterbridge"
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
$configPath = Join-Path $profileDir "matterbridge-fg-link.config.json"
$config = [ordered]@{
    name = "matterbridge-fg-link"
    type = "DynamicPlatform"
    apiUrl = $ApiUrl.TrimEnd("/")
    token = $token
    pollIntervalSeconds = 5
    exposeOfflineDevices = $true
    debug = $false
    unregisterOnShutdown = $false
}
$config | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $configPath

Write-Host ""
Write-Host "Installed successfully." -ForegroundColor Green
Write-Host "Config: $configPath"
Write-Host "Next: .\scripts\Start-FGLinkMatterBridge.ps1"
Write-Host "Matterbridge frontend is normally http://localhost:8283"
