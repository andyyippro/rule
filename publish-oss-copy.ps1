#requires -Version 7
<#
  publish-oss-copy.ps1 —— nmi OSS 独立副本的本地发布脚本
  用法:  .\publish-oss-copy.ps1 "提交说明"
         .\publish-oss-copy.ps1 -ValidateOnly
         .\publish-oss-copy.ps1 -InitializeObjectKey
         .\publish-oss-copy.ps1 -RotateObjectKey
         .\publish-oss-copy.ps1 -SyncRecordedObjectKey

  只处理 nmi-oss.full.yaml，并精确提交 5 个公开配置副本和
  nmi-oss-CHANGELOG.md。-ValidateOnly 不改工作树；普通模式和对象键操作只允许
  main 跟踪 origin/main，普通模式会 push，未经明确授权不要运行。
#>
param(
    [Parameter(Position = 0)][string]$Msg = "update OSS copy config",
    [switch]$ValidateOnly,
    [switch]$InitializeObjectKey,
    [switch]$RotateObjectKey,
    [switch]$SyncRecordedObjectKey
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$Full = 'nmi-oss.full.yaml'
$Public = 'nmi-oss.yaml'
$SecretName = 'NMI_OSS_SECRET_BLOCK'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$PendingPushState = Join-Path $PSScriptRoot '.nmi-oss.pending-push'
$PublicValidator = Join-Path $PSScriptRoot 'scripts/validate-oss-public-copies.py'
$AllowedStaged = @(
    'nmi-oss.yaml'
    'cmi-oss.yaml'
    'qichiyu-oss.ini'
    'qichiyubeifen-oss.ini'
    'bei260317-oss.ini'
    'nmi-oss-CHANGELOG.md'
)

function Invoke-QuietCheckedProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [AllowNull()][string]$StandardInput = $null,
        [ValidateRange(1, 600)][int]$TimeoutSeconds = 60,
        [int[]]$ExpectedExitCodes = @(0),
        [Parameter(Mandatory)][string]$FailureMessage
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $null -ne $StandardInput
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $Arguments) {
        $null = $startInfo.ArgumentList.Add($argument)
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $started = $false
    try {
        if (-not $process.Start()) { throw $FailureMessage }
        $started = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        $timeoutMilliseconds = $TimeoutSeconds * 1000
        if ($null -ne $StandardInput) {
            $process.StandardInput.AutoFlush = $true
            $stdinTask = $process.StandardInput.WriteAsync($StandardInput)
            $remaining = [Math]::Max(0, $timeoutMilliseconds - [int]$timer.ElapsedMilliseconds)
            $writeCompleted = $false
            try {
                if ($remaining -gt 0) {
                    $writeCompleted = $stdinTask.Wait($remaining)
                }
                if ($writeCompleted) {
                    $null = $stdinTask.GetAwaiter().GetResult()
                    $process.StandardInput.Close()
                }
            }
            catch {
                throw $FailureMessage
            }
            if (-not $writeCompleted) {
                try { $process.Kill($true) } catch { }
                $null = $process.WaitForExit(5000)
                try { $null = $stdinTask.GetAwaiter().GetResult() } catch { }
                throw "$FailureMessage（等待超过 $TimeoutSeconds 秒）。"
            }
        }

        $remaining = [Math]::Max(0, $timeoutMilliseconds - [int]$timer.ElapsedMilliseconds)
        if ($remaining -eq 0 -or -not $process.WaitForExit($remaining)) {
            try { $process.Kill($true) } catch { }
            $null = $process.WaitForExit(5000)
            throw "$FailureMessage（等待超过 $TimeoutSeconds 秒）。"
        }

        # 父进程退出不代表重定向管道一定关闭；其子进程可能仍继承 stdout/stderr。
        # 输出排空也必须受同一个总时限约束，不能在 WaitForExit 之后无限等待。
        $outputTasks = [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)
        $allOutputTask = [System.Threading.Tasks.Task]::WhenAll($outputTasks)
        $remaining = [Math]::Max(0, $timeoutMilliseconds - [int]$timer.ElapsedMilliseconds)
        $outputCompleted = $false
        try {
            if ($remaining -gt 0) {
                $outputCompleted = $allOutputTask.Wait($remaining)
            }
            if ($outputCompleted) {
                $null = $allOutputTask.GetAwaiter().GetResult()
            }
        }
        catch {
            throw $FailureMessage
        }
        if (-not $outputCompleted) {
            try { $process.Kill($true) } catch { }
            throw "$FailureMessage（等待超过 $TimeoutSeconds 秒）。"
        }
        if ($process.ExitCode -notin $ExpectedExitCodes) {
            throw $FailureMessage
        }
    }
    finally {
        if ($started -and $process.HasExited -eq $false) {
            try { $process.Kill($true) } catch { }
        }
        $process.Dispose()
    }
}

function Invoke-GitHubSecretFromStandardInput {
    # gh 未提供 --body 时从标准输入读取：https://cli.github.com/manual/gh_secret_set
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Value
    )

    $gh = Get-Command gh -ErrorAction Stop
    Invoke-QuietCheckedProcess `
        -FilePath $gh.Source `
        -Arguments @('secret', 'set', $Name) `
        -StandardInput $Value `
        -TimeoutSeconds 60 `
        -FailureMessage "GitHub Secret 设置失败；未提交、未推送。"
}

function Get-PublishUpstream {
    $branch = @(& git branch --show-current 2>$null)
    if ($LASTEXITCODE -ne 0 -or $branch.Count -ne 1 -or $branch[0] -cne 'main') {
        throw "OSS 副本发布与对象键操作只能在 main 分支执行。"
    }
    $upstream = @(& git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or $upstream.Count -ne 1 -or $upstream[0] -cne 'origin/main') {
        throw "main 分支必须且只能跟踪 origin/main，已拒绝发布或修改对象键 Secret。"
    }

    $canonicalOriginPattern = '^(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)andyyippro/rule(?:\.git)?/?$'
    $fetchUrls = @(& git remote get-url --all origin 2>$null)
    $pushUrls = @(& git remote get-url --push --all origin 2>$null)
    if (
        $fetchUrls.Count -ne 1 -or
        $pushUrls.Count -ne 1 -or
        $fetchUrls[0] -notmatch $canonicalOriginPattern -or
        $pushUrls[0] -notmatch $canonicalOriginPattern
    ) {
        throw "origin 的读取或推送地址不是唯一的 GitHub andyyippro/rule 仓库，已拒绝发布。"
    }
    return $upstream[0]
}

function Read-PendingPushCommit {
    if (-not (Test-Path -LiteralPath $PendingPushState)) { return $null }
    if (-not (Test-Path -LiteralPath $PendingPushState -PathType Leaf)) {
        throw "本机待推送状态不是普通文件，已拒绝发布。"
    }

    $bytes = [System.IO.File]::ReadAllBytes($PendingPushState)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        throw "本机待推送状态格式无效，已拒绝发布。"
    }
    try {
        $text = [System.Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    }
    catch {
        throw "本机待推送状态格式无效，已拒绝发布。"
    }
    $match = [regex]::Match($text, '\Acommit=([0-9a-f]{40,64})\n?\z')
    if (-not $match.Success) {
        throw "本机待推送状态格式无效，已拒绝发布。"
    }
    return $match.Groups[1].Value
}

function Write-PendingPushCommit {
    param([Parameter(Mandatory)][string]$Commit)

    if ($Commit -cnotmatch '^[0-9a-f]{40,64}$') {
        throw "拒绝记录格式无效的待推送提交。"
    }
    $temporaryState = "$PendingPushState.tmp"
    try {
        [System.IO.File]::WriteAllText($temporaryState, "commit=$Commit`n", $Utf8NoBom)
        Move-Item -LiteralPath $temporaryState -Destination $PendingPushState -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryState) {
            Remove-Item -LiteralPath $temporaryState -Force
        }
    }
}

function Clear-PendingPushCommit {
    if (Test-Path -LiteralPath $PendingPushState) {
        Remove-Item -LiteralPath $PendingPushState -Force
    }
}

function Get-CommitId {
    param([Parameter(Mandatory)][string]$Revision)

    $commit = @(& git rev-parse --verify $Revision 2>$null)
    if ($LASTEXITCODE -ne 0 -or $commit.Count -ne 1 -or $commit[0] -cnotmatch '^[0-9a-f]{40,64}$') {
        throw "无法核对待推送提交身份。"
    }
    $objectType = @(& git cat-file -t $commit[0] 2>$null)
    if ($LASTEXITCODE -ne 0 -or $objectType.Count -ne 1 -or $objectType[0] -cne 'commit') {
        throw "待推送对象不是有效 Git commit。"
    }
    return $commit[0]
}

function Assert-AheadCommitPathsAllowed {
    param([Parameter(Mandatory)][string]$Upstream)

    $aheadText = @(& git rev-list --count "$Upstream..HEAD" 2>$null)
    if ($LASTEXITCODE -ne 0 -or $aheadText.Count -ne 1 -or $aheadText[0] -notmatch '^\d+$') {
        throw "无法核对本地提交是否已经推送。"
    }
    $aheadCount = [int]$aheadText[0]
    $pendingCommit = Read-PendingPushCommit
    if ($aheadCount -eq 0) {
        if ($null -ne $pendingCommit) {
            $null = & git merge-base --is-ancestor $pendingCommit $Upstream 2>$null
            if ($LASTEXITCODE -ne 0) {
                throw "本机待推送状态与 origin/main 不一致，已拒绝自动清理或发布。"
            }
            Clear-PendingPushCommit
        }
        return 0
    }

    if ($null -eq $pendingCommit) {
        throw "检测到非发布器登记的本地 ahead 提交；为防止公开历史泄密，已拒绝推送。"
    }
    if ($aheadCount -ne 1) {
        throw "待推送状态只能对应一个本地 ahead 提交，已拒绝推送。"
    }

    $headCommit = Get-CommitId -Revision 'HEAD'
    $parentCommit = Get-CommitId -Revision 'HEAD~1'
    $upstreamCommit = Get-CommitId -Revision $Upstream
    if ($headCommit -cne $pendingCommit -or $parentCommit -cne $upstreamCommit) {
        throw "本机待推送提交与记录或 origin/main 基线不一致，已拒绝推送。"
    }

    $aheadPaths = @(& git log --format= --no-renames --name-only "$Upstream..HEAD" -- 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "无法审计尚未推送提交的文件范围。"
    }
    $allowed = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($path in $AllowedStaged) { $null = $allowed.Add($path) }
    $unexpected = @($aheadPaths | Where-Object { $_ -and -not $allowed.Contains($_) } | Sort-Object -Unique)
    if ($unexpected.Count -gt 0) {
        throw "尚未推送的本地提交包含副本白名单外文件，已拒绝发布：$($unexpected -join ', ')"
    }
    return $aheadCount
}

function Test-FileBytesEqual {
    param(
        [Parameter(Mandatory)][string]$Left,
        [Parameter(Mandatory)][string]$Right
    )

    $leftBytes = [System.IO.File]::ReadAllBytes($Left)
    $rightBytes = [System.IO.File]::ReadAllBytes($Right)
    return [System.Linq.Enumerable]::SequenceEqual[byte]($leftBytes, $rightBytes)
}

function Assert-RecoveryContentUnchanged {
    param([Parameter(Mandatory)][string]$CandidatePublicPath)

    $null = & git diff --quiet -- @AllowedStaged
    $worktreeStatus = $LASTEXITCODE
    $null = & git diff --cached --quiet -- @AllowedStaged
    $indexStatus = $LASTEXITCODE
    if ($worktreeStatus -gt 1 -or $indexStatus -gt 1) {
        throw "无法核对待补推送副本的工作树状态。"
    }
    if ($worktreeStatus -ne 0 -or $indexStatus -ne 0) {
        throw "存在新的副本修改；必须先补推送已登记提交，再重新运行发布。"
    }
    if (-not (Test-Path -LiteralPath $Public -PathType Leaf) -or -not (Test-FileBytesEqual -Left $CandidatePublicPath -Right $Public)) {
        throw "本机真身会生成不同公开副本；必须先补推送已登记提交，再重新运行发布。"
    }
}

function Invoke-PushMain {
    & git -c push.followTags=false push origin 'HEAD:refs/heads/main'
    if ($LASTEXITCODE -ne 0) {
        throw "git push origin/main 失败；待推送提交 SHA 已保留供精确重试。"
    }
}

function Assert-CommitMessageSafe {
    param([AllowEmptyString()][string]$Message)

    if (-not (Test-Path -LiteralPath $PublicValidator -PathType Leaf)) {
        throw "缺少 OSS 公开副本共用安全校验器；未设置 Secret、未提交、未推送。"
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        throw "本机缺少 Python，无法安全检查提交说明；未设置 Secret、未提交、未推送。"
    }
    Invoke-QuietCheckedProcess `
        -FilePath $python.Source `
        -Arguments @($PublicValidator, '--stdin-public-text') `
        -StandardInput $Message `
        -TimeoutSeconds 30 `
        -FailureMessage "提交说明疑似包含敏感内容或无法安全校验；未设置 Secret、未提交、未推送。"
}

function Assert-PublicValidatorOperational {
    if (-not (Test-Path -LiteralPath $PublicValidator -PathType Leaf)) {
        throw "缺少 OSS 公开副本共用安全校验器；未设置 Secret、未提交、未推送。"
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        throw "本机缺少 Python，无法确认安全校验器有效；未设置 Secret、未提交、未推送。"
    }

    $commonArguments = @($PublicValidator, '--stdin-public-text')
    Invoke-QuietCheckedProcess `
        -FilePath $python.Source `
        -Arguments $commonArguments `
        -StandardInput 'validator canary public text' `
        -ExpectedExitCodes @(0) `
        -TimeoutSeconds 30 `
        -FailureMessage "OSS 公开副本安全校验器未通过安全样例；未设置 Secret、未提交、未推送。"
    Invoke-QuietCheckedProcess `
        -FilePath $python.Source `
        -Arguments $commonArguments `
        -StandardInput ('pass' + 'word: VALIDATOR_CANARY') `
        -ExpectedExitCodes @(1) `
        -TimeoutSeconds 30 `
        -FailureMessage "OSS 公开副本安全校验器未拒绝敏感样例；未设置 Secret、未提交、未推送。"
    Invoke-QuietCheckedProcess `
        -FilePath $python.Source `
        -Arguments $commonArguments `
        -StandardInput ("pass" + "word&#58;`n&#45; VALIDATOR_CANARY") `
        -ExpectedExitCodes @(1) `
        -TimeoutSeconds 30 `
        -FailureMessage "OSS 公开副本安全校验器未拒绝 Markdown 语义样例；未设置 Secret、未提交、未推送。"
}

function Get-ObjectKeyRecord {
    $localDocument = Join-Path $PSScriptRoot 'CLAUDE.local.md'
    if (-not (Test-Path -LiteralPath $localDocument -PathType Leaf)) {
        throw "缺少 CLAUDE.local.md，不能安全记录或核对完整订阅 URL。"
    }
    $localBytes = [System.IO.File]::ReadAllBytes($localDocument)
    if ($localBytes.Length -ge 3 -and $localBytes[0] -eq 0xEF -and $localBytes[1] -eq 0xBB -and $localBytes[2] -eq 0xBF) {
        throw "CLAUDE.local.md 不允许 UTF-8 BOM；未设置 Secret。"
    }
    try {
        $localText = [System.Text.UTF8Encoding]::new($false, $true).GetString($localBytes)
    }
    catch {
        throw "CLAUDE.local.md 不是有效 UTF-8；未设置 Secret。"
    }

    $keyPattern = 'subscriptions/[0-9a-f]{64}/nmi-oss\.yaml'
    $currentMarker = '<!-- NMI_OSS_SUBSCRIPTION_URL -->'
    $currentLabel = 'OSS 独立副本完整订阅 URL：'
    $pendingMarker = '<!-- NMI_OSS_SUBSCRIPTION_URL_PENDING -->'
    $pendingLabel = 'OSS 独立副本待同步 URL：'
    $currentPattern = [regex]::Escape($currentMarker) + '(?:\r?\n){2}' + [regex]::Escape($currentLabel) +
        'https://cclsst\.oss-cn-shenzhen\.aliyuncs\.com/(?<key>' + $keyPattern + ')(?=\r?\n|\z)'
    $pendingPattern = [regex]::Escape($pendingMarker) + '(?:\r?\n){2}' + [regex]::Escape($pendingLabel) +
        'https://cclsst\.oss-cn-shenzhen\.aliyuncs\.com/(?<key>' + $keyPattern + ')(?=\r?\n|\z)'
    $currentMatch = [regex]::Match($localText, $currentPattern)
    $pendingMatch = [regex]::Match($localText, $pendingPattern)

    $formats = @(
        @($currentMarker, $currentLabel, $currentPattern, $currentMatch, '当前'),
        @($pendingMarker, $pendingLabel, $pendingPattern, $pendingMatch, '待同步')
    )
    foreach ($format in $formats) {
        $markerCount = [regex]::Matches($localText, [regex]::Escape($format[0])).Count
        $labelCount = [regex]::Matches($localText, [regex]::Escape($format[1])).Count
        if ($markerCount -gt 1 -or $labelCount -gt 1 -or $markerCount -ne $labelCount -or
            ($markerCount -eq 1 -and -not $format[3].Success)) {
            throw "CLAUDE.local.md 的 OSS 副本$($format[4]) URL 记录格式异常；未设置 Secret。"
        }
    }
    if ($currentMatch.Success -and $pendingMatch.Success -and
        $currentMatch.Groups['key'].Value -ceq $pendingMatch.Groups['key'].Value) {
        throw "CLAUDE.local.md 的当前与待同步对象键相同；未设置 Secret。"
    }

    return [pscustomobject]@{
        Document = $localDocument
        Text = $localText
        CurrentMarker = $currentMarker
        CurrentLabel = $currentLabel
        CurrentPattern = $currentPattern
        CurrentMatch = $currentMatch
        PendingMarker = $pendingMarker
        PendingLabel = $pendingLabel
        PendingPattern = $pendingPattern
        PendingMatch = $pendingMatch
    }
}

function Get-PromotedObjectKeyText {
    param(
        [Parameter(Mandatory)]$Record,
        [Parameter(Mandatory)][string]$ObjectKey
    )

    $currentEntry = "$($Record.CurrentMarker)`n`n$($Record.CurrentLabel)https://cclsst.oss-cn-shenzhen.aliyuncs.com/$ObjectKey"
    if ($Record.CurrentMatch.Success) {
        $result = [regex]::Replace($Record.Text, $Record.CurrentPattern, $currentEntry, 1)
        if ($Record.PendingMatch.Success) {
            $result = [regex]::Replace($result, $Record.PendingPattern, '', 1)
        }
    }
    elseif ($Record.PendingMatch.Success) {
        $result = [regex]::Replace($Record.Text, $Record.PendingPattern, $currentEntry, 1)
    }
    else {
        $result = $Record.Text.TrimEnd("`r", "`n") + "`n`n$currentEntry"
    }
    return $result.TrimEnd("`r", "`n") + "`n"
}

$objectKeyOperationCount = @(
    $InitializeObjectKey,
    $RotateObjectKey,
    $SyncRecordedObjectKey
).Where({ $_ }).Count
if ($objectKeyOperationCount -gt 1) {
    throw "对象键初始化、轮换与重同步参数不能同时使用。"
}
if ($ValidateOnly -and $objectKeyOperationCount -gt 0) {
    throw "-ValidateOnly 不能与对象键初始化、轮换或重同步参数同时使用。"
}
Assert-PublicValidatorOperational
if (-not $ValidateOnly -and $objectKeyOperationCount -eq 0) {
    Assert-CommitMessageSafe -Message $Msg
}
$publishUpstream = if (-not $ValidateOnly) { Get-PublishUpstream } else { $null }

if ($objectKeyOperationCount -eq 1) {
    $record = Get-ObjectKeyRecord
    $hasCurrent = $record.CurrentMatch.Success
    $hasPending = $record.PendingMatch.Success
    if (($InitializeObjectKey -or $RotateObjectKey) -and $hasPending) {
        throw "存在尚未确认的待同步对象键；请先使用 -SyncRecordedObjectKey 恢复一致状态。"
    }
    if ($InitializeObjectKey -and $hasCurrent) {
        throw "OSS 副本对象键已初始化；如确需轮换，必须显式使用 -RotateObjectKey。"
    }
    if ($RotateObjectKey -and -not $hasCurrent) {
        throw "尚未初始化 OSS 副本对象键；请使用 -InitializeObjectKey。"
    }
    if ($SyncRecordedObjectKey -and -not ($hasCurrent -or $hasPending)) {
        throw "本机尚无可重同步的 OSS 副本对象键。"
    }

    if ($SyncRecordedObjectKey) {
        $objectKey = if ($hasPending) {
            $record.PendingMatch.Groups['key'].Value
        }
        else {
            $record.CurrentMatch.Groups['key'].Value
        }
        Invoke-GitHubSecretFromStandardInput -Name 'OSS_NMI_COPY_OBJECT_KEY' -Value $objectKey
        if ($hasPending) {
            $promotedText = Get-PromotedObjectKeyText -Record $record -ObjectKey $objectKey
            [System.IO.File]::WriteAllText($record.Document, $promotedText, $Utf8NoBom)
        }
        Write-Host "已通过标准输入把本机记录的对象键重同步到 OSS_NMI_COPY_OBJECT_KEY。"
        return
    }

    $randomBytes = [byte[]]::new(32)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($randomBytes)
    $token = [Convert]::ToHexString($randomBytes).ToLowerInvariant()
    $objectKey = "subscriptions/$token/nmi-oss.yaml"
    if ($objectKey -cnotmatch '^subscriptions/[0-9a-f]{64}/nmi-oss\.yaml$') {
        throw "生成的 OSS 副本对象键格式无效。"
    }

    if ($record.Text.Contains("/$objectKey", [System.StringComparison]::Ordinal)) {
        throw "新对象键与本机记录的既有对象键相同；未设置 Secret。"
    }

    $pendingEntry = "$($record.PendingMarker)`n`n$($record.PendingLabel)https://cclsst.oss-cn-shenzhen.aliyuncs.com/$objectKey"
    $pendingText = $record.Text.TrimEnd("`r", "`n") + "`n`n$pendingEntry`n"
    # 当前键始终保留；新键先以“待同步”状态落盘。只有 GitHub 确认成功后才提升为当前键。
    [System.IO.File]::WriteAllText($record.Document, $pendingText, $Utf8NoBom)
    try {
        Invoke-GitHubSecretFromStandardInput -Name 'OSS_NMI_COPY_OBJECT_KEY' -Value $objectKey
    }
    catch {
        throw "GitHub Secret 设置失败或状态不确定；当前 URL 与待同步新 URL 均已保留，请确认远端状态后使用 -SyncRecordedObjectKey 重试。"
    }
    $promotedText = Get-PromotedObjectKeyText -Record $record -ObjectKey $objectKey
    [System.IO.File]::WriteAllText($record.Document, $promotedText, $Utf8NoBom)
    $action = if ($RotateObjectKey) { '轮换' } else { '初始化' }
    Write-Host "OSS_NMI_COPY_OBJECT_KEY 已通过标准输入$action；完整 URL 仅写入 CLAUDE.local.md。"
    return
}

if (-not $ValidateOnly) {
    $initialAheadCount = Assert-AheadCommitPathsAllowed -Upstream $publishUpstream
    $publicationKeyRecord = Get-ObjectKeyRecord
    if (-not $publicationKeyRecord.CurrentMatch.Success) {
        throw "OSS 副本对象键尚未初始化；发布前必须先运行 -InitializeObjectKey。"
    }
    if ($publicationKeyRecord.PendingMatch.Success) {
        throw "存在尚未确认的待同步对象键；发布前必须先运行 -SyncRecordedObjectKey。"
    }
}

function Get-StagedPaths {
    $paths = @(& git diff --cached --no-renames --name-only --)
    if ($LASTEXITCODE -ne 0) { throw "读取 Git 暂存区失败。" }
    return @($paths | Where-Object { $_ })
}

function Assert-StagedWhitelist {
    param([AllowEmptyCollection()][string[]]$Paths)

    $allowed = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($path in $AllowedStaged) { $null = $allowed.Add($path) }
    $unexpected = @($Paths | Where-Object { $_ -and -not $allowed.Contains($_) })
    if ($unexpected.Count -gt 0) {
        throw "暂存区含白名单外文件，已拒绝发布：$($unexpected -join ', ')"
    }
}

function Read-StrictUtf8Text {
    param(
        [Parameter(Mandatory)][string]$Path,
        [switch]$RequireLf
    )

    $resolvedPath = if ([System.IO.Path]::IsPathRooted($Path)) {
        $Path
    }
    else {
        Join-Path $PSScriptRoot $Path
    }
    $bytes = [System.IO.File]::ReadAllBytes($resolvedPath)
    if ($bytes.Length -eq 0) { throw "$Path 为空；已中止。" }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        throw "$Path 不允许 UTF-8 BOM；已中止。"
    }
    try {
        $text = [System.Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    }
    catch {
        throw "$Path 不是有效 UTF-8；已中止。"
    }
    if ($RequireLf -and $text.Contains("`r")) {
        throw "$Path 必须使用 LF 行尾；已中止。"
    }
    if ([regex]::IsMatch($text, '[ \t]+(?=\r?$)', [System.Text.RegularExpressions.RegexOptions]::Multiline)) {
        throw "$Path 含行尾空白；已中止。"
    }
    return $text
}

function Assert-PublicCopies {
    param(
        [Parameter(Mandatory)][string]$CandidateFullPath,
        [Parameter(Mandatory)][string]$CandidatePublicPath
    )

    $candidatePaths = @{
        $Full = $CandidateFullPath
        $Public = $CandidatePublicPath
    }
    foreach ($path in @($Full) + $AllowedStaged) {
        $sourcePath = if ($candidatePaths.ContainsKey($path)) { $candidatePaths[$path] } else { $path }
        $null = Read-StrictUtf8Text -Path $sourcePath -RequireLf:($path -in @($Full, $Public))
    }

    # 校验器输出可能触及含节点真身，因此完全丢弃子进程输出，只返回固定错误。
    $python = Get-Command python -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $PublicValidator -PathType Leaf)) {
        throw "缺少 OSS 公开副本共用安全校验器；未设置 Secret、未提交、未推送。"
    }
    $validatorArguments = @(
        $PublicValidator
        '--yaml-only'
        $CandidateFullPath
        '--copy-set'
        $CandidatePublicPath
        (Join-Path $PSScriptRoot 'cmi-oss.yaml')
        (Join-Path $PSScriptRoot 'qichiyu-oss.ini')
        (Join-Path $PSScriptRoot 'qichiyubeifen-oss.ini')
        (Join-Path $PSScriptRoot 'bei260317-oss.ini')
        (Join-Path $PSScriptRoot 'nmi-oss-CHANGELOG.md')
    )
    Invoke-QuietCheckedProcess `
        -FilePath $python.Source `
        -Arguments $validatorArguments `
        -TimeoutSeconds 30 `
        -FailureMessage "OSS 公开副本安全校验失败或本机缺少 PyYAML；未设置 Secret、未提交、未推送。"

    $null = & git diff --check -- 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "git diff --check 失败；未设置 Secret、未提交、未推送。"
    }
}

if (-not (Test-Path -LiteralPath $Full -PathType Leaf)) {
    throw "$Full 不存在；已中止。"
}
foreach ($path in $AllowedStaged | Where-Object { $_ -ne $Public }) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "缺少副本文件 $path；已中止。"
    }
}

# 在更新 Secret 前先拒绝任何越界的预暂存内容。
Assert-StagedWhitelist -Paths (Get-StagedPaths)

$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$tempDirectory = Join-Path $tempRoot ("rule-nmi-oss-" + [guid]::NewGuid().ToString('N'))
$tempDirectory = [System.IO.Path]::GetFullPath($tempDirectory)
if (-not $tempDirectory.StartsWith($tempRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "临时目录越界；已中止。"
}
$null = New-Item -ItemType Directory -Path $tempDirectory

try {
    # 必须在任何重写前按原始字节严格解码，防止无效 UTF-8 被替换字符静默“洗白”。
    $fullText = Read-StrictUtf8Text -Path $Full
    $lineList = [System.Collections.Generic.List[string]]::new()
    $reader = [System.IO.StringReader]::new($fullText)
    try {
        while (($line = $reader.ReadLine()) -ne $null) {
            $lineList.Add($line)
        }
    }
    finally {
        $reader.Dispose()
    }
    $lines = $lineList.ToArray()
    $startIndexes = @(0..($lines.Count - 1) | Where-Object { $lines[$_] -ceq '#__SECRET_START__' })
    $endIndexes = @(0..($lines.Count - 1) | Where-Object { $lines[$_] -ceq '#__SECRET_END__' })
    $hashLabelIndexes = @(0..($lines.Count - 1) | Where-Object { $lines[$_] -cmatch '^# NMI_OSS_NODES_SHA256:' })
    $hashIndexes = @(0..($lines.Count - 1) | Where-Object { $lines[$_] -cmatch '^# NMI_OSS_NODES_SHA256: [0-9a-f]{64}$' })

    if ($startIndexes.Count -ne 1 -or $endIndexes.Count -ne 1) {
        throw "真身必须且只能包含一组秘密区边界标记。"
    }
    if ($hashLabelIndexes.Count -ne 1 -or $hashIndexes.Count -ne 1) {
        throw "真身必须且只能包含一行 NMI_OSS_NODES_SHA256。"
    }

    $start = $startIndexes[0]
    $end = $endIndexes[0]
    if ($end -le ($start + 1)) { throw "秘密区为空或边界顺序错误。" }
    if ($lines[$end - 1].Length -eq 0) {
        throw "秘密区节点块末尾不得包含空行，以确保 Actions 重组后逐字节一致。"
    }

    # 节点块统一为 LF、UTF-8 无 BOM，末尾不额外添加换行。
    $nodeText = $lines[($start + 1)..($end - 1)] -join "`n"
    $nodeBytes = $Utf8NoBom.GetBytes($nodeText)
    $nodeFile = Join-Path $tempDirectory 'nodes.yaml'
    [System.IO.File]::WriteAllBytes($nodeFile, $nodeBytes)
    $hash = [Convert]::ToHexString(
        [System.Security.Cryptography.SHA256]::HashData($nodeBytes)
    ).ToLowerInvariant()
    $base64 = [Convert]::ToBase64String($nodeBytes)

    # 以当前 HEAD 的公开副本为“远端已绑定状态”。首次新增（HEAD 中不存在）必须设置 Secret。
    $previousPublicHash = $null
    $null = & git cat-file -e "HEAD:$Public" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $headPublicLines = @(& git show "HEAD:$Public")
        if ($LASTEXITCODE -ne 0) { throw "读取 HEAD 中的 $Public 失败。" }
        $oldHashes = @($headPublicLines | Where-Object { $_ -cmatch '^# NMI_OSS_NODES_SHA256: ([0-9a-f]{64})$' })
        if ($oldHashes.Count -eq 1) {
            $previousPublicHash = $oldHashes[0].Substring($oldHashes[0].Length - 64)
        }
    }

    $lines[$hashIndexes[0]] = "# NMI_OSS_NODES_SHA256: $hash"
    $publicLines = @()
    if ($start -gt 0) { $publicLines += $lines[0..($start - 1)] }
    $publicLines += '#__NODES_OSS__'
    if ($end -lt ($lines.Count - 1)) { $publicLines += $lines[($end + 1)..($lines.Count - 1)] }

    # 先在临时目录生成候选文件；任何校验失败都不得改写真身或公开产物。
    $candidateFullPath = Join-Path $tempDirectory 'nmi-oss.full.candidate.yaml'
    $candidatePublicPath = Join-Path $tempDirectory 'nmi-oss.candidate.yaml'
    [System.IO.File]::WriteAllText(
        $candidateFullPath,
        ($lines -join "`n") + "`n",
        $Utf8NoBom
    )
    [System.IO.File]::WriteAllText(
        $candidatePublicPath,
        ($publicLines -join "`n") + "`n",
        $Utf8NoBom
    )

    $placeholderCount = @($publicLines | Where-Object { $_ -ceq '#__NODES_OSS__' }).Count
    $publicHashCount = @($publicLines | Where-Object { $_ -cmatch '^# NMI_OSS_NODES_SHA256: [0-9a-f]{64}$' }).Count
    if ($placeholderCount -ne 1 -or $publicHashCount -ne 1) {
        throw "公开副本的占位符或哈希注释不唯一。"
    }

    Assert-PublicCopies -CandidateFullPath $candidateFullPath -CandidatePublicPath $candidatePublicPath
    if ($ValidateOnly) {
        Write-Host "OSS 副本已在临时目录完成派生与全量本地校验；工作树未改动，未设置 Secret、未暂存、未提交、未推送。"
        return
    }
    if ($initialAheadCount -gt 0) {
        Assert-RecoveryContentUnchanged -CandidatePublicPath $candidatePublicPath
        Invoke-PushMain
        Clear-PendingPushCommit
        Write-Host "公开副本没有新变化；已把精确登记的滞留提交补推送到 origin/main。"
        return
    }

    # 全量校验通过后才写回；第二个文件写入失败时尽力恢复两份原始字节。
    $fullDestination = Join-Path $PSScriptRoot $Full
    $publicDestination = Join-Path $PSScriptRoot $Public
    $originalFullBytes = [System.IO.File]::ReadAllBytes($fullDestination)
    $publicExisted = Test-Path -LiteralPath $publicDestination -PathType Leaf
    $originalPublicBytes = if ($publicExisted) { [System.IO.File]::ReadAllBytes($publicDestination) } else { $null }
    try {
        [System.IO.File]::WriteAllBytes($fullDestination, [System.IO.File]::ReadAllBytes($candidateFullPath))
        [System.IO.File]::WriteAllBytes($publicDestination, [System.IO.File]::ReadAllBytes($candidatePublicPath))
    }
    catch {
        try { [System.IO.File]::WriteAllBytes($fullDestination, $originalFullBytes) } catch { }
        try {
            if ($publicExisted) {
                [System.IO.File]::WriteAllBytes($publicDestination, $originalPublicBytes)
            }
            elseif (Test-Path -LiteralPath $publicDestination) {
                Remove-Item -LiteralPath $publicDestination -Force
            }
        }
        catch { }
        throw "写入 OSS 副本真身或公开产物失败；已尝试恢复原始文件。"
    }

    $nodesChanged = $previousPublicHash -cne $hash
    if ($nodesChanged) {
        Write-Host "节点哈希有变化，正在通过标准输入更新 $SecretName ..."
        Invoke-GitHubSecretFromStandardInput -Name $SecretName -Value $base64
    }
    else {
        Write-Host "节点哈希未变化，跳过 Secret 更新。"
    }

    & git add -- @AllowedStaged
    if ($LASTEXITCODE -ne 0) { throw "精确暂存副本文件失败。" }
    $staged = Get-StagedPaths
    Assert-StagedWhitelist -Paths $staged

    if ($staged.Count -eq 0) {
        Write-Host "无公开副本变化，且本地没有尚未推送的提交。"
        return
    }

    & git commit -m $Msg
    if ($LASTEXITCODE -ne 0) { throw "git commit 失败；Secret 已更新时，远端哈希校验会阻止错配覆盖。" }
    $pendingCommit = Get-CommitId -Revision 'HEAD'
    Write-PendingPushCommit -Commit $pendingCommit
    $null = Assert-AheadCommitPathsAllowed -Upstream $publishUpstream
    Invoke-PushMain
    Clear-PendingPushCommit
    Write-Host "OSS 独立副本已推送；等待独立工作流发布。"
}
finally {
    if (Test-Path -LiteralPath $tempDirectory) {
        $resolved = [System.IO.Path]::GetFullPath($tempDirectory)
        if (-not $resolved.StartsWith($tempRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "拒绝清理越界临时目录。"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
