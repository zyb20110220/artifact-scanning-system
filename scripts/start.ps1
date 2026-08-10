# 一键启动：构建并启动 Neo4j + 应用
# 用法：powershell -ExecutionPolicy Bypass -File scripts/start.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 切到项目根（脚本在 scripts/ 下）
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> 检查 .env ..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Write-Error "缺少 .env 文件！请复制 .env.example 并填入 QWEN_API_KEY / NEO4J_PASSWORD"
    exit 1
}

Write-Host "==> 启动 Neo4j 数据库 ..." -ForegroundColor Cyan
docker compose up -d neo4j

Write-Host "==> 构建并启动应用 ..." -ForegroundColor Cyan
docker compose up -d --build app

Write-Host ""
Write-Host "✅ 系统已启动！" -ForegroundColor Green
Write-Host "   应用界面:   http://localhost:7860"
Write-Host "   Neo4j 控制台: http://localhost:7474"
Write-Host "查看日志: docker compose logs -f app"
