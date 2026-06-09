$ErrorActionPreference = "Stop"

Write-Host "Starting VTCM desktop workbench..." -ForegroundColor Cyan

if (-not (Test-Path "desktop_client\node_modules")) {
    Write-Host "Installing desktop client dependencies..." -ForegroundColor Yellow
    npm --prefix desktop_client install
}

npm --prefix desktop_client run dev

