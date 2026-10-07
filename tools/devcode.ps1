$ErrorActionPreference = "Stop"
$body = @{
    client_id = "178c6fc778ccc68e1d6a"   # GitHub CLI public OAuth client id
    scope     = "repo read:org"
}
$resp = Invoke-RestMethod -Method Post -Uri "https://github.com/login/device/code" -Body $body -TimeoutSec 30
# Surface on screen for the user
Write-Output "USER_CODE=$($resp.user_code)"
Write-Output "VERIFY_URL=$($resp.verification_uri)"
# Persist for polling step
$resp | ConvertTo-Json | Set-Content -Path "$env:TEMP\gh_device.json" -Encoding utf8
Write-Output "SAVED=$env:TEMP\gh_device.json (expires_in=$($resp.expires_in), interval=$($resp.interval))"