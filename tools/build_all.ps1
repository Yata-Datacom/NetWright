# 一键构建两份产物：单文件（分发用）与目录版（日常用，启动快 4 倍）。
# 用法：
#   pwsh tools/build_all.ps1             # 构建 + 报告体积
#   pwsh tools/build_all.ps1 -NoBuild    # 只报告已有产物
param(
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if (-not $NoBuild) {
    Write-Host "== 1/2 单文件（onefile） ==" -ForegroundColor Cyan
    & $python -m PyInstaller NetWright.spec --noconfirm --clean | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "onefile 构建失败" }

    Write-Host "== 2/2 目录版（onedir） ==" -ForegroundColor Cyan
    & $python -m PyInstaller NetWright-onedir.spec --noconfirm --clean | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "onedir 构建失败" }
}

$onefile = Join-Path $root "dist\NetWright.exe"
$onedir = Join-Path $root "dist\NetWright\NetWright.exe"

if (Test-Path $onefile) {
    "{0,-8} {1,7:N1} MB  {2}" -f "onefile", ((Get-Item $onefile).Length / 1MB), $onefile
} else {
    Write-Host "onefile 产物不存在（先不带 -NoBuild 跑一次）" -ForegroundColor Yellow
}

if (Test-Path $onedir) {
    $folder = Split-Path $onedir
    $total = (Get-ChildItem $folder -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
    $files = (Get-ChildItem $folder -Recurse -File | Measure-Object).Count
    "{0,-8} {1,7:N1} MB  {2}（{3} 个文件）" -f "onedir", $total, $onedir, $files
} else {
    Write-Host "onedir 产物不存在（先不带 -NoBuild 跑一次）" -ForegroundColor Yellow
}

$sums = Join-Path $root "dist\SHA256SUMS.txt"
$lines = @()
foreach ($file in @($onefile, $onedir)) {
    if (Test-Path $file) {
        $hash = (Get-FileHash -Algorithm SHA256 $file).Hash.ToLower()
        $distRoot = Join-Path $root "dist"
        $rel = $file.Substring($distRoot.Length + 1).Replace("\", "/")
        $lines += "$hash  $rel"
    }
}
if ($lines.Count -gt 0) {
    $lines | Set-Content -Path $sums -Encoding ASCII
    Write-Host "SHA256: $sums" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "提示：onedir 暖启动约 0.6 s；刚复制完的第一轮会被杀软扫描拖慢到 2 s 左右。" -ForegroundColor DarkGray
Write-Host "注意：单文件启动要把整包解压到 %TEMP%，所以比目录版慢 4 倍左右。" -ForegroundColor DarkGray
