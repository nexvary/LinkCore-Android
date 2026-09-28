param(
    [string]$ApiUrl = "",
    [string]$Token = ""
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ApiUrl)) {
    $ApiUrl = Read-Host "FG Link API URL"
}
if ([string]::IsNullOrWhiteSpace($Token)) {
    $secure = Read-Host "FG Link CONTROL/Home Assistant token" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $Token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

Write-Host "Testing $ApiUrl/api/v1/health" -ForegroundColor Cyan
$health = Invoke-RestMethod -Uri ($ApiUrl.TrimEnd("/") + "/api/v1/health") -Method Get -TimeoutSec 5
$health | ConvertTo-Json -Depth 5

Write-Host "Testing authenticated device list..." -ForegroundColor Cyan
$headers = @{ Authorization = "Bearer $Token" }
$devices = Invoke-RestMethod -Uri ($ApiUrl.TrimEnd("/") + "/api/v1/devices") -Headers $headers -Method Get -TimeoutSec 5
$count = @($devices.devices).Count
Write-Host "FG Link devices visible to this token: $count" -ForegroundColor Green
$devices.devices | Select-Object mac, name, room, connected | Format-Table -AutoSize

Write-Host "IPv6 adapters:" -ForegroundColor Cyan
Get-NetIPAddress -AddressFamily IPv6 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "fe80::*" -or $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object InterfaceAlias, IPAddress, AddressState |
    Format-Table -AutoSize

Write-Host "Doctor completed. Do not continue to pairing until the API device list works." -ForegroundColor Green
