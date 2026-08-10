# 一键停止：关闭 app 和 Neo4j 服务
# 用法：powershell -ExecutionPolicy Bypass -File scripts/stop.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> 停止所有服务 ..." -ForegroundColor Cyan
docker compose down

Write-Host "✅ 已停止。" -ForegroundColor Green
Write-Host "（数据保留在 data/ 与 neo4j 数据卷，重启不丢失）"
