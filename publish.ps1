#requires -Version 7
<#
  publish.ps1 —— 本地一键发布（方案 C）
  用法:  .\publish.ps1 "提交说明"

  流程:
    ① 从 nmi.full.yaml（含密钥真身）派生脱敏 nmi.yaml（密钥区 → 一行 #__NODES__）
    ② 节点变化时，把密钥块 base64 同步到 GitHub Secret NMI_SECRET_BLOCK
    ③ 提交并推送脱敏版 + .list（push 触发云端发布到 OSS）
    ④ 仅改节点（nmi.yaml 未变）时，手动触发云端 workflow
  前提: 已安装并登录 gh CLI（token 具备 repo + workflow 权限）
#>
param([Parameter(Position = 0)][string]$Msg = "update config")

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$Full     = 'nmi.full.yaml'
$Pub      = 'nmi.yaml'
$HashFile = '.nodes.hash'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path -LiteralPath $Full)) { throw "$Full 不存在（真身文件丢失？）已中止。" }

# ---- 定位密钥区标记 ----
$lines = Get-Content -LiteralPath $Full -Encoding UTF8
$a = ($lines | Select-String -Pattern '^#__SECRET_START__$' | Select-Object -First 1).LineNumber
$b = ($lines | Select-String -Pattern '^#__SECRET_END__$'   | Select-Object -First 1).LineNumber
if (-not $a -or -not $b -or $b -le $a) { throw "找不到 #__SECRET_START__ / #__SECRET_END__ 标记，已中止。" }

# ---- ① 派生脱敏版（强制 LF 行尾、UTF-8 无 BOM）----
$out = $lines[0..($a - 2)] + '#__NODES__' + $lines[$b..($lines.Count - 1)]
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $Pub), ($out -join "`n") + "`n", $Utf8NoBom)

# 脱敏自检：脱敏版绝不允许出现节点密钥特征
$leak = Select-String -LiteralPath $Pub -Pattern 'apiserver\.zodnext', 'reality-opts', '^\s*uuid:', '^\s*password:', 'obfs-password'
if ($leak) { throw "脱敏自检失败：$Pub 仍含疑似密钥，已中止（未推送）。" }

# ---- ② 节点块 → base64；变化时才更新 Secret ----
$block = ($lines[$a..($b - 2)] -join "`n")
$b64   = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($block))
$sha   = [System.Security.Cryptography.SHA256]::Create()
$h     = [BitConverter]::ToString($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($b64))) -replace '-', ''
$nodesChanged = (-not (Test-Path -LiteralPath $HashFile)) -or ((Get-Content -LiteralPath $HashFile -Raw).Trim() -ne $h)

if ($nodesChanged) {
    Write-Host "节点有变化 → 更新 GitHub Secret NMI_SECRET_BLOCK ..."
    gh secret set NMI_SECRET_BLOCK --body $b64
    if ($LASTEXITCODE -ne 0) { throw "gh secret set 失败，已中止（未推送）。" }
    Set-Content -LiteralPath $HashFile -Value $h -NoNewline -Encoding ascii
} else {
    Write-Host "节点无变化 → 跳过 Secret 同步。"
}

# ---- ③ 提交并推送脱敏版 + .list ----
git add -- $Pub '*.list' .gitignore
$staged = git diff --cached --name-only
$pushed = $false
if ($staged) {
    git commit -m $Msg
    if ($LASTEXITCODE -ne 0) { throw "git commit 失败（pre-commit 拦截？），已中止。" }
    git push
    if ($LASTEXITCODE -ne 0) { throw "git push 失败，已中止。" }
    $pushed = $true
    Write-Host "已推送脱敏版（push 将触发云端发布到 OSS）。"
} else {
    Write-Host "无文件变化，未提交。"
}

# ---- ④ 仅改节点（nmi.yaml 未变）时，手动补触发云端 ----
if ($nodesChanged -and -not $pushed) {
    Write-Host "仅节点变化 → 手动触发云端 workflow ..."
    gh workflow run publish.yml
}

Write-Host "`n完成。云端发布约 30s–1 分钟；之后 OpenClash 按周期或手动刷新即可生效。"
