$ErrorActionPreference = "Stop"
if (-not (Get-Command matterbridge -ErrorAction SilentlyContinue)) {
    throw "Matterbridge is not installed. Run Install-FGLinkMatterBridge.ps1 first."
}
Write-Host "Starting FG Link Matter Bridge..." -ForegroundColor Cyan
Write-Host "Keep this window open during the Windows beta test." -ForegroundColor Yellow
matterbridge --bridge --frontend 8283 --port 5540
