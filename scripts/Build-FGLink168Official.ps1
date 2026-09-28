param(
    [Parameter(Mandatory=$true)][string]$KeystorePath,
    [Parameter(Mandatory=$true)][string]$KeyAlias
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $KeystorePath)) {
    throw "Keystore not found: $KeystorePath"
}

$store = Read-Host "Keystore password" -AsSecureString
$key = Read-Host "Key password" -AsSecureString

function Secure-To-Plain([Security.SecureString]$s) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$env:FG_RCK_KEYSTORE_PATH = (Resolve-Path $KeystorePath).Path
$env:FG_RCK_KEYSTORE_PASSWORD = Secure-To-Plain $store
$env:FG_RCK_KEY_ALIAS = $KeyAlias
$env:FG_RCK_KEY_PASSWORD = Secure-To-Plain $key

try {
    gradle --no-daemon clean testDebugUnitTest lintDebug assembleRelease
    if ($LASTEXITCODE -ne 0) { throw "Gradle build failed." }

    $apk = Resolve-Path "app\build\outputs\apk\release\app-release.apk"
    $hash = (Get-FileHash $apk -Algorithm SHA256).Hash.ToLowerInvariant()

    Write-Host ""
    Write-Host "FG Link 1.6.8 official hardened APK:"
    Write-Host $apk
    Write-Host "SHA-256: $hash"
    Write-Host ""
    Write-Host "Keep the keystore private. Never upload it with the APK."
}
finally {
    Remove-Item Env:FG_RCK_KEYSTORE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:FG_RCK_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:FG_RCK_KEY_ALIAS -ErrorAction SilentlyContinue
    Remove-Item Env:FG_RCK_KEY_PASSWORD -ErrorAction SilentlyContinue
}
